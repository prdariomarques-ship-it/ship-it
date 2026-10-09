# Acompanhamento geral — frentes em andamento

> Documento de controle para não perder o fio entre as três frentes paralelas
> desta sessão. Atualizado a cada decisão relevante. Nenhuma frase aqui é
> declaração de implantação — implantação só ocorre com janela aprovada e
> comprovação de rollback.

Última atualização: 2026-10-09.

---

## Frente 1 — Correção WhatsApp (PR #63)

**Branch:** `whatsapp-agents-fix-review` → PR #63 (`draft`, não mergeada).

**Status:** em revisão. CI com 1 falha pré-existente em `master`
(`agents/tools/flowcore_tools.py:25`), não relacionada a esta PR.

### Entregue e testado
- `backend/jobs/handlers.py` / `backend/webhooks/router.py`: baseline real de
  produção registrado em commit separado (`2ff7f4b`), correção em commit
  separado (`48061b0`) — pausa/retomada com revalidação no envio, barreira de
  marcador interno, dedup de alerta.
- `services/conversation_control.py`, `orchestrator/incident_dedup.py`,
  `orchestrator/twin_risk_gate.py`, `services/output_safety.py` — novos,
  testados (SQLite real + 1 teste opt-in Postgres real).
- **Novo nesta sessão:** `twin_risk_gate.py` — "sem crise" (gíria = "sem
  problema") não escalava mais como crise real de impersonação. Corrigido com
  exceção estreita (não ampliando a janela geral de negação, que arriscaria
  apagar sinais reais como "sem razão, quero me matar"). 25/25 testes, lint
  limpo, commit pushado.

### Identificado, ainda NÃO corrigido (incidente novo, autoria correta)
- **Bug real em produção confirmado:** mensagens 9486/9488, hoje, contato
  real "Flávio" (contact_id 190) tratado como "Micael" (funcionário) pelo
  agente da loja (Marquescolor). Causa raiz: o agente não lê `Contact.name`
  do banco — infere o nome da fala/áudio do cliente.
- Busca no histórico completo do banco correto (`darioos_cutover_20260927`)
  não achou outras ocorrências do mesmo padrão (só esse incidente, 2
  mensagens, 1 conversa).
- **Bloqueio:** preciso do conteúdo real de `planner.py`, `store_agent.py`,
  `descriptions.py`, `context.py`, `utils/config.py` — hashes já confirmados
  divergentes da produção (mesmo problema que já resolvemos para
  handlers.py/router.py). Pedido enviado à VPS, ainda sem retorno completo.
- Padrão de referência já existe e já foi testado: branch não-mergeada
  `feat/marquescolor-sales-agent`, commit `97d9c5d`
  (`describe_contact_identity` em `services/descriptions.py` +
  `_gather_contact_identity` em `orchestrator/context.py`) — aplicar o mesmo
  padrão ao `StoreAgent`.

### Identificado, ainda NÃO corrigido (prevenção de loop entre bots)
- **Correção da afirmação anterior** (estava imprecisa): existe sim um
  throttle genérico em `webhooks/router.py` (`auto-reply:{instance}:{contact_id}`,
  `settings.auto_reply_max_per_contact_per_minute`, janela de 60s), aplicado
  **antes de qualquer agente ser enfileirado** — cobre Twin, B2B, Azusa e
  Loja igualmente. Não é verdade que esses três não tenham proteção alguma.
- O que falta de fato (cobertura completa, não "proteção zero"):
  - Detecção específica de automação no outro lado (`whatsapp_twin_loop_guard_*`
    + alerta ao proprietário via `decide_owner_alert`) **só existe no fluxo do
    Twin** — os outros três só silenciam após o limite genérico, sem alertar.
  - Não há registro explícito das identidades/números das OUTRAS instâncias
    gerenciadas (pessoal/Loja/B2B/Igreja) para detectar conversa bot-a-bot
    especificamente, em nenhum fluxo.
  - O fencing de pausa humana (`claim_send`/`_twin_revision`) **não se aplica
    a B2B/Azusa/Loja**: o payload que esses fluxos enfileiram para
    `whatsapp.send_text` não carrega `is_autopilot_reply`/`_twin_revision`/
    `_twin_contact_id`, então a revalidação de pausa nunca é acionada pra
    eles, mesmo depois de corrigir a conexão real da pausa (item D abaixo).
- Correção planejada: generalizar o fencing de pausa + a detecção/alerta de
  automação para os três fluxos sem essa cobertura, reaproveitando o mesmo
  mecanismo já testado do Twin.

### Revisão externa (2026-10-09) — 5 bugs reais confirmados por leitura direta do código, ainda SEM correção aplicada

> Documentação não é correção. Nada abaixo está implementado ainda — isto é
> o resultado da verificação, não da implementação.

- **A. Reserva sem commit antes do transporte** — `send_whatsapp_text` chama
  `claim_send`/`claim_alert` com sucesso mas nunca faz `await db.commit()`
  antes de `provider.send_text(...)`. O próprio docstring de
  `conversation_control.py` exige esse commit explicitamente ("Callers must
  COMMIT a successful claim before transport"). Sem ele, um crash/timeout
  durante o transporte pode reenviar a mesma mensagem.
- **B. Alerta ao proprietário nunca é entregue** — o job de alerta é
  enfileirado sem o campo `instance` no payload; `claim_alert` depois usa
  escopo vazio (`''`), que nunca bate com o escopo real da reserva
  (`alert_claim`, feita com a instância certa). Resultado: `claimed != 'claimed'`
  sempre, e o alerta de segurança **nunca chega a ser enviado**, silenciosamente.
- **C. Conclusão de envio sempre incerta + crash confirmado** — duas falhas
  na mesma área:
  - `finish_send(db, send_intent_id, None)` sempre passa `None` como
    `receipt_id`, então o envio nunca é promovido a `'sent'` mesmo quando
    o provedor aceitou de verdade (fica `needs_review` pra sempre).
  - **Pior, confirmado por leitura da assinatura real**: `persist_outbound_message`
    em `services/messaging.py` tem assinatura `(db, phone, content, media_type=...)`
    — **não aceita** `is_autopilot_reply=` nem `instance=`, que é exatamente
    o que `handlers.py` passa. Isso é um `TypeError` garantido em toda
    chamada real. O caminho de envio, como está, nunca rodaria de ponta a
    ponta em produção.
- **D. Pausa humana nunca é conectada ao evento real** — `_capture_human_reply`
  (webhooks/router.py) grava a mensagem do proprietário e zera
  `awaiting_reply_since`, mas **nunca chama `conversation_control.pause`**.
  Os 5 testes de `test_pause_fencing.py` provam que o mecanismo funciona
  isolado — não provam que uma resposta humana real o aciona. Hoje, não aciona.
- **E. Import quebrado em `output_safety.py`** — `from twin_risk_gate import
  normalize_text` (plano) em vez de `from orchestrator.twin_risk_gate import
  normalize_text`. Mesma classe de bug que já corrigi em `incident_dedup.py`
  nesta sessão — deixei passar este arquivo.

### Novo achado estrutural (bloqueia a correção de C)
- O modelo `Message` deste repositório **não tem** as colunas `sent_by_human`,
  `is_autopilot_reply`, `whatsapp_instance` — mas `handlers.py` (já verificado
  byte-idêntico à produção) as usa extensivamente (10+ referências). Nenhuma
  migração existente nesta PR as adiciona. Mesma classe de divergência que
  `config.py` — pedido de schema real (`\d messages` + `alembic_version`)
  enviado à VPS, aguardando retorno antes de escrever a migração certa.

### Requisitos de produto registrados (ainda não implementados — StoreAgent)
- **Abster-se quando não sabe:** avisar o cliente ("um momento, vou
  verificar") + registrar em log para revisão humana depois — nunca inventar
  preço/estoque/disponibilidade, e nunca ficar em silêncio total.
- **Tom por segmento (Marquescolor):** respostas mais curtas e informais
  para o público de oficina/pintor (tinta automotiva: PU, verniz,
  poliéster — público mais rústico). Tinta imobiliária parece ser um
  segmento menor/diferente, tom a confirmar.
- Pendente do conteúdo real de `store_agent.py`/`planner.py` para aplicar.

---

## Frente 2 — Integração Open WebUI ↔ Dario OS

**Branch:** `open-webui-integration` (sem PR ainda — só diagnóstico até agora).
Documento próprio: `OPEN_WEBUI_INTEGRATION_NOTES.md` (nessa branch).

**Status:** fase de diagnóstico, nenhuma edição de produção.

### Achados confirmados
- 🚨 **Bloqueio de segurança ativo:** `WEBUI_AUTH=False` na instalação da
  VPS. Não pode haver rota pública/Caddy para essa instância até isso ser
  corrigido com aprovação específica (mudança de segurança).
- 🚨 **Bloqueio de capacidade:** VPS com ~268 MB RAM livre e swap em 95% de
  uso. Não dá para build de frontend nem serviço novo pesado agora.
- Único backend ativo: `darioos-evolution-backend-1`, conectado ao banco
  real `darioos_cutover_20260927` (não `darioos` — descoberta importante,
  ver Frente 1).
- Open WebUI: imagem oficial fixada por digest, dados persistidos em volume
  nomeado (`migrated-extras_open_webui`), compartilha rede Docker `evolution`
  com o Caddy (rota interna possível via `open-webui:8080`, sem depender da
  porta `127.0.0.1:3001`).
- `OLLAMA_BASE_URL` já aponta para `darioos-ollama-1` (Ollama da própria
  VPS) — bom sinal de independência do PC Windows.
- "FlowCore RAG" identificado: é uma **Function do próprio Open WebUI**
  (tabela `function`, `id='example_filter'`, `name='flowcore-rag'`, tipo
  `pipe`, ativa, não-global). Conteúdo do código ainda não lido (pedido
  enviado, sem retorno).
- Caddyfile real lido (`/opt/chroma-migration-20260927/Caddyfile.prepared`,
  montado só-leitura no container): hoje roteia só `/manager`,
  `/evolution-api/*`, `/api/*`, `/docs`, `/n8n/*` e o catch-all pro frontend
  Next.js. **Nenhuma rota para Open WebUI ainda.**

### Pendente
- Ler código da function `flowcore-rag` (dependências reais: PC ou VPS?).
- Confirmar backups SQLite de 08/10 (versão, cobertura).
- Confirmar versão real do frontend publicado (`16.3.6` informado vs
  `16.2.10` no repo).
- Desenhar o item de navegação "Central de IA" + página de acesso
  (estrutura do `Sidebar.tsx` já mapeada: array `NAV_ITEMS` simples).

---

## Frente 3 — "FlowCore WhatsApp AI Platform" (evolução maior)

**Branch:** ainda não criada.

**Status:** autorizado a avançar com escopo reduzido e específico (resposta
do usuário ao pedir confirmação sobre executar sem supervisão):

1. Comparar código existente com os 4 repositórios de referência
   (licença/compatibilidade/testes) — **não reconstruir nem duplicar**
   serviços/agentes/bancos.
2. Só implementar complementos com benefício demonstrado, branch isolada,
   mudanças pequenas e reversíveis. Não é obrigatório usar os 4 repositórios.
3. **Priorizar falhas atuais antes de capacidades novas**: autoria correta
   (Frente 1), silêncio durante atendimento humano, bloqueio de mensagens
   antigas na fila, prevenção de loop entre bots, alertas sem repetição.
4. Testar com dados sintéticos, Postgres isolado quando necessário, handler
   real + provedor falso. Nunca mensagem a cliente real.
5. Nenhum deploy, migração de banco de produção, reinício de serviço,
   alteração de permissão, criação de credencial ou ferramenta autônoma.
6. Entregar matriz de reaproveitamento, diffs, commit, resultados reais de
   teste — separando implementado/testado/preparado/pendente.

### Mapeamento feito até agora (reaproveitamento, não reconstrução)
Das 5 falhas prioritárias do item 3, **3 já estão cobertas pela Frente 1**
(PR #63) — não serão duplicadas:
- Silêncio durante atendimento humano → `conversation_control.py`
  (pause/resume com fencing de revisão).
- Bloqueio de mensagens antigas na fila → `claim_send` (revalidação
  atômica no momento do envio).
- Alertas sem repetição → `incident_dedup.py` (dedup por janela/categoria).

Faltam (ver Frente 1 para detalhe):
- Autoria correta (Flávio/Micael).
- Prevenção de loop entre bots (hoje só existe no fluxo Twin).

### Ainda não iniciado
- Leitura/comparação de código dos 4 repositórios externos
  (`devthayron/whatsapp-ai-agent`, `Kjudeh/whatsapp-ai-receptionist`,
  `leandrosilvajs/evolution-n8n-whatsapp`, `YonaidisSoto/Whatsapp-Automation`)
  — via leitura pública (WebFetch), sem usar as credenciais GitHub desta
  sessão (escopo restrito a `prdariomarques-ship-it/ship-it`).
- Matriz de reaproveitamento formal (componente → origem → destino →
  adaptação → teste de aceitação).
- Perfis independentes (pessoal/Marquescolor/B2B/Igreja) como configuração
  de uma única plataforma — desenho ainda não feito.
- Multiempresa/comercial — base técnica, não implementação completa agora.

---

## Bloqueios transversais (afetam mais de uma frente)

1. **Sem shell direto na VPS** — todo comando é relayed pelo usuário
   (copia/cola). Vários pedidos de leitura de arquivo ainda pendentes de
   retorno completo.
2. **`backend/utils/config.py` também divergente da produção** (achado
   nesta sessão) — mesmo problema que já tratamos para handlers.py/router.py.
   Afeta tanto a correção de autoria quanto a generalização do loop-guard.
3. **VPS com pouquíssima RAM livre** — qualquer trabalho de build/novo
   serviço precisa considerar isso antes de propor.

## Próximo passo imediato

Aguardar o conteúdo real de `planner.py`, `store_agent.py`,
`descriptions.py`, `context.py`, `utils/config.py` (pedido já enviado) para
desbloquear: correção de autoria (Flávio/Micael), generalização do
loop-guard, e ajustes de tom/abstenção do StoreAgent.
