# Google Contacts — Sprint 2

Domínio novo, isolado do resto do Dario OS: leitura e escrita no Google Contacts (People API). Mesmo padrão arquitetural do domínio de e-mail e do Google Calendar (`docs/EMAIL.md`, `docs/CALENDAR.md`) — Strategy + Factory, OAuth com `state` assinado, criptografia de token em repouso, isolamento por usuário resolvido só em código, gateway único (`assistant`).

## Escopo

| Funcionalidade | Sprint 2 |
| --- | --- |
| Listar contatos | ✅ |
| Buscar contatos | ✅ |
| Criar contato | ✅ |
| Editar contato | ✅ |
| Remover contato | ✅ |
| Localizar telefone | ✅ (via busca) |
| Localizar e-mail | ✅ (via busca) |

## Não confundir com o contato interno do Dario OS (WhatsApp)

Dario OS já tinha, desde antes desta sprint, um modelo de **Contato** próprio — `models.contact.Contact`, usado para identificar quem está conversando pelo WhatsApp, com toda a lógica de isolamento por conversa do PROD-005 (`find_contact`/`send_whatsapp_message`, `agents/tools/communication.py`). Esse é o "caderno de conversas do WhatsApp" do próprio sistema.

Esta sprint adiciona um domínio **completamente separado**: a **agenda de contatos real do Google** (People API) do usuário, acessada via OAuth. Por isso:

- Modelos, tools, rotas e pacotes usam o prefixo `gcontacts`/`google_contacts`/`Google Contacts`, nunca apenas `contacts`, evitando qualquer colisão de nome com o domínio interno já existente.
- As tools se chamam `search_google_contacts`, `create_google_contact`, etc. — nunca `find_contact` (que já pertence ao domínio de WhatsApp e continua funcionando exatamente como antes).
- A rota é `/api/gcontacts/*`, não `/api/contacts/*` (que já existe e continua servindo o CRUD interno de contatos do WhatsApp).
- Os dois domínios nunca compartilham dados nem lógica de isolamento: uma pessoa pode existir como `Contact` (conversou pelo WhatsApp) e/ou como entrada no Google Contacts, sem nenhuma relação automática entre os dois registros.

## Gateway único: o agente `assistant`

Mesmo princípio dos outros dois domínios Google desta plataforma: **somente o agente `assistant` tem acesso direto às ferramentas de Google Contacts.** Nenhum outro agente as lista. Um agente especializado que precise de algo do Google Contacts passa pelo Cognitive Planner, que roteia a etapa para `assistant` — nenhum canal novo de comunicação entre agentes foi criado.

## Arquitetura

```
providers/contacts/
  base.py             ContactsProvider (Strategy) — authorization_url, exchange_code,
                       refresh_access_token, search_contacts, get_contact, create_contact,
                       update_contact, delete_contact
                       + Contact, ContactSearchQuery, NewContact, ContactUpdate, OAuthTokens
  factory.py           get_contacts_provider() — seleciona por CONTACTS_PROVIDER (hoje só "google")
  google/provider.py   GoogleContactsProvider — REST via httpx puro contra a People API

gcontacts/
  router.py            /api/gcontacts/connect, /oauth/callback, /status, /disconnect
  schemas.py           GContactsConnectResponse, GContactsStatusResponse

models/gcontacts_account.py       GoogleContactsAccount — uma conta Google Contacts por (user, provider)
repositories/gcontacts_account.py GoogleContactsAccountRepository — get_by_user, upsert_for_user

agents/tools/gcontacts.py          as 4 tools — registradas só em assistant_agent.py
```

`Contact` em `providers/contacts/base.py` é deliberadamente um nome diferente de `models.contact.Contact` (o contato de WhatsApp) — ver seção acima.

### Por que "buscar" cobre "listar", "localizar telefone" e "localizar e-mail"

Mesmo padrão já usado pelo `search_emails` do Gmail: uma única tool com um parâmetro `query` opcional em vez de uma tool por variação. `search_google_contacts` sem `query` lista todos os contatos; com `query`, filtra por nome, telefone **ou** e-mail (a mesma chamada resolve "localizar o telefone de X" e "localizar o e-mail de X" — o agente lê o campo relevante da resposta).

### Por que buscar + filtrar em vez do endpoint de busca da People API

A People API tem um endpoint dedicado (`people:searchContacts`), mas ele depende de um índice de busca com consistência eventual (precisa de um "aquecimento" prévio via `connections.list`, e pode devolver resultados desatualizados/incompletos logo após uma mudança). `GoogleContactsProvider.search_contacts` sempre lista a agenda **inteira** (`people.connections.list`, seguindo `nextPageToken` por quantas páginas de 1000 forem necessárias — não só a primeira) e filtra no lado do servidor Dario OS — resultado imediato e previsível, sem a fragilidade do índice de busca assíncrono. Ver `docs/CONTACTS.md#limitações-desta-sprint`.

## Fluxo de autorização (OAuth 2.0)

Idêntico ao fluxo do Gmail e do Google Calendar (ver `docs/EMAIL.md#fluxo-de-autorização-oauth-20-authorization-code`), com:

- Escopo solicitado: `https://www.googleapis.com/auth/contacts` (leitura **e** escrita).
- `state` assinado com propósito próprio (`gcontacts_oauth_state`) — isolado dos propósitos `gmail_oauth_state`/`gcalendar_oauth_state`, mesmo reutilizando o mesmo `auth/jwt.py::create_oauth_state_token`/`decode_oauth_state_token`.

**Reaproveita o mesmo app OAuth do Google Cloud já criado para o Gmail/Calendar** — basta adicionar mais uma URI de redirecionamento e mais um escopo.

## Segurança e isolamento

Mesmos princípios do PROD-005 e dos outros dois domínios Google (ver `SECURITY.md`):

