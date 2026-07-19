# Dario OS v1.3.1 — Notas de Release

**Data:** 2026-07-19

## Novidades

- **Watchdog de verificação de backup.** Além do backup diário já
  automatizado (03:00), um segundo timer (03:15) confirma que ele
  realmente rodou e produziu arquivos válidos — 8 checagens, relatório com
  timestamp, alerta Telegram opcional em caso de falha. Ver `BACKUP.md`.
- **Endpoint admin-only de criação de usuário** (`POST /admin/users`) —
  única forma de adicionar contas depois da conta de bootstrap.
- **Retry/backoff para os providers Google** (Gmail, Calendar, Contacts,
  Drive) — mesmo padrão já usado pelo WhatsApp, respeita o header
  `Retry-After` quando o Google o envia.
- **Backup do Qdrant.** `scripts/backup.sh` agora cobre a memória semântica
  além do Postgres.

## Correções de bugs

- `OpenWAProvider.health_check()` não trata mais erro de API como saudável.
- `send_text`/`send_image`/`send_file`/`send_audio`/`send_location` não
  reportam mais sucesso quando o OpenWA rejeita o envio (Issue #3).
- `validate_phone_e164` aceita telefone com ou sem `+` (convenção real do
  WhatsApp); validação de e-mail/telefone conectada em contatos/membros/clientes.
- Estatística de memória do Qdrant (`/admin/memory`) corrigida — mostrava
  "0 vetores" mesmo com dados reais.
- Labels do Analytics traduzidas.
- `/logs` redireciona pra `/admin/logs` (que tem filtro/busca/exportar).
- `providers/google_http.py`: corrigido um `raise` de exceção `None` que
  ocorreria se `max_attempts` fosse configurado como `<= 0`.

## Melhorias de segurança

- **Registro público fechado após a conta de bootstrap** — antes, qualquer
  pessoa podia se auto-registrar e ganhar acesso de leitura a todo o
  histórico de mensagens do WhatsApp e escrita em contatos/membros da
  igreja/clientes da loja. Agora só o admin cria novas contas.
- **Timeout global de execução de job** — fecha uma corrida onde um job
  lento (>5min) podia ser executado duas vezes concorrentemente pela
  recuperação de jobs "presos" (risco: resposta duplicada ao cliente no
  WhatsApp, efeitos colaterais duplicados, cobrança duplicada de LLM).
- **Credencial padrão do Grafana eliminada** — `admin`/`admin` (nunca
  trocado desde a instalação) substituído por um valor forte gerado; sem
  fallback silencioso possível daqui pra frente.
- **Senha do Postgres rotacionada** — de `change-me` (a senha real usada em
  produção desde a instalação) pra um valor forte gerado.
- Troca de senha autenticada (`POST /auth/change-password`) — revoga todas
  as outras sessões ativas ao trocar.

## Melhorias operacionais

- Backup diário automatizado via `systemd --user` timer (antes: script
  manual sem agendamento real registrado em lugar nenhum).
- Pré-requisito de *lingering* do `systemd --user` no WSL documentado —
  causa raiz de por que o timer original não estava de fato rodando.
- CI restaurado (estava vermelho no step de type-check desde um commit
  anterior nesta mesma sprint).

## Breaking changes

- **`POST /auth/register` agora rejeita qualquer tentativa depois da
  primeira conta** (`403 Forbidden`, "Public registration is closed"). Se
  algum fluxo externo dependia de auto-registro para múltiplos usuários,
  ele vai quebrar — use `POST /admin/users` (autenticado como admin) no lugar.
- **`GF_SECURITY_ADMIN_PASSWORD` é obrigatório** no `docker/.env` — o
  Grafana não sobe mais sem ele (antes, tinha fallback silencioso pra `admin`).

## Notas de migração

- Se você tem um script/automação que chamava `POST /auth/register` para
  criar contas além da primeira, migre para `POST /admin/users` com um
  token de admin válido.
- Confirme que `docker/.env` tem `GF_SECURITY_ADMIN_PASSWORD` definido
  antes do próximo `docker compose up` — sem ele, o Grafana não inicia.
- Se você ainda usa a senha padrão do Grafana (`admin`) ou a senha original
  do Postgres (`change-me`) em qualquer ambiente que não seja este, rotacione
  seguindo o procedimento em `RELEASE_1_3_1_POSTMORTEM.md` (`ALTER USER` +
  `.env` + restart do backend, ou `grafana cli admin reset-admin-password`
  pro Grafana) — não edite `.env` sozinho sem rodar o comando de rotação
  primeiro, ou a credencial real fica dessincronizada da documentada.
- Sem migração de banco de dados nesta release.

## Problemas conhecidos

- **Caddy não roteia `/health/ready`** corretamente (cai no 404 do
  frontend) — ver `docs/issues/caddy-health-ready-routing.md`. Alvo: v1.4.
- `docker-compose.yml` ainda tem um fallback fraco (`:-dario`) pra
  `POSTGRES_PASSWORD` no nível do compose file, mesmo padrão já corrigido
  no Grafana. O valor real em produção já foi rotacionado; o compose file
  em si ainda não falha-fechado. Ver `TECHNICAL_DEBT.md`.
- `chat_router`/`workflows_router` sem cobertura de teste.
- Ver `TECHNICAL_DEBT.md` para a lista completa de itens não-bloqueantes.
