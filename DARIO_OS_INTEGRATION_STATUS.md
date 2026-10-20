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
- ~~Não verificado: renderização no navegador~~ e ~~conversas pausadas indisponíveis~~: **superados no ciclo 5** (seção 13): validação em Chrome real contra stack isolado e endpoint `GET /admin/darius/paused-conversations` implementado.

### Limitações e INCONCLUSIVO deste ciclo
- Instância roteada ao DARIUS **não** cai para o pipeline local se o DARIUS falhar (decisão deliberada: evita resposta duplicada/divergente); o cliente fica sem resposta automática e o vínculo registra `failed`/`expired` para atendimento humano.
- Só texto nesta etapa (mídia/áudio não roteados).
- A conformidade do **LLM real** com o formato `DONE:` não foi medida (Ollama simulado). Se o modelo não emitir `DONE:`, a tarefa falha por iterações máximas e nada é enviado (falha segura, mas sem resposta).
- O caminho de aprovação (`PAUSED` -> aprovar) foi validado com mocks aqui e pelos testes de ciclo de vida do próprio DARIUS; não houve aprovação real ponta a ponta com a ponte do Dario OS.
- Segue não verificado: qual backend serve o WhatsApp em produção; contrato do FlowCore `/api/ask`; localização do Monitor SCPX; limiares do antiloop em produção.

## 11. Próxima ação concreta

Atualizado no ciclo 5. Itens 2 a 4 do plano anterior (painel no navegador, conversas pausadas, auditoria Telegram, retry/scheduler/métricas do DARIUS) estão feitos (seção 13). Resta, e depende de decisão do usuário:

1. Demonstração WhatsApp->DARIUS com **instância de teste isolada + número controlado** (não confirmados; segue `INCONCLUSIVO`; nenhuma mensagem real foi enviada).
2. Medir a conformidade do **modelo real** com o protocolo `DONE:` (hoje só com Ollama simulado e parser testado).
3. Layout mobile do painel e cliques de aprovação/suspensão no navegador (ver limites na seção 13).
4. Validar o painel contra PostgreSQL (o e2e usou SQLite) e, só com autorização explícita, push/deploy. Monitor SCPX segue `INCONCLUSIVO`.

## 12. Log

- 2026-10-19: Fase 0 concluída (somente leitura). Único artefato criado neste repo: este arquivo.
- 2026-10-19: Ciclo 1 concluído no repo DARIUS (`d983c93`; gate completo em `2d98c5f`, evidência em `5a72e24`).
- 2026-10-19: Ciclo 2 concluído no Dario OS (`33896b0`): adaptador DARIUS + ponte admin + testes de contrato contra o servidor real. Pendente: painel/frontend, suspensão, fluxo WhatsApp, Telegram, hardening do DARIUS.
- 2026-10-19: Ciclo 3 concluído: árvore do Codex documentada e protegida (`fd4c9b3`) + suspensão global/por instância no transporte (`e093d9c`). Pendente: fluxo WhatsApp->DARIUS, painel, Telegram, hardening do DARIUS.
- 2026-10-19: Ciclo 4 (parcial): suspensão atômica (`959ade4`), adaptador WhatsApp->DARIUS (`060c1d1`; DARIUS `08d2b9c`), regressão de migrações corrigida (`0ee5074`); suíte completa em `0ee5074`: 2 failed + 2 errors = só as 4 pré-existentes. Pendente: painel (P4), Telegram/hardening (P5).
- 2026-10-19: Ciclo 4 (P1/P4): painel DARIUS (`29ef291`, `83c749e`); defeito de resposta duplicada achado pela suíte completa e corrigido (`8aedd8a`); suíte completa em `8aedd8a`: 2 failed + 2 errors = só as 4 pré-existentes. Sem push, deploy ou envio real. Pendente: P5 (Telegram, hardening do DARIUS).
- 2026-10-19: Ciclo 5 (P5 + hardening final): Telegram (`7a49b69`); DARIUS retry/backoff (`a94f197`), scheduler + métricas (`3620058`), protocolo `DONE:` (`c08077b`); Dario OS: testes de modelo/WhatsApp contra o runtime real (`0873881`), ponte de métricas + conversas pausadas (`14a44d8`), abas do painel (`9705cfe`), correções achadas no navegador (`015e5cd`). Suíte completa do backend em `015e5cd`: 2 failed + 2 errors = só as 4 pré-existentes. **CONCLUSÃO PARCIAL.** Sem push, deploy ou envio real.

