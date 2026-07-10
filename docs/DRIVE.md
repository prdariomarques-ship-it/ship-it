# Google Drive — Sprint 3 (Base de Conhecimento)

Domínio novo, isolado do resto do Dario OS: o Google Drive como base oficial de conhecimento. Mesmo padrão arquitetural do e-mail, Calendar e Contacts (`docs/EMAIL.md`, `docs/CALENDAR.md`, `docs/CONTACTS.md`) — Strategy + Factory, OAuth com `state` assinado, criptografia de token em repouso, isolamento por usuário resolvido só em código, gateway único (`assistant`) — com uma diferença central: **o que este domínio produz (conhecimento indexado) não fica numa tabela nova; alimenta exclusivamente o Memory Manager / Knowledge Store / Qdrant que já existiam desde a Fase 4.2**, nunca um banco ou mecanismo paralelo.

## Escopo

| Funcionalidade | Sprint 3 |
| --- | --- |
| Listar arquivos | ✅ |
| Buscar arquivos (nome, pasta, tipo, texto livre) | ✅ |
| Obter metadados | ✅ (parte da busca/listagem e da leitura) |
| Download seguro | ✅ (nunca bytes brutos ao modelo — só texto extraído, limitado, sempre via token resolvido pelo backend) |
| Leitura de PDF, DOCX, TXT, Markdown, CSV | ✅ |
| Indexação | ✅ |
| Atualização do índice | ✅ |
| RAG (perguntas sobre os documentos indexados) | ✅ — via a ferramenta `search_memory` já existente, nenhuma nova |
| Google Docs, Sheets, Slides, Meet, Tasks, Keep | ❌ fora do escopo — arquivos nativos do Google são recusados explicitamente, nunca convertidos/exportados |

## Memória: nenhum mecanismo novo

Esta é a exigência mais importante da sprint e a que mais define o design: **toda informação lida do Drive alimenta exclusivamente a infraestrutura de memória que já existia.**

- O conteúdo extraído de um arquivo é dividido em pedaços (`_chunk_text`, ~1500 caracteres, até 30 pedaços por arquivo) e cada pedaço é gravado com `memory_manager.remember(db, content=..., source="knowledge")` — a **mesma** `MemoryManager`/`MemoryService`/coleção Qdrant já usada por `store_memory`, com a **mesma** tag `KNOWLEDGE_SOURCE = "knowledge"` que a Fase 4.2 já previa e documentava como "pronta para uso, só faltando quem alimentasse" (`memory/manager.py::knowledge_search`).
- Não existe uma segunda coleção Qdrant, um segundo banco vetorial, nem uma tabela de conteúdo paralela. O que este domínio grava em uma tabela nova (`google_drive_indexed_files`) é **só bookkeeping**: qual arquivo, quando foi indexado, e quais `Embedding.id` (do Postgres, não do Qdrant) seus pedaços geraram — nunca o conteúdo em si. Ver `models/gdrive_indexed_file.py`.
- **RAG usa a ferramenta que já existe.** Como o conteúdo indexado entra na mesma coleção que qualquer outra memória, a ferramenta `search_memory` (`agents/tools/communication.py`, já registrada em `assistant` desde antes desta sprint) já é capaz de responder "qual documento fala sobre investimentos?", "procure o contrato da Oficina das Tintas" etc. assim que os arquivos relevantes forem indexados — nenhuma ferramenta de busca de conhecimento nova foi criada. Cada pedaço indexado carrega uma citação no próprio texto (`[Google Drive: nome.pdf | atualizado em ... | parte 1/3]`) para que a resposta do agente possa identificar de qual arquivo veio.
- **"O que mudou na última versão?"** é respondido reindexando: `update_google_drive_index` reindexa arquivos cujo `modifiedTime` no Drive mudou desde a última indexação, e o pedaço antigo é removido antes do novo ser gravado (nunca os dois coexistem).

### A única extensão feita no Memory Manager (e por quê)

Sem uma forma de **remover** pedaços antigos, reindexar um arquivo alterado geraria duplicatas para sempre — o Qdrant acumularia a versão antiga e a nova do mesmo trecho, degradando exatamente a pergunta "o que mudou" que a sprint pede para responder. `MemoryService`/`MemoryManager` ganharam um método `delete`/`forget(db, embedding_ids)`, pequeno, aditivo e genérico (não específico do Drive) — mesma categoria de extensão mínima já aplicada em `auth/jwt.py::create_oauth_state_token` (parâmetro `purpose`, Sprint 2). Nenhuma linha do `store`/`search`/`knowledge_search` pré-existentes foi alterada; a coleção, o formato do payload e o contrato de busca são exatamente os mesmos de antes desta sprint.

