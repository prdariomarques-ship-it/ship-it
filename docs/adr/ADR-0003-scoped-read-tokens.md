# ADR-0003: Tokens com escopo de leitura para integrações confiáveis

**Status:** Proposto
**Data:** 2026-10-17
**Origem:** Integração do Dario OS com o Zérvis (assistente de voz e
orquestrador de sessões de código, repositório externo, AGPL-3.0).

## Contexto

O Zérvis precisa ler o estado do Dario OS (status dos componentes, agentes e
tools, execuções recentes, observação do dono, metas, tarefas) para falar e
exibir isso ao operador. A inspeção da autenticação mostrou:

- A auth é JWT Bearer **vinculado a um usuário**. O token de acesso dura 30
  minutos, o de refresh 30 dias, e não existe service account, API key nem
  escopo. Uma integração hoje só poderia usar o login do próprio dono, com
  poder total.
- Os endpoints de leitura úteis ficam em `/admin/*`, protegidos por
  `require_admin` no nível do router.
- Pela ADR-0002 (operador único), os dados "do dono" pertencem ao primeiro
  admin: `/admin/observation` resolve o dono por `get_first_admin()`, e metas
  e tarefas são escopadas por `user_id`. Um usuário de serviço separado
  enxergaria tudo vazio.
- `UserRole` é um enum nativo do Postgres (`userrole`). Um papel novo exigiria
  `ALTER TYPE` em migration e, mesmo assim, não passaria por `require_admin`.

## Decisão

Introduzir **tokens com escopo**: JWT assinado para o dono, com a claim
`scope`, que só alcança o que o escopo permite. Sem papel novo e sem migration.

1. **Escopo `darioos:read`** (`auth/scopes.py`): apenas `GET`/`HEAD`, e apenas
   caminhos de um allowlist explícito, comparados por match completo (nunca
   por prefixo). Hoje: `/agents`, `/agents/tools`, `/admin/status`,
   `/admin/agents`, `/admin/tools`, `/admin/executions`, `/admin/observation`,
   `/goals`, `/goals/ready`, `/goals/{id}`, `/tasks`, `/tasks/{id}`.
2. **Fail-closed, num ponto único.** A política é aplicada em
   `get_current_user`, por onde toda rota autenticada já passa; um router novo
   não consegue alargar o escopo sem editar o allowlist. Escopo desconhecido,
   claim malformada, método de escrita ou caminho fora da lista resultam em 403.
3. **Emissão fora da API.** `scripts/mint_scoped_token.py`, executado no
   servidor, exige um admin ativo, limita a validade a `SCOPED_TOKEN_MAX_DAYS`
   (padrão 90) e audita a emissão em `logs` (usuário, escopo, validade e
   `jti`, nunca o token). Nenhuma rota da API cria credenciais de longa duração.
4. **Revogação.** `SCOPED_TOKEN_REVOKED_BEFORE` (timestamp unix): tokens com
   escopo emitidos antes dele são rejeitados (401). Revoga todos de uma vez;
   não há armazenamento por token, de propósito.
5. **Tokens com escopo não são tokens completos.** `decode_access_token`
   (que devolve só o `sub`) passa a recusá-los; quem trata escopo usa
   `decode_access_claims`.

### Correção adjacente

`decode_access_token` aceitava como Bearer os tokens de `state` do OAuth
(`create_oauth_state_token`), que compartilham a chave de assinatura e viajam
na URL do redirect para o Google. Isso valia por 10 minutos como acesso
completo. Agora `decode_access_claims` rejeita qualquer token com a claim
`purpose`. Coberto por teste.

## Consequências

- Uma integração lê o necessário sem poder agir: nem `POST /agents/{name}/run`
  (que roda LLM e tools, incluindo envio de WhatsApp, como o dono), nem
  logs, usuários, configurações, QR do WhatsApp ou memória.
- **Vazamento de dados é o risco residual.** O que o token lê (metas, tarefas,
  agenda e execuções do dono) sai do Dario OS para a integração e, no caso do
  Zérvis, pode chegar ao provedor de LLM configurado lá. O allowlist é a
  fronteira de privacidade: cada caminho novo é uma decisão de revisão, não um
  detalhe.
- Estender o escopo é editar `_READ_PATHS` e acrescentar o caso em
  `tests/test_scoped_tokens.py`. Um escopo de escrita (por exemplo, para
  aprovar ações por voz) exige ADR própria.
- Um token vazado vale até expirar ou até `SCOPED_TOKEN_REVOKED_BEFORE`.
  Por isso o TTL é limitado e a revogação não depende do banco.
- Multiusuário (ADR-0002) continua bloqueado. Este desenho presume um único
  dono; ao revisar a ADR-0002, o escopo precisa passar a carregar o dono
  explicitamente.

## Alternativas consideradas

- **Papel `READONLY` em `UserRole`:** exige migration de enum no Postgres,
  não enxerga os dados do dono e não passa por `require_admin`.
- **Usuário admin dedicado à integração:** poder total para uma credencial
  de longa duração.
- **API key em tabela própria:** mais flexível (revogação individual), mas
  exige migration e uma superfície nova de gestão. Reavaliar se surgirem
  várias integrações com ciclos de vida diferentes.
- **Endpoint para emitir o token:** amplia a superfície da API com uma rota que
  cria credenciais; o script no servidor tem a mesma utilidade com acesso
  mais restrito.
