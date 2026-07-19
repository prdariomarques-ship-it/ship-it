# Postmortem — Fechamento da Release 1.3.1

**Período coberto:** 2026-07-18 a 2026-07-19
**Preparado em:** 2026-07-19, no fechamento formal da release

Este documento cobre o ciclo de trabalho que começou com a homologação
funcional de 18/07 e terminou com o fechamento formal da v1.3.1 em 19/07 —
incluindo dois achados P0 de um audit de produção, sua correção completa, e
o encerramento de duas lacunas operacionais (credenciais padrão fracas em
Grafana e Postgres).

## Timeline

| Data/Hora | Commit/Ação | O quê |
|---|---|---|
| 2026-07-18 12:01 | `8493a96` | `VERSION.json` atualizado pro commit deployado |
| 2026-07-18 12:29 | `5bdb6a7` | v1.3.0 GA + patch v1.3.1 registrados em `VERSION_HISTORY.md` |
| 2026-07-18 12:33 | `de2d393` | Entradas de v1.3.0/v1.3.1 adicionadas ao `CHANGELOG.md` |
| 2026-07-18 12:40 | `56900b5` | Resumo final da release v1.3.1 documentado |
| 2026-07-18 13:32 | `fa7c8ff` | **Incidente corrigido**: `OpenWAProvider.health_check()` tratava erro da API como saudável |
| 2026-07-18 15:15 | `9816877` | **Incidente corrigido**: `send_text`/`send_image`/etc. reportavam sucesso mesmo com envio rejeitado pelo OpenWA (Issue #3) |
| 2026-07-18 16:54–18:44 | `522b742`, `24f30cd`, `1995530` | Achados P2/P3 da homologação funcional corrigidos (UX do dashboard admin) |
| 2026-07-19 01:51 | `8ed3b52` | Fechamento do ciclo de homologação: retry/backoff Google, troca de senha autenticada, backup+Qdrant, criação de item pela UI em 5 módulos |
| 2026-07-19 01:53 | `dae6e1b` | Números de cobertura de teste do frontend atualizados no relatório de prontidão |
| 2026-07-19 12:22 | `1fdf5bb` | Watchdog de verificação de backup implementado (timer + service systemd) |
| 2026-07-19 13:18 | `6b773c0` | **P0-1 corrigido**: registro público fechado após o bootstrap; endpoint admin-only de criação de usuário |
| 2026-07-19 14:17 | `8ff38bf` | **P0-2 corrigido**: timeout global por job, fecha a corrida de execução duplicada |
| 2026-07-19 16:25 | `2a9d643` | CI restaurado (erro de mypy em `google_http.py`) + gap de credencial padrão do Grafana fechado no `docker-compose.yml` |
| 2026-07-19 ~16:37 | operacional (sem commit) | Senha do admin do Grafana rotacionada ao vivo (`grafana cli admin reset-admin-password`), zero downtime |
| 2026-07-19 ~16:38–16:41 | operacional (sem commit) | Senha do Postgres rotacionada (`ALTER USER` + `.env` + restart do backend), ~31–95s de downtime do backend |
| 2026-07-19 (agora) | — | Audit final de produção, fechamento formal da v1.3.1 |

## Correções principais

1. **Registro público fechado após o bootstrap** (P0) — qualquer pessoa
   podia se auto-registrar e ganhar acesso de leitura a todo o histórico de
   mensagens do WhatsApp e escrita em contatos/membros da igreja/clientes da
   loja.
2. **Timeout global de execução de job** (P0) — corrida que permitia um job
   travado/lento (>5min) ser reclamado pela recuperação de jobs "presos" e
   executado duas vezes concorrentemente.
3. **`OpenWAProvider.health_check()` e `send_*`** (incidentes de produção,
   18/07) — dois bugs reais de confiabilidade no provider WhatsApp.
4. **CI restaurado** — erro de mypy em `google_http.py` (presente desde
   `8ed3b52`) fazia o step de type-check falhar em todo commit desde então;
   corrigido, e revelou um bug latente real (`raise None` se
   `max_attempts <= 0`).
5. **Credenciais padrão fracas eliminadas** — Grafana (`admin`/`admin`
   nunca trocado desde 15/07) e Postgres (`change-me` nunca trocado desde
   10/07, a senha real usada em produção o tempo todo) — ambas rotacionadas
   com procedimento seguro e verificado.
6. **Backup automatizado + watchdog de verificação** — antes só existia um
   script manual sem agendamento real; agora `systemd --user` timers
   (03:00 backup, 03:15 verificação) cobrindo Postgres e Qdrant, com
   relatório PASS/FAIL e alerta Telegram opcional.

## Incidentes de produção corrigidos

- `health_check()` tratando erro de API do OpenWA como "saudável" — mascarava
  uma falha real de conexão.
- `send_text`/`send_image`/`send_file`/`send_audio`/`send_location`
  reportando `{"status": "sent"}` para envios que o OpenWA rejeitou de fato
  (confirmado ao vivo contra um número que não é contato) — mensagem nunca
  chegava, mas o sistema achava que sim.
- CI silenciosamente vermelho desde `8ed3b52` (~15h antes de ser notado e
  corrigido) — nenhum teste real estava quebrado, só o step de mypy.

## Melhorias de segurança

- Registro público fechado após o bootstrap (P0-1).
- Endpoint admin-only de criação de usuário, com testes de regressão
  cobrindo: bootstrap permitido, segundo registro público negado, criação
  por admin bem-sucedida, criação por não-admin negada.
- `GF_SECURITY_ADMIN_PASSWORD` não tem mais fallback silencioso pra `admin`.
- Senha do Postgres rotacionada da credencial real usada desde a
  inicialização (`change-me`) pra um valor forte gerado
  (`openssl rand -hex 16`).
- Webhook do WhatsApp (`/api/webhooks/whatsapp`) auditado ao vivo: confirmado
  que rejeita requisição sem `WEBHOOK_SECRET` válido (401), tanto por design
  quanto por comportamento observado.

## Melhorias de infraestrutura

- `docker-compose.yml`: `GF_SECURITY_ADMIN_PASSWORD` agora obrigatório
  (`:?`), mesmo padrão de `JWT_SECRET`/`WEBHOOK_SECRET`.
- Timer systemd de backup + timer de verificação, ambos com
  `Restart=on-failure` limitado e `TimeoutStartSec`.
- `providers/google_http.py`: bug de `raise None` corrigido, com teste de
  regressão.

## Melhorias de autenticação

- `POST /auth/register`: bootstrap-only, retorna 403 depois da primeira conta.
- `POST /admin/users`: novo endpoint, herda `require_admin` do router.
- `AuthError` ganhou o flag `forbidden`, mapeado pra 403 no router.

## Melhorias de backup

- `scripts/backup.sh`: agora cobre Qdrant (snapshot por coleção), além do
  Postgres já coberto.
- `scripts/verify-backup.sh` (novo): 8 checagens (timer disparou, serviço
  concluiu, sem falha persistente, sem erro no journal, arquivos existem e
  são de hoje, não vazios, integridade `gunzip -t`/`tar -tf`), relatório
  com timestamp, alerta Telegram opcional.
- `scripts/tests/test_verify_backup.sh`: 7 cenários rodando o script real
  contra `systemctl`/`journalctl` simulados.
- Pré-requisito de *lingering* do `systemd --user` no WSL documentado em
  `BACKUP.md` — causa raiz de por que o timer original não estava
  realmente rodando havia meses.

## Resumo de testes

- Backend: **890 testes**, 0 falhas (era 864 no início deste ciclo).
- Frontend: **268 testes**, 0 falhas (era 241).
- `ruff check .`: limpo.
- `mypy` (repositório inteiro, 293 arquivos): limpo — restaurado nesta sessão.
- Suite de testes do watchdog de backup: 7 cenários, execução real contra
  `systemctl`/`journalctl` simulados.

## Problemas remanescentes conhecidos

Ver `TECHNICAL_DEBT.md` (atualizado nesta release) para a lista completa
classificada. Destaques:

- **P1**: `docker-compose.yml` ainda tem `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-dario}`
  — mesmo padrão de fallback fraco que acabou de ser corrigido no Grafana,
  ainda não aplicado ao Postgres no nível do compose file (o valor real em
  `.env` já foi rotacionado, mas o compose file em si não falha-fechado).
- **P1**: `chat_router`/`workflows_router` sem nenhuma cobertura de teste.
- **P1**: Caddy não roteia `/health/ready` — ver
  `docs/issues/caddy-health-ready-routing.md`, alvo v1.4.
- Restante: ver classificação completa em `TECHNICAL_DEBT.md`.

## Lições aprendidas

1. **"Testes passando" ≠ "CI verde"** — CI ficou silenciosamente vermelho
   por ~15h porque as verificações locais de mypy neste ciclo eram
   escopadas aos arquivos alterados, não ao repositório inteiro (que é o
   escopo real do CI). Lição: rodar mypy sem escopo pelo menos uma vez
   antes de qualquer fechamento de release.
2. **Fallback silencioso de credencial é uma classe de bug, não um caso
   isolado** — o mesmo padrão (`${VAR:-valor-fraco}`) apareceu em Grafana E
   em Postgres. Corrigir um não corrige o outro; vale uma varredura
   dedicada por todo `docker-compose.yml` procurando esse padrão
   especificamente.
3. **"Restart" nem sempre significa "aplicar a mudança"** — tanto Grafana
   quanto Postgres só aplicam sua variável de senha na inicialização de um
   volume vazio; um container recriado com volume existente ignora a
   variável para fins de autenticação. A correção real exige a ferramenta
   própria de cada sistema (`grafana cli admin reset-admin-password`,
   `ALTER USER`), não só editar `.env` e reiniciar.
4. **`docker compose up -d <serviço>` recria dependências cujo config
   mudou, não só o serviço nomeado** — rotacionar a senha do Postgres via
   `.env` fez o Compose recriar o container do Postgres também, não só o
   backend, porque a variável afeta o `environment:` de ambos os serviços.
5. **Achados de um audit anterior podem estar desatualizados sem que
   ninguém tenha mentido** — o `SECURITY_AUDIT.md` original checou "toda
   rota exige autenticação" e concluiu correto; nunca checou "autenticação
   aberta a qualquer um realmente protege alguma coisa dado que os dados
   não são escopados por usuário". A pergunta certa importa mais que a
   resposta certa pra pergunta errada.
