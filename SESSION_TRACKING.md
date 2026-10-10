# Acompanhamento geral — frentes em andamento

> Documento de controle para não perder o fio entre as três frentes paralelas
> desta sessão. Atualizado a cada decisão relevante. Nenhuma frase aqui é
> declaração de implantação — implantação só ocorre com janela aprovada e
> comprovação de rollback.

Última atualização: 2026-10-10 (acompanhamento de CI pós-rodada 4 da PR #63).

---

## Frente 1 — Correção WhatsApp (PR #63)

**Branch:** `whatsapp-agents-fix-review` → PR #63 (`draft`, não mergeada).

**Status:** em revisão. SHA atual: `6e19648`. A falha de lint que era
tratada como pré-existente/não relacionada (`agents/tools/flowcore_tools.py:25`)
foi corrigida na 4ª rodada — `ruff check .` no `backend/` inteiro está limpo
(0 erros). Corrigir esse lint desmascarou passos da CI que nunca tinham
rodado de fato nesta PR (ver "Acompanhamento de CI" abaixo): um crash do
`mypy` e uma cadeia de migração quebrada desde as rodadas 1-2, ambos
corrigidos; e um achado crítico novo (`Contact.awaiting_reply_since`
inexistente no modelo), reportado mas **não corrigido** por falta de
evidência de produção.

### Rodada 7 — revisão externa sobre `567d480` (SHA final `6a04bf6`)

- **Repetição pela fila (Loja, B2B, Azusa, agente, desculpas)** ✅ corrigido
  e testado pelo worker real. Envio comum agora reserva intenção por job antes
  do transporte e checa pausa sob o lock do escopo. Retentativa do mesmo job
  não transmite de novo. Falha comprovadamente anterior ao envio libera a
  reserva. Teste falso de repetição (que zerava o contador) removido.
  - **Limite:** pausa é checada no momento do envio. Envio antigo que roda
    após um `resume` não é barrado por revisão (só o Twin tem essa cerca).
  - **Limite:** provedores sem escopo de instância continuam sem reserva.
- **Eco antes do recibo** ⚠️ parcial. Recibo agora é gravado logo após o
  transporte, antes da persistência. Janela durante o envio em andamento
  continua aberta: eco nessa janela vira resposta humana e pausa a conversa.
  **Decisão pendente do dono:** pausar na ambiguidade (comportamento atual,
  silêncio do bot) ou adiar a classificação (risco de passar por cima de um
  humano que digitou durante o envio).
- **`Contact.awaiting_reply_since`** ⛔ bloqueado. Sem evidência do schema de
  produção. Não adicionei coluna nem migração às cegas. Latente com o modo Twin
  desligado. **Não ativar o Twin antes de resolver.**
- **Transcrição de áudio** ⛔ bloqueado. Existe contrato (`providers/stt`),
  mas nenhum backend implementado. Fonte real ausente.
- **`9e2f1c6d7a80`** ⛔ bloqueado (ver rodada 6).
- **mypy:** 5 erros de fonte ausente (`download_media`, `index_product`,
  `deindex_product`, `awaiting_reply_since` ×2). CI não passa enquanto existirem.

**Resultados locais (`6a04bf6`):** `backend/tests` 1144 passam;
`whatsapp_agents_fix/` 153 passam; fila 4 testes passam; `ruff` limpo.

### Rodada 6 — bloqueadores da revisão (SHA inicial `6e19648` → código `066321c`)

Este arquivo está no branch da PR de propósito: a versão em `master` só deve
mudar por PR. Estado honesto: **a CI deste SHA ainda falha no mypy**
(3 erros reais sem fonte no repositório, ver abaixo). Nada aqui declara
integração completa.

- **1. Propriedade da migração 003** ✅ corrigido, testado em PostgreSQL.
  Antes: um marcador global — criar uma coluna ausente autorizava apagar as
  três. Agora: uma linha por objeto (coluna ou índice) que o `upgrade()`
  realmente criou. Downgrade remove só o que comprovadamente criou; recusa
  com dado real, com acoplamento a índice alheio, ou se encontrar o marcador
  global antigo (nunca reinterpreta). Matriz de 13 testes em PostgreSQL real
  cobrindo: nenhuma coluna preexistente; todas; uma ou duas; índice
  preexistente com colunas ausentes; tabela vazia; tabela com padrões;
  dados de autoria preenchidos. Upgrade e rollback não removem estrutura nem
  dados preexistentes (verificado por consulta, não por suposição).
- **2. Migração histórica `9e2f1c6d7a80`** ⛔ **BLOQUEADO**. Busca exaustiva
  em todo o histórico (280 commits, todos os branches) mostra que o ID só
  aparece em arquivos escritos nesta própria revisão. O conteúdo real e os
  pais de produção não existem aqui e não há acesso à VPS. O placeholder
  continua marcado como não verificado. Não usei `stamp`, não inventei
  parentesco novo. Teste novo: ciclo `upgrade head` → `downgrade base` via CLI
  do alembic em PostgreSQL isolado (`test_full_migration_chain_…`). Isso prova
  só que o grafo deste repositório é percorrível, não equivalência com
  produção.
- **3. Eco não pode impedir atendimento humano** ✅ corrigido. Prova de autoria
  agora é exclusivamente um recibo do provedor gravado no envio
  (`conversation_receipts`). Texto igual e recência não provam nada. Todo envio
  com recibo reconhecido grava o recibo com o escopo que o eco vai trazer
  (correção de regressão encontrada nesta rodada: sem isso, eco de Loja, B2B e
  Azusa pausaria a própria conversa). O recibo é gravado logo após o
  transporte, **antes** de `persist_outbound_message` (teste:
  `test_receipt_is_durable_even_when_the_later_persistence_step_fails`).
  **Risco residual, não eliminado:** se o eco chegar ao webhook antes do
  `commit` do recibo (janela de milissegundos entre a resposta HTTP e o commit,
  ou eco que chega antes mesmo da resposta HTTP), não há prova e o eco é lido
  como resposta humana: pausa a conversa e grava a mensagem do bot com
  `sent_by_human=True`. Falha no sentido seguro para atendimento, mas erra a
  autoria. Corrigir por completo exige identificador do provedor antes do envio,
  que este gateway não oferece.
  Testes pelo parser e pela rota reais:
  eco com recibo; humano igual a texto antigo sem recibo; humano igual a texto
  recente sem recibo; reenvio do mesmo eco (`own_echo_unmatched`, sem pausa,
  sem mensagem nova); mesmo texto em dois contatos (sem contaminação cruzada);
  pausa persistida bloqueando envio antigo na fila.
- **4. Retry de POST em 500/502/504** ✅ corrigido. `HTTPStatusError` deixou de
  ser exceção: um 5xx não prova que o provedor recusou o envio. Um envio agora
  tenta exatamente uma vez, salvo falha anterior a qualquer byte da requisição
  (`ConnectError`, `ConnectTimeout`, `PoolTimeout`). Testes no cliente httpx
  real com transporte simulado, contando POSTs: aceitação seguida de
  `ReadTimeout`; `ReadError`, `WriteError`, `RemoteProtocolError`; 500, 502 e
  504 (cada um com 1 POST, `max_attempts=3`); conexão falha antes do envio
  (retenta); reexecução do job após resultado incerto (1 POST por execução);
  envio confirmado e próximo turno normal.
- **5. Contratos e CI** ⛔ **PARCIAL — CI ainda vermelha no mypy**.
  Resolvido com contrato real, sem stub de produção:
  - `providers/stt` (contrato `STTProvider`/`STTProviderError` e fábrica que
    devolve `None` quando não há backend). Destrava a coleta de `backend/tests`
    (1140 testes, todos passando).
  - Campos de `Settings` lidos pelos handlers, com defaults desligados ou
    vazios. **Não são valores de produção**, são marcados como tais no código.
  - `get_latest_inbound`, `has_human_reply_after`, `has_inbound_reply`,
    `recent_for_contact(instance=)`. Cada um testado contra SQLite e
    PostgreSQL reais.
  - Erros `int | None` e narrowing de `evidence` (equivalência verificada:
    todo caminho que define `is_risky` também define `evidence`).
  - `alembic` importado como módulo explícito (`import alembic.op as op`),
    não como `from alembic import op`. Isso resolve o falso positivo do mypy
    sem `# type: ignore`.
  - `whatsapp_agents_fix` vira passo próprio da CI, com serviço PostgreSQL
    efêmero (`postgres:16`, credencial só de CI). Passo separado porque os dois
    harnesses sombreiam o pacote `providers` e não coexistem no mesmo processo.

  **Mypy, reproduzido num venv limpo com `requirements-dev.txt` (igual à CI):
  5 erros, todos de fonte ausente.** Rodar localmente sem essas dependências
  escondeu erros; a CI do `066321c` mostrou 7 e eles foram corrigidos em
  `373b51c` (`task.py` e um reuso de variável em `handlers.py`).
  - `Contact.awaiting_reply_since` (2 ocorrências em `jobs/handlers.py`): não
    está no modelo nem em nenhuma migração. Latente enquanto
    `whatsapp_twin_mode_enabled` estiver desligado. Ligá-lo levanta
    `AttributeError` em `webhooks/router.py:593`. **Não ativar o modo Twin
    antes de confirmar o schema de `contacts` contra produção.**
  - `webhooks/router.py:185` — `WhatsAppProvider.download_media` **não existe**
    em nenhum provedor. Bloqueio: é preciso o endpoint real de download de mídia
    do Evolution. Não há evidência dele neste repositório. Hoje o trecho é
    inalcançável: só roda com um backend de STT configurado, e não existe
    nenhum.
  - `jobs/handlers.py:109-112` — `MemoryManager.index_product` /
    `deindex_product` **não existem**. O job `catalog.index_product` não tem
    produtor, e o import que ele documenta (`services/store_catalog.py`) não
    está neste repositório. Bloqueio: o módulo de catálogo, ou a decisão de
    removê-lo. Não removi por conta própria.

- **6. Preservação e cobertura declarada por caminho.** Testes existentes cobrem
  reserva durável antes do envio, pausa humana com bloqueio de jobs antigos,
  alerta com escopo separado, recibos e estado incerto, normalizações separadas
  com regressões multilinha, exceção estreita de "sem crise", e proteção contra
  repetição de alerta e vazamento de marcador. Cobertura por caminho:

  | Caminho de envio | Fence de pausa (revisão) | Dedup de alerta | Recibo p/ eco |
  |---|---|---|---|
  | Twin: resposta automática e mensagem de espera | sim (`claim_send`) | — | sim |
  | Twin: alerta ao proprietário | não, por desenho | sim (`claim_alert`) | sim |
  | Loop guard: alerta | não, por desenho | sim | sim |
  | **Loja / B2B / Azusa (resposta automática)** | **não** | — | sim (nesta rodada) |
  | Agente via `communication.py` | **não** | — | sim |
  | Desculpa de erro | **não** | — | sim |

  **Lacuna conhecida, não coberta:** um humano que assume uma conversa de Loja,
  B2B ou Azusa **não bloqueia** envios já enfileirados desses fluxos. Para
  fechar: passar `is_autopilot_reply`, `_twin_contact_id`, `_twin_revision` e
  `_twin_source_message_id` nos três pontos de enfileiramento
  (`jobs/handlers.py`), calculando a revisão antes da geração. Não implementado
  nesta rodada: é mudança estrutural e não foi pedida isoladamente.

**Resultados de teste (commit `066321c`, este ambiente, PostgreSQL local real):**
- `backend/tests` (suíte principal): **1140 passaram, 0 falharam**.
- `whatsapp_agents_fix/`: **153 passaram, 0 falharam**.
- `ruff check .`: **limpo**.
- `mypy` (venv limpo, igual à CI): 5 erros de fonte ausente, detalhados acima.
- `alembic upgrade head` → `downgrade base`: **limpo** em SQLite e em
  PostgreSQL isolado.
- **CI do GitHub do `066321c`: falhou no passo "Type check"** (7 erros, dos
  quais 2 corrigidos em `373b51c`). A CI do `373b51c` ainda não foi reportada.
  Os 5 erros restantes continuam a fazer o passo falhar.

**Plano de implantação/reversão: não emitido.** Compatibilidade com produção não
foi demonstrada (item 2 bloqueado). Nenhuma implantação, migração, restart ou
alteração de configuração foi feita.

### Acompanhamento de CI (2026-10-10, pós-rodada 4)

Corrigir `flowcore_tools.py:25` fez a CI avançar além de `ruff check .`
pela primeira vez nesta PR — cada passo seguinte nunca tinha sido
realmente exercitado antes. Dois problemas pré-existentes (de rodadas
anteriores desta mesma PR, nunca de produção) apareceram e foram
corrigidos (commit `6e19648`):
- `mypy` travava com "Duplicate module named 'database'"
  (`whatsapp_agents_fix/app_stub/` colide de propósito com nomes reais) →
  `backend/mypy.ini` excluindo esse diretório de harness.
- `alembic upgrade head`/`downgrade base` (os comandos exatos do passo
  "Migrations apply and roll back" da CI) travavam e depois recusavam:
  `e610080001` apontava para o head real de produção (`9e2f1c6d7a80`),
  revisão que não existe em nenhum arquivo deste repositório → migração-
  placeholder sem efeito em produção, só para o grafo fechar a partir de
  um banco em branco. `e610080002` recusava downgrade incondicionalmente,
  tornando o teste de fumaça da CI impossível de passar para sempre →
  aplicada a mesma política condicional de `e610080003` (recusa só com
  dado real). Testado localmente reproduzindo os comandos exatos da CI,
  ponta a ponta, limpo. Sem efeito prático em produção nos dois casos.

**Números reais da CI neste SHA** (não mais estimativa local): `ruff`
limpo; `mypy`, agora que roda de fato, aponta **38 erros em exatamente 4
arquivos** — `jobs/handlers.py`, `webhooks/router.py`, `admin/router.py`,
`repositories/task.py`. A maioria confirma com linha exata o gap já
documentado (`utils/config.py`/`Settings` sem várias flags) mais métodos
já sabidos como ausentes (`MessageRepository`, `JobRepository`,
`MemoryManager`, `download_media`).

**Achado crítico novo, NÃO corrigido:** `Contact.awaiting_reply_since` é
lido/escrito em 8 lugares (`webhooks/router.py:220,542,543`;
`jobs/handlers.py:527,541,815,911,919-920`) — inclusive numa `update()`
do SQLAlchemy Core que referencia o atributo no nível da classe
(`contact_type.awaiting_reply_since`) — mas **não existe em
`models/contact.py`**. Isso não é um no-op silencioso: a instrução
`update()` precisa de um `InstrumentedAttribute` real; se o campo não
existe, levanta `AttributeError` toda vez que esse trecho do pipeline de
áudio do proprietário rodar. Diferente das colunas de `e610080003`, não
há confirmação de produção (`\d contacts`) sobre se essa coluna já
existe lá — **não implementei uma migração às cegas**. Recomendação:
próxima rodada começa confirmando o schema real de `contacts` antes de
qualquer correção.

Ainda sem rodar nesta CI: `backend/tests/` (passo "Tests") não coleta
(`providers.stt` ausente, pré-existente, confirmado via `git log`) e
`backend/pytest.ini` nunca incluiu `whatsapp_agents_fix/` no `testpaths`
— os 133 testes de regressão desta PR nunca foram executados pela CI em
nenhuma rodada até agora (sinalizado na PR, não alterado).

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

### Prevenção de loop entre bots
- Existe um throttle genérico em `webhooks/router.py`
  (`auto-reply:{instance}:{contact_id}`, `settings.auto_reply_max_per_contact_per_minute`,
  janela de 60s), aplicado **antes de qualquer agente ser enfileirado** —
  cobre Twin, B2B, Azusa e Loja igualmente.
- ✅ **Corrigido (3ª rodada):** detecção específica de automação no outro
  lado + alerta ao proprietário (antes só no Twin) generalizada para B2B,
  Azusa e Loja via `_loop_guard_or_alert` — ver seção da revisão externa
  abaixo.
- **Ainda NÃO corrigido:** não há registro explícito das identidades/números
  das OUTRAS instâncias gerenciadas (pessoal/Loja/B2B/Igreja) para detectar
  conversa bot-a-bot especificamente (hoje a detecção é por volume/frequência,
  não por identidade do remetente). E o fencing de pausa humana
  (`claim_send`/`_twin_revision`) **ainda não se aplica a B2B/Azusa/Loja**:
  o payload que esses fluxos enfileiram para `whatsapp.send_text` não carrega
  `is_autopilot_reply`/`_twin_revision`/`_twin_contact_id`, então a
  revalidação de pausa nunca é acionada pra eles, mesmo com a pausa real já
  conectada (item D). Isso é uma mudança mais estrutural (threading dos
  campos de revisão por todos os 3 fluxos) ainda pendente.

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

### Revisão externa, 3ª rodada (2026-10-10) — SHA inicial `a137aff` → SHA final `70ede22`

- **Loop/automação generalizado para B2B, Azusa e Loja** ✅ corrigido e
  testado. Antes, a detecção específica de automação + alerta ao
  proprietário (`rate_limiter` + `incident_dedup`) só existia no fluxo do
  Twin — B2B/Azusa/Loja tinham só o throttle genérico de `router.py`.
  Extraído numa função compartilhada (`_loop_guard_or_alert`, reaproveita o
  mesmo `rate_limiter`, os mesmos campos de settings e o mesmo dedup de
  `incident_dedup` — não é mecanismo novo) e conectada nos 3 fluxos sem
  cobertura. Diferença deliberada do Twin: **nunca envia mensagem de
  espera ao contato** — responder a um provável loop de bots, mesmo com
  pedido de desculpas, só alimenta o loop. Silêncio pro outro lado, alerta
  pro proprietário. 4 testes novos contra a função real, o `rate_limiter`
  real (fallback em memória) e o dedup real: abaixo do limite não suprime;
  passar do limite suprime e alerta exatamente uma vez com o escopo
  correto; repetição na mesma janela não alerta de novo; instâncias
  diferentes do mesmo contato têm orçamentos independentes.
- **Busca exaustiva confirmou**: `find_unacknowledged_outbound` e
  `download_media` não aparecem em **nenhum** commit de **nenhuma** branch
  deste repositório, além dos arquivos que eu mesmo escrevi documentando a
  ausência deles. Não há mais evidência local a encontrar — permanecem
  como bloqueio real, não falta de busca.

### Revisão externa, 4ª rodada (2026-10-10) — SHA inicial `a137aff` → SHA final `62fcda3`

> Esta rodada confirmou os avanços da rodada anterior mas encontrou 2
> regressões reais (introduzidas pela própria correção da rodada 3) e 3
> gaps que precisavam de mais profundidade do que a rodada anterior deu.

- **1. Regressão na normalização (`normalize_text`)** ✅ corrigida e testada.
  A correção da rodada 3 (trocar toda quebra de linha por `". "`) resolveu a
  contaminação entre cláusulas mas quebrou termos fixos de crise partidos por
  uma quebra de linha ("quero\nmorrer", "me\nmatar", "não quero mais\nviver",
  "sem\nesperança") — e, como `output_safety.py` importava a mesma função,
  também passou a deixar passar um marcador interno/alegação de leitura
  partidos por quebra de linha. Separado em duas normalizações independentes:
  `output_safety.py` ganhou a sua própria (colapso total de espaço em
  branco — seus padrões não precisam de consciência de cláusula);
  `twin_risk_gate.py` passou a preservar `\n` como caractere literal
  (`\s` já casa `\n` nativamente nos padrões de termo) e adicionar `\n` ao
  conjunto de quebra de cláusula (`_CLAUSE_BREAK`) — resolve as duas
  direções com uma representação só. Os 3 exemplos já corrigidos antes e a
  exceção de "sem crise" foram preservados; 6 testes novos (4 +2).
- **2. Resposta humana por texto e eco do bot (`find_unacknowledged_outbound`)**
  ✅ implementado e testado — resolve o gap que a 3ª rodada deixou aberto
  por falta de evidência. A semântica foi derivada da própria chamada em
  `_capture_human_reply` e do modelo `Message`: casa uma linha OUTBOUND,
  **não** `sent_by_human`, com `external_id IS NULL` (nunca escrito por
  `persist_outbound_message`, logo toda mensagem enviada pelo sistema
  começa "não confirmada"), mesmo `content` e mesmo `whatsapp_instance`.
  2 testes novos cobrindo exatamente a distinção que o usuário pediu: uma
  resposta humana genuína (sem casamento → nova linha, pausa automação) e
  o eco do próprio bot (casamento → anexa o `external_id` na linha
  existente, não cria linha nova, **não** pausa). "Não tratar todo `fromMe`
  como humano" está provado nos dois sentidos.
- **3. Erro de rede ambíguo ainda podia repetir envio** ✅ corrigido e
  testado. A proteção da rodada 3 só cobria `ReadTimeout`/`WriteTimeout`;
  `ReadError`, `WriteError` e `RemoteProtocolError` ainda podiam disparar
  reenvio cego. Troquei a lista de bloqueio por uma lista de permissão
  (`ConnectError`/`ConnectTimeout`/`PoolTimeout` — falhas comprovadamente
  anteriores ao envio) para que qualquer erro não listado, conhecido ou
  futuro, falhe seguro por padrão em vez de repetir por padrão. 5
  testes novos/atualizados.
- **4. Downgrade ainda não provava quem criou as colunas** ✅ corrigido e
  testado. O check por valor de dado (TRUE/não-nulo) não provava autoria —
  uma tabela preexistente e não-vazia cujas colunas carregassem só os
  padrões FALSE/FALSE/NULL parecia "segura para apagar" sem nunca ter
  passado por esta migração. Adicionada uma tabela-marcadora que o
  `upgrade()` só escreve quando realmente cria uma coluna antes ausente;
  `downgrade()` agora exige a marca (prova de autoria) **e** a ausência de
  dado real (defesa em profundidade) antes de apagar. Novo cenário de teste
  (colunas preexistentes com valores padrão, tabela não vazia) — recusa
  corretamente agora. 5 cenários verificados em PostgreSQL real.
- **5. Lint** ✅ corrigido — import não usado em
  `agents/tools/flowcore_tools.py:25` removido; `ruff check .` limpo em todo
  o `backend/`.

**Resultados de teste (commit `62fcda3`, mesmo ambiente desta sessão):**
- `whatsapp_agents_fix/` com PostgreSQL local real habilitado: **133
  passaram, 0 pulados, 0 falharam**.
- Mesma suíte sem a variável de ambiente do Postgres (testes opt-in
  pulados em vez de rodados): **123 passaram, 10 pulados, 0 falharam**.
- `ruff check .` no `backend/` inteiro: **limpo, 0 erros**.
- `backend/tests/` (a suíte principal do app, via `main.py`/`conftest.py`)
  **não pôde ser coletada** neste ambiente: `ModuleNotFoundError: No
  module named 'providers.stt'`. Confirmado via `git log` que
  `providers/stt` nunca existiu em nenhum commit deste repositório — é um
  gap pré-existente do ambiente/repositório, não relacionado a nada desta
  rodada nem introduzido/corrigido por ela. Não tentei corrigir (fora do
  escopo desta tarefa).

**Explicitamente NÃO feito nesta rodada** (mesmos itens de antes, ainda
pendentes): reconciliação completa de `utils/config.py`, implementação de
`download_media`, escrita de volta do `receipt_id` real de um envio na
própria linha `Message` (hoje é calculado em `jobs/handlers.py` mas só é
persistido pelo caminho de eco do `fromMe` que esta rodada adicionou), e
cobertura dos outros agentes (B2B/Azusa/Loja) equivalente à do Twin. Nenhum
merge, downgrade, migração ou implantação em produção foi executado.

### Gaps confirmados, NÃO corrigidos (sem evidência suficiente para corrigir com segurança)
- `download_media` — chamado por `router.py`, **não existe** em nenhum
  provider nem na interface base (confirmação exaustiva, ver 3ª rodada).
  Áudio do proprietário não pode ser transcrito/baixado hoje.
- `utils/config.py` ainda divergente da produção — bloqueado no conteúdo real
  da VPS (ver Bloqueios).
- Correlação do `receipt_id` real de um envio de volta na própria linha
  `Message` (`jobs/handlers.py` calcula `extract_receipt_id(send_result)`
  mas nada escreve esse valor em `Message.external_id` no momento do envio
  — só o caminho de eco do `fromMe`, novo nesta rodada, chega a preencher
  esse campo, e só quando o eco realmente chega).

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
3. `download_media` ainda é um gap confirmado (ver Frente 1) —
   `find_unacknowledged_outbound` foi implementado e testado na 4ª rodada.
   `download_media` provavelmente também precisa de mais contexto/decisão
   do usuário, não é "procurar mais no código".
