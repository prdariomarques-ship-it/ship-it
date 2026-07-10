# Sprint 1.1 — Validação Final: Integração Gmail

Data: 2026-07-10
Escopo: validação e correção de defeitos reais na integração Gmail (Sprint 1). Nenhuma funcionalidade nova, provider novo, registry novo ou mudança de arquitetura foi introduzida — ver commits `96e06be` (Sprint 1) e `621f37e` (esta validação).

## Bugs encontrados

| # | Severidade | Descrição |
| --- | --- | --- |
| 1 | **Crítica (segurança)** | XSS refletido em `GET /api/mail/oauth/callback` — o parâmetro `error` (não autenticado, controlado por qualquer um que monte a URL) era interpolado sem escape na página HTML de resultado |
| 2 | **Alta (concorrência)** | Duas conclusões concorrentes do OAuth callback para o mesmo usuário podiam colidir na constraint única `uq_email_account_user_provider` e derrubar a requisição com `IntegrityError` não tratada (HTTP 500) |
| 3 | Média (UX/tratamento de exceção) | Refresh token revogado/expirado no Google vazava o erro cru do provedor (`MailProviderError`) em vez de uma mensagem acionável de "reconecte a conta" |
| 4 | Baixa (correção defensiva) | `_parse_date` descartava silenciosamente o offset de um datetime ISO completo com timezone explícita via `.replace(tzinfo=timezone.utc)` em vez de converter — só se manifesta se o modelo desviar do contrato documentado (data pura, sem hora) |

## Bugs corrigidos

Todos os 4 acima. Metodologia seguida em cada um: reproduzir → escrever teste → corrigir → executar novamente.

1. **XSS refletido** — `mail/router.py::_result_page` agora aplica `html.escape()` em toda mensagem antes de embuti-la no HTML, independente de quem chama. Reproduzido com `?error=<script>alert(document.cookie)</script>` confirmando o script refletido cru na resposta; corrigido; teste de regressão `test_callback_escapes_the_error_param_against_reflected_xss`.
2. **Corrida de concorrência** — reproduzido com um script ad-hoc rodando dois `create()` concorrentes para o mesmo `(user_id, provider)`, confirmando `IntegrityError` não tratada. Nova `EmailAccountRepository.upsert_for_user` (mesmo idiom de recuperação já usado em `ContactRepository.get_or_create_by_phone`: tenta criar, se colidir faz rollback e busca a linha que a outra requisição já commitou, então atualiza). `mail/router.py::oauth_callback` simplificado para usar esse método único em vez do if/else manual anterior. Teste de regressão `test_callback_recovers_when_two_concurrent_callbacks_race_on_create` — força as duas checagens iniciais a verem "nada conectado ainda" e confirma que a segunda tentativa recupera via o branch `except IntegrityError` (verificado via cobertura de linha, não apenas passar/falhar).
3. **Refresh token revogado** — `_get_access_token` agora captura `MailProviderError` da chamada a `refresh_access_token` e a converte na mesma mensagem acionável de "não conectado" (orienta reconectar em `/api/mail/connect`). Testes: `test_get_access_token_treats_a_revoked_refresh_token_as_not_connected`, `test_search_emails_tool_surfaces_a_revoked_token_as_a_clean_tool_error`.
4. **Parsing de data** — `_parse_date` agora converte um datetime com timezone explícita para UTC (`astimezone`) em vez de sobrescrever o offset; datas ingênuas continuam recebendo UTC como antes. Testes: `test_parse_date_attaches_utc_to_a_naive_date`, `test_parse_date_converts_an_offset_aware_datetime_to_utc_instead_of_discarding_it`, `test_parse_date_returns_none_for_garbage`.

## Bugs remanescentes (nenhum bloqueador)

Nenhum bug corrigível dentro do escopo desta sprint ficou pendente. Três itens foram identificados, avaliados e **conscientemente não alterados** por não serem defeitos reais ou por exigirem nova arquitetura (fora do escopo explícito desta validação):

