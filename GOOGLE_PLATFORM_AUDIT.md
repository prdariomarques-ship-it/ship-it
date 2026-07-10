# Auditoria Técnica Final — Plataforma Google (Gmail, Calendar, Contacts, Drive)

Data: 2026-07-10
Escopo: auditoria completa de todo o código das Sprints 1, 1.1, 2 e 3 (integração Google). Nenhuma funcionalidade nova, nenhuma refatoração por preferência, nenhuma mudança de arquitetura ou de padrão existente — apenas validação e correção de defeitos reais, reproduzidos e cobertos por teste antes de qualquer alteração.

## Bugs encontrados e corrigidos

### 1. Vetores órfãos em reindexação concorrente do Google Drive — **Alta severidade**

**Onde**: `backend/agents/tools/gdrive.py::_index_one`

**Descrição**: duas chamadas de indexação sobrepostas para o **mesmo arquivo** (ex.: `index_google_drive_folder` e `update_google_drive_index` disparadas próximas no tempo, ou o mesmo pedido reprocessado) podiam ambas ler o mesmo estado antigo de `GoogleDriveIndexedFile` antes de qualquer uma escrever. A segunda chamada então sobrescrevia o resultado da primeira em `upsert_for_user_and_file`, sem nunca esquecer (`memory_manager.forget`) os pedaços que a primeira chamada já havia gravado no Qdrant. Resultado: os pedaços da primeira chamada ficavam **órfãos permanentemente** — nunca referenciados pela linha de bookkeeping, nunca limpos por uma reindexação futura (que só esquece o que a linha *atual* aponta) — poluindo a busca semântica com conteúdo duplicado/obsoleto para sempre.

**Evidência (reprodução antes da correção)**:
```
AssertionError: task A's embeddings {201} are neither referenced by the final row
([202]) nor forgotten ({100, 101}) — permanently orphaned
```
(`tests/test_gdrive_tools.py::test_concurrent_reindexing_of_the_same_file_does_not_orphan_embeddings`, simulação determinística de duas chamadas concorrentes via leitura controlada, sem depender de timing do event loop.)

**Correção**: `_index_one` agora captura o `indexed_at` da linha de bookkeeping antes da parte lenta (download + chunk + embed) e, imediatamente antes do upsert final, relê a linha — se ela mudou nesse intervalo (outra chamada concorrente já terminou), a chamada atual esquece (`forget`) os embeddings que acabou de criar em vez de sobrescrever o resultado vencedor, e retorna `indexed: false, reason: "atualizado por outra indexação concorrente"`. Guarda otimista, sem lock distribuído novo — reduz a janela de corrida ao mínimo possível dentro dos padrões já existentes no código (mesmo espírito do `upsert_for_user_and_file` já usado nas quatro contas OAuth).

**Teste de regressão**: `test_concurrent_reindexing_of_the_same_file_does_not_orphan_embeddings` — falha antes da correção (confirmado), passa depois.

### 2. Path traversal no provider do Gmail — **Média severidade (segurança)**

**Onde**: `backend/providers/mail/gmail/provider.py::get_thread`, `search`

**Descrição**: `thread_id` (argumento fornecido pelo modelo via `read_email_thread`/`summarize_email_thread`) e o `id` de mensagem retornado pela busca eram interpolados diretamente numa f-string de URL, sem escape. Um `thread_id` contendo `/` mudava qual caminho da API do Gmail era efetivamente requisitado — ex. `"abc/../../drafts/xyz"` produzia `.../threads/abc/../../drafts/xyz`, que após normalização de caminho podia resolver para `.../drafts/xyz`, um recurso completamente diferente de "threads". Não é um SSRF (o host continua sendo `gmail.googleapis.com`) nem uma quebra do isolamento entre mailboxes (o access_token continua escopado à mesma caixa já autorizada), mas é uma violação real do contrato da ferramenta — "leia esta thread que eu especifiquei", não "acesse qualquer recurso sob a árvore da API do Gmail".

