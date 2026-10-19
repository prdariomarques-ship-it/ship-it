# DARIO OS x DARIUS OSS - Estado da missão de integração

Atualizado: 2026-10-19 | Status: **CONCLUSÃO PARCIAL (Fase 0 e ciclos 1-2 concluídos; painel, suspensão, WhatsApp->DARIUS e Telegram pendentes)**
Branch de trabalho: `integration/dario-os-darius` (criada a partir de `feat/vendedor-ativo-voz` @ `e64d2f7`). Sem push, sem deploy, sem mensagens reais.

## 1. Repositórios (Fase 0, somente leitura)

| Repo | Caminho | Branch @ commit | Estado | Papel |
|---|---|---|---|---|
| Dario OS (alvo) | `C:\Users\dario\FlowCore\ship-it` | `feat/vendedor-ativo-voz` @ `e64d2f7` | só `voice-service/.venv-ptbr/` sem versionar | tem antiloop, autopilot, vigia de linhas; **escolhido pelo usuário** como alvo |
| DARIUS OSS | `C:\Users\dario\Downloads\darius-rc2-prepush-gate` | `completion/darius-final` @ `8f860d1` | limpo | runtime TypeScript canônico |
| Dario OS (runtime ativo) | `C:\Users\dario\FlowCore\ship-it-zervis` | `feat/scoped-read-tokens` @ `5a216e2` | 1 arquivo (`docker/docker-compose.override.yml`) | origem dos containers `darioos-backend-1` e `darioos-zervis-bridge-1` |
| Frontend em execução | `...\Codex\2026-09-16\...\work\ship-it` | `codex/marquescolor-evolution` @ `f6084df` | 80 arquivos modificados | origem de `darioos-local-control-*` (porta 3000) |
| Outros clones | `~\ship-it`, `~\darioos-wt`, `~\ship-it-reversa`, `~\dario-os-lab` | vários | com alterações locais | fora de escopo; preservados |
| FlowCore (app financeiro) | `C:\Users\dario\FlowCore` | `claude/dario-os-platform-gcg6i2` @ `78712b1` | 37 arquivos modificados | **somente leitura**; não alterado |

Stack do alvo: FastAPI + SQLAlchemy async + Alembic (28 migrações), Next.js 16.2.10 / React 18.3.1, vitest 4, pytest (81 arquivos de teste backend, 50 frontend). Scripts frontend: `next build`, `eslint .`, `vitest run`.

Serviços Docker observados: `darioos-*` (backend, postgres, redis, qdrant, jaeger, zervis-bridge:8810), `darioos-local-control-*` (Caddy em 127.0.0.1:3000), `marquescolor-*` (evolution-manager 127.0.0.1:8081, frontend 3002), `azusa-mysql:3306`, `open-webui:3001`. Nada foi parado ou alterado.

## 2. Divergências entre o prompt e o código real

- `backend/agents/tools/flowcore.py` **não existe**. O real é `backend/agents/tools/flowcore_tools.py` (REST shim com `flowcore_base_url`, `flowcore_request_max_attempts=3`, `flowcore_request_backoff_seconds=1.0`). Contrato `/api/ask` e a ferramenta `flowcore_finance`: **ainda não confirmados** (INCONCLUSIVO).
- Nenhum arquivo `.py` do backend referencia DARIUS como runtime. Os hits de "darius" são outra coisa (`darius.distill_style`, job de aprendizado de estilo). **Integração Dario OS -> DARIUS: AUSENTE.**
- Os bots Telegram não são serviços neste repo: aparecem como workflows (`.github/workflows/telegram-{commands,fx,market}.yml`) e scripts em `work/` (`market_command_bot.py`, `send_fx_telegram.py`, `send_market_telegram.py`). Segundo o usuário, o Termux legado hospeda bots Telegram. Monitor SCPX: **não localizado** como código aqui (INCONCLUSIVO). Bot Mercado e Mercado Global: **candidatos** nos scripts acima, não confirmados.
- A imagem em execução `darioos-backend-1` (`/app`) **não contém** `twin_autopilot`/`cross-talk`; o alvo escolhido contém. Qual backend serve o WhatsApp em produção: INCONCLUSIVO até inspecionar os logs/containers sem alterá-los.
- O alerta do incidente diz "10+ respostas em 15 min". No código, o texto é montado de `whatsapp_twin_loop_guard_max_replies`/`_window_seconds` (defaults 6 e 60 s). Portanto produção usa valores configurados por ambiente (não verificados).