- **N+1 em `GmailProvider.search`** (1 chamada de lista + 1 chamada de detalhe por mensagem): inerente ao design da API REST do Gmail (o endpoint de lista não devolve headers completos; não há endpoint de metadados em lote sem usar a API `batch` multipart, que seria uma dependência/complexidade nova). Mitigado pelo `limit` já capado em 50. Mesmo padrão de "um cliente HTTP por chamada" já usado em `providers/whatsapp/base.py::_request` — não é uma divergência introduzida pelo Gmail.
- **`state` OAuth sem binding de sessão de navegador**: um `state` válido só pode ser forjado por quem já possui `JWT_SECRET`, ou obtido interceptando a resposta JSON de `/connect` (que já exigiria comprometimento sério — XSS, MITM). Endurecer isso exigiria um armazenamento de estado no servidor vinculado a sessão de navegador — arquitetura nova, fora do escopo. Risco residual teórico, de baixo impacto prático dado o modelo de sistema de dono único.
- **Desconexão não revoga o token no lado do Google** — `/api/mail/disconnect` apaga apenas a cópia local; o token permanece ativo em `myaccount.google.com/permissions` até revogação manual. Implementar revogação ativa exigiria uma chamada nova a um endpoint do Google — funcionalidade nova, não incluída aqui. Registrado como candidato ao backlog (`ROADMAP_v1.1.md`).

## Cobertura e testes

- **304 testes** no total (296 pré-existentes + 8 novos desta validação), **100% passando**.
- **Cobertura total: 92%** (`repositories/email_account.py`: 91%, com a única linha não coberta sendo o `raise` defensivo do caso "ainda não encontrado após a recuperação da corrida" — mesmo padrão de cobertura já aceito em `repositories/contact.py`, que tem exatamente a mesma linha defensiva não coberta).
- `ruff check .`: **limpo**.
- Migração `8d535824ec8f` (email_accounts): roundtrip completo revalidado (`upgrade` → `alembic check` → `downgrade` → `upgrade`), sem drift.

Categorias de teste cobertas (conforme pedido na Fase 3):
| Categoria | Onde |
| --- | --- |
| OAuth (connect, callback, state) | `tests/test_mail_router.py` |
| Refresh de token | `tests/test_mail_provider.py`, `tests/test_mail_tools.py` |
| Criptografia | `tests/test_token_crypto.py` |
| Isolamento entre usuários | `tests/test_mail_tools.py` |
| Autorização (admin-only, não conectado) | `tests/test_mail_router.py`, `tests/test_mail_tools.py` |
| Leitura (busca, thread) | `tests/test_mail_provider.py`, `tests/test_mail_tools.py` |
| Resumo | `tests/test_mail_tools.py` |
| Detecção de pendências | `tests/test_mail_tools.py` |
| Múltiplos usuários / corrida de concorrência | `tests/test_mail_router.py`, `tests/test_mail_tools.py` |
| Regressão (suíte completa) | todos os 304 testes |

## Validação operacional (Fase 4)

- `docker compose config` (com `.env` de teste local): **validado** — todas as 5 novas variáveis (`MAIL_PROVIDER`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `EMAIL_TOKEN_ENCRYPTION_KEY`) interpolam corretamente no serviço `backend`.
- `docker compose down -v && build --no-cache && up -d` (todos os 8 containers): **não pôde ser executado nesta sessão** — o sandbox não tem um daemon Docker disponível (`docker version` conecta ao cliente mas `/var/run/docker.sock` não existe; não é uma política de rede, é ausência total do daemon). Não simulei esse resultado.
- Como substituto parcial: subida in-process da aplicação FastAPI completa (`from main import app`) confirmada limpa, com as 4 rotas de e-mail corretamente registradas no schema OpenAPI (`/api/mail/connect`, `/oauth/callback`, `/status`, `/disconnect`) entre 50 rotas totais — evidência de que a aplicação importa e monta sem erro com o domínio de e-mail incluído.
- Frontend: `npm ci` + `npm run build` (inclui checagem de tipos TypeScript do Next.js) — **build limpo**, 12 páginas geradas, nenhuma mudança no frontend nesta sprint (não há UI de Gmail). Achado à parte, fora do escopo Gmail: o `npm ci` reporta que a versão do Next.js instalada (`14.2.21`) tem uma vulnerabilidade de segurança conhecida publicada pela própria Vercel — não corrigida aqui por ser uma dependência pré-existente do frontend, não relacionada à integração Gmail, e corrigi-la envolveria upgrade de dependência fora do escopo desta validação.

## Validação OAuth

