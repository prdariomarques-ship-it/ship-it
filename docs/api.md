# API do Dario OS

Referência completa e interativa: `http://localhost/docs` (Swagger) e `http://localhost/redoc` (ReDoc), gerados pelo FastAPI a partir do OpenAPI.

Todas as rotas usam o prefixo `/api` e exigem `Authorization: Bearer <access_token>`, exceto `/health*`, `/metrics`, `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh` e `/api/webhooks/whatsapp`.

## Autenticação

| Método | Rota | Descrição |
| --- | --- | --- |
| POST | `/api/auth/register` | Cria usuário (primeiro usuário vira `admin`) |
| POST | `/api/auth/login` | Retorna `access_token` + `refresh_token` |
| POST | `/api/auth/refresh` | Rotaciona o refresh token e emite novo par |
| POST | `/api/auth/logout` | Revoga o refresh token |
| GET | `/api/auth/me` | Usuário autenticado |

## IA

| Método | Rota | Descrição |
| --- | --- | --- |
| POST | `/api/chat` | Conversa com um agente (`{message, agent?, contact_id?}`); retorna `reply` + `steps` (tools executadas) |
| GET | `/api/agents` | Agentes disponíveis com suas ferramentas |
| POST | `/api/agents/{name}/run` | Executa um agente diretamente (function calling) |
| POST | `/api/memory` | Grava uma memória (embedding no Qdrant) |
| GET | `/api/memory/search?q=...&contact_id=` | Busca semântica na memória |

## WhatsApp

| Método | Rota | Descrição |
| --- | --- | --- |
| POST | `/api/webhooks/whatsapp` | Entrada de mensagens (payload de qualquer provider configurado) |
| POST | `/api/whatsapp/send-text` | Envia texto |
| POST | `/api/whatsapp/send-image` | Envia imagem (URL pública) |
| POST | `/api/whatsapp/send-file` | Envia arquivo/PDF |
| POST | `/api/whatsapp/send-audio` | Envia áudio |
| POST | `/api/whatsapp/send-location` | Envia localização |

## E-mail (Gmail)

Somente leitura (Sprint 1); `/connect`, `/status` e `/disconnect` são admin-only. Guia completo (OAuth, isolamento, setup do Google Cloud): [`docs/EMAIL.md`](EMAIL.md).

| Método | Rota | Descrição |
| --- | --- | --- |
| GET | `/api/mail/connect` | Retorna a URL de consentimento do Google (admin) |
| GET | `/api/mail/oauth/callback` | Callback do Google (chamado pelo próprio Google, autenticado via `state` assinado) |
| GET | `/api/mail/status` | Status da conexão do usuário autenticado (admin) |
| DELETE | `/api/mail/disconnect` | Remove a conta conectada (admin) |

As quatro ferramentas de leitura de e-mail (`search_emails`, `read_email_thread`, `summarize_email_thread`, `detect_pending_email_actions`) são acessadas via `/api/chat`/`/api/agents/assistant/run`, como qualquer outra tool — não têm rota HTTP própria.

## Google Calendar

Leitura e escrita (Sprint 2); `/connect`, `/status` e `/disconnect` são admin-only. Não confundir com `/api/calendar` (agenda interna do Dario OS — ver `docs/CALENDAR.md`). Guia completo: [`docs/CALENDAR.md`](CALENDAR.md).

| Método | Rota | Descrição |
| --- | --- | --- |
| GET | `/api/gcalendar/connect` | Retorna a URL de consentimento do Google (admin) |
| GET | `/api/gcalendar/oauth/callback` | Callback do Google (autenticado via `state` assinado) |
| GET | `/api/gcalendar/status` | Status da conexão do usuário autenticado (admin) |
| DELETE | `/api/gcalendar/disconnect` | Remove a conta conectada (admin) |

As seis ferramentas (`list_google_calendars`, `search_google_calendar_events`, `create_google_calendar_event`, `update_google_calendar_event`, `delete_google_calendar_event`, `check_google_calendar_availability`) são acessadas via `/api/chat`/`/api/agents/assistant/run`, como qualquer outra tool.