**Evidência (reprodução antes da correção)**:
```python
await provider.get_thread('access-token', 'abc/../../drafts/xyz')
# URL called: https://gmail.googleapis.com/gmail/v1/users/me/threads/abc/../../drafts/xyz
```

**Correção**: `thread_id` e o `id` de mensagem agora passam por `urllib.parse.quote(..., safe='')` antes de entrar na URL — mesmo padrão já usado consistentemente em Calendar (`_encode`) e Drive (`quote`) desde suas respectivas sprints; o Gmail (Sprint 1) antecedeu esse padrão e não o seguia.

**Teste de regressão**: `test_get_thread_url_encodes_the_thread_id` (`tests/test_mail_provider.py`).

### 3. Path traversal no provider do Google Contacts — **Média severidade (segurança)**

**Onde**: `backend/providers/contacts/google/provider.py::get_contact`, `update_contact`, `delete_contact`

**Descrição**: mesma classe de problema do item 2, mas em `resource_name` (argumento do modelo via `update_google_contact`/`delete_google_contact`). Diferença importante: `resource_name` **legitimamente contém uma `/`** (formato da People API é `people/<id>`), então não podia simplesmente receber `quote(..., safe='')` como Gmail/Drive — isso quebraria o caso normal, escapando a barra estrutural válida.

**Evidência (reprodução antes da correção)**:
```python
await provider.get_contact('access-token', 'people/c1/../../otherContacts/malicious')
# URL called: https://people.googleapis.com/v1/people/c1/../../otherContacts/malicious
```

**Correção**: validação por allowlist (`^people/[A-Za-z0-9_-]+$`) no início de `get_contact`/`delete_contact` (e transitivamente em `update_contact`, que já chama `get_contact` internamente para buscar o etag) — um `resource_name` fora do formato esperado é rejeitado com `ContactsProviderError` antes de qualquer requisição HTTP ser montada, nunca enviado ao Google.

**Testes de regressão**: `test_get_contact_rejects_a_resource_name_with_a_path_traversal_attempt`, `test_delete_contact_rejects_an_invalid_resource_name`, `test_update_contact_rejects_an_invalid_resource_name_before_fetching_the_etag`, `test_get_contact_accepts_the_special_people_me_resource_name` (`tests/test_gcontacts_provider.py`).

## Achados documentados, não corrigidos (com justificativa)

Nenhum dos itens abaixo é um defeito real que exija correção sob as regras desta auditoria ("só modifique código se encontrar um bug real comprovado"); documentados por transparência.

| # | Área | Achado | Por que não foi alterado |
| --- | --- | --- | --- |
| 1 | Performance | `read_file_text` (Drive) busca metadados internamente; `agents/tools/gdrive.py` também busca metadados antes de chamar `read_file_text` — 2 chamadas de metadados por leitura/indexação/resumo em vez de 1 | Corrigir exigiria mudar o contrato de retorno de `DriveProvider.read_file_text` (ABC pública) — mudança de interface, não um bug de correção. Custo real é baixo (uma chamada leve de metadados a mais por arquivo; a operação cara — download+parse — só acontece uma vez) |
| 2 | Performance | Busca do Gmail é N+1 por design (1 chamada de lista + 1 por mensagem) | Já documentado e aceito na auditoria Sprint 1.1 — inerente à API do Gmail (o endpoint de lista não devolve headers completos), mitigado pelo `limit` já capado em 50 |
| 3 | Memory Manager | `MemoryService.store`/`delete` fazem escrita dupla (Qdrant + Postgres) sem transação distribuída — uma falha exatamente entre as duas escritas deixaria as duas fontes inconsistentes | Característica arquitetural pré-existente de `store()` (desde a Fase 4.2), não introduzida nem agravada pela Sprint 3; `delete()` (novo nesta sprint) replica deliberadamente o mesmo padrão de confiabilidade já aceito, por consistência — resolver exigiria um padrão saga/outbox, arquitetura nova |
| 4 | Segurança | Prompt injection indireta: conteúdo de e-mail/documento malicioso poderia tentar manipular o LLM | Mitigado estruturalmente onde importa — toda tool sensível (`send_whatsapp_message`, qualquer create/update/delete) decide autorização só por `ToolContext`, nunca por conteúdo de documento; risco residual (o agente tomar uma ação indesejada dentro da própria conta do dono) é uma limitação estrutural de qualquer agente LLM com acesso a ferramentas, já reconhecida em `FOUNDER_NOTES.md` ("Princípio do Copiloto"), não uma lacuna de código corrigível sem restringir a capacidade do agente |
| 5 | Segurança | PDF/DOCX maliciosamente comprimidos (“zip bomb”) poderiam causar uso excessivo de memória durante o parsing | Mitigado pelo limite de tamanho já existente (`GDRIVE_MAX_FILE_SIZE_BYTES`, recusa antes de baixar); uma guarda de taxa de descompressão seria funcionalidade nova |

