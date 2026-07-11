# Contribuindo com o Dario OS

Guia prático para quem vai mexer no código. Para a arquitetura completa,
ver `docs/architecture.md` — este documento é o "como fazer X", não o
"como o sistema funciona por dentro".

## Padrões do projeto

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2.
- **Frontend**: Next.js 14 (App Router), TypeScript, Tailwind (só no
  `app/admin/`), Vitest, Playwright.
- **Estilo de código**: Ruff (backend), ESLint (frontend) — ambos rodam
  limpos como pré-requisito de qualquer merge. Sem configuração de `mypy`
  no projeto hoje (ver `KNOWN_LIMITATIONS.md`).
- **Toda mudança de comportamento vem com teste.** Este projeto não aceita
  "vou testar manualmente depois" — os relatórios de cada sprint
  (`SPRINT5_REPORT.md`, `DASHBOARD_REPORT.md`, etc.) só existem porque cada
  um documenta cobertura real.
- **Alteração mínima e justificada.** Não refatore código não relacionado
  à sua mudança. Não invente abstração para um caso de uso hipotético.

## Arquitetura em uma frase por camada

`api/routers` (HTTP) → `services`/`repositories` (regra de negócio e
acesso a dados) → `models` (SQLAlchemy) — e, paralelamente, `agents` +
`agents/tools` (o que a IA pode fazer) coordenados por `orchestrator`
(`AIOrchestrator`, Cognitive Pipeline) e `providers/*` (integrações
externas plugáveis: LLM, WhatsApp, Google, Mail). Ver
`docs/architecture.md` para o diagrama completo e o racional de cada
decisão.

## Como criar um Agent

1. Crie `agents/<nome>_agent.py`.
2. Estenda `agents.base.BaseAgent`, declare `name`, `description`, o
   `system_prompt` e a lista `tools` (instâncias de `Tool` já existentes —
   ver "Como criar uma Tool" abaixo).
3. Decore a classe com `@register_agent`.
4. Pronto — nenhum outro arquivo muda. `agents/registry.py` descobre o
   módulo automaticamente por convenção de pasta (`agents/*_agent.py`); o
   agente já aparece em `GET /api/agents`, fica disponível em `/api/chat`
   e `/api/agents/{name}/run`, e se torna uma opção válida para o
   Cognitive Planner escolher.

Guia completo (anatomia, exemplo mínimo, como um agente é escolhido,
observabilidade automática): `docs/AGENTS.md`.

## Como criar uma Tool

1. Escreva o handler: `async def _my_handler(context: ToolContext, **kwargs) -> str: ...`,
   devolvendo `agents.tools.base.ok(**data)` no caminho feliz (ou
   `agents.tools.base.error(...)` no caminho de erro).
2. Declare `my_tool = Tool(name=..., description=..., parameters=..., handler=_my_handler)`
   em nível de módulo dentro de `agents/tools/<categoria>.py` (o registro
   acontece sozinho na construção do objeto).
3. Liste `my_tool` em `tools` do(s) agente(s) que devem usá-la.
4. **Nunca deixe o LLM escolher de quem é o dado.** Qualquer isolamento
   por usuário/contato (ex.: qual mailbox, qual contato) vem de
   `ToolContext`, preenchido pela aplicação — nunca de um parâmetro que o
   modelo possa manipular. Este é o princípio de segurança mais repetido
   em todo o histórico de auditorias do projeto (PROD-005 e as extensões
   Google que vieram depois).

Nenhum outro arquivo muda — nem o Tool Registry, nem o `AgentExecutor`,
nem o Cognitive Planner. Guia completo: `docs/TOOLS.md`.

## Como criar um Provider

Providers seguem Strategy + Factory — trocar de provider é configuração
(uma env var), nunca código de negócio em nenhuma outra camada.

- **WhatsApp**: implemente `WhatsAppProvider`
  (`providers/whatsapp/base.py`), registre em
  `providers/whatsapp/factory.py`, selecione com `WHATSAPP_PROVIDER=<nome>`.
  Guia dedicado e completo (contrato, exemplo mínimo, checklist de testes
  de compatibilidade obrigatório): `backend/providers/whatsapp/README.md`.
- **LLM**: implemente `LLMProvider` (`chat` com tools + `embed`) em
  `providers/llm/<nome>/provider.py`, registre em
  `providers/llm/factory.py`, selecione com `LLM_PROVIDER=<nome>`.
  Reaproveite `OpenAIProvider` por herança quando o vendor for compatível
  com a API da OpenAI (caso de GLM e Ollama).
- **Mail/Google**: seguem o mesmo padrão Strategy + Factory
  (`providers/mail/`, `providers/google/`) — use o Gmail/Calendar/
  Contacts/Drive existentes como referência antes de adicionar um domínio
  novo.

## Como escrever testes

- Backend: `pytest` + `pytest-asyncio`. `tests/conftest.py` já fornece um
  banco SQLite in-memory por teste (`db_engine` fixture) e um cliente HTTP
  autenticado (`client` fixture) — não crie infraestrutura de teste
  própria, reuse essas fixtures.
- Singletons com estado entre testes (cache, rate limiter, event bus) são
  resetados automaticamente por uma fixture `autouse` — não precisa fazer
  isso manualmente no seu teste.
- Mocke a borda externa (o cliente HTTP do provider, o `AsyncQdrantClient`),
  nunca a lógica da sua própria mudança — um teste que mocka o próprio
  código sob teste não prova nada. Ver `tests/test_memory_service_delete.py`
  e `tests/test_memory_service_search.py` como exemplo do padrão esperado.
- Frontend: Vitest + Testing Library para componentes/hooks
  (`frontend/tests/`); Playwright para fluxos de ponta a ponta reais
  contra o dev server (`frontend/e2e/`) — ver `OBSERVABILITY_GUIDE.md` e
  `frontend/playwright.config.ts` para como rodar localmente.
- Rode a suíte inteira antes de propor uma mudança:
  `cd backend && pytest`, `cd frontend && npm test && npm run e2e`.

## Como criar uma migration

```bash
cd backend
alembic revision --autogenerate -m "descrição curta"
```

- Revise sempre o arquivo gerado — o autogenerate do Alembic não detecta
  tudo (renomear coluna vira "drop + add", por exemplo).
- **Tipos `ENUM` do Postgres**: crie o tipo explicitamente na migration em
  vez de depender do `CREATE TYPE` implícito do SQLAlchemy/asyncpg — ele só
  é emitido pela primeira migration que referencia cada tipo, e uma
  migration posterior que reutilize o mesmo `ENUM` falha em qualquer banco
  que não tenha a revisão original aplicada. Ver `MIGRATION_FIX_REPORT.md`
  para o caso real que motivou esta regra.
- Teste em banco vazio (`alembic upgrade head`) e, se a migration mexe em
  dado existente, em banco parcialmente migrado também.
- `alembic check` detecta drift entre os models e o schema — rode antes
  de commitar.

## Antes de abrir um PR

1. `ruff check .` (backend) e `npx eslint . --ext .ts,.tsx` (frontend) —
   limpos.
2. `pytest` (backend) e `npm test` (frontend) — tudo passando.
3. Se a mudança toca UI: `npm run e2e` (Playwright) também.
4. `git status` limpo — nada esquecido fora do commit.
5. Descreva o que mudou e por quê — a maioria dos relatórios de sprint
   deste projeto (`SPRINT5_REPORT.md` e similares) existe justamente para
   que "por quê" nunca precise ser reconstruído por arqueologia de código.
