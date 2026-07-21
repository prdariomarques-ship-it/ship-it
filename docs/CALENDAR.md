# Google Calendar — Sprint 2

Domínio novo, isolado do resto do Dario OS: leitura e escrita no Google Calendar. Mesmo padrão arquitetural do domínio de e-mail (`docs/EMAIL.md`) — Strategy + Factory, OAuth com `state` assinado, criptografia de token em repouso, isolamento por usuário resolvido só em código, gateway único (`assistant`).

## Escopo

| Funcionalidade | Sprint 2 |
| --- | --- |
| Listar agendas (calendários) | ✅ |
| Listar/buscar eventos por período e palavra-chave (cobre "hoje", "amanhã", "esta semana", "próximos compromissos" via `since`/`until`) | ✅ |
| Criar evento | ✅ |
| Editar evento | ✅ |
| Excluir evento | ✅ |
| Criar evento recorrente (RRULE) | ✅ |
| Editar/excluir uma série recorrente inteira (`scope="all_events"`), não só a ocorrência | ✅ |
| Verificar conflitos / consultar disponibilidade | ✅ (uma única pergunta: o que está ocupado nesse período) |

## Não confundir com o calendário interno do Dario OS

Dario OS já tinha, desde antes desta sprint, um calendário **próprio e interno** — `models.calendar.CalendarEvent`, as tools `create_calendar_event`/`list_calendar_events` (`agents/tools/productivity.py`), a rota `/api/calendar` (CRUD genérico). Essa é a agenda de tarefas/lembretes do próprio sistema, sem nenhuma dependência do Google.

Esta sprint adiciona um domínio **completamente separado**: o **Google Calendar real** do usuário, acessado via OAuth. Por isso:

- Modelos, tools, rotas e pacotes usam o prefixo `gcalendar`/`google_calendar`/`Google Calendar` em vez de `calendar`, evitando qualquer colisão de nome com o domínio interno já existente.
- As tools se chamam `list_google_calendars`, `search_google_calendar_events`, etc. — nunca `list_calendar_events`/`create_calendar_event` (esses nomes já pertencem ao calendário interno e continuam funcionando exatamente como antes, sem nenhuma mudança).
- A rota é `/api/gcalendar/*`, não `/api/calendar/*` (que já existe e continua servindo o CRUD interno).
- Os dois domínios nunca compartilham dados: o agente pode ter uma tarefa interna E um evento no Google Calendar sobre o mesmo assunto, mas são registros independentes.

## Gateway único: o agente `assistant`

Mesmo princípio do domínio de e-mail: **somente o agente `assistant` tem acesso direto às ferramentas de Google Calendar.** Nenhum outro agente (`personal`, `church`, `store`, `content`) importa ou lista uma tool de calendário. Se um agente especializado precisar de algo do Google Calendar, a etapa correspondente do plano do Cognitive Planner é roteada para `assistant` — nenhum canal novo de comunicação entre agentes foi criado.

## Arquitetura

```
providers/calendar/
  base.py             CalendarProvider (Strategy) — authorization_url, exchange_code,
                       refresh_access_token, list_calendars, search_events, create_event,
                       update_event, delete_event, check_availability
                       + CalendarInfo, CalendarEvent, EventSearchQuery, NewEvent,
                         EventUpdate, AvailabilityResult, OAuthTokens
  factory.py           get_calendar_provider() — seleciona por CALENDAR_PROVIDER (hoje só "google")
  google/provider.py   GoogleCalendarProvider — REST via httpx puro (mesma escolha do Gmail)

gcalendar/
  router.py            /api/gcalendar/connect, /oauth/callback, /status, /disconnect
  schemas.py           GCalendarConnectResponse, GCalendarStatusResponse

models/gcalendar_account.py       GoogleCalendarAccount — um Google Calendar autorizado por (user, provider)
repositories/gcalendar_account.py GoogleCalendarAccountRepository — get_by_user, upsert_for_user
                                   (recuperação de corrida de concorrência — mesmo idiom de
                                   EmailAccountRepository/ContactRepository)

agents/tools/gcalendar.py          as 6 tools — registradas só em assistant_agent.py
```