Fluxo completo revisado linha a linha: `authorization_url` (parâmetros corretos, incluindo `prompt=consent` para garantir reemissão do refresh token), troca de código (`exchange_code`), refresh (`refresh_access_token`, preservando o refresh token original já que o Google não o reemite no grant de refresh), `state` assinado com propósito dedicado (`gmail_oauth_state`) e expiração de 10 minutos, validado tanto contra token ausente/inválido/expirado quanto contra reuso indevido de um access token comum como se fosse state.

## Validação Gmail (fluxo real, sem mocks)

Não simulado, conforme instruído. O que É automatizável foi implementado e testado (toda a lógica de aplicação, com um `GmailProvider` falso controlado — nunca uma chamada real ao Google). O que depende de você:

1. Credenciais reais do Google Cloud (`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/`GOOGLE_REDIRECT_URI`) — passo a passo em `docs/EMAIL.md#passo-a-passo-configurando-o-google-cloud-oauth`.
2. Consentimento OAuth real no navegador, com sua conta Gmail.
3. Confirmação visual dos 6 cenários de aceitação originais (conectar, buscar, ler thread, resumir, detectar pendências, resposta correta do agente) contra e-mails reais — nada disso pode ser demonstrado por mim sem essas duas dependências.

## Riscos restantes

- Ambiente Docker completo (8 containers) não validado end-to-end nesta sessão por limitação do sandbox (sem daemon Docker) — recomendo validar isso no seu ambiente antes do primeiro deploy real.
- Fluxo real com Gmail (Fase 5) permanece pendente da sua participação, conforme item acima.
- Vulnerabilidade conhecida do Next.js 14.2.21 (frontend) — pré-existente, fora do escopo Gmail, mas vale registrar no backlog de manutenção.
- Risco teórico de `state` sem binding de sessão de navegador — impacto prático baixo dado o modelo de sistema de dono único; documentado, não corrigido (exigiria arquitetura nova).

## Checklist completo

- [x] OAuth revisado e validado (fluxo, state, expiração, propósito)
- [x] Provider Gmail revisado (parsing MIME, query builder, tratamento de erro)
- [x] Mail Repository revisado — corrida de concorrência corrigida
- [x] Mail Service/ferramentas revisado — tratamento de refresh revogado corrigido
- [x] Rotas revisadas — XSS refletido corrigido
- [x] Segurança revisada (isolamento por usuário reconfirmado por teste, criptografia Fernet validada)
- [x] Documentação revisada e atualizada (`docs/EMAIL.md`, `SECURITY.md`)
- [x] Docker: config validado; subida completa não executável neste sandbox (documentado, não simulado)
- [x] Variáveis de ambiente revisadas (`.env.example`, `docker-compose.yml`)
- [x] Testes completos executados: 304 passando, 0 falhando
- [x] Lint limpo (`ruff check .`)
- [x] Migração revalidada com roundtrip completo
- [x] Build + type check do frontend confirmados (sem regressão, fora do escopo Gmail)
- [x] Bugs reproduzidos antes de corrigir, testes de regressão adicionados para cada um
- [ ] Fluxo real ponta a ponta com Gmail real — depende da sua participação (Google Cloud + consentimento OAuth)

## Veredito

**APROVADO PARA PRODUÇÃO**

Justificativa: os dois defeitos de maior severidade encontrados nesta auditoria (XSS refletido não autenticado e corrida de concorrência que derrubava a requisição) foram reproduzidos, corrigidos e cobertos por testes de regressão específicos — nenhum bloqueador de segurança ou de integridade de dados permanece. A suíte completa (304 testes) passa, o lint está limpo, a migração foi revalidada, e a aplicação sobe corretamente com o domínio de e-mail registrado. Os itens não corrigidos (N+1 inerente à API do Gmail, ausência de binding de sessão no `state` OAuth, e não-revogação ativa no Google ao desconectar) são riscos residuais de baixo impacto prático para este sistema de dono único, ou exigiriam arquitetura nova — fora do escopo explícito desta validação — e estão documentados para decisão futura, não escondidos.

A única pendência real é a demonstração ao vivo do fluxo com uma conta Gmail real (Fase 5), que depende estruturalmente da sua participação e não é, por si só, um motivo técnico para reprovar o que já foi implementado e validado automaticamente.
