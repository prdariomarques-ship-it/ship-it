# Darius OS — Frente Visual (Frontend) — Status

Responsável: frente frontend (esta sessão). Escopo: recuperação do visual aprovado,
navegação, testes, pacote e preparação de implantação das telas. Não toca backend,
banco, workers, providers, prompts ou configuração produtiva — essa é a outra frente.

## Base (reconstruída neste ciclo — commit anterior `d83f21d` estava na base errada)

`frontend/darius-os-visual-prod-base`, criada a partir de **`master` @
`08958f1eda440c19b2595441e2c2cfee03b59037`** — não da minha branch antiga
(`claude/dario-os-platform-gcg6i2`), que não tinha Contatos, Metas, Notas,
Calendário ampliado, Action Center, Timeline, Esqueci/Redefinir senha nem a Loja
completa. `master` tem tudo isso; é a base correta.

## Por que o commit anterior (`d83f21d`) estava errado — e por que não dá pra só trocar o número do Next

1. Foi construído em cima da minha branch, não do `master` — por isso a Sidebar
   remota omitia Contatos/CRM, Metas, Notas e Briefings, e "Logs" apontava para
   `/logs` em vez de `/admin/logs` (rotas diferentes: `/admin/logs` é protegida
   pelo `AdminShell`/`useAdminGuard` em `app/admin/layout.tsx`; `/logs`, no grupo
   dashboard, não tem esse guard — hoje `/logs` apenas redireciona para
   `/admin/logs`, mas a Sidebar não deveria ter apontado pra lá em primeiro lugar).
2. `package.json`/lockfile continuavam em Next **14.2.21**. Todos os 121 testes,
   o build e as 7 capturas daquele commit foram produzidos nessa versão — não
   provam nada sobre a versão **16.3.6** real (VPS confirmada:
   `darioos-evolution`, serviço `frontend`, imagem
   `sha256:23357543fb50fd2b4e7c94454f80c85e214093f1e9cee53b44fd11376098e84a`;
   cópia local também fixa 16.3.6).

## Diff de dependências contra `master` — uma linha, confirmada

```diff
-    "next": "16.2.10",
+    "next": "16.3.6",
```

Nada mais em `package.json` difere de `master`. `package-lock.json` foi
regenerado com `npm install` em cima dessa mudança (não copiado de nenhuma cópia
externa) — reflete exatamente essa única atualização mais suas dependências
transitivas. Confirmado por leitura, não suposição:
`node -e "console.log(require('next/package.json').version)"` → `16.3.6`.

## O que foi corrigido neste ciclo (todos os pontos da revisão de código)

1. **Base/dependências**: resolvido acima — base `master`, Next 16.3.6 real,
   instalado e testado nessa versão.
2. **Home e marca**:
   - `app/layout.tsx`: `title: "Dario OS"` → `"Darius OS"`.
   - `app/login/page.tsx`: cabeçalho visível também dizia "Dario OS" (achado à
     parte, mesma categoria) → `"Darius OS"`.
   - `app/(dashboard)/page.tsx`: agora abre com "Mercados" em primeiro plano
     (estado honesto de indisponibilidade, com links para as duas páginas de
     mercado), título mudou de "Início" para "Visão geral" (consistente com o
     rótulo de navegação e com DESIGN.md). O resumo real
     (`useApi("/dashboard/summary")`) e seus estados de carregamento/erro
     continuam exatamente como estavam, abaixo da seção de mercados — não foram
     substituídos por conteúdo fictício.
3. **Navegação completa**: Sidebar reconstruída preservando literalmente tudo
   que `master` tinha (Contatos, Metas, Notas, Agenda, Calendário, Tarefas,
   Briefings→`/admin/briefing`, Igreja, Loja) mais as 3 rotas novas aprovadas
   (Mercado · Brasil, Mercado Global, Pessoal). Logs aponta para `/admin/logs`
   (a rota protegida) — nunca para `/logs`.
4. **Rotas da base**: nenhuma removida. Build lista as 34 rotas originais de
   `master` + 3 novas = 37, incluindo `/contatos`, `/contatos/[id]`, `/metas`,
   `/notas`, `/admin/action-center`, `/admin/briefing`, `/admin/timeline`,
   `/esqueci-senha`, `/redefinir-senha`, calendário com `CalendarEventForm`,
   loja com `ProductForm`/`ProductsPanel`/`StoreCustomerForm` — tudo
   inalterado, só herdando os novos tokens de cor.
5. **Menu móvel fora da ordem de Tab quando fechado** (achado real de
   acessibilidade, não só do teste): a gaveta fechada no mobile só ficava fora
   da tela via `transform`, mas seus links continuavam focáveis/tabuláveis.
   Corrigido com `inert` (mesma lógica do protótipo aprovado,
   `sidebar.toggleAttribute("inert", isMobile && !open)`, que eu tinha deixado
   de portar). Também achei e corrigi um segundo bug relacionado: o foco ao
   abrir a gaveta caía no link da marca ("Darius OS", também um `<a href="/">`)
   em vez do primeiro item de navegação — o teste que eu tinha escrito antes
   prometia essa verificação no título mas não a fazia de fato; agora faz,
   e o componente foi corrigido pra valer (não só o teste).
