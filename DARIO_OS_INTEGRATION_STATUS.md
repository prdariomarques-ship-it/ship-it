# DARIO OS x DARIUS OSS - Estado da missão de integração

Atualizado: 2026-10-19 | Status: **CONCLUSÃO PARCIAL (Fase 0 concluída; nenhuma implementação ainda)**
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

## 7. Próxima ação concreta

Criar branch no repo DARIUS a partir de `8f860d1` e implementar `POST /api/tasks/:id/approve|reject|cancel` e `GET /api/tasks/:id/result` com autorização por dono, 404 uniforme e testes HTTP.

## 8. Log

- 2026-10-19: Fase 0 concluída (somente leitura). Único artefato criado neste repo: este arquivo.
