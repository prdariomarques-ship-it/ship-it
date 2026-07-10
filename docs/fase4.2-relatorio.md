# Fase 4.2 — Cognitive Engine

## 1. Objetivo e escopo

A Fase 4.1 provou que o fluxo do WhatsApp funciona ponta a ponta. A Fase 4.2 respondeu a uma pergunta diferente: **quando uma mensagem chega, o sistema pensa antes de agir, ou só executa uma regra fixa?** Antes desta fase, `whatsapp.process_inbound` chamava `ai_orchestrator.run(agent_name="assistant")` diretamente — todo mundo recebia o mesmo agente, a mesma profundidade de memória, nenhuma noção de urgência, nenhum plano composto.

Restrição explícita do pedido, levada a sério: **nenhuma camada arquitetural nova, nenhum componente duplicado, usar integralmente a infraestrutura existente** (Agent Registry, Tool Registry, Event Bus, AI Orchestrator, Memory Manager). O resultado é uma composição de módulos pequenos dentro da camada de "Coordenação cognitiva" que já existia (`orchestrator/`), terminando sempre no mesmo `AIOrchestrator.run` de sempre — nunca um caminho de execução paralelo.

## 2. O que foi entregue

| Componente | Arquivo | Responsabilidade |
| --- | --- | --- |
| Intent Engine | `orchestrator/intent.py` | Classifica intenção via function calling, com múltiplas hipóteses e confiança; degrada para heurística só em falha do modelo |
| Priority Engine | `orchestrator/priority.py` | Classifica urgência (baixa/normal/alta/urgente); expõe `quick_priority_hint` síncrona para o webhook |
| Cognitive Planner | `orchestrator/planning.py` | Decide 1..5 etapas, agente por etapa (lido do Agent Registry em tempo real), se precisa de confirmação |
| Response Validator | `orchestrator/validation.py` | Checagem determinística (sem LLM): resposta vazia, erro de ferramenta vazado, ferramenta que falhou |
| Learning Engine | `orchestrator/learning.py` | Tagueia domínios recorrentes do contato (`Contact.categories`), deduplicado na escrita |
| Cognitive Pipeline | `orchestrator/pipeline.py` | Compõe os cinco acima + Memory Manager + AI Orchestrator no fluxo completo de 16 etapas do pedido |

Extensões pontuais e não-invasivas na infraestrutura já existente, todas retrocompatíveis (parâmetros novos com default `None`/vazio):

- `AIOrchestrator.run(..., memories=None, history=None)` — permite ao pipeline injetar contexto já carregado uma única vez por plano, sem duplicar a busca por etapa.
- `BaseAgent.run(..., history=None)` — conectou pela primeira vez o parâmetro `history` que `agents.planner.Planner.build_messages` já tinha desde a Fase 3 mas nunca era preenchido por ninguém.
- `ExecutedStep` ganhou `status`/`reason` — a auditabilidade "motivo da escolha, tempo, resultado, falhas" pedida para seleção de ferramentas, sem mudar a assinatura de nenhuma das ~20 ferramentas existentes.
- `AgentExecutor` ganhou troca automática de provider (`LLM_FALLBACK_PROVIDER`) — quando o provider configurado levanta uma exceção (não quando degrada normalmente para `STUB_REPLY`), tenta uma vez com o fallback.
- `MemoryManager` ganhou `get_summary`/`add_categories` — dois métodos pequenos, mesmo estilo dos já existentes.
- `Job`/webhook ganharam prioridade de execução real: `quick_priority_hint` decide `delay_seconds` ao enfileirar `whatsapp.process_inbound`, sem tocar o schema do banco (reaproveita `scheduled_at`, que `due_jobs` já ordenava).

## 3. Gaps reais fechados (não hipotéticos)

1. **`knowledge_search` nunca era chamado por ninguém.** A Fase 3 já tinha construído a busca semântica filtrada por `source="knowledge"` e documentado "pronta para a Fase 4" — mas nenhum caminho de execução a usava. O Cognitive Pipeline é o primeiro consumidor real.
2. **`Planner.build_messages(history=...)` era um parâmetro morto.** Existia desde a Fase 3, nunca preenchido. Agora carrega o histórico de curto prazo de verdade.
3. **Falha de memória semântica no carregamento de contexto do pipeline não era protegida.** Descoberto por um teste (`test_multiple_tools_executed_and_recorded_as_steps`) que derrubou a suíte inteira com `ResponseHandlingException` do Qdrant antes da correção — `CognitivePipeline._load_context` agora tem o mesmo `try/except` que `BaseAgent.run` já usava para seu próprio auto-fetch desde a Fase 3.
4. **Classificação (intenção/prioridade/planejamento) podia derrubar o pipeline inteiro.** A primeira versão só degradava para heurística quando o modelo respondia sem uma tool_call estruturada — uma exceção *levantada* pelo provider (rede fora do ar) não era capturada. Corrigido nos três engines antes de escrever os testes de integração de falha de provider.
5. **Nenhum mecanismo de troca de provider existia.** `providers/llm/factory.py` sempre foi 100% estático — a Fase 4.2 adicionou o único ponto de troca automática que existe hoje no sistema, dentro do `AgentExecutor`, sem tocar a interface pública `LLMProvider`.

