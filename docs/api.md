# API do Dario OS

Referência completa e interativa: `http://localhost/docs` (OpenAPI/Swagger gerado pelo FastAPI).

Todas as rotas usam o prefixo `/api` e exigem `Authorization: Bearer <token>`, exceto `/health`, `/api/auth/register`, `/api/auth/login` e `/api/webhooks/whatsapp`.

## Autenticação

| Método | Rota | Descrição |
| --- | --- | --- |
| POST | `/api/auth/register` | Cria usuário (email, full_name, password) |
| POST | `/api/auth/login` | Retorna `access_token` JWT |
| GET | `/api/auth/me` | Usuário autenticado |

## IA

| Método | Rota | Descrição |
| --- | --- | --- |
| POST | `/api/chat` | Conversa com um agente (`{message, agent, contact_id?}`), com memória |
| GET | `/api/agents` | Lista os agentes disponíveis |
| POST | `/api/agents/{name}/run` | Executa um agente diretamente |
| POST | `/api/memory` | Grava uma memória (embedding no Qdrant) |
| GET | `/api/memory/search?q=...` | Busca semântica na memória |

## WhatsApp

| Método | Rota | Descrição |
| --- | --- | --- |
| POST | `/api/webhooks/whatsapp` | Entrada de mensagens (chamado pelo OpenWA) |
| POST | `/api/whatsapp/send-text` | Envia texto |
| POST | `/api/whatsapp/send-image` | Envia imagem (URL pública) |
| POST | `/api/whatsapp/send-file` | Envia arquivo/PDF |
| POST | `/api/whatsapp/send-audio` | Envia áudio |
| POST | `/api/whatsapp/send-location` | Envia localização |

## Automação

| Método | Rota | Descrição |
| --- | --- | --- |
| POST | `/api/workflows/{name}/trigger` | Dispara um workflow do n8n via webhook |

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

| Recurso | Rota |
| --- | --- |
| Mensagens | `/api/messages?contact_id=` |
| Logs | `/api/logs?source=&level=` |
| Dashboard | `/api/dashboard/summary` |
