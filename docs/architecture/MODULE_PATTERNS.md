# Dario Platform — Engineering Guide

Práticas de engenharia de produção para todo módulo novo da Dario
Platform. Este documento estende, no nível de plataforma, as convenções
que `CONTRIBUTING.md` (raiz do repositório) já estabelece no nível do
Core — não as substitui. Para decisões arquiteturais, ver
`ARCHITECTURE_DECISIONS.md` (raiz) e `ARCHITECTURE_FINAL.md` (raiz).

## Antes de qualquer módulo novo: o teste obrigatório

Todo RFC em `research_lab/` que toque fronteira entre Core e módulo,
contrato de Event Bus, ou modelo de dado compartilhado, responde
explicitamente, como seção obrigatória do próprio documento:

> **"Esta alteração aproxima ou afasta a Dario Platform da visão de
> longo prazo?"**

Isso é critério de aceite do RFC, não reflexão informal do arquiteto do
momento. Um RFC sem essa seção respondida não está pronto para revisão.

## CI

Continua um pipeline único enquanto couber no tempo de execução
aceitável (hoje: lint + testes + migrações no backend, build no
frontend, por PR — ver `CONTRIBUTING.md`).

Quando o número de módulos justificar: CI por caminho de arquivo
alterado para a suíte específica do módulo — mas a suíte completa do
Core roda **sempre**, em todo PR, independente do que mudou, porque Core
é a dependência compartilhada de tudo.

**Item de trabalho nomeado, não implementado**: lint de importação que
falha o build se `backend/orchestrator/**` (ou qualquer pacote do Core)
importar algo de `backend/business/**` ou qualquer outro módulo —
enforça AD-002 automaticamente em vez de depender só de revisão manual.

## Testes

- Mesma disciplina já documentada em `CONTRIBUTING.md` se estende a cada
  módulo: mockar a borda externa (Provider), nunca a própria lógica sob
  teste.
- **Testes de contrato** entre Core e módulo — garantem que o payload de
  um evento do Event Bus que um módulo consome não muda de formato
  silenciosamente. Sem isso, o desacoplamento do Event Bus vira fonte de
  bugs de integração invisíveis em tempo de compilação.
- Todo módulo novo mantém sua própria suíte em `<módulo>/tests/`, seguindo
  o mesmo padrão de fixtures (`conftest.py`) já usado no Core.

## E2E (Playwright)

**Lição já vivida no Core, aplicada daqui para frente**: a suíte E2E
roda contra build de produção (`npm run build && npm start`), nunca
contra `next dev`. A flakiness observada em sprints anteriores veio do
dev server recompilando sob demanda no cold start — não de bug de
aplicação. Rodar contra build de produção elimina essa classe inteira de
falso negativo antes que vire ruído normalizado.

## Feature flags

Todo módulo novo nasce atrás de uma flag (padrão env-var, mesmo estilo
de `OTEL_ENABLED` já usado no Core) — habilitável/desabilitável sem novo
deploy (AD-007). Especialmente importante para módulos de maior risco
(Investments): permite ligar em modo restrito, observar, desligar
instantaneamente sem reverter código.

## Migrações

Ver DEC-5 em `ARCHITECTURE_DECISIONS.md` (raiz): uma única
história do Alembic, revisões prefixadas por módulo, disciplina
expand-contract obrigatória (coluna nova nullable → backfill →
obrigatória em release seguinte).

## Rollback

Mudança de módulo = reverter código + redeploy do container, contanto
que as migrações do módulo sigam expand-contract. Nenhuma extração para
serviço próprio deveria ser necessária para reverter um módulo
problemático — é exatamente o que a decisão de monolito modular (AD-001)
compra em troca de não ter escalabilidade independente por módulo desde
o dia um.

## Providers — integração externa

Toda integração externa nova é Strategy+Factory (AD-004). Nenhum router
ou service de módulo importa um SDK de terceiro diretamente — só a
implementação do Provider correspondente pode. Ver
`MODULE_CATALOG.md` (raiz) para as integrações já disponíveis no
ambiente de desenvolvimento (HubSpot, Canva, Adobe, Figma, Gamma) e
onde cada uma se encaixa.

## Observabilidade

Convenção de métrica `darioos_<módulo>_*` (ver AD-006). Correlation ID
por requisição HTTP já existe e se herda automaticamente — o gap de Flow
ID para fluxos multi-etapa (Event Bus + fila de jobs) está registrado
como decisão parcial em AD-006, não resolvido ainda.

## Antes de abrir um PR de módulo

Mesma lista de `CONTRIBUTING.md`, aplicada por módulo:

1. `ruff check .` / `npx eslint . --ext .ts,.tsx` — limpos.
2. Suíte do módulo + suíte completa do Core — tudo passando.
3. Se a mudança toca UI: Playwright contra build de produção também.
4. `git status` limpo — nada fora do escopo do módulo incluído no PR.
5. Revisão de diff confirmando AD-002 (nenhum import de Core → módulo).
6. Descrição do PR responde a pergunta obrigatória desta guia, se o PR
   tocar fronteira entre módulos.
