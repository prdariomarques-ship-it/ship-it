# Darius OS — Frente Visual (Frontend) — Status

Responsável: frente frontend (esta sessão). Escopo: recuperação do visual aprovado,
navegação, testes, pacote e preparação de implantação das telas. Não toca backend,
banco, workers, providers, prompts ou configuração produtiva — essa é a outra frente.

Branch de trabalho: `frontend/darius-os-visual`, criada a partir de
`claude/dario-os-platform-gcg6i2` @ `0fab8cb` (2026-10-07). Nenhum merge amplo de
branch foi feito — todas as comparações abaixo são leitura/inventário, não integração.

---

## Concluído (com evidência)

### 1. Branch isolada criada
`git checkout -b frontend/darius-os-visual` a partir de `claude/dario-os-platform-gcg6i2`
(commit `0fab8cb`). Nenhum arquivo de backend tocado.

### 2. Baseline real das duas branches do repositório (evidência, não suposição)

| | `master` @ `08958f1` | `claude/dario-os-platform-gcg6i2` @ `0fab8cb` |
|---|---|---|
| Next.js | **16.2.10** (Turbopack) | **14.2.21** |
| React | 18.3.1 | (ver package.json — não é o foco desta checagem) |
| `npm run test -- --run` | **339/339 passando** (50 arquivos) | **108/108 passando** (25 arquivos) |
| `npm run build` | compila limpo, 34 rotas, typecheck ok | compila limpo, 37 rotas, typecheck ok (1 warning cosmético — ver abaixo) |
| `npm run lint` | limpo | limpo |
| Último commit | 2026-09-09 | 2026-10-07 |

Comandos exatos usados (reproduzíveis):
```bash
npm ci
NEXT_PUBLIC_API_URL=/api npm run build
npm run test -- --run
npm run lint
```

Warning não-bloqueante no build da minha branch (Next 14, grupo de rotas `(dashboard)`):
`ENOENT` ao copiar `page_client-reference-manifest.js` no output `standalone` — é um
problema cosmético conhecido do Next 14 com route groups no modo standalone; o build
termina com sucesso e todas as 37 rotas são geradas. Não investighei a fundo porque
não é bloqueante e está fora do escopo desta entrega.

### 3. Inventário de rotas/componentes — master vs. minha branch

**Só existe em `master`** (ausente na minha branch — risco de perda se eu partir só
da minha branch):
- Rotas: `contatos`, `contatos/[id]`, `metas`, `notas`, `admin/action-center`,
  `admin/briefing`, `admin/timeline`, `esqueci-senha`, `redefinir-senha`
- Componentes: `AIOperatorCenter`, `ActionWorkflowControl`, `BriefingRecommendationCard`,
  `CalendarPanel`, `ContactPriorityPanel`, `CurrentContextPanel`, `GoalsPanel`,
  `HealthScoreCard`, `MemorySearch`, `PendingJobsPanel`, `PipelineActivityPanel`,
  `TasksPanel`, `TimelineEventCard`, `ui/switch`, `CalendarEventForm`,
  `ChurchMemberForm`, `GoalDetails`, `GoalForm`, `NoteForm`, **`ProductForm`,
  `ProductsPanel`, `StoreCustomerForm`** (loja/Marquescolor mais completa que a minha)
- Hooks/libs: `use-action-execution`, `use-last-login`, `use-operator-state`,
  `use-previous`, `actions.ts`, `briefing.ts`, `operator.ts`, `timeline.ts`
- 20 arquivos de teste cobrindo tudo isso (ver lista completa no diff — omitido aqui
  por tamanho)
- `eslint.config.mjs` (master já migrou pro formato flat config do ESLint 9)

**Só existe na minha branch** (ausente em `master`):
- `admin/monitors` (painel dos bots financeiros — fora do escopo desta entrega,
  não deve ir pro Darius OS visual sem decisão explícita)
- `admin/runtime` + 8 subpáginas (`api`, `audit`, `executions`, `health`,
  `performance`, `persistence`, `recovery`, `workflows`)
