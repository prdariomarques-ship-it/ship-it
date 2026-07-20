# Release Report — Upgrade Next.js 16

**Status: concluída e em produção.**
Branch: `chore/nextjs-16-upgrade` · PR: [#4](https://github.com/prdariomarques-ship-it/ship-it/pull/4) · Merge: `1ea265b` · Deploy em produção: commit `1ea265b`, imagem `darioos-frontend:latest` (`ec5ff23dcc31`).

## Objetivo da migração

Eliminar as CVEs remanescentes do Next.js 14.2.35 (`npm audit`: 1 moderada + 4 altas, sem patch disponível na série 14.x) e modernizar a stack de frontend antes de iniciar o próximo ciclo de desenvolvimento de produto (v1.5). Identificado como item 8 (Should Have) do `ROADMAP_v1_4.md`, com a exigência explícita de branch isolada e suíte de regressão completa antes de mesclar, dado o risco de breaking change de uma major version.

## Versões

| Pacote | Antes | Depois |
|---|---|---|
| next | 14.2.35 | **16.2.10** |
| @next/bundle-analyzer | ^14.2.21 | ^16.2.10 |
| eslint | ^8.57.1 | ^9.39.5 |
| eslint-config-next | ^14.2.35 | ^16.2.10 |
| react / react-dom | 18.3.1 | 18.3.1 (mantido — peerDeps do Next 16.2.10 aceitam `^18.2.0 \|\| ^19.0.0`) |
| typescript | ^5 (5.9.3) | inalterado |
| Node (imagem Docker) | `node:20-alpine` | inalterado |
| Bundler de produção | Webpack | **Turbopack** (novo padrão do `next build` no Next 16) |

Nenhum uso de `--force` ou `--legacy-peer-deps` em nenhum momento da migração.

## Dependências atualizadas (transitivas)

67 pacotes adicionados / 54 removidos em `package-lock.json` — todos identificados e confirmados como transitivos esperados da árvore do ESLint 9 / `eslint-config-next@16` (Babel toolchain, `typescript-eslint@8`, etc.). Nenhum pacote não relacionado ou suspeito encontrado na auditoria do diff.

## Breaking changes encontradas e como cada uma foi resolvida

1. **`next lint` removido do CLI do Next 16.** Confirmado via `npx next --help`. Corrigido: script `lint` em `package.json` passou a rodar `eslint .` diretamente.
2. **ESLint 8→9 exige flat config.** `.eslintrc.json` removido; criado `eslint.config.mjs` importando `eslint-config-next/core-web-vitals`.
3. **`eslint-plugin-react-hooks@7`** (trazido transitivamente por `eslint-config-next@16`) introduziu regras que capturaram **4 violações reais e pré-existentes** de Rules of Hooks:
   - `react-hooks/refs` — `use-previous.ts` lia `ref.current` durante o render. Reescrito para o padrão documentado do React de "estado derivado do render anterior" (comparação + `setState` condicional durante o render).
   - `react-hooks/set-state-in-effect` (×3) — `use-last-login.ts`, `use-operator-state.ts`: `setState` como primeira instrução síncrona de um efeito. Corrigido com inicializador preguiçoso de `useState` (`useState(readStorage)`), eliminando o efeito onde possível. `useApi.ts`: reestruturado para função `async function run()` nomeada dentro do efeito, seguindo o padrão oficial do React para fetch de dados.
   - `react-hooks/purity` — `app/admin/page.tsx` chamava `Date.now()` durante o render (dentro de um `useMemo`). Movido para `useState(() => Date.now())` com `useEffect` de resincronização; um `eslint-disable-next-line` pontual e comentado foi necessário nessa resincronização (sem trabalho assíncrono genuíno ali, decisão aprovada explicitamente).
4. **`<a href="/">` → `next/link`** em `AdminShell.tsx` (regra `no-html-link-for-pages`).
5. **Turbopack como bundler padrão do `next build`** (antes Webpack). Build compilou limpo; sinalizado como mudança de comportamento subjacente real, não erro — confirmado em produção via chunk `_next/static/chunks/turbopack-*.js`.
6. **`tsconfig.json` reescrito automaticamente pelo próprio Next** no primeiro build (`jsx: "preserve"` → `"react-jsx"`, `target: "ES2017"` adicionado, novo `include` com `.next/dev/types/**/*.ts`) — exigência mandatória do framework, mantida como está.
7. **Aviso de workspace-root ambíguo**: Turbopack detectou um lockfile solto e não relacionado em `/home/dario/package-lock.json` (fora do projeto, `{"packages": {}}` vazio) e cogitou usá-lo como raiz. Corrigido fixando `turbopack.root` em `next.config.mjs`, apontando explicitamente para o diretório `frontend/`.

## Arquivos modificados

12 arquivos, 1405 inserções / 897 remoções (`git diff master...HEAD` no momento do merge):

```
 frontend/.eslintrc.json                  |    4 - (removido)
 frontend/app/admin/page.tsx              |   20 +-
 frontend/components/admin/AdminShell.tsx |    5 +-
 frontend/eslint.config.mjs               |   10 + (novo)
 frontend/hooks/use-last-login.ts         |   17 +-
 frontend/hooks/use-operator-state.ts     |   13 +-
 frontend/hooks/use-previous.ts           |   24 +-
 frontend/hooks/useApi.ts                 |   21 +-
 frontend/next.config.mjs                 |    8 +
 frontend/package-lock.json               | 2137 +++ (transitivo)
 frontend/package.json                    |   10 +-
 frontend/tsconfig.json                   |   33 +-
```

`docker/docker-compose.yml` e `frontend/Dockerfile`: **não tocados** (confirmado via diff vazio contra master). Nenhuma mudança de arquitetura, backend, autenticação, middleware, roteamento ou providers.

## Resultados de validação

| Validação | Resultado |
|---|---|
| `npm run lint` | ✅ exit 0, zero erros/avisos |
| `npx tsc --noEmit` | ✅ exit 0, zero erros de tipo |
| `npm test -- --run` | ✅ 36 test files, **268/268 testes**, exit 0 |
| `npm run build` | ✅ Compilado com sucesso, **30/30 páginas estáticas**, exit 0, sem aviso de workspace-root |
| CI (GitHub Actions, PR #4) | ✅ 3/3 checks verdes (`backend`, `frontend`, `docker-compose-config`) |

Nenhum teste removido ou diminuído (268 testes antes e depois). Nenhuma cobertura perdida.

## Resultado do deploy em produção

Procedimento padrão do projeto (documentado em `DEPLOYMENT_REPORT.md`): rebuild + recriação isolada com `--no-deps`, restrito ao serviço `frontend`.

```bash
docker tag darioos-frontend:latest darioos-frontend:pre-nextjs16-rollback   # backup de segurança
docker compose build frontend
docker compose up -d --no-deps frontend
```

| Item | Antes | Depois |
|---|---|---|
| Commit em produção (confirmado via `GET /api/version`) | `9816877` | `1ea265b` (frontend) |
| Commit backend | `9816877` | `9816877` (**inalterado** — confirmado idêntico antes/depois) |
| Next.js em execução | 14.x (Webpack) | **16.2.10** (Turbopack, confirmado via chunk servido) |
| Imagem frontend | `b1f02f7e0450` | `ec5ff23dcc31` |
| Healthcheck | — | ✅ `healthy` ~12s após recriação |
| Logs pós-deploy | — | ✅ zero erros |
| Outros 11 serviços | — | ✅ uptimes inalterados, nenhuma reinicialização inesperada |
| Memória frontend | 41.6MiB (0.53%) | 67.55MiB (0.86%) — aumento esperado do runtime Next 16, sem impacto |
| CPU frontend | 0.01% | 0.00% |
| Tempo de resposta homepage | 0.014–0.017s | 0.011–0.016s — equivalente |
| `/health` e `/health/ready` | ok | ok (idêntico) |

Tempo total do deploy: build da imagem ~110s; recriação do container ~4s (`docker compose up -d --no-deps frontend`, do "Recreate" ao "Started").

Backup da imagem anterior (tag `pre-nextjs16-rollback`) foi mantido por um período de observação e removido posteriormente após confirmação de estabilidade, a pedido explícito do usuário (rollback a partir desse ponto exigiria rebuild via git, não troca de tag).

## Resultado do smoke test

**Pré-merge** (ambiente temporário isolado, container + Caddy temporários na rede Docker existente, backend real): homepage, navegação entre 10 rotas de dashboard, login (form + submissão), guard de `/admin` redirecionando corretamente, assets, zero exceções JS, zero erros de hidratação.

**Pós-deploy em produção** (`https://localhost`, Playwright real): 14/14 verificações aprovadas — homepage, 10 rotas de dashboard, guard de `/admin` sem sessão, navegação client-side. Zero exceções JS não tratadas, zero erros de hidratação, zero warnings do React, zero erros 404/500/CORS/rede. Único ruído de console: `401` esperado nas chamadas de API das páginas de dashboard sem sessão — padrão pré-existente, não relacionado a esta migração (essas rotas não têm guard de autenticação em `(dashboard)/layout.tsx`).

**Login/logout com sessão real: não testados em nenhuma das duas rodadas** — a única credencial fornecida durante a validação foi rejeitada pelo backend real (`401 Invalid credentials`, confirmado também via `curl` direto, sem envolvimento do frontend). Nenhuma tentativa de adivinhar senha ou contornar via usuário de teste foi feita.

## Pendências conhecidas

- **Validação funcional autenticada** (login bem-sucedido, Dashboard/Admin com sessão real, logout) segue sem cobertura de smoke test end-to-end, por falta de credenciais válidas no momento dos testes. Não é uma falha de código — é uma lacuna de validação manual a fechar quando credenciais estiverem disponíveis.
- `VERSION.json` do backend está desatualizado (commit `2a9d643`, anterior a todo o ciclo v1.4) — não foi alterado nesta tarefa por estar fora do escopo explícito (documentação/planejamento, não código de aplicação), mas fica registrado como item de higiene para o próximo ciclo.

## Riscos residuais

- **Troca de bundler (Webpack → Turbopack)** é uma mudança de comportamento real agora ativa em produção. Sem nenhum sinal de problema até o momento; recomenda-se observação continuada nos próximos dias.
- `@next/bundle-analyzer` (opt-in, `ANALYZE=true`) não foi exercitado em nenhuma validação desta migração — compatibilidade com Turbopack não confirmada.
- CSP (`Content-Security-Policy`) no Caddyfile segue pendente, bloqueada por depender de um domínio real com HTTPS para testar com segurança (não é um risco introduzido por esta migração, mas segue como debt de segurança aberto).

## Recomendações futuras

1. Repetir o smoke test cobrindo login/logout com sessão real assim que credenciais válidas estiverem disponíveis.
2. Monitorar métricas de memória/CPU do frontend nos próximos dias de uso real para confirmar que o padrão observado (leve aumento de memória) se mantém estável sob carga real, não só no smoke test.
3. Ao planejar a próxima mudança estrutural de frontend, validar `@next/bundle-analyzer` contra Turbopack antes de depender do relatório de bundle gerado por ele.
4. Atualizar `VERSION.json` do backend para refletir o commit real de produção, como parte da rotina normal de release (não urgente, não bloqueante).