## 4. Decisões de design e trade-offs

- **Decisão sobre regras fixas**: o caminho primário de intenção/prioridade/planejamento é sempre uma chamada de function calling ao LLM configurado — a heurística por palavras-chave só roda quando o modelo não responde de forma estruturada ou levanta exceção, no mesmo espírito de como `LLMProvider` já degrada para `STUB_REPLY` sem chave configurada. Isso significa até 3 chamadas LLM extra por mensagem antes mesmo do agente escolhido rodar; documentado como trade-off deliberado (decisões independentes e testáveis) e como candidato a otimização na Fase 4.3 (combinar os três em uma única chamada).
- **Prioridade de execução é real, não simbólica**: em vez de fingir uma fila de prioridade, o webhook usa a heurística rápida (sem LLM, sem latência) para agendar `whatsapp.process_inbound` alguns segundos no passado quando urgente — `due_jobs` já ordenava por `scheduled_at`, então isso é uma mudança de dado, não de mecanismo. Mensagens normais mantêm `delay_seconds=0`, idêntico ao comportamento anterior — nenhum teste de timing pré-existente quebrou.
- **Reconexão de sessão honesta permanece o padrão** (herdado da Fase 4.1): da mesma forma, a "reconexão automática de provider" da Fase 4.2 é limitada ao que é tecnicamente possível — uma retentativa com um provider alternativo, não uma tentativa infinita nem uma reparação mágica do provider original.
- **Composição de resposta multi-etapa é concatenação, não síntese via LLM** — mais barato, mais previsível, ligeiramente menos fluido para planos de 2+ etapas. Risco remanescente documentado abaixo.
- **`needs_confirmation` interrompe a execução, não apenas a sinaliza** — nenhuma etapa roda, nenhuma ferramenta é chamada, quando o Planner decide que o pedido precisa de confirmação humana antes. Testado explicitamente (`test_needs_confirmation_stops_before_executing_any_step`).

## 5. Cobertura de testes

Suíte completa: **231 testes passando** (186 pré-existentes intactos + 45 novos desta fase), lint limpo (`ruff check .`), cobertura total 91% (`orchestrator/` especificamente: 92%, com `intent.py`/`priority.py`/`planning.py`/`service.py`/`validation.py`/`learning.py` entre 97% e 100%).

Novos arquivos de teste, mapeados às categorias pedidas:

| Categoria pedida | Arquivo(s) |
| --- | --- |
| Mensagem simples | `test_cognitive_pipeline.py::test_simple_message_end_to_end` |
| Mensagem composta | `test_cognitive_pipeline.py::test_composite_message_executes_every_planned_step`, `test_cognitive_planner.py::test_llm_decision_produces_a_multi_step_plan` |
| Múltiplas ferramentas | `test_cognitive_pipeline.py::test_multiple_tools_executed_and_recorded_as_steps` |
| Erro de ferramenta | `test_response_validation.py`, `test_cognitive_pipeline.py::test_validation_retries_once_then_succeeds`, `test_validation_gives_up_after_max_attempts_but_never_goes_silent` |
| Falha de provider / troca automática | `test_provider_fallback.py` (unitário, `AgentExecutor`), `test_cognitive_pipeline.py::test_provider_failure_triggers_automatic_switch` (ponta a ponta) |
| Prioridade | `test_priority_engine.py`, `test_cognitive_pipeline.py::test_urgent_message_is_classified_as_urgent_priority` |
| Planejamento | `test_cognitive_planner.py` (10 testes: plano simples, multi-etapa, agente inválido, limite de etapas, confirmação, degradação) |
| Aprendizado | `test_learning_engine.py`, `test_cognitive_pipeline.py::test_learning_tags_contact_after_conversation` |
| Memória | `test_intent_engine.py`/`test_priority_engine.py` (degradação), `test_cognitive_pipeline.py::test_memory_context_is_loaded_and_passed_to_execution` |

## 6. Demonstração do critério de aceitação