## 3. Capacidades já presentes no Dario OS (a reutilizar, não recriar)

| Capacidade | Evidência (arquivo) | Situação |
|---|---|---|
| Webhook Evolution com segredo (hmac) | `backend/webhooks/router.py` | presente, não testada por mim |
| Deduplicação por `external_id` | `webhooks/router.py` (resposta `duplicate`) | presente, não testada por mim |
| Eco/cross-talk entre números administrados | `webhooks/router.py` (`_administered_instance_phones`) | presente |
| Loop guard com alerta ao dono | `jobs/handlers.py` (`_loop_guard_or_alert`), `services/rate_limit.py` | presente |
| Pausa/fencing de conversa | `_conversation_paused`, `test_pause_fencing.py` | presente (parte em `whatsapp_agents_fix/`, a confirmar se aplicada) |
| Vigia de linhas e alerta ao dono | `services/line_watch.py` | presente |
| Admin: status, logs, execuções, métricas, WhatsApp | `backend/admin/router.py` + `frontend/app/admin/*` | presente |
| Retry/backoff para FlowCore | `utils/config.py`, `agents/tools/flowcore_tools.py` | presente |

## 4. Lacunas no DARIUS que bloqueiam o contrato com o painel

Confirmadas em `src/server.ts` (rotas atuais: `GET /api/health|dashboard|tasks|tasks/:id|agents|agents/:id|memory|skills|logs` e `POST /api/tasks`):

1. Sem rota para **aprovar/rejeitar**, **cancelar**, **retomar** nem **ler resultado** de uma task.
2. Sem paginação/filtros em `GET /api/tasks`; sem stream de eventos.
3. Sem limite de payload explícito além do default do `express.json()`.
4. Consumidor `QUEUED` sem política de retry/backoff e sem distinção transitório/permanente.
5. Scheduler não ligado ao `server.ts`.
6. Endpoint de métricas/saúde por componente (workers, scheduler, banco) não existe.

Regra: essas rotas serão implementadas **no DARIUS** (runtime canônico), com testes, e só então consumidas por um adaptador no backend do Dario OS.

## 5. Plano em ciclos (ordem)

1. **DARIUS** (`completion/darius-final` -> nova branch): rotas approve/reject/cancel/result, paginação/filtros, limite de payload, retry/backoff do consumidor + testes HTTP + doc de contratos.
2. **Dario OS backend**: adaptador `DariusClient` (timeout, auth por token de cliente, circuit breaker, versão de contrato) + rota admin `/admin/darius/*` + testes com servidor DARIUS real em processo.
3. **Dario OS backend**: controle de suspensão por instância e global (persistido, aplicado no caminho de envio) + testes; revisar o que `whatsapp_agents_fix/` já cobre.
4. **Fluxo WhatsApp -> task DARIUS -> resposta** assíncrono, com `Idempotency-Key` derivada de `instance+external_id`.
5. **Frontend**: painel (visão geral, aprovações, tarefas, instâncias, antiloop, FlowCore) conforme a referência visual, só com dados reais e estado "indisponível" explícito.
6. **Telegram**: auditar os scripts/workflows, localizar Monitor SCPX; integrar apenas o que for confirmado.
7. Demonstrações E2E (16 + 12 do módulo Telegram), documentos de arquitetura/contratos/runbook/segurança.

## 6. Decisões do usuário necessárias (não bloqueiam o ciclo 1)

- Confirmar qual backend atende o WhatsApp em produção (alvo escolhido: `FlowCore\ship-it`).
- Autorizar, quando chegar a hora, testes com instância/número de teste da Evolution (nenhum envio real foi feito).
- Localização do Monitor SCPX (o `spcx-monitor` do VPS foi descontinuado).

## 7. Ciclo 1 CONCLUÍDO (DARIUS) - evidência

Repo `darius-rc2-prepush-gate`, branch `integration/darius-lifecycle-api`, commit `d983c93` (sobre `8f860d1`). Sem push.