## Não confundir com nada que já existia

Esta é a primeira das quatro sprints Google sem um domínio interno homônimo para colidir — não existe "Drive" no Dario OS anterior à Sprint 3. Ainda assim, os nomes seguem o mesmo prefixo `gdrive`/`Google Drive` das outras integrações Google (`gcalendar`, `gcontacts`), por consistência: modelos, tools e rotas usam `gdrive`/`GoogleDrive`, rota em `/api/gdrive/*`.

## Gateway único: o agente `assistant`

Mesmo princípio dos outros três domínios Google: **somente o agente `assistant` tem acesso direto às ferramentas de Google Drive.** Nenhum outro agente as lista. Um agente especializado que precise de algo do Drive passa pelo Cognitive Planner, que roteia a etapa para `assistant` — nenhum canal novo de comunicação entre agentes foi criado.

## Arquitetura

```
providers/drive/
  base.py             DriveProvider (Strategy) — authorization_url, exchange_code,
                       refresh_access_token, list_files, search_files, get_metadata,
                       read_file_text (baixa com trava de tamanho + extrai texto)
                       + DriveFile, DriveSearchQuery, OAuthTokens
  factory.py           get_drive_provider() — seleciona por DRIVE_PROVIDER (hoje só "google")
  google/provider.py   GoogleDriveProvider — REST via httpx puro; extração de texto via
                       pypdf (PDF) e python-docx (DOCX) — duas dependências novas, mas
                       para uma funcionalidade declarada da sprint, não uma arquitetura
                       nova (mesma categoria da adição de `cryptography` na Sprint 1)

gdrive/
  router.py            /api/gdrive/connect, /oauth/callback, /status, /disconnect
  schemas.py           GDriveConnectResponse, GDriveStatusResponse

models/gdrive_account.py         GoogleDriveAccount — um Google Drive autorizado por (user, provider)
models/gdrive_indexed_file.py    GoogleDriveIndexedFile — bookkeeping (arquivo, quando,
                                  quais embedding_ids) — nunca o conteúdo em si
repositories/gdrive_account.py
repositories/gdrive_indexed_file.py

agents/tools/gdrive.py            as 7 tools — registradas só em assistant_agent.py
```

### Extração de texto: onde vive e por quê

Assim como `GmailProvider._extract_body` decodifica um payload MIME dentro do próprio provider (tradução, não regra de negócio), `GoogleDriveProvider` extrai texto de PDF/DOCX/TXT/Markdown/CSV dentro de si mesmo — o contrato `DriveProvider.read_file_text` já devolve texto pronto, nunca bytes brutos para quem chama. Arquivos nativos do Google (`application/vnd.google-apps.*` — Docs, Sheets, Slides) são recusados **antes de tentar baixar** (a API do Drive nem aceita `alt=media` para eles; seria preciso `files.export`, que é a própria integração de Docs/Sheets/Slides que esta sprint exclui).

### Download seguro

"Seguro" aqui significa: (1) sempre autenticado pelo token OAuth resolvido pelo backend, nunca uma URL pública; (2) tamanho verificado nos metadados **antes** de baixar — arquivo acima de `GDRIVE_MAX_FILE_SIZE_BYTES` (padrão 20 MB) é recusado sem gastar memória com ele; (3) o modelo nunca recebe bytes brutos, só texto já extraído e limitado (`_MAX_CONTENT_CHARS` = 8000 caracteres por leitura/resumo).

## Consolidação de ferramentas

O escopo lista várias capacidades de leitura/busca; a seção FERRAMENTAS pede exatamente 7 tools. Cobertura:

| Tool | Cobre |
| --- | --- |
| `list_google_drive_files` | listar arquivos (opcionalmente por pasta) |
| `search_google_drive_files` | buscar arquivos, buscar por nome, buscar por pasta, buscar por tipo, obter metadados |
| `read_google_drive_file` | leitura de PDF/DOCX/TXT/Markdown/CSV, obter metadados |
| `index_google_drive_file` | indexação de um arquivo |
| `index_google_drive_folder` | indexação de uma pasta (até 20 arquivos por chamada) |
| `summarize_google_drive_document` | "resuma o documento X" |
| `update_google_drive_index` | "o que mudou na última versão" — reindexa arquivos já indexados que mudaram |