- `_get_access_token(context)` (`agents/tools/gcontacts.py`) resolve a conta de contatos estritamente a partir de `ToolContext.user.id`. Nenhuma das quatro tools tem um parâmetro de usuário/conta no schema.
- Refresh token cifrado em repouso (Fernet, `EMAIL_TOKEN_ENCRYPTION_KEY` — mesma chave usada para Gmail e Calendar).
- Testes de isolamento entre usuários (`backend/tests/test_gcontacts_tools.py`) provam na prática que dois usuários conectados a agendas diferentes nunca se cruzam, inclusive quando o modelo tenta apontar um `resource_name` de um usuário para a chamada de outro — a atualização do People API exige buscar o contato primeiro (para obter o `etag`), e essa busca já falha sozinha se o `resource_name` não pertencer à agenda autorizada pelo access_token em uso.
- Refresh token revogado/expirado vira o mesmo erro acionável de "não conectado", nunca um erro cru do provedor.

## Ferramentas (catálogo)

| Tool | Parâmetros principais | Descrição |
| --- | --- | --- |
| `search_google_contacts` | `query?, limit?` | Busca/lista contatos por nome, telefone ou e-mail |
| `create_google_contact` | `given_name, family_name?, emails?, phones?` | Cria um contato |
| `update_google_contact` | `resource_name, ...campos opcionais` | Edita um contato (só os campos informados mudam) |
| `delete_google_contact` | `resource_name` | Remove um contato |

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `CONTACTS_PROVIDER` | não (padrão `google`) | Seleciona o provider de contatos (Strategy) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | só para usar Contacts | Reaproveita as mesmas credenciais OAuth já criadas para o Gmail |
| `GOOGLE_CONTACTS_REDIRECT_URI` | só para usar Contacts | Deve bater exatamente com a URI cadastrada no Google Cloud, ex. `https://seu-dominio/api/gcontacts/oauth/callback` |
| `EMAIL_TOKEN_ENCRYPTION_KEY` | só para usar Contacts | Mesma chave Fernet já usada para Gmail e Calendar |

Sem essas variáveis, o backend sobe normalmente — `/api/gcontacts/connect` responde `503` até serem configuradas.

## Passo a passo: estendendo o Google Cloud OAuth já criado

Reaproveite o mesmo projeto/app OAuth do Gmail/Calendar:

1. No [Google Cloud Console](https://console.cloud.google.com/), no mesmo projeto: **APIs e serviços → Biblioteca** → busque "People API" → **Ativar**.
2. **Tela de consentimento OAuth → Escopos**: adicione `https://www.googleapis.com/auth/contacts`.
3. **Credenciais → seu ID do cliente OAuth existente → editar**: em **URIs de redirecionamento autorizados**, adicione a URL que você vai configurar em `GOOGLE_CONTACTS_REDIRECT_URI` — ex. `https://seu-dominio.com/api/gcontacts/oauth/callback`.
4. Preencha no `.env`:
   ```bash
   CONTACTS_PROVIDER=google
   GOOGLE_CONTACTS_REDIRECT_URI=<a URL cadastrada no passo 3>
   ```
5. Suba/reinicie o backend.
6. Como usuário `admin`, chame `GET /api/gcontacts/connect` e abra a `authorization_url` retornada num navegador autenticado com a conta Google a conectar.
7. Confirme: `GET /api/gcontacts/status` deve responder `{"connected": true, ...}`.

## Limitações desta sprint

- Um único provider de contatos (Google); a interface `ContactsProvider` já é o ponto de extensão para outros sem mudar nenhum chamador.
- Uma conta Google Contacts conectada por usuário (`UNIQUE(user_id, provider)`).
- `search_google_contacts` pagina a agenda inteira antes de filtrar (sem limite artificial de 1000) — uma agenda muito maior que o uso pessoal típico paga o custo de mais chamadas HTTP sequenciais (uma por página de 1000), mas nenhum contato fica invisível pra busca. Teto de segurança de 50 páginas (50 mil contatos) só como proteção contra `nextPageToken` nunca esvaziar, não um limite de produto (a própria conta Google já limita bem abaixo disso).
- Atualização de contato busca o registro atual antes de aplicar a mudança (necessário para o `etag` exigido pela People API) — uma chamada HTTP extra por edição, aceitável dado o volume de uso.

## Testes

| Arquivo | Cobertura |
| --- | --- |
| `tests/test_gcontacts_provider.py` | `GoogleContactsProvider` (OAuth, listar/buscar/criar/editar/excluir contatos, fluxo de etag na edição, filtro client-side por nome/telefone/e-mail, **paginação**: segue `nextPageToken` através de várias páginas, filtro/limite aplicados sobre o resultado paginado completo, teto de segurança de páginas), factory |
| `tests/test_gcontacts_router.py` | `/connect`, `/oauth/callback` (sucesso, reconexão, corrida de concorrência, sem refresh token, sem chave de cifra, erro do Google, state inválido/errado propósito/de outro domínio, XSS refletido escapado), `/status`, `/disconnect`, admin-only |
| `tests/test_gcontacts_tools.py` | As 4 tools: rejeição sem conta conectada, refresh token revogado, sucesso, mapeamento de erro do provider, **isolamento entre dois usuários conectados** (inclusive tentativa de editar o `resource_name` de outro usuário) |

## O que ainda depende do fundador

A suíte automatizada cobre toda a lógica de aplicação com um provider falso (nenhuma chamada real ao Google). A demonstração ao vivo (conectar, listar/buscar contatos reais, criar/editar/remover um contato real) depende de credenciais OAuth reais e de uma sessão supervisionada com o fundador para o consentimento do Google — mesma dependência já documentada para o Gmail e o Calendar.