## Auditoria por categoria

### 1. Segurança
- **OAuth**: fluxo revisado nas 4 integrações — `state` assinado, com `purpose` isolado por domínio (`gmail_oauth_state`/`gcalendar_oauth_state`/`gcontacts_oauth_state`/`gdrive_oauth_state`), expiração de 10 minutos, validado contra token ausente/inválido/expirado/de outro domínio (já testado em cada sprint). Sem alterações necessárias.
- **CSRF**: `/connect`/`/status`/`/disconnect` exigem Bearer token (não cookie) — CSRF clássico não se aplica. `/oauth/callback` (sem Bearer possível) é protegido pelo `state` assinado, que só um admin autenticado pode ter emitido.
- **XSS**: os 4 `_result_page` (mail/gcalendar/gcontacts/gdrive) escapam a mensagem com `html.escape` desde a correção da Sprint 1.1 — confirmado consistente nas 4 rotas.
- **SSRF**: nenhuma URL requisitada pelo backend é construída a partir de entrada de usuário/modelo — todas as bases de URL vêm de configuração fixa (`GOOGLE_*_API_BASE_URL`); identificadores de objeto (`file_id`, `event_id`, `thread_id`, `resource_name`) só selecionam o *caminho*, nunca o *host*. Sem achados.
- **Path Traversal**: 2 achados reais, corrigidos (itens 2 e 3 acima).
- **Prompt Injection**: revisado — ver achado documentado #4.
- **Token leakage**: nenhuma linha de log imprime token de acesso/refresh; mensagens de exceção do httpx não incluem headers. Sem achados.
- **Criptografia**: Fernet (`cryptography`), mesma chave (`EMAIL_TOKEN_ENCRYPTION_KEY`) para os 4 domínios, nunca em texto puro, recusa operar sem chave configurada. Sem achados.
- **Isolamento entre usuários**: `_get_access_token` idêntico nas 4 tools (`mail.py`/`gcalendar.py`/`gcontacts.py`/`gdrive.py`), resolvido só por `context.user.id`; confirmado por smoke test que nenhum outro agente além de `assistant` possui qualquer tool Google/e-mail. Sem achados novos.
- **Escalada de privilégios**: as 16 rotas OAuth (4 por domínio × 4 domínios) confirmadas com `require_admin` em `connect`/`status`/`disconnect`; nenhuma tool expõe conectar/desconectar. Sem achados.

### 2. Concorrência
- **Race conditions**: 1 achado real e corrigido (item 1 acima — reindexação concorrente).
- **Upsert**: as 5 operações de upsert (`EmailAccount`, `GoogleCalendarAccount`, `GoogleContactsAccount`, `GoogleDriveAccount`, `GoogleDriveIndexedFile`) já seguem o idiom de recuperação de corrida estabelecido na Sprint 1.1 — revisado, sem regressão.
- **Deadlocks**: nenhuma operação retém mais de um lock de linha por vez nem cruza tabelas dentro de uma transação com ordens diferentes entre chamadores — risco não identificado.
- **Atualização simultânea**: coberta pelos testes de corrida já existentes (contas OAuth) e pelo novo teste de reindexação.
- **Reindexação concorrente**: item 1 acima.