## 13. Ciclo 5 - P5 e hardening final (CONCLUSÃO PARCIAL)

Sem push, deploy ou envio real de mensagem. Só os processos do stack de teste deste ciclo (portas 18000/18100/13100) foram iniciados e encerrados; nada do que já rodava foi tocado. O frontend do Codex não foi alterado por este ciclo (`git status` só mostra os artefatos deste ciclo e `voice-service/.venv-ptbr/`, não rastreado e deixado como estava) e o snapshot `C:\Users\dario\backups\codex-ship-it-20261019\` continua existindo.

### Commits
- **DARIUS** (`integration/darius-lifecycle-api`): `a94f197` retry/backoff do consumidor QUEUED; `3620058` scheduler durável no ciclo de vida do servidor + `GET /api/admin/metrics`; `c08077b` protocolo `DONE:` fixado por testes. Suíte: **519/519**, `tsc --noEmit` limpo (JSON em `docs/evidence/cycle5/darius/`).
- **Dario OS** (`integration/dario-os-darius`): `7a49b69` Telegram (auditoria, poller fail-closed, inventário somente leitura); `0873881` testes de saída malformada, queda do provedor e escopo de suspensão contra o runtime real; `14a44d8` ponte de métricas + conversas pausadas; `9705cfe` abas Métricas e Conversas pausadas; `015e5cd` correções achadas no navegador.

### Garantias do DARIUS (a confiabilidade mora nele; o TS segue canônico)
- **Retry/backoff** (desligado por padrão; `DARIUS_QUEUE_RETRY_*`, valor inválido = recusa subir). Só `BEFORE_EFFECT_TRANSIENT` é repetida. `EFFECT_UNKNOWN`, `EFFECT_CONFIRMED` e `BEFORE_EFFECT_PERMANENT` **nunca** são repetidas; esgotadas viram `RETRIES_EXHAUSTED`. `TransientError{beforeEffect}` é atestado de quem lança; erro dentro do ACT sem esse atestado é `EFFECT_UNKNOWN`. A chave de efeito não avança ao reenfileirar. `/result` expõe só `failureClass` e `retry` (lista branca; metadado bruto e cadeia de raciocínio nunca cruzam a API).
- **Scheduler** (desligado por padrão): dispara 1x; reinício não redispara; dois processos geram 1 tarefa (CAS + chave `schedule:<id>:<slot>`); configuração inválida recusa subir. Testado com processos `server.ts` reais.
- **Métricas**: contagens duráveis vêm do armazenamento; contadores de processo zeram no reinício e dizem isso; o que não é lido é `null`, nunca 0.
- **`DONE:`**: `parseDoneOutput` exportado; espaço antes do marcador tolerado; resultado vazio não conclui; verificado contra o runtime real.

### Painel (validação em Chrome real; detalhes em `docs/evidence/cycle5/panel-e2e-20261019.md`)
Stack isolado (backend 18000, DARIUS 18100, Next 13100, bancos SQLite descartáveis; nada na 3000). Verificados: navegação nas 9 abas, dados reais, polling de 10 s, tráfego só para o backend isolado, erro com DARIUS derrubado, recuperação automática, 403 na API e "Acesso restrito" na UI para usuário comum. A validação **achou 2 defeitos reais** (número anterior à queda exibido como atual; `paused_since` sem fuso), corrigidos com teste de regressão (o primeiro falha sem a correção).

### Conversas pausadas/humanas
Endpoint implementado (`GET /admin/darius/paused-conversations`, somente leitura, paginado, filtro por instância; telefone mascarado nos 4 últimos dígitos; motivo e autor da pausa mais recente). Retomar continua só dentro da conversa, com a checagem de revisão que protege envio em andamento.

### Suíte completa do backend em `015e5cd`
`python -m pytest -q ... --junitxml=full_final_015e5cd.xml` (com `DARIUS_REPO_PATH`): **1992 testes, 1963 passaram, 25 skips, 2 falhas + 2 erros em 674,8 s**. As 4 são exatamente as pré-existentes, com baseline comparável em `e64d2f7` (seção 10, P1): `test_context_builder` x2 e `test_groq_stt::test_audio_vazio_ou_grande_demais_nem_chega_a_rede` x2 (variável de ambiente > 32767 caracteres no Windows). Os testes de duplicata/CAS do WhatsApp (`test_transition_is_compare_and_set`, `test_a_duplicated_inbound_job_creates_one_task_and_one_reply`, `test_a_create_whose_response_was_lost_does_not_duplicate_the_task`, `test_pause_and_resume_after_submission_still_blocks_the_stale_reply` e o de contrato real `test_real_darius_idempotency_a_duplicate_message_does_not_create_a_second_task`) estão presentes e passaram nesta execução; nenhum foi removido nem enfraquecido. Frontend: vitest **54 arquivos / 392 testes**, `tsc --noEmit` e eslint sem erro. O log bruto (209 MB, inflado pelo parâmetro gigante do teste groq) e o XML (26 MB) ficam fora do repositório.

### Classificação
| Requisito | Estado | Evidência / observação |
|---|---|---|
| Retry/backoff do consumidor QUEUED | COMPROVADO | Testes unitários e multiprocesso; só falha antes do efeito é repetida |
| Scheduler no servidor real + métricas | COMPROVADO | Processos `server.ts` reais; ponte e painel exibem os mesmos números |
| Protocolo `DONE:` com parser | COMPROVADO | Runtime real com Ollama simulado |
| Fluxo WhatsApp->DARIUS até o adaptador de envio | COMPROVADO (mocks) | Evolution simulado; sem mensagem real |
| Suspensão global/por instância, inclusive jobs já enfileirados | COMPROVADO | Job e worker reais, só o transporte é falso |
| Painel no navegador real (desktop) | COMPROVADO | Seção acima |
| Listagem de conversas pausadas | COMPROVADO | Backend + painel + 12 testes backend / 13 frontend |
| Telegram: inventário e poller fail-closed | COMPROVADO (estático) | Estado em tempo real **indisponível** por desenho |
| Layout mobile do painel | PARCIAL | Não verificado: o redimensionamento não alterou o viewport |
| Aprovar/rejeitar/suspender no navegador, paginação | PARCIAL | Só vitest e testes da ponte; não clicados no navegador |
| Datas do vínculo WhatsApp (`created_at`) | PARCIAL | 3 h adiantadas no SQLite (mesma causa do `paused_since`); PostgreSQL não verificado |
| Desligamento gracioso (SIGTERM) | PARCIAL | Não provável no Windows (SIGTERM mata); testes usam kill forçado; recuperação de lease é a rede de segurança |
| Painel contra PostgreSQL | PARCIAL | E2E usou SQLite |
| Conformidade do modelo real com `DONE:` | INCONCLUSIVO | Sem medição com LLM real |
| Demonstração WhatsApp real (instância de teste + número controlado) | INCONCLUSIVO | Instância e número não confirmados pelo usuário |
| Monitor SCPX | INCONCLUSIVO | Localização/estado não verificados |
| Qual backend serve o WhatsApp em produção; contrato FlowCore `/api/ask`; limiares do antiloop | INCONCLUSIVO | Não verificados |

### Limites conhecidos (documentados, não corrigidos)
- `listTasksByStatus` do DARIUS tem `LIMIT 100` ordenado por `updatedAt`: mais de 100 tarefas em espera podem atrasar as prontas do consumidor.
- Retry e scheduler vêm **desligados** por padrão; ligar é decisão operacional explícita.
- O stack e2e é reproduzível por `docs/evidence/cycle5/e2e/` (caminhos fixos desta máquina; valores de teste, nenhum segredo).



## 14. Ciclo 6 - ajuste de escopo (P0-P6) - ENCERRAMENTO

Sem push, deploy, release ou envio real de mensagem (WhatsApp ou Telegram). Os quatro agentes de WhatsApp, Evolution API, OCR, leitor de áudio e Celis não foram tocados. A curva DI foi **adiada por decisão do usuário** (Yahoo Finance e Google Finance não têm; nenhuma fonte foi integrada). O frontend do Codex e o snapshot `C:\Users\dario\backups\codex-ship-it-20261019\` não foram alterados. Só processos de teste (portas 13100/18000/18001/18100 e o contêiner descartável `c6-pg-tz` na 15432) foram iniciados, por porta/nome exatos, e encerrados.

### Commits
- **DARIUS** (`integration/darius-lifecycle-api`): `f7d0069` seleção QUEUED consciente de elegibilidade (sem fome atrás de 100 linhas inelegíveis; `listQueuedReady` opcional no store, em memória e SQLite).
- **Dario OS** (`integration/dario-os-darius`): `4d098b2` varredura de autorização sobre todas as rotas `/api/admin`; `d46e320` modos de falha da ponte de métricas + evidência WSL do ciclo de vida; `f1f954b` evidência do Telegram e decisão de construir dois bots novos; `0d78de1` timestamps UTC explícitos no painel (SQLite devolvia valores sem fuso); `8c3a5e8` bots de mercado `market-bots/` + serviço no compose.
- Arquivos novos não versionados antes deste fechamento: `docs/evidence/cycle6/{suites,ui-flow,timezone,e2e}/` (commit do fechamento). `docs/evidence/cycle6/mobile/` e `voice-service/.venv-ptbr/` estavam não rastreados; o segundo foi deixado como estava.

### Suítes (cabeça `8c3a5e8` no Dario OS, `f7d0069` no DARIUS)
| Suíte | Resultado |
|---|---|
| DARIUS Vitest completo, **sem paralelismo de arquivos** | **67 arquivos, 530/530 passaram** (261 s) |
| DARIUS `tsc --noEmit` | limpo |
| DARIUS Vitest completo **em paralelo** | 5 arquivos falharam por `Hook timed out in 10000ms` sob carga (suítes HTTP com processos reais + `queue.starvation`); as mesmas suítes sem paralelismo: 10 arquivos / 105 testes passam. Classificação: **timeout sob carga**, não falha de lógica |
| Backend Dario OS completo | **2074 testes: 2045 passaram, 2 falhas, 2 erros, 25 ignorados** (720 s) |
| Frontend Vitest | 54 arquivos / **392/392** |
| Frontend `tsc --noEmit` e ESLint | saída 0 nos dois |

**Comparação com a baseline `e64d2f7`** (árvore completa: 1790 testes, 2 falhas, 2 erros, 25 skips): as falhas são **as mesmas 3 identidades**, 0 regressões e 0 corrigidas: `test_context_builder::test_awaiting_approval_goals_are_excluded_from_context`, `test_context_builder::test_goal_lookup_failure_does_not_block_context_building` (lógica preexistente) e `test_groq_stt::test_audio_vazio_ou_grande_demais_nem_chega_a_rede` (erro de setup: variável de ambiente > 32767 caracteres no Windows; artefato do teste). Resumos estruturados em `docs/evidence/cycle6/suites/`; o XML bruto (26 MB, inflado pelo parâmetro gigante do teste groq) fica fora do repositório (SHA-256 no JSON).

### P0 - integridade e segurança
Varredura automática (71 testes) enumera todas as rotas `/api/admin` via OpenAPI e exige 401 sem token e 403 para usuário comum. Nenhuma rota admin aberta; nenhum runtime/scheduler concorrente encontrado. No navegador: usuário comum recebe 403 em `status`, `metrics`, `tasks`, `paused-conversations` e `automation/suspension` e **não consegue aprovar** (403); anônimo recebe 401; a UI mostra "Acesso restrito" sem botões de decisão.

### P1 - consumidor QUEUED
Defeito corrigido: com mais de 100 linhas QUEUED inelegíveis (em backoff ou de agente não registrado) o consumidor não via as prontas. A elegibilidade agora é filtro do store aplicado antes do LIMIT. 11 testes (memória e SQLite): 130 tarefas drenam exatamente uma vez; dois motores sobre um SQLite processam 120 tarefas exatamente uma vez.

### P2 - ciclo de vida do servidor (WSL Ubuntu; `docs/evidence/cycle6/p2-wsl/`)
Configuração inválida recusa subir ("REFUSING TO START", saída 1) em 5 variantes; padrão desligado; scheduler dispara, SIGTERM encerra graciosamente e nada dispara depois; reinício no mesmo banco não duplica nem rajada; dois processos no mesmo banco: slots exatamente-uma-vez; `kill -9` + reinício: slots únicos. **PARCIAL:** SIGTERM com um ACT em andamento no nível do servidor completo não foi provado (no Windows SIGTERM mata o processo).

### P3 - métricas
Modos de falha da ponte testados (DARIUS fora, circuito aberto, sem números velhos, invariantes). O painel mostra "indisponível" com motivo; nunca zero inventado.

### P4 - Telegram
Radares antigos: agendas removidas (apenas `workflow_dispatch`), execuções antigas falharam por causa **não determinada**; o Poller roda e termina com sucesso no GitHub, mas **entrega real não comprovada**. Monitor SCPX: **INCONCLUSIVO** (não localizado). Decisão do usuário: dois bots novos.
**`market-bots/`** (`8c3a5e8`): bots **Mercado Brasil** e **Mercado Global**, Python stdlib, `profiles.toml`, Docker e serviço `market-bots` no compose (dry-run por padrão, volume próprio, usuário não-root). 58 testes, ruff limpo; contêiner descartável: `healthy` e boletim real da Ásia só em leitura. Limites: entrega real no Telegram não testada (faltam tokens do BotFather no `.env`); download real do zip da CVM não testado (aguarda autorização); sem curva DI; América Central só via ETF `CPA` (Panamá); Colômbia sem fonte; alguns tickers B3 inexistentes no Yahoo ficaram fora dos maiores altas/baixas.

### P5 - painel no navegador (Chrome real com Playwright; stack isolado 13100/18000/18100; nada na 3000; evidência em `docs/evidence/cycle6/ui-flow/` e `e2e/ui_flow.mjs`)
**26/26 verificações** do fluxo principal, mais 6/6 de erro e recuperação:
- Paginação (137 tarefas, 25 por página): página 1 = itens 1-25 da API; "Próxima" = itens 26-50; "Anterior" volta; última página desabilita "Próxima".
- Aprovar (desktop): confirmação obrigatória; "Voltar" não tem efeito; confirmar tira a tarefa de PAUSED no DARIUS; segunda aprovação da mesma tarefa recusada (409). Observação: a tarefa aprovada foi para RUNNING no DARIUS isolado (Ollama inalcançável de propósito); nenhuma ação externa.
- Rejeitar (**emulação móvel real**, 390x844, toque, DSF 3): tarefa vira FAILED no DARIUS e o motivo é persistido.
- Suspender/retomar instância `store`: "Confirmar" desabilitado sem motivo; suspensão e retomada persistem no backend.
- DARIUS derrubado: Métricas, Visão geral e Aprovações mostram indisponibilidade (circuito aberto) sem números e sem botões de aprovar; DARIUS religado: os números reais (137 tarefas) voltam. A recuperação **sem recarregar a página** foi observada no ciclo 5 (`panel-e2e-20261019.md`); neste ciclo cada fase abriu uma sessão nova.
- Mobile real (`docs/evidence/cycle6/mobile/`): 9 abas em 390x844 e 360x640 sem overflow horizontal do documento. Tabelas de 454-598 px ficam contidas na página; **não verificado** se o conteúdo cortado é alcançável por rolagem interna.

Defeito do **meu teste** (não do painel), corrigido: a paginação da tela é de 25 e mostra os 8 primeiros caracteres do id; a primeira execução comparava páginas de 10 e ids completos (2 falsas falhas). Rodada nova, stack recriado do zero: 26/26.

### Timezone com PostgreSQL 16 descartável (porta 15432, servidor em `Asia/Tokyo` de propósito; `docs/evidence/cycle6/timezone/`)
Comparação persistido x API x interface (navegador em `America/Sao_Paulo`):
| Campo | Persistido (sessão Tóquio / UTC) | API | Interface (BRT) |
|---|---|---|---|
| `darius_whatsapp_tasks.created_at` | `2026-10-20 10:19:37.045677+09` / `01:19:37.045677` | `2026-10-20T01:19:37.045677Z` | `19/10/2026, 22:19:37` |
| `conversation_control_audit.created_at` (paused_since) | `10:19:36.939098+09` / `01:19:36.939098` | `...01:19:36.939098Z` | `19/10/2026, 22:19:36` |
| `automation_suspensions.created_at` (since) | `10:20:06.230967+09` / `01:20:06.230967` | `...01:20:06.230967+00:00` | `19/10/2026, 22:20:06` |
Todos `timestamptz`, mesmo instante nas três camadas, API sempre com offset. **Nenhum defeito reproduzido em PostgreSQL**, portanto nenhum código alterado. O defeito de SQLite (valores sem fuso) já estava corrigido em `0d78de1`. Limite: a UI foi servida pelo Next isolado com as chamadas `/api` redirecionadas (interceptação do navegador) ao backend PostgreSQL; `GET /api/admin/logs` continua devolvendo valores sem fuso **em SQLite** (preexistente, fora do painel DARIUS; em PostgreSQL saiu com fuso).

### Mapa de lacunas do dashboard "Hub de agentes"
`claude/hub_gap_map.md` (Projeto "Hub de agentes"): cards, fila, aprovações e status têm dado real hoje; séries históricas, uso por cliente, recursos do sistema e tempo real (SSE) **faltam** no backend; Hermes/FlowCore sem endpoint no bridge.

### Classificação final
| Item | Estado | Observação |
|---|---|---|
| Autorização de todas as rotas admin | COMPROVADO | 71 testes + navegador/API |
| Consumidor QUEUED sem fome | COMPROVADO | testes memória+SQLite, multiprocesso |
| Scheduler/ciclo de vida (config inválida, 1x, reinício, 2 processos, kill -9) | COMPROVADO | WSL, processos reais |
| Desligamento gracioso com ACT em andamento | PARCIAL | só com scheduler; ACT em voo no servidor completo não provado |
| Métricas e modos de falha da ponte | COMPROVADO | testes + painel |
| Painel: paginação, aprovar, rejeitar, suspender, permissões, erro/recuperação | COMPROVADO (stack isolado) | seção P5 |
| Layout mobile real | COMPROVADO (sem overflow do documento) / PARCIAL (rolagem interna das tabelas) | emulação Playwright com toque |
| Timezone em PostgreSQL (3 campos) | COMPROVADO | seção própria |
| Suíte completa sem regressão vs `e64d2f7` | COMPROVADO | mesmas 3 falhas preexistentes |
| Estabilidade da suíte DARIUS em paralelo | PARCIAL | 5 suítes estouram o timeout de 10 s sob carga; sequencial 530/530 |
| Bots de mercado: build, healthcheck, boletim real somente leitura | COMPROVADO | contêiner descartável |
| Bots de mercado: entrega no Telegram, CVM real, curva DI, América Central | INCONCLUSIVO / NÃO FEITO | tokens, autorização e fonte pendentes |
| Radares antigos (causa das falhas) e Monitor SCPX | INCONCLUSIVO | |
| Conformidade de um LLM real com `DONE:`; demonstração WhatsApp real; backend de produção do WhatsApp; contrato FlowCore `/api/ask` | INCONCLUSIVO | sem medição/confirmação |
| Nenhum teste local equivale a comprovação em produção | - | Evolution, Ollama e Telegram foram simulados ou desligados |

### Riscos residuais
1. Produção não foi exercida: retry e scheduler vêm **desligados** por padrão; ligar é decisão operacional explícita com monitoramento.
2. O ACT em voo durante SIGTERM do servidor completo não foi provado; a rede de segurança é a recuperação de lease (`EFFECT_UNKNOWN` vai para conciliação humana).
3. A suíte DARIUS paralela é sensível à carga (timeouts de hook de 10 s); no CI usar paralelismo reduzido ou aumentar o `hookTimeout`.
4. Os bots de mercado dependem de fontes públicas não contratuais (Yahoo chart, AwesomeAPI, BCB); sem SLA. Um token de bot deve rodar em um só lugar (409).
5. `/api/admin/logs` sem fuso em SQLite (dev/test).
6. Três falhas de teste preexistentes do backend continuam abertas (`test_context_builder` x2, `test_groq_stt`).

### Recomendação GO/NO-GO
- **GO** para publicar as duas branches de integração (push + revisão por pull request), porque: sem regressão contra `e64d2f7`, painel e autorização comprovados em stack isolado, defeitos achados foram corrigidos com teste, e os padrões continuam desligados.
- **NO-GO** para deploy em produção e para ligar retry/scheduler/fluxo WhatsApp->DARIUS real **até** haver: demonstração com instância de teste e número controlado, medição com o modelo real do protocolo `DONE:`, decisão sobre o SIGTERM em voo, e (para os bots) tokens e uma execução real validada.
- **Aguardando autorização explícita do usuário** para qualquer push ou deploy.