6. **Assets da imagem standalone** (`Dockerfile`):
   - `npm install` sem lockfile → `npm ci` com `package-lock.json` copiado
     (build reproduzível).
   - `public/` (contém `sw.js`, o service worker, e o favicon) nunca era
     copiado pro estágio final → adicionado `COPY --from=builder /app/public
     ./public`. Sem isso, a imagem subiria sem esses assets.
   - **Limitação declarada**: não consegui rodar `docker build` de verdade
     neste ambiente (daemon Docker não sobe aqui — `dockerd`/cgroups sem
     permissão no sandbox). Validei o equivalente funcional manualmente:
     reproduzi exatamente os três passos `COPY` do Dockerfile corrigido num
     diretório separado e rodei `node server.js` a partir dele — confirmei
     `sw.js` servido (200) e o app funcionando. Isso prova a lógica dos passos,
     não substitui um build Docker real — fica registrado como pendência pra
     quem tiver acesso a um daemon Docker confirmar.

## Evidência rodada neste ciclo (comandos exatos, Next 16.3.6 real)

```bash
npm install                                 # Next 16.2.10 → 16.3.6, lockfile regenerado
npm run test -- --run                       # 356/356 passando (53 arquivos)
NEXT_PUBLIC_API_URL=/api npm run build      # compila limpo (Turbopack), typecheck ok, 37 rotas
npm run lint                                # sem avisos
```

Capturas reais tiradas contra o equivalente funcional da imagem standalone
corrigida (não `next dev`): Visão geral (mercados em primeiro plano + resumo
real + erro real sem backend), Contatos, Metas, Notas, `/admin/briefing`
(corretamente redirecionado para `/login` pelo guard — confirma a proteção
funcionando), Pessoal, Igreja (existente, visual herdado sem tocar código),
Login (marca corrigida), mobile fechada e com a gaveta aberta. Todas revisadas
uma a uma antes deste relatório.

## Não feito / fora do escopo desta entrega (declarado)

- Marca "Dario OS" ainda aparece em páginas dentro de `/admin/*`
  (`AdminSidebar.tsx`, `admin/layout.tsx`, `admin/users`, `admin/page.tsx`,
  `admin/timeline`) — não tocado: é uma superfície própria (painel
  administrativo interno), com seu próprio Sidebar/CSS, fora do que a revisão
  pediu especificamente (`app/layout.tsx` + a experiência do grupo dashboard).
  Sinalizando para decisão explícita, não corrigindo por conta própria.
- Nenhuma implantação, nenhum container na VPS tocado.
- Plano de implantação/reversão do frontend continua bloqueado no contrato
  real do Compose de produção (nome do serviço e imagem já confirmados;
  falta o trecho sanitizado de rede/healthcheck/volumes do serviço
  `frontend` em `app.compose.prepared.json` para escrever o plano sem
  adivinhar nada).

## Ciclo 3 — contexto Docker, bug de foco mobile→desktop, build Docker real

1. **Contexto Docker limpo**: criado `frontend/.dockerignore` (não existia
   nenhum antes — `COPY . .` no Dockerfile enviava `node_modules`, `.next`,
   testes e qualquer `.env*` local pro contexto de build sem filtro nenhum).
   Exclui `node_modules`, `.next`, `.turbo`, `.git`, `.env`/`.env.*`,
   chaves/certificados (`*.pem`, `*.key`, `*.crt`), e ferramentas só de
   desenvolvimento não lidas por `next build` (`tests/`, `e2e/`,
   `playwright.config.ts`, `vitest.config.ts`, `coverage/`,
   `tsconfig.tsbuildinfo`). Revisado item a item contra o que `next build`
   de fato precisa (`app/`, `components/`, `hooks/`, `lib/`, `public/`,
   `styles/`, configs e `package*.json`) — nada necessário ficou de fora;
   confirmado rodando o build real dentro do container (abaixo).