## Google Contacts

Leitura e escrita (Sprint 2); `/connect`, `/status` e `/disconnect` são admin-only. Não confundir com `/api/contacts` (contatos internos de WhatsApp do Dario OS — ver `docs/CONTACTS.md`). Guia completo: [`docs/CONTACTS.md`](CONTACTS.md).

| Método | Rota | Descrição |
| --- | --- | --- |
| GET | `/api/gcontacts/connect` | Retorna a URL de consentimento do Google (admin) |
| GET | `/api/gcontacts/oauth/callback` | Callback do Google (autenticado via `state` assinado) |
| GET | `/api/gcontacts/status` | Status da conexão do usuário autenticado (admin) |
| DELETE | `/api/gcontacts/disconnect` | Remove a conta conectada (admin) |

As quatro ferramentas (`search_google_contacts`, `create_google_contact`, `update_google_contact`, `delete_google_contact`) são acessadas via `/api/chat`/`/api/agents/assistant/run`, como qualquer outra tool.

## Google Drive (base de conhecimento)

Somente leitura (Sprint 3); `/connect`, `/status` e `/disconnect` são admin-only. Guia completo: [`docs/DRIVE.md`](DRIVE.md).

| Método | Rota | Descrição |
| --- | --- | --- |
| GET | `/api/gdrive/connect` | Retorna a URL de consentimento do Google (admin) |
| GET | `/api/gdrive/oauth/callback` | Callback do Google (autenticado via `state` assinado) |
| GET | `/api/gdrive/status` | Status da conexão do usuário autenticado (admin) |
| DELETE | `/api/gdrive/disconnect` | Remove a conta conectada (admin) |

As sete ferramentas (`list_google_drive_files`, `search_google_drive_files`, `read_google_drive_file`, `index_google_drive_file`, `index_google_drive_folder`, `summarize_google_drive_document`, `update_google_drive_index`) são acessadas via `/api/chat`/`/api/agents/assistant/run`. Perguntas sobre o conteúdo já indexado ("qual documento fala sobre X") usam a ferramenta `search_memory` já existente — não têm rota própria, ver `docs/DRIVE.md`.

## Automação e jobs

| Método | Rota | Descrição |
| --- | --- | --- |
| POST | `/api/workflows/{name}/trigger` | Dispara um workflow do n8n |
| GET | `/api/jobs` | Lista jobs da fila (admin; filtro `?status=`) |
| POST | `/api/jobs` | Enfileira job (`{name, payload, delay_seconds, max_attempts}`) (admin) |
| POST | `/api/jobs/{id}/cancel` | Cancela job pendente (admin) |
| GET | `/api/jobs/handlers` | Handlers registrados (admin) |

## Recursos (CRUD)

Todos seguem o mesmo padrão: `GET` (lista, com `limit`/`offset`), `GET /count`, `POST`, `GET /{id}`, `PATCH /{id}`, `DELETE /{id}`.

| Recurso | Rota base | Escopo |
| --- | --- | --- |
| Contatos | `/api/contacts` | global |
| Tarefas | `/api/tasks` | por usuário |
| Agenda | `/api/calendar` | por usuário |
| Notas | `/api/notes` | por usuário |
| Igreja (membros) | `/api/church/members` | global |
| Loja (clientes) | `/api/store/customers` | global |

Somente leitura:

| Recurso | Rota | Acesso |
| --- | --- | --- |
| Mensagens | `/api/messages?contact_id=` | autenticado |
| Logs | `/api/logs?source=&level=` | admin |
| Dashboard | `/api/dashboard/summary` | autenticado (cache 30s) |

## Observabilidade

| Rota | Descrição |
| --- | --- |
| `/health`, `/health/live` | Liveness |
| `/health/ready` | Readiness (Postgres obrigatório; Redis/Qdrant degradam) |
| `/metrics` | Métricas Prometheus |