`CalendarEvent` em `providers/calendar/base.py` é deliberadamente um nome diferente de `models.calendar.CalendarEvent` (o calendário interno) — ver seção acima.

### Consolidação de ferramentas (por quê 6, não 12)

O escopo pedido lista 12 capacidades (listar agendas, listar eventos, buscar eventos, criar, editar, excluir, verificar conflitos, consultar disponibilidade, próximos compromissos, agenda de hoje, agenda de amanhã, agenda da semana). Seguindo o mesmo padrão já estabelecido pelo `search_emails` do Gmail (uma tool com parâmetros em vez de uma tool por variação), a Sprint 2 implementa **6 tools**, cada uma cobrindo várias dessas capacidades por parametrização:

| Tool | Cobre |
| --- | --- |
| `list_google_calendars` | listar agendas |
| `search_google_calendar_events` | listar eventos, buscar eventos, próximos compromissos, agenda de hoje/amanhã/semana (via `since`/`until`) |
| `create_google_calendar_event` | criar evento |
| `update_google_calendar_event` | editar evento |
| `delete_google_calendar_event` | excluir evento |
| `check_google_calendar_availability` | verificar conflitos **e** consultar disponibilidade (a mesma pergunta: o que está ocupado nesse período) |

"Hoje"/"amanhã"/"esta semana"/"próximos compromissos" não são tools separadas — o agente calcula o intervalo de datas ISO correspondente (instrução no `description` da tool) e chama `search_google_calendar_events` com `since`/`until`, exatamente como o Gmail já faz para buscar e-mails por período.

## Fluxo de autorização (OAuth 2.0)

Idêntico ao fluxo do Gmail (ver `docs/EMAIL.md#fluxo-de-autorização-oauth-20-authorization-code`), com duas diferenças:

- Escopo solicitado: `https://www.googleapis.com/auth/calendar` (leitura **e** escrita — a Sprint 2 pede explicitamente criar/editar/excluir, diferente do Gmail que é somente leitura).
- `state` assinado com propósito próprio (`gcalendar_oauth_state`), diferente do propósito do Gmail (`gmail_oauth_state`) — um token de state de um domínio nunca é aceito pelo callback de outro, mesmo reutilizando o mesmo `auth/jwt.py::create_oauth_state_token`/`decode_oauth_state_token`.

**Reaproveita o mesmo app OAuth do Google Cloud já criado para o Gmail** — não é necessário criar um novo projeto: basta adicionar mais uma URI de redirecionamento e mais um escopo na mesma tela de consentimento. Ver passo a passo abaixo.

## Segurança e isolamento

Mesmos princípios do PROD-005 e do domínio de e-mail (ver `SECURITY.md`):

- `_get_access_token(context)` (`agents/tools/gcalendar.py`) resolve a conta de calendário estritamente a partir de `ToolContext.user.id`. Nenhuma das seis tools tem um parâmetro de usuário/conta no schema.
- Refresh token cifrado em repouso (Fernet, `EMAIL_TOKEN_ENCRYPTION_KEY` — mesma chave usada para Gmail, mesma categoria de segredo).
- Testes de isolamento entre usuários (`backend/tests/test_gcalendar_tools.py`) provam na prática que dois usuários conectados a calendários diferentes nunca se cruzam, inclusive quando o modelo tenta apontar um `event_id` de um usuário para a chamada de outro (a Google Calendar API já escopa eventos pelo access_token).
- Refresh token revogado/expirado vira o mesmo erro acionável de "não conectado", nunca um erro cru do provedor.

## Ferramentas (catálogo)