- Rotas novas: `POST /api/tasks/:id/approve|reject` (admin no modo isolado), `POST /api/tasks/:id/cancel` (dono ou admin), `GET /api/tasks/:id/result`; `GET /api/tasks` com `status/limit/offset` + `X-Total-Count/X-Next-Offset` (sem parâmetros = array inalterado); limites `DARIUS_MAX_BODY_BYTES` e `DARIUS_MAX_OBJECTIVE_CHARS`; erros 413/400 em JSON.
- Engine: `resumeTask` retorna se a chamada venceu a transição; `noteDecision` grava `{decision, by, at, reason?}` em `metadata.decisions`. O teste pegou um bug real na minha primeira versão (o loop de execução sobrescrevia o registro); corrigido em `syncWithStore`.
- Resultado: 18 testes HTTP novos; suíte completa **61 arquivos / 440 testes verdes**; `tsc` = 0; arquivos de concorrência/crash 3x = 56/56 em cada rodada; `test:gaps` exit 0. Três mutações (aprovar sem admin, sem isolamento por dono, loop apagando decisões) foram detectadas.
- O sentinel `HITL GAP` de `webcontract.http.test.ts` (que afirmava 404) foi invertido para o novo contrato, de forma documentada.
- Contrato documentado em `DARIUS_API_CONTRACTS.md` (DARIUS).
- Estado final do ciclo 1: cadeia `8f860d1 -> d983c93 -> 2d98c5f -> 5a72e24` (este último só com a evidência do gate). Gate `scripts/verify-all.ps1` em `2d98c5f` (Windows, Node v22.23.2): typecheck 0; suíte completa 61/440; repetição x5 do conjunto de concorrência/crash/idempotência/ciclo de vida = 221 testes verdes em todas as 5 rodadas; `test:gaps` exit 0; demos 11/11; workers órfãos 0; `allGreen=true`. Logs em `artifacts/verification/2d98c5f/windows/` (DARIUS).
- Não feito neste ciclo: retry/backoff do consumidor QUEUED, scheduler ligado ao `server.ts`, métricas por componente, stream de eventos, execução em container `--network none`.

## 8. Ciclo 2 CONCLUÍDO (Dario OS: adaptador + ponte admin) - evidência

Repo `ship-it`, branch `integration/dario-os-darius`, commit `33896b0` (sobre `f9c9e68`). Sem push, sem deploy; `voice-service/.venv-ptbr/` continua sem versionar e intocado.

- `backend/services/darius_client.py`: cliente HTTP puro (nunca lê o banco do DARIUS). Autenticação Bearer; **duas credenciais** (serviço = cria/lê tarefas do app; operador admin = decisões humanas e visão transversal). Retry/backoff apenas em GET e em `create_task` com `Idempotency-Key` obrigatória; **approve/reject/cancel são enviados uma única vez** e, se a resposta se perder, o erro carrega `outcome_unknown=True` (o chamador deve ler o estado, não repetir). Circuit breaker (abre após N falhas consecutivas de transporte/5xx; meia-abertura após cooldown; 4xx não conta). Respostas validadas com pydantic (campos extras ignorados); corpo inválido = `DariusInvalidResponse`, nunca valor presumido. Erros tipados (auth/404/409/4xx/indisponível/não configurado); mensagens nunca ecoam o corpo bruto; token fora de `repr` e de erros; `task_id` validado contra path traversal antes de sair do processo.
- `backend/admin/darius.py` (`/api/admin/darius/*`, só admin): `status` (configurado/alcançável/latência/circuito/credenciais configuradas, sem segredos), `tasks` (filtro de status + paginação), `tasks/{id}`, `tasks/{id}/result`, `approve|reject|cancel`. Cada decisão é auditada em `LogEntry(source="darius_decision")` com o **usuário admin do Dario OS** (o DARIUS só conhece a credencial). Falhas do adaptador viram 502/503; credencial de serviço recusada pelo DARIUS vira 502 (`DARIUS_CREDENTIAL_REJECTED`), nunca 401/403 para o usuário do navegador.
- `utils/config.py`: `darius_base_url` (vazio = integração desligada, estado "não configurado" explícito), `darius_api_token`, `darius_operator_token`, timeout/tentativas/backoff e parâmetros do circuito. Nenhum segredo no repositório.
- Testes novos: 16 (adaptador, `httpx.MockTransport`), 34 (router: 401/403 sem chegar ao DARIUS, validação de query, erros mapeados, auditoria, decisão enviada uma vez mesmo com `max_attempts=2`), 7 de **contrato contra o servidor DARIUS real** (processo `node --import tsx src/server.ts` em porta livre, banco temporário, 3 credenciais): token inválido = 401, isolamento por dono (404 uniforme para outro cliente), visibilidade do operador, idempotência, cabeçalhos de paginação, aprovar/rejeitar = 403 para cliente não admin e 409 `NOT_AWAITING_APPROVAL` para admin em tarefa não pausada, cancelamento com um dos dois desfechos documentados. O teste de contrato é opt-in via `DARIUS_REPO_PATH` e **é ignorado com motivo explícito** quando a variável não existe (nunca conta como aprovado).
- Resultado: 57/57 nos três arquivos; ruff limpo e mypy limpo nos arquivos novos; 0 processos `node` órfãos após o contrato. Duas mutações foram detectadas (retry em `approve` -> 2 testes falham; token no `repr` -> 1 teste falha).
- Regressão completa do backend (Windows, venv fora do repo `C:\Users\dario\.venvs\shipit`): **1818 passed, 25 skipped, 2 failed, 2 errors**. Os mesmos 4 (`test_context_builder.py` x2, `test_groq_stt.py` x2, o último por nome de diretório temporário longo no Windows) falham de forma idêntica em uma extração limpa de `HEAD` (`f9c9e68`, sem minhas mudanças): **preexistentes, não causados por este ciclo**, e não corrigidos aqui (fora do escopo). `test_auth.py::...minimum_response_time` falhou uma vez por resolução de relógio no Windows e passou na execução completa (instável, preexistente). O Windows precisa de `tzdata` no venv (`store_timezone` America/Sao_Paulo).
- Não feito: nenhum segredo real foi configurado (`DARIUS_*` vazios); a ponte ainda não está ligada a nenhum fluxo; sem frontend.