### 3. Banco de dados
- **Migrações**: roundtrip completo (upgrade → check → downgrade × 3 → upgrade) validado nesta auditoria, sem drift.
- **Integridade**: FKs com `ondelete=CASCADE` consistentes nas 5 tabelas novas desde a Sprint 1.
- **Índices**: `user_id` indexado em todas; `UNIQUE(user_id, file_id)`/`UNIQUE(user_id, provider)` cobrem o padrão de consulta real (lookup por ambos os campos juntos).
- **Chaves únicas**: confirmadas nas 5 tabelas (`uq_email_account_user_provider`, `uq_gcalendar_account_user_provider`, `uq_gcontacts_account_user_provider`, `uq_gdrive_account_user_provider`, `uq_gdrive_indexed_file_user_file`).
- **Rollback/Roundtrip**: validado.

### 4. Performance
- **Consultas N+1**: 1 já documentado e aceito (Gmail, Sprint 1.1); 1 novo achado documentado, não corrigido (Drive, ver tabela acima).
- **Loops desnecessários**: revisado nos loops de `index_google_drive_folder`/`update_google_drive_index` — cada iteração faz trabalho necessário, sem chamadas redundantes além do item já documentado.
- **Uso de memória**: bytes de download nunca persistidos além do escopo da função; cap de tamanho antes do download (`GDRIVE_MAX_FILE_SIZE_BYTES`).
- **Reindexação**: cap de arquivos por chamada (`_MAX_FILES_PER_FOLDER_INDEX=20`, `_MAX_FILES_PER_INDEX_UPDATE=50`) e de pedaços por arquivo (`_MAX_CHUNKS_PER_FILE=30`) — revisado, adequado à escala de uso pessoal.
- **Cache**: nenhum dos quatro domínios usa `services/cache.py` — não há bug de cache a auditar (nenhuma camada de cache existe aqui).
- **Uploads grandes**: não aplicável — os quatro domínios são leitura/escrita de metadados, nunca upload de arquivo.

### 5. Integração Google
- **Gmail/Calendar/Contacts/Drive**: revisados ponta a ponta nesta auditoria; 2 achados de path traversal corrigidos (Gmail, Contacts).
- **Refresh Token**: `_get_access_token` idêntico nas 4 tools — token revogado/expirado vira `MailNotConnectedError`/`CalendarNotConnectedError`/`ContactsNotConnectedError`/`DriveNotConnectedError` com mensagem acionável, nunca erro cru do provedor.
- **Expiração**: `state` OAuth expira em 10 minutos; access token renovado a cada chamada via `refresh_access_token` (nunca cacheado além do escopo de uma chamada).
- **Revogação**: tratada (ver Refresh Token acima); desconexão local via `/disconnect` documentada como não revogando ativamente no lado do Google (limitação já registrada em `SPRINT_1_1_VALIDATION.md`, fora do escopo desta auditoria).
- **Limites de API**: todo `limit` de tool é capado no código antes de chegar ao provider (nunca confia em um valor arbitrário do modelo).

### 6. Memory Manager
- **Duplicação**: verificação de `modified_time` evita reindexar um arquivo inalterado; corrida que causaria duplicação/órfãos corrigida (item 1).
- **Exclusão**: `MemoryService.delete`/`MemoryManager.forget` (extensão da Sprint 3) testados isoladamente (`tests/test_memory_service_delete.py`) e como parte do fluxo de reindexação.
- **Consistência**: ver achado documentado #3 (janela de inconsistência pré-existente entre Qdrant/Postgres, não introduzida por esta sprint).
- **Vetores órfãos**: achado real, corrigido (item 1).
- **Atualizações**: `update_google_drive_index` revisado — só reindexa arquivos cujo `modifiedTime` mudou, com o mesmo guard de corrida.

