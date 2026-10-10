# Acompanhamento geral — frentes em andamento

> Documento de controle para não perder o fio entre as três frentes paralelas
> desta sessão. Atualizado a cada decisão relevante. Nenhuma frase aqui é
> declaração de implantação — implantação só ocorre com janela aprovada e
> comprovação de rollback.

Última atualização: 2026-10-10.

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
- `twin_risk_gate.py` — "sem crise" (gíria = "sem problema") não escalava
  mais como crise real de impersonação. Corrigido com exceção estreita (não
  ampliando a janela geral de negação, que arriscaria apagar sinais reais
  como "sem razão, quero me matar"). 25/25 testes, lint limpo.
- **7 bugs da revisão externa (A-G) corrigidos e testados** — ver seção
  própria abaixo. Commit `bac6df2`, pushado.

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

### Revisão externa (2026-10-09) — 7 bugs confirmados, CORRIGIDOS e TESTADOS

**Commit:** `bac6df2` em `whatsapp-agents-fix-review` (pushado, PR #63).
**Testes:** 10 testes novos em 3 arquivos, execução real contra os arquivos
reais (não cópia, não só AST) — 97 passaram, 5 skipped (Postgres opt-in,
inalterado), ruff limpo (só a mesma falha pré-existente e não relacionada
em `agents/tools/flowcore_tools.py`).

- **A. Reserva sem commit antes do transporte** — ✅ corrigido. `await
  db.commit()` adicionado logo após `claim_send`/`claim_alert` ter sucesso,
  antes de `provider.send_text(...)` (exigido pelo próprio docstring de
  `conversation_control.py`). Também adicionado um commit final (os writes
  de `finish_send`/`finish_alert` nunca eram commitados, independente
  disso). Testado simulando um crash no meio do transporte — confirmado
  que um retry não reenvia.
- **B. Alerta ao proprietário nunca era entregue** — ✅ corrigido. Novo
  campo `_twin_alert_instance` separa o escopo da reserva do alerta do
  campo `instance` (que também seleciona o número/gateway de envio) —
  evita trocar o remetente do alerta ao corrigir o escopo.
- **C. Conclusão de envio sempre incerta + crash garantido** — ✅ corrigido.
  `extract_receipt_id` captura o `receipt_id` real (`response["key"]["id"]`,
  formato real do Baileys/Evolution API) em vez de sempre `None`.
  `persist_outbound_message` agora aceita `is_autopilot_reply=`/`instance=`
  (antes era `TypeError` garantido em todo envio real). Testado: recibo
  reconhecido promove a `'sent'`; recibo não reconhecido continua
  `'needs_review'` (nunca promove por suposição).
- **D. Pausa humana nunca conectada ao evento real** — ✅ corrigido.
  `_capture_human_reply` agora chama `conversation_control.pause` de
  verdade. Testado de ponta a ponta: um evento real de resposta do
  proprietário pausa `conversation_controls` E essa pausa de fato bloqueia
  um `claim_send` com revisão antiga — não são duas provas desconectadas.
- **E. Import quebrado em `output_safety.py`** — ✅ corrigido (mesmo padrão
  já usado em `incident_dedup.py`).
- **F. (novo, achado ao escrever os testes) `InboundMessage` sem `instance`/
  `media_key`** — ✅ parcialmente corrigido. Campos adicionados;
  `EvolutionProvider.parse_webhook` agora popula `instance` do envelope real
  do webhook. `media_key` deliberadamente **não** populado — não existe
  lógica de extração nem `download_media` em nenhum provider; documentado,
  não inventado.
- **G. (novo) `EvolutionProvider.send_text`/`send_image`/etc. não aceitavam
  `instance=`** — ✅ corrigido, mesmo que `handlers.py` já chamava.

### Revisão externa, 2ª rodada (2026-10-10) — SHA inicial `bac6df2` → SHA final `a137aff`

> Esta rodada partiu exatamente do commit revisado (`bac6df23ab0b9a...`, HEAD
> confirmado antes de editar) e tratou as 5 prioridades indicadas, nessa ordem.

- **Prioridade 1 — downgrade destrutivo da migração `e610080003`** ✅ corrigido
  e testado em PostgreSQL real (4 cenários pedidos: upgrade sem as colunas,
  upgrade como no-op com dados reais, downgrade recusando e preservando dados
  reais, downgrade funcionando limpo quando não há dados). `downgrade()` agora
  recusa (levanta erro) sempre que as 3 colunas carregam qualquer dado real —
  existência da coluna nunca prova que esta migração a criou.
- **Prioridade 2 — pausa humana pelo webhook real** ✅ corrigido e testado de
  ponta a ponta. Achado novo, mais profundo que o da rodada anterior:
  `InboundMessage` não tinha campo `from_me`, **e os dois providers
  descartavam todo evento `fromMe=True` antes do router.py sequer ver** —
  mesmo com o router já esperando `inbound.from_me` para decidir entre
  captura humana e fluxo normal. Ou seja, o caminho de captura de resposta do
  proprietário era código morto, não só "pausa não conectada". Corrigido nos
  dois providers + `InboundMessage`. Teste novo parte de um payload JSON real
  da Evolution → parser real → `whatsapp_webhook` real (função da rota, não
  só `_capture_human_reply` direto) → pausa real → revisão incrementada →
  `claim_send` antigo bloqueado. Mais um teste de webhook duplicado
  (idempotência).
- **Prioridade 3 — reenvio cego em timeout de resposta** ✅ corrigido e
  testado com transporte HTTP determinístico (sem rede real). O commit antes
  do transporte (rodada anterior) só protege contra o *worker* repetir o job
  inteiro depois de um crash — não protege contra a própria camada HTTP
  tentando de novo *dentro* da mesma execução depois que o provedor aceitou o
  envio e a resposta deu timeout. `_request` agora distingue
  `ReadTimeout`/`WriteTimeout` (ambíguo — a mensagem pode já ter sido
  entregue) de `ConnectError`/`ConnectTimeout` (nunca saiu daqui, sem
  ambiguidade) — só o primeiro caso deixa de repetir.
- **Prioridade 4 — lint/CI** — sem mudança: ainda só a mesma falha
  pré-existente e não relacionada (`agents/tools/flowcore_tools.py:25`).
  114/114 testes passam, **0 pulados** nesta rodada (rodados com PostgreSQL
  local real, não pulados por falta de banco).
- **Prioridade 5 (parcial) — 3 falsos negativos reais em `twin_risk_gate.py`**
  ✅ corrigidos: `:` não era reconhecido como quebra de cláusula ("não estou
  bem: quero morrer" deixava a negação da primeira frase cancelar o sinal
  real da segunda); quebra de linha era colapsada num espaço antes de
  qualquer lógica de cláusula rodar (mesmo problema, variante com `\n`); e o
  padrão de "negação depois" aceitava qualquer cópula depois do negador
  ("quero morrer não é fácil" era lido como "a culpa não é nossa" apesar de
  significarem coisas opostas) — restringido para exigir complemento de
  atribuição/posse. Abstenção/tom do StoreAgent continuam bloqueados (ver
  abaixo). Dupla negação ("não quero morrer, mas às vezes penso") foi
  verificada e é genuinamente ambígua — não forcei uma resposta específica,
  como a revisão pediu.

### Gaps confirmados, NÃO corrigidos (sem evidência suficiente para corrigir com segurança)
- `MessageRepository.find_unacknowledged_outbound` — chamado por
  `_capture_human_reply`, **não existe** em nenhum lugar do repositório.
  Detecta eco da própria mensagem enviada por nós; a semântica exata de
  casamento não está evidenciada em lugar nenhum — implementar às cegas
  arriscaria errar a lógica de detecção de eco. Bloqueia o caminho de texto
  (não-áudio) de `_capture_human_reply` inteiramente (o caminho de áudio do
  proprietário, usado nos testes novos, não passa por aqui).
- `download_media` — chamado por `router.py`, **não existe** em nenhum
  provider nem na interface base. Áudio do proprietário não pode ser
  transcrito/baixado hoje.
- Generalização do fencing de pausa + detecção/alerta de automação para
  B2B/Azusa/Loja — ainda só existe de verdade no fluxo do Twin (ver seção
  acima sobre loop entre bots).
- `utils/config.py` ainda divergente da produção — bloqueado no conteúdo real
  da VPS (ver Bloqueios).

### Requisitos de produto registrados (ainda não implementados — StoreAgent)
- **Abster-se quando não sabe:** não é silêncio — enviar uma mensagem
  reconhecendo ("um momento, vou verificar e te retorno") **uma única vez
  por incidente**, só quando houver encaminhamento real, e registrar em log
  para revisão humana depois. Nunca durante atendimento humano ou bloqueio
  entre bots. Nunca inventar preço/estoque/disponibilidade/pedido concluído.
  Busca vazia não comprova inexistência (ex: variações "thinner"/"thiner").
  Nunca afirmar que o proprietário já viu/leu uma mensagem sem evidência.
- **Tom por segmento (Marquescolor):** respostas mais curtas e informais
  para o público de oficina/pintor (tinta automotiva: PU, verniz,
  poliéster — público mais rústico). Tinta imobiliária parece ser um
  segmento menor/diferente, tom a confirmar.
- Pendente do conteúdo real de `store_agent.py`/`planner.py`/`descriptions.py`/
  `orchestrator/context.py` para aplicar (e para a correção de autoria
  Flávio/Micael acima) — pedido enviado à VPS, retorno incompleto até agora.

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
3. **VPS com pouquíssima RAM livre** — recomendação dada: mínimo 8GB pra
   parar de estourar swap, 12GB recomendado (folga pra build de frontend),
   16GB se for usar modelos maiores no Ollama. Decisão do usuário, ainda
   não executada. **Prioridade confirmada pelo usuário: WhatsApp 24/7 vem
   antes de Open WebUI** — Open WebUI pode continuar só local no PC por
   enquanto, já que não é usado fora de casa.
4. **Telegram não está nesta auditoria ainda** — o usuário apontou que os
   bots do Telegram (se existirem na mesma arquitetura) ainda não foram
   mapeados em nenhuma das 3 frentes. Pendente: descobrir se há
   integração Telegram real em produção (grep no repo não achou nada
   óbvio até agora) e, se houver, aplicar o mesmo tratamento dado ao
   WhatsApp (auditoria antes de editar, mesma disciplina de divergência
   de base).

## Próximo passo imediato

1. Aguardar o conteúdo real de `planner.py`, `store_agent.py`,
   `descriptions.py`, `context.py`, `utils/config.py` (pedido já enviado)
   para desbloquear: correção de autoria (Flávio/Micael) e ajustes de
   tom/abstenção do StoreAgent.
2. Mapear Telegram (ver bloqueio 4 acima).
3. Decidir o que fazer com `find_unacknowledged_outbound`/`download_media`
   (gaps confirmados, sem evidência suficiente pra implementar sem
   adivinhar semântica) — provavelmente precisa de mais contexto/decisão
   do usuário, não é "procurar mais no código".