- `lib/drt-api.ts`, `src/utils/performance.ts`, `e2e-validation.mjs`
- `.eslintrc.json` (formato antigo do ESLint — a minha branch não migrou pro flat
  config que o master já tem)

**Em comum, substancialmente idêntico**: `frontend/hooks/useApi.ts` — contrato de
auth (token/refresh em `localStorage`, `/auth/refresh`, base `NEXT_PUBLIC_API_URL`)
é o mesmo nas duas branches. **Atenção**: isso NÃO confirma que bate com a cópia
local no Windows nem com o que está rodando na VPS — só confirma consistência
dentro deste repositório. Continua sem confirmação externa.

---

## Decisão pendente que bloqueia qualquer integração de código

**As duas branches estão em versões MAJOR diferentes do Next.js (14 vs. 16).** Isso
não é um detalhe — significa que eu não posso simplesmente copiar um componente de
uma branch pra outra sem risco de quebra (mudanças de API entre major versions do
App Router, Turbopack vs. webpack, etc.). Antes de integrar qualquer coisa de
`master` na branch de trabalho (ou vice-versa), preciso saber:

- Em qual versão do Next.js o `integracao-local-darius-os/frontend` (a cópia local
  no Windows) está?
- Em qual versão está a imagem de frontend que roda hoje em `darioos-evolution`?

Sem essa informação, qualquer "patch visual" que eu monte corre o risco de ser
incompatível com o que de fato vai pra produção.

---

## Bloqueado (pedido uma única vez, continua pendente)

1. **Visual aprovado**: conteúdo de `proposta-dario-os/index.html`, `README.md`,
   `DESIGN.md`, captura `visao-geral.jpg` — arquivos no Windows do Dário, sem
   acesso desta sessão.
2. **Estado da integração parcial**: `integracao-local-darius-os/INTEGRATION_STATUS.md`
   e o conteúdo de `integracao-local-darius-os/frontend` (especialmente `Sidebar.tsx`)
   — mesma limitação de acesso.
3. **Nome do serviço/imagem de frontend** em
   `/opt/chroma-migration-20260927/app.compose.prepared.json` — só isso, não o
   compose completo nem segredos (conforme instruído). Necessário pro plano de
   implantação (critério E).

Nenhuma tentativa repetida de acessar Windows ou VPS foi feita além da constatação
inicial already registrada na conversa — não vou insistir.

---

## Em andamento / Próximos passos (assim que o bloqueio for resolvido)

1. Com o visual aprovado em mãos: decidir a versão-alvo do Next.js pro patch visual
   (provavelmente 16, se for a mais recente e mais testada — 339 testes vs. 108 —
   mas essa decisão depende de qual versão a cópia local/VPS realmente usa).
2. Montar a navegação com Pessoal (Gêmeo Darius + Conversas pessoais), Loja/
   Marquescolor, B2B, Azusa, Investimentos, preservando as rotas listadas acima que
   hoje só existem numa das branches.
3. Implementar em partes pequenas, testando a cada parte (ciclo implementar →
   testar → revisar → corrigir), não tudo de uma vez.
4. Capturas de tela reais (desktop + mobile) assim que houver UI pra capturar.
5. Pacote de implantação (diff, hashes, comandos PowerShell + VPS separados,
   backup/rollback do serviço de frontend) — depende do item 3 do bloqueio.

---

## Critérios de conclusão (A–E) — status atual

- **A** (referência aprovada incorporada + Pessoal presente): **bloqueado**, falta a referência.
- **B** (funcionalidades preservadas ou diferenças resolvidas): inventário feito
  (acima) — resolução (decidir o que entra no patch) depende do visual aprovado.
- **C** (testes/build/revisão visual): **baseline feito** para as duas branches
  existentes (evidência acima). Revisão visual real ainda não é possível — não há
  UI do Darius OS nesta branch ainda.
- **D** (pacote com diff/hashes/base): parcial — base e commit documentados acima;
  diff de integração ainda não existe (nada foi integrado).
- **E** (plano de implantação frontend): **bloqueado**, falta nome do
  serviço/imagem real.