`search_memory` (já existente) responde "qual documento fala sobre X" / "procure o contrato de Y" / "qual arquivo contém informações de Z" depois de indexado — não é uma tool nova desta sprint.

## Fluxo de autorização (OAuth 2.0)

Idêntico ao fluxo do Gmail/Calendar/Contacts (ver `docs/EMAIL.md#fluxo-de-autorização-oauth-20-authorization-code`), com:

- Escopo solicitado: `https://www.googleapis.com/auth/drive.readonly` — somente leitura (a sprint não pede upload/edição/exclusão de nada no Drive).
- `state` assinado com propósito próprio (`gdrive_oauth_state`), isolado dos propósitos das outras três integrações mesmo reutilizando o mesmo `auth/jwt.py::create_oauth_state_token`/`decode_oauth_state_token`.

**Reaproveita o mesmo app OAuth do Google Cloud já criado para o Gmail** — mais uma URI de redirecionamento e mais um escopo, no mesmo app.

## Segurança e isolamento

Mesmos princípios das três integrações anteriores (ver `SECURITY.md`):

- `_get_access_token(context)` (`agents/tools/gdrive.py`) resolve a conta do Drive estritamente a partir de `ToolContext.user.id`. Nenhuma das sete tools recebe um parâmetro de conta/drive/usuário no schema — `file_id`/`folder_id` são identificadores de **objeto dentro do Drive já autorizado**, nunca seletores de qual conta usar (mesma distinção já estabelecida para `calendar_id` no Sprint 2, aceita sem objeção).
- Refresh token cifrado em repouso (Fernet, `EMAIL_TOKEN_ENCRYPTION_KEY` — mesma chave de Gmail/Calendar/Contacts).
- Testes de isolamento entre usuários (`backend/tests/test_gdrive_tools.py`) provam que dois usuários conectados a Drives diferentes nunca se cruzam, inclusive quando o modelo tenta apontar um `file_id` de um usuário para a chamada de outro (a API do Drive já escopa arquivos pelo access_token).
- **A base de conhecimento resultante é global à instância, por design** — não particionada por usuário. Isso não é uma exceção ao isolamento: é a mesma característica que `knowledge_search`/`search_memory` já tinham desde a Fase 4.2, consistente com o Dario OS ser um sistema de dono único (ver `FOUNDER_NOTES.md`). O que precisa e está isolado é *qual Drive é lido*, nunca *quem pode ver o conhecimento resultante*.
- Refresh token revogado/expirado vira o mesmo erro acionável de "não conectado", nunca um erro cru do provedor.

## Ferramentas (catálogo)

| Tool | Parâmetros principais | Descrição |
| --- | --- | --- |
| `list_google_drive_files` | `folder_id?, limit?` | Lista arquivos, opcionalmente de uma pasta |
| `search_google_drive_files` | `name?, mime_type?, folder_id?, query?, limit?` | Busca por nome/tipo/pasta/texto livre |
| `read_google_drive_file` | `file_id` | Lê o conteúdo de um arquivo (texto extraído, limitado) |
| `index_google_drive_file` | `file_id` | Indexa um arquivo na base de conhecimento |
| `index_google_drive_folder` | `folder_id, limit?` | Indexa até 20 arquivos de uma pasta |
| `summarize_google_drive_document` | `file_id` | Resume um documento (LLM) |
| `update_google_drive_index` | `limit?` | Reindexa arquivos já indexados que mudaram no Drive |

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `DRIVE_PROVIDER` | não (padrão `google`) | Seleciona o provider de Drive (Strategy) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | só para usar Drive | Reaproveita as mesmas credenciais OAuth já criadas para o Gmail |
| `GOOGLE_DRIVE_REDIRECT_URI` | só para usar Drive | Deve bater exatamente com a URI cadastrada no Google Cloud, ex. `https://seu-dominio/api/gdrive/oauth/callback` |
| `EMAIL_TOKEN_ENCRYPTION_KEY` | só para usar Drive | Mesma chave Fernet já usada para Gmail/Calendar/Contacts |
| `GDRIVE_MAX_FILE_SIZE_BYTES` | não (padrão 20.000.000) | Trava de "download seguro" — arquivo maior é recusado antes de baixar |

Sem essas variáveis, o backend sobe normalmente — `/api/gdrive/connect` responde `503` até serem configuradas.