| Tool | Parâmetros principais | Descrição |
| --- | --- | --- |
| `list_google_calendars` | — | Lista as agendas do Google Calendar conectado |
| `search_google_calendar_events` | `calendar_id?, query?, since?, until?, limit?` | Busca/lista eventos por período e/ou palavra-chave |
| `create_google_calendar_event` | `summary, start, end, calendar_id?, description?, location?, attendees?, recurrence?` | Cria um evento; `recurrence` (lista de linhas RRULE) cria uma série recorrente |
| `update_google_calendar_event` | `event_id, calendar_id?, ...campos opcionais, recurrence?, scope?` | Edita um evento (só os campos informados mudam); `scope="all_events"` edita a série inteira em vez de só a ocorrência |
| `delete_google_calendar_event` | `event_id, calendar_id?, scope?` | Exclui um evento; `scope="all_events"` exclui a série inteira em vez de só a ocorrência |
| `check_google_calendar_availability` | `start, end, calendar_ids?` | Verifica conflitos/disponibilidade em um período |

## Eventos recorrentes: série vs. ocorrência

O Google Calendar modela uma série recorrente como um evento **mestre** (`recurrence: ["RRULE:..."]`) mais **instâncias** — cada ocorrência retornada por `search_google_calendar_events` (que já usa `singleEvents=true`) carrega `recurring_event_id` apontando pro mestre. `CalendarEvent` (`providers/calendar/base.py`) expõe os dois campos: `recurrence` só vem preenchido no mestre, `recurring_event_id` só vem preenchido numa instância — nunca os dois ao mesmo tempo.

- **Criar uma série**: `create_google_calendar_event` com `recurrence` (ex: `["RRULE:FREQ=WEEKLY;BYDAY=MO;COUNT=10"]`). A regra é passada direto pro Google — nenhum parsing/validação de RRULE é feito pela aplicação, é tradução pura, mesmo princípio já documentado pra `EventSearchQuery`/`NewEvent`.
- **Editar/excluir só uma ocorrência**: `scope="this_event"` (padrão) — comportamento inalterado desde a Sprint 2, já funcionava porque o Google já isola PATCH/DELETE pelo id da instância.
- **Editar/excluir a série inteira**: `scope="all_events"`. A tool primeiro chama `CalendarProvider.get_event` (novo método do Strategy, não exposto como tool própria — usado só internamente pra essa resolução) pra descobrir `recurring_event_id`, e aplica a edição/exclusão nesse id mestre em vez do id da instância. Se o evento não fizer parte de nenhuma série (`recurring_event_id` ausente), o próprio id é usado — `scope="all_events"` nunca falha só por o evento ser um evento único, vira um no-op seguro.
- **Fora do escopo, deliberadamente**: "este evento e os seguintes" (o terceiro modo que a própria UI do Google Calendar oferece). Implementar isso exigiria dividir a RRULE manualmente (terminar a série original com `UNTIL` no ponto de corte + criar uma nova série a partir dali) — risco real de bug de fuso/data sem ter sido pedido explicitamente. Só `this_event`/`all_events` existem hoje.

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `CALENDAR_PROVIDER` | não (padrão `google`) | Seleciona o provider de calendário (Strategy) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | só para usar Calendar | Reaproveita as mesmas credenciais OAuth já criadas para o Gmail |
| `GOOGLE_CALENDAR_REDIRECT_URI` | só para usar Calendar | Deve bater exatamente com a URI cadastrada no Google Cloud, ex. `https://seu-dominio/api/gcalendar/oauth/callback` |
| `EMAIL_TOKEN_ENCRYPTION_KEY` | só para usar Calendar | Mesma chave Fernet já usada para o Gmail (ver `docs/EMAIL.md`) |

Sem essas variáveis, o backend sobe normalmente — `/api/gcalendar/connect` responde `503` até serem configuradas (mesma validação lazy, não fail-closed no boot, do domínio de e-mail).

## Passo a passo: estendendo o Google Cloud OAuth já criado

Se você já configurou o Gmail (`docs/EMAIL.md`), reaproveite o mesmo projeto e o mesmo app OAuth — não crie um novo:

1. No [Google Cloud Console](https://console.cloud.google.com/), no mesmo projeto do Gmail: **APIs e serviços → Biblioteca** → busque "Google Calendar API" → **Ativar**.
2. **Tela de consentimento OAuth → Escopos**: adicione `https://www.googleapis.com/auth/calendar`.
3. **Credenciais → seu ID do cliente OAuth existente → editar**: em **URIs de redirecionamento autorizados**, adicione a URL que você vai configurar em `GOOGLE_CALENDAR_REDIRECT_URI` — ex. `https://seu-dominio.com/api/gcalendar/oauth/callback`.
4. Preencha no `.env`:
   ```bash
   CALENDAR_PROVIDER=google
   GOOGLE_CALENDAR_REDIRECT_URI=<a URL cadastrada no passo 3>
   # GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET e EMAIL_TOKEN_ENCRYPTION_KEY já
   # existentes (do Gmail) são reaproveitados — nada novo a gerar aqui.
   ```
5. Suba/reinicie o backend.
6. Como usuário `admin`, chame `GET /api/gcalendar/connect` (Bearer token) e abra a `authorization_url` retornada num navegador autenticado com a conta Google a conectar.
7. Confirme: `GET /api/gcalendar/status` deve responder `{"connected": true, ...}`.

Começando do zero (sem ter feito o Gmail antes), siga o passo a passo completo do zero em `docs/EMAIL.md#passo-a-passo-configurando-o-google-cloud-oauth` primeiro, depois volte aqui para os passos 2-3 acima (adicionar escopo e redirect URI ao mesmo app).

## Limitações

- Um único provider de calendário (Google); a interface `CalendarProvider` já é o ponto de extensão para outros (Outlook/Microsoft Graph, CalDAV) sem mudar nenhum chamador.
- Uma conta Google Calendar conectada por usuário (`UNIQUE(user_id, provider)`).
- `search_google_calendar_events` busca apenas uma agenda por chamada (`calendar_id`, padrão `primary`) — para consultar várias agendas, chame a tool uma vez por agenda (a lista vem de `list_google_calendars`).
- Edição de série recorrente cobre só `this_event`/`all_events` — sem "este evento e os seguintes" (ver seção acima).

## Testes

| Arquivo | Cobertura |
| --- | --- |
| `tests/test_gcalendar_provider.py` | `GoogleCalendarProvider` (OAuth, listar agendas, buscar/criar/editar/excluir eventos, **`get_event`**, **recorrência** — `recurrence` enviado/omitido em create/update, parsing de `recurringEventId`/`recurrence`, disponibilidade, parsing de datas/eventos), factory |
| `tests/test_gcalendar_router.py` | `/connect`, `/oauth/callback` (sucesso, reconexão, corrida de concorrência, sem refresh token, sem chave de cifra, erro do Google, state inválido/errado propósito/de outro domínio, XSS refletido escapado), `/status`, `/disconnect`, admin-only |
| `tests/test_gcalendar_tools.py` | As 6 tools: rejeição sem conta conectada, refresh token revogado, sucesso, mapeamento de erro do provider, datas inválidas, **isolamento entre dois usuários conectados** — **recorrência**: `recurrence` passado ao criar, `scope="this_event"` (padrão) não chama `get_event` e edita/exclui só a instância dada, `scope="all_events"` resolve pro `recurring_event_id` (mestre) tanto em editar quanto excluir, no-op seguro em `all_events` para evento não recorrente, `scope` inválido rejeitado |

## O que ainda depende do fundador

A suíte automatizada cobre toda a lógica de aplicação com um provider falso (nenhuma chamada real ao Google). A demonstração ao vivo (conectar, listar agendas, criar/editar/excluir um evento real, verificar disponibilidade) depende de credenciais OAuth reais e de uma sessão supervisionada com o fundador para o consentimento do Google — mesma dependência já documentada para o Gmail.
