# Segurança — Dario OS

Este documento descreve o modelo de segurança do Dario OS: o que já está implementado, onde os controles vivem no código, e como reportar um problema. É a referência central citada por `docs/EMAIL.md`, `PRODUCTION_APPROVAL.md` e `PRODUCTION_BLOCKERS_RESOLVED.md` — em caso de divergência sobre um controle específico, aqueles documentos têm o histórico da decisão; este aqui é o estado atual consolidado.

## Reportando uma vulnerabilidade

Dario OS é, hoje, um sistema de instância única operado pelo próprio fundador — não há um programa público de bug bounty. Se você encontrar um problema de segurança, descreva-o diretamente para o mantenedor do repositório em vez de abrir uma issue pública, para dar tempo de corrigir antes de qualquer divulgação.

## Princípio central: autorização em código, nunca só no prompt

A regra mais importante deste sistema, aplicada consistentemente em todo domínio que envolve dados de terceiros ou ações externas: **uma decisão de autorização nunca depende apenas da instrução dada ao modelo de linguagem.** O LLM escolhe *o quê* fazer; o código decide, de forma determinística, se aquilo é permitido — usando estado que a aplicação controla (`ToolContext`), nunca um argumento que o próprio modelo forneceu.

Dois casos concretos, resolvidos com o mesmo princípio:

- **WhatsApp (PROD-005)** — `send_whatsapp_message` e `find_contact` (`agents/tools/communication.py`) só podem agir sobre o contato ao qual a conversa atual está associada (`ToolContext.contact_id`, definido por `BaseAgent.run` a partir de estado da aplicação). Um argumento `to`/`query` apontando para outro contato é recusado antes de qualquer enfileiramento ou consulta — ver `tests/test_tool_isolation.py` (10 testes, incluindo tentativas de burlar o isolamento via formatação de telefone).
- **E-mail / Gmail (Sprint 1)** — `_get_access_token` (`agents/tools/mail.py`) resolve o mailbox estritamente a partir de `ToolContext.user.id`. Nenhuma das quatro tools de e-mail tem um parâmetro de usuário/mailbox no schema — não existe argumento que um modelo manipulado possa fornecer para alcançar a caixa de entrada de outra pessoa. Ver `docs/EMAIL.md#segurança-e-isolamento-mesmos-princípios-do-prod-005` e `tests/test_mail_tools.py`.

Ao adicionar um novo domínio que acesse dados de um usuário/contato específico, siga o mesmo padrão: um único ponto de resolução de identidade, alimentado só por `ToolContext`, nunca por um argumento do modelo.

## Autenticação e autorização

- **JWT de acesso** de vida curta (30 min por padrão) + **refresh token rotativo** (30 dias), armazenado como hash SHA-256 — o valor em texto puro nunca é persistido. Rotação revoga o token anterior; reuso de um refresh token já revogado é rejeitado (mitiga replay). Tokens expirados são purgados a cada novo login.
- **RBAC** com dois papéis, `admin`/`user`. O primeiro usuário registrado na instância vira `admin` automaticamente (`auth/service.py`); os demais nascem `user`. Rotas administrativas (`/api/logs`, `/api/jobs`, `/api/mail/*`) usam `require_roles(...)`/`require_admin`.
- **Senhas**: PBKDF2-SHA256 salteado, hash/verificação executados fora do event loop (`asyncio.to_thread`) para não bloquear a aplicação, e em tempo constante.

## Produção: boot fail-closed

`main.py::_validate_production_settings` recusa subir em produção (`ENVIRONMENT=production`) sem segredos fortes configurados — a aplicação não inicia em um estado inseguro por omissão:

| Variável | Exigência em produção | Por quê |
| --- | --- | --- |
| `JWT_SECRET` | ≥ 32 caracteres, diferente do valor padrão de desenvolvimento | Assina todo token de acesso e refresh |
| `WEBHOOK_SECRET` | ≥ 32 caracteres | Único mecanismo de autenticação que a maioria dos gateways de WhatsApp oferece (OpenWA/Baileys/Evolution não têm assinatura própria) — sem ele, `/api/webhooks/whatsapp` fica aberto a requisições não autenticadas capazes de disparar todo o Cognitive Pipeline |

Gerar valores fortes: `openssl rand -hex 32`. Em desenvolvimento (`ENVIRONMENT=development`), os valores padrão continuam funcionando sem bloquear o boot — a checagem é específica de produção.

`EMAIL_TOKEN_ENCRYPTION_KEY` (Gmail) **não** passa por essa validação de boot: o domínio de e-mail é opcional por instância, então sua ausência não impede o sistema de subir — apenas mantém `/api/mail/connect` indisponível (`503`) até ser configurada. Ver `docs/EMAIL.md#variáveis-de-ambiente`.

## Webhooks