## Passo a passo: estendendo o Google Cloud OAuth já criado

Reaproveite o mesmo projeto/app OAuth do Gmail/Calendar/Contacts:

1. No [Google Cloud Console](https://console.cloud.google.com/), no mesmo projeto: **APIs e serviços → Biblioteca** → busque "Google Drive API" → **Ativar**.
2. **Tela de consentimento OAuth → Escopos**: adicione `https://www.googleapis.com/auth/drive.readonly`.
3. **Credenciais → seu ID do cliente OAuth existente → editar**: em **URIs de redirecionamento autorizados**, adicione a URL que você vai configurar em `GOOGLE_DRIVE_REDIRECT_URI` — ex. `https://seu-dominio.com/api/gdrive/oauth/callback`.
4. Preencha no `.env`:
   ```bash
   DRIVE_PROVIDER=google
   GOOGLE_DRIVE_REDIRECT_URI=<a URL cadastrada no passo 3>
   ```
5. Suba/reinicie o backend.
6. Como usuário `admin`, chame `GET /api/gdrive/connect` e abra a `authorization_url` retornada num navegador autenticado com a conta Google a conectar.
7. Confirme: `GET /api/gdrive/status` deve responder `{"connected": true, ...}`.
8. Indexe: peça ao `assistant` (via WhatsApp ou `/api/chat`) para indexar uma pasta ou arquivo específico — ex. "indexe a pasta Contratos do meu Drive".

## Limitações desta sprint

- Um único provider de Drive (Google); a interface `DriveProvider` já é o ponto de extensão para outros (Dropbox, WebDAV) sem mudar nenhum chamador.
- Apenas PDF, DOCX, TXT, Markdown e CSV são lidos. Google Docs/Sheets/Slides e qualquer outro tipo binário são recusados explicitamente (`UnsupportedDriveFileTypeError`), nunca convertidos.
- `index_google_drive_folder` indexa até 20 arquivos por chamada; `update_google_drive_index` reverifica até 50 arquivos já indexados por chamada (mais que isso, chame de novo — sem paginação completa, adequado ao volume de uma base de conhecimento pessoal).
- Cada arquivo é dividido em até 30 pedaços de ~1500 caracteres (~45 mil caracteres por arquivo) — um documento maior que isso é indexado parcialmente (os primeiros 30 pedaços), sem erro, mas sem cobrir o restante.
- CSV é indexado como texto simples (linhas/colunas concatenadas), sem semântica tabular — suficiente para busca semântica, não para consultas estruturadas tipo planilha.

## Testes

| Arquivo | Cobertura |
| --- | --- |
| `tests/test_gdrive_provider.py` | `GoogleDriveProvider` (OAuth, listar/buscar/metadados, extração de texto PDF/DOCX/CSV/TXT/MD, tipos não suportados, trava de tamanho antes do download), factory |
| `tests/test_gdrive_router.py` | `/connect`, `/oauth/callback` (sucesso, reconexão, corrida de concorrência, sem refresh token, sem chave de cifra, erro do Google, state inválido/errado propósito/de outro domínio, XSS refletido escapado), `/status`, `/disconnect`, admin-only |
| `tests/test_gdrive_tools.py` | As 7 tools: rejeição sem conta conectada, refresh token revogado, isolamento entre dois usuários (inclusive `file_id` de outro usuário), indexação (grava no Memory Manager existente, pula arquivo sem alteração, substitui pedaços obsoletos ao reindexar, agrega sucesso/pulado/falha em pasta), atualização de índice, resumo, corrida de concorrência na tabela de bookkeeping, multiusuário |
| `tests/test_memory_service_delete.py` | A extensão `MemoryService.delete`/`MemoryManager.forget` (Qdrant mockado) — apagar pontos específicos sem afetar outros, lista vazia é no-op |

## O que ainda depende do fundador

A suíte automatizada cobre toda a lógica de aplicação com um provider falso e um Memory Manager mockado (nenhuma chamada real ao Google, nenhum Qdrant real nesta sessão). A demonstração ao vivo (conectar, indexar arquivos reais, perguntar "qual documento fala sobre X" e receber uma resposta correta via `search_memory`) depende de credenciais OAuth reais, de um Qdrant rodando de verdade, e de uma sessão supervisionada com o fundador para o consentimento do Google — mesma dependência já documentada para Gmail, Calendar e Contacts.