2. **Bug real de foco reproduzido e corrigido**: abrir a gaveta no mobile e
   depois ampliar a janela pra desktop sem clicar em "Fechar navegação"
   deixava o aprisionamento de Tab do teclado ativo pra sempre — o efeito
   que intercepta Tab só reagia a `mobileOpen`, nunca ao viewport ter
   mudado, então o usuário ficava travado dentro da nav mesmo no layout de
   desktop (sem gaveta, sem botão de fechar visível). Reproduzido com um
   teste que primeiro comprova a armadilha ativa no mobile (focar o último
   link, apertar Tab, `defaultPrevented` vira `true`, foco volta pra marca),
   depois simula o alargamento (`matchMedia` disparando `change` pra
   `matches:false`) e comprova que o mesmo Tab já não é mais interceptado
   (`defaultPrevented` fica `false`) — `frontend/tests/Sidebar.test.tsx`,
   teste "releases the Tab trap when the viewport widens to desktop...".
   Confirmei que esse teste falha de verdade contra o componente anterior
   (reapliquei o `Sidebar.tsx` do commit `978d756` temporariamente e rodei
   só esse teste: falhou) antes de aceitar a correção como válida.
   **Correção em `Sidebar.tsx`**: unificado o rastreio de viewport num só
   efeito (`isMobile`, via `matchMedia`) que também reseta `mobileOpen` para
   `false` ao cruzar para desktop — não existe "gaveta aberta" fora do
   mobile, é a sidebar estática sempre visível. O efeito de `inert` e o de
   captura de Tab/Escape passam a depender desse `isMobile` compartilhado
   em vez de cada um reimplementar sua própria leitura de `matchMedia`.

3. **Testes, lint e build depois da correção**: `357/357` testes (356 + o
   novo teste de reprodução), `npm run lint` sem avisos, `npm run build`
   limpo com as mesmas 37 rotas de antes (nenhuma rota afetada pela
   correção, que é só no componente de navegação).

4. **Build Docker isolado + smoke test — executado de verdade nesta
   rodada** (o daemon Docker, indisponível nas rodadas anteriores, subiu
   nesta sessão). `npm ci` falhou duas vezes dentro do container com
   `SELF_SIGNED_CERT_IN_CHAIN` contra `registry.npmjs.org` — não é um
   defeito do Dockerfile/lockfile: é o proxy de saída deste sandbox, que
   intercepta TLS e cujo certificado os containers não recebem por padrão
   (documentado em `/root/.ccr/README.md`, seção "docker build": "Processes
   inside containers cannot reach 127.0.0.1:34079 and do not trust the
   CA"). Para validar o pipeline sem alterar o Dockerfile de produção (a
   VPS não tem esse proxy e não precisa dessa CA), fiz um build único com
   uma variante local (`Dockerfile.sandboxtest`, nunca commitada, apagada
   junto com a cópia temporária da CA ao final) que só adiciona
   `NODE_EXTRA_CA_CERTS` apontando pro bundle do proxy durante o `npm ci`,
   com `--network host`:
   - `docker build --no-cache --network host -f Dockerfile.sandboxtest ...`
     → build completo, mesmas 37 rotas, sem erro de TypeScript/lint.
   - Smoke test num container isolado, porta `18080` (nenhum serviço
     existente tocado — `docker ps` confirmado vazio antes e depois):
     - `GET /` → `200`, contém "Darius OS" e "Visão geral".
     - `GET /login` → `200`, contém "Darius OS".
     - `GET /sw.js` → `200`, `content-type: application/javascript` (o
       gap de `public/` não copiado, achado e corrigido num ciclo
       anterior, confirmado agora contra um build Docker real, não só o
       equivalente manual).
     - `GET /admin/briefing` → `200` (shell protegido server-side; o guard
       de autenticação roda no client, como testado nas capturas).
     - `GET /pessoal` → `200`, contém "Gêmeo Darius" (estado honesto, sem
       fetch).
     - CSS real do Turbopack (`/_next/static/chunks/26c4kh0ln7dy-.css`) →
       `200`.
     - Logs do container sem erro, só o boot normal do Next.
   - Container, imagens de teste (`darius-os-frontend:sandbox-smoke`,
     imagens de debug) e os arquivos auxiliares do sandbox foram removidos
     ao final; nada disso foi commitado. O `.dockerignore` adicionado ao
     repositório é real e permanente — o `Dockerfile.sandboxtest` não é.

5. **Implantação continua não realizada.** Plano de troca/reversão
   somente do frontend ainda depende do contrato real do Compose de
   produção — ver "Não feito" acima.

## Critérios de conclusão (A–E)

- **A**: feito — visual aprovado, marca Darius OS, Pessoal presente e protegido.
- **B**: feito — todas as rotas de `master` preservadas (nenhuma substituição de
  base), verificado por build + capturas, não só por não ter deletado arquivo.
- **C**: feito — 357/357 testes, build/lint limpos, capturas revisadas, TUDO
  rodado na versão real de produção (16.3.6), não mais 14.2.21.
- **D**: feito — base `master@08958f1`, diff de 1 linha em dependências,
  commit abaixo.
- **E**: feito — Dockerfile corrigido e agora validado por um build Docker
  real (não só equivalente manual) mais smoke test num container isolado;
  `.dockerignore` adicionado. Falta só o plano de implantação/reversão em
  si, bloqueado no contrato do Compose de produção (campos sanitizados
  pendentes, não segredos).