## 9. Ciclo 3 CONCLUÍDO (Codex documentado + suspensão de automação)

Commits `fd4c9b3` (documentação) e `e093d9c` (código), sobre `8a6921f`. Sem push/deploy.

**Árvore do Codex** (`DARIO_OS_CODEX_TREE_STATE.md`, somente leitura): clone separado, 40 arquivos modificados + 40 novos, **inclui backend** (instância dupla, PDV, STT, migrações). O `:3000` serve uma imagem já construída; o Caddy encaminha `/api` para o backend de **produção** (`admissaoazusa.com.br`). Snapshot de proteção fora da árvore: `C:\Users\dario\backups\codex-ship-it-20261019\` (patch com SHA-256 + 40/40 arquivos novos; `git status` da árvore idêntico antes/depois). Consequência: painel novo é desenvolvido contra o backend local desta branch, em arquivos novos.

**Suspensão** (reuso do `app_settings`, sem sistema paralelo):
- Achado: `auto_reply_enabled` só era checado ao ENFILEIRAR; o transporte (`send_whatsapp_text`) não tinha portão, então mensagens já na fila saíam após suspender; não havia suspensão por instância.
- `services/automation_suspension.py` + 2 configurações persistidas (`automation_suspended`, `automation_suspended_instances`) que sobrevivem a reinício.
- Portão no transporte, antes de qualquer reserva/cerca: job enfileirado ANTES da suspensão é retido, o job conclui (sem retry, não é liberado em rajada ao retomar) e nada fica em `needs_review`. Alertas ao dono (`_twin_alert_dedup_key`, `owner_alert` do vigia de linhas) e envios humanos do painel (`/api/whatsapp/send-*`, chamam o provider direto) não são afetados. `process_inbound` também pula a geração de resposta (apenas custo).
- `/api/admin/automation/suspension` (GET) e `PUT .../global`, `PUT .../instances/{instance}`: só admin, motivo obrigatório (3-500), auditoria com o usuário admin.
- 17 testes novos com o **worker real** e o handler real (só o transporte é falso). Mutações detectadas: portão desligado (6 testes caem) e alerta ao dono desprotegido (2 caem). Regressão: 198/198 nos arquivos afetados; suíte completa antes do ajuste dos 2 testes de catálogo = 1832 passed, falhas apenas as preexistentes (4) + `test_auth` (instável no Windows); os 2 testes de catálogo (`test_admin`, `test_app_settings`) foram atualizados e passam.
- Limites: o motivo/estado por instância mora em uma lista CSV (duas edições simultâneas de instâncias diferentes podem competir; operação rara, processo único); nome de instância inexistente é aceito (typo é inócuo, não protege nada); `str` de instância é comparado exato (maiúsculas importam).

## 10. Ciclo 4 (em andamento) - P1 regressão, P2 suspensão atômica, P3 WhatsApp -> DARIUS, P4 painel

### P1 - suíte completa do backend (evidência)
- **Commit**: `0ee5074271f64f9a9afaf691d8b63905420da1bf` (depois de todas as mudanças de código do ciclo 4 até P3).
- **Comando**: `python -m pytest -q -p no:cacheprovider --basetemp=<fora de Temp> --junitxml=full_final.xml` em `backend/`, com `DARIUS_REPO_PATH` apontando para o checkout do DARIUS (os testes de contrato contra o runtime real **rodaram**).
- **Resultado**: exit code **1**; `2 failed, 1886 passed, 25 skipped, 2 errors` em 503,60 s. Os 25 skips são as variantes PostgreSQL (`TEST_POSTGRES_URL` ausente) e testes opt-in sem pré-requisito.
- **Falhas = exatamente as 4 pré-existentes** (reproduzidas no HEAD de referência `e64d2f7`, ver ciclo 3): `test_context_builder` x2 (falhas) e `test_groq_stt::test_audio_vazio_ou_grande_demais_nem_chega_a_rede` x2 (erros de teardown: variável de ambiente > 32767 caracteres no Windows, parâmetro gigante). Nenhuma regressão.
- **Histórico honesto**: uma execução anterior (commit `060c1d1`) deu `7 failed, 1877 passed, 2 errors`: as 4 pré-existentes + **5 regressões minhas** (`test_migration_chain_reconciled` e `test_store_voice_migration` fixavam `c8f3a1d27b40` como cabeça; minhas migrações P2/P3 deslocaram a cabeça). Corrigido em `0ee5074` (testes exigem cabeça única e a mesma ordem histórica; migração de voz testada na própria revisão) e foram adicionados testes próprios das duas migrações novas. Antes disso a suíte completa NÃO tinha sido rodada depois do P2 - essa regressão só apareceu agora.
- `test_auth` (timing instável no Windows, também na baseline) não falhou nesta execução.

### P2 - suspensão atômica e persistente (commit `959ade4`)
- Tabela `automation_suspensions` (PK = escopo: `global` ou instância) como árbitro atômico (INSERT/DELETE); sem lista CSV e sem leitura-modificação-escrita. Migração `d91b5e7a3c20`.
- Instâncias validadas contra as configuradas: inexistente = 404, inválida = 422; `changed` informa se a chamada mudou o estado; chamadas concorrentes e repetidas são idempotentes.
- Preservados: alertas ao dono e envios humanos autorizados do painel. Portão no transporte (`whatsapp.send_text`) e no início do processamento de entrada.
- 27 testes (job real + worker real; só o transporte é falso): enfileirado antes da suspensão, global, por instância, retomada sem rajada, reinício (estado persistente), concorrência. Mutações detectadas.

### P3 - adaptador WhatsApp -> DARIUS (commit `060c1d1`, DARIUS `08d2b9c`)
- **Opt-in por instância** (`darius_whatsapp_enabled` + `darius_whatsapp_instances`); sem a flag o caminho legado não muda. Mensagem -> mesmos portões do fluxo local (opt-out, pausa humana, idade, antiloop, suspensão) -> tarefa DARIUS (`Idempotency-Key` = `dedupe_key` UNIQUE) -> resposta consultada (poll) -> **somente `COMPLETED` com resultado não vazio** vira `whatsapp.send_text` (suspensão, revisão de pausa e `output_safety` continuam valendo). Aprovação fica no DARIUS (`PAUSED`); falha/expiração/cancelamento não enviam nada; saída parcial de tarefa não concluída nunca é enviada.
- Tabela `darius_whatsapp_tasks` (migração `e7a42c9f1b35`): estado do vínculo, auditoria (`history`), sem telefone no objetivo enviado ao DARIUS.
- **Achados do contrato real** (rodando o `server.ts` do DARIUS): (1) o agente geral só conclui com saída `DONE: ...` (o texto após o prefixo vira `result`); o objetivo agora instrui esse protocolo; (2) `POST /api/tasks` fixava `successCriteria: "Done"` e a verificação exigia que o resultado contivesse "done" - uma resposta de chat nunca verificava. Corrigido **no DARIUS** (canônico) com mudança mínima e testada: `completion: "non_empty"` opcional (omitido = contrato legado; valor inválido = 400; `Idempotency-Key` repetida com outro modo = 422), regra de verificação `NON_EMPTY`; 13 testes novos; suíte DARIUS 62 arquivos / 453 testes verdes, `tsc --noEmit` limpo. `DariusClient.create_task(..., completion=)` envia o campo só quando pedido.
- **Defeito real corrigido**: `claim()` fazia `rollback` ao perder a corrida do UNIQUE, expirando contato/mensagem da sessão do job; o job duplicado quebrava com `MissingGreenlet` e era repetido. Agora usa SAVEPOINT (teste de regressão + mutação detectada).
- Testes: 31 com `FakeDarius` (dedup, criação, aprovação, falhas, expiração, suspensão, pausa/retomada, opt-out, antiloop, rota legada intocada) + testes de contrato opt-in contra o DARIUS real (Ollama simulado devolvendo `DONE: <resposta>`; Evolution simulado): tarefa real concluída, resposta enviada pelo Evolution simulado, duplicata = 1 tarefa, falha do modelo = nada enviado, expiração cancela a tarefa real.
- **Nenhuma mensagem real foi enviada.** O Evolution é sempre simulado; a demonstração com instância de teste + número controlado segue `INCONCLUSIVO` (instância/número não confirmados pelo usuário).

### P1 (re-execução final) - achado de at-most-once e suíte no commit `8aedd8a`
- A execução completa em `83c749e` deu `3 failed, 1896 passed, 25 skipped, 2 errors`: as 4 pré-existentes **+ 1 defeito real meu**: `test_real_darius_idempotency_a_duplicate_message_does_not_create_a_second_task` (contrato contra o DARIUS real) mostrou **2 envios para 1 vínculo**.
- **Causa**: o perdedor do `claim` retoma o vínculo em `SUBMITTING` (recuperação de crash), chega à mesma tarefa DARIUS pela `Idempotency-Key` e agendava um segundo poll; dois polls viam `COMPLETED` e `_queue_reply` (sem guarda atômica) enfileirava dois `whatsapp.send_text`. O teste com `FakeDarius` só passava por acaso de agendamento.
- **Correção (`8aedd8a`)**: `repository.transition(expect, to)` = UPDATE condicional (compare-and-set). Só quem vence `SUBMITTING->SUBMITTED` agenda o poll; só quem vence `SUBMITTED->REPLY_QUEUED` enfileira o envio. 3 testes determinísticos (cópias obsoletas da linha); mutação (`won = True`) derruba os 3 e reproduz `assert 2 == 1`.
- **Suíte completa em `8aedd8a`**: `python -m pytest -q ... --junitxml=full_final_8aedd8a.xml` em `backend/` (com `DARIUS_REPO_PATH`), `2 failed, 1900 passed, 25 skipped, 2 errors` em 662,62 s. As falhas são **exatamente as 4 pré-existentes** (`test_context_builder` x2, `test_groq_stt` x2). Nenhuma regressão. Commits posteriores a este são só documentação/frontend.
- Risco residual conhecido: caminhos terminais (`_finish`) ainda não usam compare-and-set; dois workers com resultados *diferentes* do mesmo vínculo não ocorrem na prática (mesma tarefa, mesmo resultado), mas não há teste para isso.

### P4 - painel DARIUS no frontend (endpoints `29ef291`, UI `83c749e`)
- Backend (somente leitura): `GET /api/admin/darius/whatsapp-tasks` (paginado, filtro por status/instância) e `/whatsapp-routing` (flag, instâncias roteadas, estado de suspensão real). 11 testes.
- Frontend (`frontend/app/admin/darius`, `components/darius`, `lib/darius-{api,types}.ts`): visão geral/saúde, tarefas, aprovações (aprovar/rejeitar com confirmação e motivo), WhatsApp (vínculos + roteamento), suspensão global/por instância, logs. Polling de 10 s; todo estado sem dado vira "indisponível" explícito, sem dados fictícios. Item de menu novo na sidebar; árvore do Codex e snapshot preservados.
- `useApi`: `ApiError` tipado (status/detail); `detail` objeto não vira mais `[object Object]` (comportamento com string preservado).
- Evidência: `tsc --noEmit` limpo, eslint limpo nos arquivos novos/alterados, vitest completo **52 arquivos / 371 testes verdes** (DariusPanel 26, useApi-errors 6). Mutações do painel detectadas.
- Como rodar localmente: backend local (`uvicorn`) + `npm run dev` apontando `NEXT_PUBLIC_API_URL`/proxy para o backend **local** e abrir `/admin/darius`. Nunca validar rotas novas em `localhost:3000` se ele faz proxy de `/api` para produção.
- **Não verificado**: renderização no navegador contra o backend local (`next build`/visual) - só jsdom.
- **Conversas pausadas/humanas**: não há endpoint de listagem no backend; a seção aparece como **indisponível** (limitação declarada, não simulada).

### Limitações e INCONCLUSIVO deste ciclo
- Instância roteada ao DARIUS **não** cai para o pipeline local se o DARIUS falhar (decisão deliberada: evita resposta duplicada/divergente); o cliente fica sem resposta automática e o vínculo registra `failed`/`expired` para atendimento humano.
- Só texto nesta etapa (mídia/áudio não roteados).
- A conformidade do **LLM real** com o formato `DONE:` não foi medida (Ollama simulado). Se o modelo não emitir `DONE:`, a tarefa falha por iterações máximas e nada é enviado (falha segura, mas sem resposta).
- O caminho de aprovação (`PAUSED` -> aprovar) foi validado com mocks aqui e pelos testes de ciclo de vida do próprio DARIUS; não houve aprovação real ponta a ponta com a ponte do Dario OS.
- Segue não verificado: qual backend serve o WhatsApp em produção; contrato do FlowCore `/api/ask`; localização do Monitor SCPX; limiares do antiloop em produção.

## 11. Próxima ação concreta

1. (feito) Fluxo WhatsApp -> DARIUS com mocks e contrato real; (feito) painel. Pendente: demonstração com instância de teste isolada + número controlado (precisa de confirmação do usuário; senão `INCONCLUSIVO`).
2. Verificação visual do painel contra o backend local; listagem backend de conversas pausadas.
3. Telegram: auditar scripts/workflows (`work/market_command_bot.py`, `send_fx_telegram.py`, `send_market_telegram.py`, workflows `telegram-*.yml`); Monitor SCPX segue `INCONCLUSIVO`.
4. Hardening do DARIUS: consumidor QUEUED com retry/backoff, scheduler no ciclo de vida do servidor, métricas por componente, shutdown/recuperação, `--network none`.

## 12. Log

- 2026-10-19: Fase 0 concluída (somente leitura). Único artefato criado neste repo: este arquivo.
- 2026-10-19: Ciclo 1 concluído no repo DARIUS (`d983c93`; gate completo em `2d98c5f`, evidência em `5a72e24`).
- 2026-10-19: Ciclo 2 concluído no Dario OS (`33896b0`): adaptador DARIUS + ponte admin + testes de contrato contra o servidor real. Pendente: painel/frontend, suspensão, fluxo WhatsApp, Telegram, hardening do DARIUS.
- 2026-10-19: Ciclo 3 concluído: árvore do Codex documentada e protegida (`fd4c9b3`) + suspensão global/por instância no transporte (`e093d9c`). Pendente: fluxo WhatsApp->DARIUS, painel, Telegram, hardening do DARIUS.
- 2026-10-19: Ciclo 4 (parcial): suspensão atômica (`959ade4`), adaptador WhatsApp->DARIUS (`060c1d1`; DARIUS `08d2b9c`), regressão de migrações corrigida (`0ee5074`); suíte completa em `0ee5074`: 2 failed + 2 errors = só as 4 pré-existentes. Pendente: painel (P4), Telegram/hardening (P5).
- 2026-10-19: Ciclo 4 (P1/P4): painel DARIUS (`29ef291`, `83c749e`); defeito de resposta duplicada achado pela suíte completa e corrigido (`8aedd8a`); suíte completa em `8aedd8a`: 2 failed + 2 errors = só as 4 pré-existentes. Sem push, deploy ou envio real. Pendente: P5 (Telegram, hardening do DARIUS).