- **Segredo compartilhado** (`WEBHOOK_SECRET`): quando definido, toda entrada em `/api/webhooks/whatsapp` exige o header `X-Webhook-Token` com o mesmo valor.
- **Assinatura real por provider**: `WhatsAppProvider.verify_signature(raw_body, headers)` permite que cada gateway valide seu próprio esquema. `OfficialProvider` (WhatsApp Cloud API) implementa HMAC-SHA256 real via `X-Hub-Signature-256` (`OFFICIAL_APP_SECRET`) — verificação criptográfica, não apenas um segredo compartilhado.
- **Deduplicação**: mensagens são identificadas por `external_id` antes de processar; uma constraint única no banco cobre a corrida entre requisições concorrentes (mesma redelivery processada duas vezes em paralelo).
- **Saída HTML sempre escapada em rotas que aceitam entrada não autenticada**: `mail/router.py::/oauth/callback` é chamado diretamente pelo Google (sem Bearer possível) e devolve uma página HTML de resultado — o parâmetro `error` da query string (não autenticado, controlável por qualquer um que monte a URL) é sempre passado por `html.escape` antes de entrar na resposta (`_result_page`), fechando um XSS refletido encontrado e corrigido na auditoria da Sprint 1.1 (`tests/test_mail_router.py::test_callback_escapes_the_error_param_against_reflected_xss`). Regra geral: qualquer rota que renderiza HTML a partir de um valor não autenticado escapa a saída, nunca confia no formato do valor de entrada.

## Credenciais de terceiros em repouso

Nenhuma credencial de longa duração de um serviço externo é persistida em texto puro. Hoje isso se aplica ao refresh token OAuth do Gmail:

- Cifrado com **Fernet** (AES-128-CBC + HMAC autenticado, biblioteca `cryptography`) usando `EMAIL_TOKEN_ENCRYPTION_KEY` — uma chave que só existe em configuração, nunca no banco.
- Sem a chave configurada (ou com uma chave inválida/trocada), `encrypt_token`/`decrypt_token` recusam operar (`TokenEncryptionNotConfigured`) em vez de cair para um caminho inseguro ou corromper silenciosamente um valor já cifrado.
- Escopo mínimo solicitado ao provedor: só `gmail.readonly` — mesmo um bug futuro na aplicação não teria como usar esse token para enviar ou apagar e-mail, porque o Google nunca concedeu essa permissão.
- Ver `services/token_crypto.py` e `docs/EMAIL.md` para o fluxo completo.

## Rate limiting e proteção contra loop/flood

- Rate limit por IP (Redis, com fallback em memória se o Redis não estiver disponível); probes de `/health*` e `/metrics` ficam isentos para não cegar o monitoramento.
- Freio específico de auto-reply: no máximo `AUTO_REPLY_MAX_PER_CONTACT_PER_MINUTE` respostas automáticas por contato por minuto, reaproveitando o mesmo `RateLimiter` (sem lógica de limite duplicada).
- Retry com backoff exponencial em toda chamada HTTP de um provider ao seu gateway (`WHATSAPP_REQUEST_MAX_ATTEMPTS`/`WHATSAPP_REQUEST_BACKOFF_SECONDS`), evitando que uma falha transitória vire uma tempestade de requisições.

## Rede e transporte

- HTTPS automático (Let's Encrypt) via Caddy quando a instância é servida por um domínio real; headers de segurança padrão do Caddy.
- CORS restrito à lista configurada em `CORS_ORIGINS` — sem wildcard por padrão.

## Auditoria e observabilidade de segurança

- Toda execução de agente publica eventos (`agent.selected`, `agent.replied`, `agent.failed`) no Event Bus e fica registrada com métricas Prometheus (`darioos_agent_runs_total{agent,provider,status}`).
- Toda chamada de ferramenta vira um `ExecutedStep` auditável (`tool`, `arguments`, `result`, `status`, `duration_ms`), visível na resposta da API — inclusive as negações de autorização (`status="error"`, `result` contém o motivo).
- Tabela `logs` persiste eventos de webhook e de fila de jobs, mesmo sem nenhum assinante ativo no Event Bus no momento.

## Backups e segredos operacionais

Ver `BACKUP.md`/`RESTORE.md` para a rotina de backup do Postgres e do Qdrant, e `OPERATIONS.md`/`RUNBOOK.md` para procedimentos operacionais gerais. Segredos (`JWT_SECRET`, `WEBHOOK_SECRET`, `EMAIL_TOKEN_ENCRYPTION_KEY`, chaves de API de LLM/WhatsApp) vivem exclusivamente em `docker/.env` (fora do controle de versão — ver `.gitignore`) ou no ambiente do processo; nenhum deles é gravado em log, commit ou documentação.

## Checklist de segurança para produção

- [ ] `JWT_SECRET` forte e único (`openssl rand -hex 32`)
- [ ] `WEBHOOK_SECRET` forte e único, mesmo valor configurado no gateway de WhatsApp/n8n
- [ ] `OFFICIAL_APP_SECRET` configurado, se usando o provider `official` (WhatsApp Cloud API)
- [ ] `EMAIL_TOKEN_ENCRYPTION_KEY` gerada e preservada, se usando a integração de Gmail — trocá-la invalida todos os refresh tokens já armazenados
- [ ] `CORS_ORIGINS` restrito aos domínios reais do frontend
- [ ] Domínio real configurado no Caddy para HTTPS automático (não usar `localhost` em produção)
- [ ] Backup diário agendado (`scripts/backup.sh` no cron)
- [ ] `ENVIRONMENT=production` definido — ativa a validação fail-closed de segredos descrita acima

Ver `PRODUCTION_APPROVAL.md` para o histórico completo da auditoria de release que originou este checklist.
