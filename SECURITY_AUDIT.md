# Security Audit — Sprint 5

Complementa `SECURITY.md` (política e práticas gerais já documentadas).
Este arquivo cobre especificamente a auditoria de segurança da Sprint 5
(Fase 4 do plano) e os achados dela — o que já estava correto, o que foi
corrigido, e o que fica documentado como gap conhecido.

## Já validado / correto (sem alteração)

- **Headers HTTP de segurança** (`docker/caddy/Caddyfile`): `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`,
  header `Server` removido, `encode gzip`.
- **CORS**: configurado explicitamente (não wildcard) em `backend/main.py`.
- **Rate limiting**: `services/rate_limit.py` — janela fixa, Redis com
  fallback em memória, aplicado como o middleware mais externo (para que
  os próprios 429 sejam contados nas métricas).
- **Endpoints sem autenticação**: auditados um a um (todos os routers +
  `api/routes.py`, `auth/router.py`, `chat/router.py`, `api/crud.py`). Os
  únicos endpoints públicos são os intencionalmente públicos: callbacks
  OAuth, o endpoint de webhook (que tem seu próprio esquema de token) e
  `auth/register|login|refresh|logout`. O router CRUD genérico injeta
  `CurrentUser` em toda rota gerada (create/get/update/delete/count) — sem
  gaps encontrados.
- **SSRF**: os parâmetros `url` de mídia do WhatsApp (`send_image`,
  `send_file`, `send_audio`) nunca são buscados pelo próprio backend — são
  repassados ao provider, que os entrega à API do WhatsApp. Não há
  `fetch`/`requests.get` no backend a partir de input de usuário.
- **SQL Injection**: 100% SQLAlchemy ORM/Core parametrizado; nenhuma
  concatenação de string em query encontrada na auditoria.
- **Path Traversal**: sem endpoints que aceitem caminho de arquivo bruto do
  usuário para leitura/escrita em disco.
- **JWT / Cookies / Tokens**: `auth/jwt.py`, `services/token_crypto.py` —
  tokens assinados, refresh tokens rotacionados (um novo por uso, o antigo
  invalidado), sem token em cookie não-HttpOnly.
- **CSRF**: mitigado pela ausência de autenticação por cookie (Bearer token
  em header, não sujeito a CSRF clássico).

## Achados corrigidos nesta sprint

1. **`memory/service.py`: chamada a um método inexistente no
   `qdrant-client` instalado.** Não é uma vulnerabilidade de segurança per
   se, mas é uma falha de disponibilidade (DoS funcional silencioso) em
   toda busca semântica — documentado em detalhe em `PRODUCTION_READINESS.md`.
2. **`apiFetch` 401-handling** redirecionava a página de login para si
   mesma em vez de deixar o formulário reportar "credenciais inválidas" —
   não é uma falha de segurança (o backend já rejeitava corretamente com
   401), mas atrapalhava o feedback ao usuário sobre uma tentativa de
   autenticação falha.

## Gaps conhecidos, documentados e não corrigidos (fora do escopo mínimo)

1. **CSP e HSTS ausentes no `Caddyfile`.** Nenhuma `Content-Security-Policy`
   nem `Strict-Transport-Security` configurada. Adicionar uma CSP sem poder
   testá-la contra HTTPS real e os domínios de asset reais de produção
   neste sandbox arrisca quebrar carregamento de scripts/estilos sem forma
   de validar aqui — decisão deliberada de documentar em vez de arriscar
   uma alteração não testável. Recomendação para uma sprint futura: iniciar
   com uma CSP em `Content-Security-Policy-Report-Only` em produção antes
   de aplicar.
2. **`npm audit` no frontend**: 5 vulnerabilidades em dependências
   (`next@14.2.21` — CVEs de DoS/cache-poisoning/SSRF em versões antigas do
   Next.js; `postcss` — XSS no stringify). A correção (`npm audit fix
   --force`) instalaria `next@16.2.10` e `eslint-config-next@16.2.10` —
   upgrades *major*, breaking, fora do escopo de "alteração mínima e
   justificada" desta sprint. Recomendação: tratar como item de uma sprint
   dedicada a upgrade de dependências, com o tempo de regressão que um
   major bump do Next.js exige.
3. **Google OAuth**: fluxo revisado por código (troca de tokens,
   armazenamento criptografado do refresh token, escopos mínimos por
   integração), mas sem credenciais reais do Google neste sandbox não é
   possível validar o round-trip completo (`/authorize` → callback → troca
   de código → refresh) contra o Google real. Ver `GOOGLE_PLATFORM_AUDIT.md`.

## Segredos / credenciais

Nenhum segredo, chave de API ou credencial foi encontrado hardcoded no
código-fonte ou commitado nesta sprint. `.env`/`.env.local` seguem
ignorados pelo `.gitignore` (pré-existente).

## Veredito de segurança

Nenhuma vulnerabilidade de severidade alta foi introduzida ou encontrada no
código da aplicação em si. Os dois gaps documentados (CSP/HSTS ausentes,
CVEs em dependências do Next.js) são reais e devem entrar no backlog, mas
não bloqueiam produção isoladamente — nenhum deles é explorável sem outra
falha adicional, e ambos exigem trabalho de upgrade/validação maior do que
o escopo desta sprint permite. Ver veredito consolidado em
`SPRINT5_REPORT.md`.