`test_cognitive_pipeline.py::test_whatsapp_flow_runs_through_the_cognitive_pipeline_and_logs_every_step` exercita o critério de aceitação completo, sem mock do pipeline: uma mensagem chega via `POST /api/webhooks/whatsapp`, o worker roda `whatsapp.process_inbound` de verdade, e o teste verifica — lendo a tabela `logs` — que existe exatamente um registro `source="cognitive_pipeline"` contendo intenção válida, prioridade válida, tempo por etapa (`stage_durations_ms`) e a lista de agentes usados. Isso cobre, em ordem:

1. Mensagem chega (webhook) ✓
2. Intenção identificada (classificação real, com fallback verificado separadamente) ✓
3. Memória e conhecimento consultados automaticamente (`_load_context`, testado com contexto real em `test_memory_context_is_loaded_and_passed_to_execution`) ✓
4. Planejamento (`CognitivePlanner`, testado com plano real de múltiplas etapas em outro teste) ✓
5. Agente escolhido (Agent Registry, nunca hardcoded) ✓
6. Ferramentas selecionadas (Tool Registry, dentro do `AgentExecutor`) ✓
7. Múltiplas ferramentas quando necessário (`test_multiple_tools_executed_and_recorded_as_steps`) ✓
8. Memória atualizada (`test_learning_tags_contact_after_conversation`) ✓
9. Resposta correta (stub determinístico no ambiente de teste, sem chave de LLM configurada) ✓
10. Todos os passos em logs estruturados (a tabela `logs`, verificada diretamente) ✓

## 7. Métricas antes/depois

| Métrica | Antes (Fase 4.1) | Depois (Fase 4.2) |
| --- | --- | --- |
| Testes | 186 | 231 (+45) |
| Cobertura total | ~91% | 91% (mantida, com módulos novos em 92-100%) |
| Agente usado pelo WhatsApp | Sempre `assistant`, fixo | Decidido por intenção/prioridade, com fallback honesto para `assistant` |
| Etapas por pedido | Sempre 1 | 1 a 5, dependendo do pedido |
| Memória consultada | Só longo prazo (auto-fetch de `BaseAgent.run`) | Curto prazo + preferências + resumo (sempre) + longo prazo + conhecimento (condicional) |
| `knowledge_search` em uso | Nunca chamado | Chamado para intenções informacionais |
| Troca de provider em falha | Inexistente | Um fallback configurável, testado |
| Prioridade de execução | Inexistente (FIFO puro) | Mensagens urgentes agendadas à frente da fila |
| Métricas Prometheus novas | — | 6 (`pipeline_stage_duration`, `pipeline_run_duration`, `intent_classifications`, `priority_classifications`, `pipeline_validation_retries`, `pipeline_memory_lookups`) |

## 8. Riscos remanescentes

- **Custo/latência de 3 chamadas LLM extra por mensagem** (intenção, prioridade, planejamento) antes da execução real — aceitável no volume atual, mas a Fase 4.3 deveria medir em produção e considerar combinar as três decisões em uma única chamada se o custo/latência justificar.
- **Composição de resposta multi-etapa é concatenação simples**, não uma síntese fluida — funcionalmente correta, estilisticamente melhorável.
- **`needs_confirmation` ainda não tem um mecanismo de retomada** — o pipeline pergunta e para, mas não existe hoje um jeito de a próxima mensagem do contato ("sim, pode fazer") retomar o plano pausado; ela vira uma nova classificação do zero. Fica como gap explícito para a Fase 4.3.
- **`_MAX_VALIDATION_ATTEMPTS = 2` é um valor fixo no código**, não configurável via `Settings` — intencional para o escopo desta fase (simplicidade > flexibilidade prematura), mas fácil de promover a uma env var se necessário.
- **A tabela intenção→agente do fallback é pequena e estática** — cobre os casos óbvios (agenda→personal, loja→store, igreja→church); intenções sem uma entrada caem para `assistant`, o que é seguro mas não necessariamente o melhor agente.

## 9. Recomendações para a Fase 4.3

1. Medir o custo/latência real do Cognitive Pipeline em produção (usar as novas métricas Prometheus) e decidir se vale combinar intenção+prioridade+planejamento numa única chamada.
2. Mecanismo de retomada de plano pendente de confirmação (provavelmente: guardar o `Plan` pendente associado ao contato, e a próxima mensagem do contato o interpreta como confirmação/cancelamento antes de rodar uma nova classificação).
3. Síntese de resposta multi-etapa via LLM, opcional (feature-flag), para planos com 2+ etapas que produziram respostas heterogêneas.
4. Pipeline de ingestão de documentos para popular `knowledge_search` de verdade (hoje ele funciona, mas não há nenhum jeito de carregar conhecimento além da tool `store_memory` genérica).
5. Considerar expor `CognitiveResult` (intenção, prioridade, plano, validação) na API para o dashboard, dando visibilidade humana ao raciocínio do pipeline — hoje só existe em logs estruturados e métricas.
