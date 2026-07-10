# Production Blockers Resolved

Data: 2026-07-10
Branch: `claude/dario-os-platform-gcg6i2`
Escopo: exclusivamente os dois bloqueadores abaixo. Nenhuma funcionalidade nova, refatoração ou mudança de arquitetura foi feita.

## PROD-004: CORRIGIDO

**Problema**: `WEBHOOK_SECRET` era opcional; nada impedia o boot em produção sem ele, deixando `/api/webhooks/whatsapp` aberto a requisições não autenticadas.

**Correção**:
- `backend/main.py::_validate_production_settings` agora também recusa o boot em produção se `WEBHOOK_SECRET` estiver ausente ou tiver menos de 32 caracteres — mesma regra e mesmo padrão já aplicado a `JWT_SECRET`.
- `docker/docker-compose.yml`: `WEBHOOK_SECRET` passou de `${WEBHOOK_SECRET:-}` (opcional) para `${WEBHOOK_SECRET:?set WEBHOOK_SECRET in .env}` (obrigatório), mesmo padrão de `JWT_SECRET`.
- `scripts/setup.sh`: passa a gerar `WEBHOOK_SECRET` automaticamente (`openssl rand -hex 32`) junto com `JWT_SECRET`, para que a instalação padrão continue subindo sem intervenção manual.
- `docker/.env.example`: comentário atualizado para deixar claro que a variável é obrigatória em produção.

**Testes** (`backend/tests/test_audit_fixes.py`), cobrindo exatamente os 5 cenários pedidos:

| Cenário | Teste |
| --- | --- |
| Ambiente de desenvolvimento | `test_development_does_not_require_a_webhook_secret` |
| Ambiente de produção (geral) | todos os testes abaixo usam `environment="production"` |
| Secret ausente | `test_production_rejects_missing_webhook_secret` |
| Secret inválido (curto) | `test_production_rejects_weak_webhook_secret` |
| Secret válido | `test_production_accepts_strong_webhook_secret` |

Teste adicional de não-regressão: `test_production_still_checks_jwt_secret_before_webhook_secret` (garante que a nova checagem não mascara a checagem de `JWT_SECRET` já existente).

**Validação operacional**: `docker compose config` confirmado como recusando interpolar sem `WEBHOOK_SECRET` definido (`required variable WEBHOOK_SECRET is missing a value`), e aceitando quando definido.

## PROD-005: CORRIGIDO

**Problema**: `send_whatsapp_message` aceitava qualquer número de destino escolhido pelo modelo; `find_contact` buscava qualquer contato por nome/telefone. Nenhuma das duas tinha restrição técnica ao contato da conversa atual — a única "proteção" era uma instrução de prompt (`needs_confirmation`), não uma fronteira de segurança real.

**Correção** (decisão de autorização inteiramente no código, nunca no prompt):
- `backend/agents/tools/base.py::ToolContext` ganhou o campo `contact_id: int | None = None` — a identidade do contato da conversa atual, definida pela aplicação (`BaseAgent.run`, que já recebia `contact_id` como parâmetro desde a Fase 4.1/4.2), nunca escolhida ou influenciável pelo LLM.
- `backend/agents/base.py::BaseAgent.run` passa a repassar esse `contact_id` para o `ToolContext` construído para o `AgentExecutor`.
- `backend/agents/tools/communication.py`:
  - `_send_whatsapp`: quando a conversa está associada a um contato (`context.contact_id` definido), o destino é normalizado (`normalize_phone`) e comparado ao telefone desse contato — qualquer outro destino é recusado com um erro explícito, **antes** de qualquer enfileiramento. Sem conversa associada (ex: uso administrativo via dashboard), o destino precisa ao menos corresponder a um contato já conhecido pelo backend — o modelo nunca pode inventar um número novo do zero.
  - `_find_contact`: quando a conversa está associada a um contato, a busca só pode resolver para esse mesmo contato — qualquer nome/telefone que aponte para outro contato (ou para nenhum contato) é recusado. Sem conversa associada, o comportamento de busca aberta existente é preservado (uso administrativo).

**Testes** (`backend/tests/test_tool_isolation.py`, 10 testes), cobrindo tentativas de acesso indevido:

| Cenário | Teste |
| --- | --- |
| Enviar para outro contato com conversa associada | `test_send_blocks_message_to_another_contact_when_conversation_scoped` |
| Enviar para o próprio contato da conversa | `test_send_allows_message_to_the_current_conversation_contact` |
| Enviar para contato conhecido sem conversa associada | `test_send_allows_message_to_a_known_contact_without_conversation_scope` |
| Enviar para número desconhecido sem conversa associada | `test_send_blocks_arbitrary_unknown_number_without_conversation_scope` |
| Tentativa de burlar o isolamento via formatação do telefone | `test_send_isolation_is_not_bypassable_by_phone_formatting` |
| Buscar outro contato por nome, com conversa associada | `test_find_contact_blocks_lookup_of_another_contact_when_conversation_scoped` |
| Buscar outro contato por telefone, com conversa associada | `test_find_contact_blocks_lookup_by_phone_of_another_contact` |
| Buscar o próprio contato da conversa | `test_find_contact_allows_lookup_of_the_current_conversation_contact` |
| Busca aberta preservada sem conversa associada | `test_find_contact_open_lookup_preserved_without_conversation_scope` |
| Busca sem correspondência, com conversa associada, não vaza informação | `test_find_contact_scoped_query_with_no_match_is_denied_not_leaked_as_not_found` |

Nenhum job de envio é enfileirado quando a tentativa é negada — verificado diretamente na tabela `jobs` nos testes de bloqueio de envio.

## Checklist executado após as correções

| Item | Resultado |
| --- | --- |
| Build (import da aplicação) | ✅ OK |
| Lint (`ruff check .`) | ✅ limpo |
| Type Check | não configurado no projeto (sem mypy/pyright — limitação preexistente, fora do escopo desta correção; mitigado por Pydantic em runtime) |
| Todos os testes (`pytest -q`) | ✅ **246 passed** (231 antes + 15 novos: 5 para PROD-004, 10 para PROD-005) |
| Testes de regressão | ✅ nenhum teste pré-existente quebrou |
| Migrações (`alembic upgrade head` / `alembic check`) | ✅ aplicadas sem erro, sem drift de schema |
| `docker compose config` | ✅ válido; confirmado que agora recusa subir sem `WEBHOOK_SECRET` |
| Cobertura das linhas alteradas | `main.py` (checagem de produção): 100% coberta pelos novos testes; `agents/tools/communication.py` (lógica de isolamento): 100% coberta pelos novos testes |

## Resumo

| Bloqueador | Status |
| --- | --- |
| PROD-004 | **CORRIGIDO** |
| PROD-005 | **CORRIGIDO** |

Ambos os bloqueadores identificados na auditoria final foram eliminados. `PRODUCTION_APPROVAL.md` foi atualizado para **STATUS: APROVADO PARA PRODUÇÃO**.