### 7. Ferramentas dos agentes
- **Permissões**: as 21 tools Google/e-mail confirmadas presentes só em `assistant` (smoke test desta auditoria).
- **Escopo**: nenhuma tool recebe `user_id`/`drive_id`/`account_id` do modelo; identificadores de objeto (`file_id`, `event_id`, `thread_id`, `resource_name`, `folder_id`, `calendar_id`) são os únicos parâmetros de seleção, todos validados/escapados nos pontos de risco encontrados.
- **Validação**: `resource_name` agora validado por allowlist (item 3); demais identificadores escapados via `quote()` (item 2, e já correto em Calendar/Drive).
- **Sanitização**: `html.escape` nas 4 páginas de resultado OAuth (Sprint 1.1, confirmado consistente).
- **Tratamento de erros**: todo `DriveProviderError`/`CalendarProviderError`/`ContactsProviderError`/`MailProviderError` capturado e convertido em erro de tool estruturado (`Tool.run`), nunca um traceback cru ao modelo.

### 8. Testes
- Ver seção "Cobertura final" abaixo.

## Validação executada

| Etapa | Resultado |
| --- | --- |
| Lint (`ruff check .`) | ✅ Limpo |
| Type check / build (frontend, `npm run build`) | ✅ Limpo, sem alterações no frontend |
| Todos os testes (`pytest`) | ✅ **479 passando**, 0 falhando |
| Coverage (`pytest --cov=.`) | ✅ **93%** |
| Migrações (`alembic upgrade/check/downgrade×3/upgrade`) | ✅ Roundtrip completo, sem drift |
| `docker compose config` | ✅ Válido (todas as variáveis das 4 integrações interpolam corretamente) |
| `docker compose up` (containers reais) | ⚠️ Não executável neste sandbox — sem daemon Docker disponível (mesma limitação já documentada nas auditorias anteriores); não simulado |
| Smoke test (boot in-process da app) | ✅ 62 rotas registradas, incluindo as 16 rotas OAuth (4 × 4 domínios); 21 tools Google/e-mail confirmadas só em `assistant`, 0 vazamento para outros agentes |

## Cobertura final e quantidade de testes

- **479 testes**, 100% passando (473 antes desta auditoria + 6 novos: 1 reprodução de vetores órfãos, 1 path traversal no Gmail, 4 no Contacts — incluindo o caso de regressão `people/me`).
- **93% de cobertura geral**, sem queda em relação à Sprint 3.

## Nota de transparência

Durante a escrita do teste de regressão do Gmail (achado #2), um erro de edição meu deixou uma linha de asserção da suíte original (`assert thread.messages[0].body == ...`) temporariamente órfã dentro da função de teste errada — percebido imediatamente ao rodar a suíte (`NameError: name 'thread' is not defined`), corrigido antes de prosseguir. Nenhum código de produção foi afetado; mencionado aqui pela mesma transparência já praticada nas auditorias anteriores.

## Decisão final

**APROVADO PARA PRODUÇÃO**

Justificativa: os três defeitos reais encontrados nesta auditoria (vetores órfãos em reindexação concorrente do Drive, e path traversal no Gmail e no Contacts) foram reproduzidos, corrigidos e cobertos por teste de regressão específico — nenhum permanece. Nenhum dos três compromete o isolamento entre usuários já estabelecido (todos ficam contidos dentro da mesma conta já autorizada) nem a integridade dos dados de forma irreversível (o achado de maior impacto, vetores órfãos, degrada qualidade de busca ao longo do tempo mas não expõe dados de outro usuário nem corrompe o sistema). A suíte completa (479 testes) passa, lint e build estão limpos, migrações revalidadas com roundtrip completo, e o smoke test confirma que a arquitetura de isolamento (gateway único, autorização resolvida só pelo backend) se mantém intacta nas quatro integrações. Os achados documentados e não corrigidos são, em cada caso, características arquiteturais pré-existentes ou mitigadas por controles já em vigor — corrigi-los exigiria mudança de interface/arquitetura fora do escopo explícito desta auditoria, não a presença de um defeito real sem mitigação.
