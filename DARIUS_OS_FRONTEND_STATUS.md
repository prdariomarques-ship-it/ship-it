# Darius OS — Frente Visual (Frontend) — Status

Responsável: frente frontend (esta sessão). Escopo: recuperação do visual aprovado,
navegação, testes, pacote e preparação de implantação das telas. Não toca backend,
banco, workers, providers, prompts ou configuração produtiva — essa é a outra frente.

Branch de trabalho: `frontend/darius-os-visual`, criada a partir de
`claude/dario-os-platform-gcg6i2` @ `0fab8cb` (2026-10-07). Nenhum merge amplo de
branch foi feito.

---

## Referência aprovada recebida (ciclo 2)

Pacotes enviados pelo Dário (4 zips; 3 eram cópias idênticas — mesmo md5 — do mesmo
arquivo, então só havia 2 pacotes distintos na prática):

- `proposta-dario-os`: `index.html`, `styles.css`, `app.js`, `README.md`,
  `DESIGN.md`, `visao-geral.jpg` (declarada desatualizada pelo próprio README —
  anterior à marca Darius OS e à área Pessoal; não usada como referência visual).
- `integracao-local-darius-os`: `INTEGRATION_STATUS.md`, `Sidebar.tsx`,
  `package.json`, `package-lock.json`.

Confirmado por leitura destes arquivos: Next.js **16.3.6**, React **18.3.1** — nem
14.2.21 (minha branch) nem 16.2.10 (`master`). Nenhuma das duas branches do
repositório é, portanto, a base exata da cópia local — ponto que o Dário já havia
sinalizado antes de eu pedir. Não tentei adivinhar a origem/commit exato; segui
usando a branch de trabalho como base de implementação (ela já tinha a maior parte
da estrutura de rotas) e portei o desenho aprovado para dentro dela.

---

## Concluído (com evidência)

### 1. Shell + navegação Darius OS implementados

- `styles/globals.css`: tokens de cor trocados para a paleta aprovada (fundo cinza
  claro, superfícies brancas, navy `#14293d`, teal `#117467`, âmbar `#8a5000`
  reservado a "dado desatualizado", vermelho reservado a erro). Como todo o app já
  usava essas variáveis (`--bg`, `--surface`, `--accent` etc.) em `.card`, `.badge`,
  `.button`, `.stat-card`, tabelas — **nenhuma página existente precisou ter seu
  JSX alterado** para herdar o novo visual. Adicionadas também as classes próprias
  da Sidebar aprovada (`.sidebar-wrap`, `.sidebar-group`, `.sidebar-link`,
  `.sidebar-link-disabled`, `.brand`, `.mobile-menu-toggle`, `.sidebar-backdrop`) e
  duas variantes de badge (`.badge-stale` âmbar, `.badge-error` vermelho) + um
  `.empty-state` para os estados "sem dado ainda".
- `components/Sidebar.tsx`: substituída pela versão aprovada (gaveta móvel com
  Escape, foco devolvido ao botão, `aria-current`), com dois ajustes
  deliberados e documentados no próprio arquivo: grupo SISTEMA ganhou "Runtime"
  (`/admin/runtime`, existe nesta branch) e **o painel de bots financeiros
  (`/admin/monitors`) foi deixado de fora da navegação**, por instrução explícita
  de não misturar essa frente.
- Três rotas novas: `/mercado-brasil`, `/mercado-global`, `/pessoal` — conteúdo
  honesto de indisponibilidade (nunca número, cotação ou conversa inventados),
  nenhuma chamada de API (comprovado em teste, não só por leitura do código).

### 2. Proteção da área Pessoal preservada exatamente como instruído

"Gêmeo Darius" e "Conversas pessoais" **não são links** — são `<span aria-disabled>`
com o motivo real escrito (vindo do `INTEGRATION_STATUS.md`: rota dedicada
inexistente; `GET /messages` não filtra por usuário/instância). A página `/pessoal`
repete os dois motivos por extenso, também sem link de saída e sem chamar API.
Testado explicitamente (`tests/Sidebar.test.tsx`, `tests/PersonalArea.test.tsx`):
nenhum `fetch` acontece, os dois itens nunca aparecem como `role="link"`.

### 3. Bug real encontrado e corrigido (fora do que eu vim pra construir, mas dentro do escopo de navegação)

`frontend/app/page.tsx` (criado num commit de julho, `56d3367`, pra "resolver" um
404) reexportava o componente de `(dashboard)/page.tsx` **por fora** do grupo de
rotas `(dashboard)` — ou seja, a URL `/` nunca passou pelo `(dashboard)/layout.tsx`,
nunca mostrou a Sidebar, desde julho, independente de qualquer coisa feita aqui.
Confirmei isso rodando o build de produção de verdade (servidor standalone, não só
`next dev`) e inspecionando o HTML servido — a Sidebar simplesmente não estava lá.
Removi o arquivo (uma linha, só reexport, sem lógica própria); `(dashboard)/page.tsx`
passou a servir `/` normalmente. Esse mesmo bug também causava o warning cosmético
de build que eu tinha registrado como "não investigado" no ciclo anterior — as duas
coisas tinham a mesma causa raiz; o warning sumiu depois da correção.

### 4. Testes novos (todos passando, rodados de verdade)

`tests/Sidebar.test.tsx`, `tests/PersonalArea.test.tsx`, `tests/MarketPlaceholder.test.tsx`
— cobrem: grupos/rótulos de navegação, estado ativo, Gêmeo Darius/Conversas
pessoais nunca viram link, painel financeiro ausente da navegação, gaveta móvel
abre/fecha, Escape fecha e devolve foco ao botão, nenhuma das três páginas novas
chama `fetch`, nenhuma mostra valor com formato de cotação.

Durante a escrita destes testes, 3 falhas reais apareceram e foram corrigidas no
teste (não no componente — a ambiguidade era da asserção, não um bug): o botão de
alternância e o backdrop dividem o mesmo `aria-label` quando abertos ("Fechar
navegação"), e `.closest("span")` pegava o span errado (o de dentro, não o
`aria-disabled`). Corrigido com seletores mais específicos, sem enfraquecer o que
a asserção verifica.

### 5. Evidência rodada (comandos exatos, resultados reais)

```bash
npm run test -- --run     # 121/121 passando (28 arquivos)
NEXT_PUBLIC_API_URL=/api npm run build   # compila limpo, typecheck ok, 39 rotas, SEM warning de trace
npm run lint               # sem avisos
```

### 6. Validação visual real (capturas de tela, servidor de produção real)

Build de produção real, servidor standalone (`node .next/standalone/server.js` —
não `next dev`), navegador Chromium via Playwright, duas viewports (1440×900
desktop, 390×844 mobile). Sete capturas tiradas e conferidas uma a uma antes de
declarar sucesso — a primeira rodada, por sinal, mostrou o app **sem nenhum CSS
aplicado** (engano meu copiando os assets estáticos pro build standalone sem
sobrescrever o diretório já existente) e foi isso que também expôs o bug do item 3.
Corrigido, as capturas finais mostram: sidebar navy com os grupos corretos, item
ativo em teal, Gêmeo Darius/Conversas pessoais e B2B visivelmente desabilitados
com o motivo, Mercado · Brasil com o estado âmbar "sem dado ao vivo", página Igreja
(já existente) herdando o novo visual claro sem nenhuma mudança no seu próprio
código, gaveta móvel abrindo/fechando corretamente. Erro real e não fabricado
("Erro: Request failed: 404") aparece onde a página tenta buscar dados reais e não
há backend disponível neste ambiente — não escondido, não maquiado.

Arquivos das capturas (enviados ao Dário junto com este relatório):
`desktop-01-visao-geral.png`, `desktop-02-pessoal.png`, `desktop-03-mercado-brasil.png`,
`desktop-04-mercado-global.png`, `desktop-05-igreja-existente.png`,
`mobile-01-visao-geral-fechada.png`, `mobile-02-gaveta-aberta.png`.

---

## Não feito nesta entrega (declarado, não escondido)

- **Reconciliação com `master`**: as rotas exclusivas de `master` (contatos, metas,
  notas, calendário próprio de eventos, action-center, briefing, timeline, loja com
  formulários completos) continuam fora desta branch. Não copiei nada de lá —
  decisão explícita de não fazer merge amplo. Ficam listadas no inventário do
  ciclo anterior (abaixo) como pendência a resolver numa próxima rodada, se for
  o caso.
- **Versão do Next.js real da VPS/darioos-evolution**: ainda não confirmada por
  mim. A cópia local está em 16.3.6; minha branch de trabalho continua em 14.2.21
  (não fiz upgrade — trocar a versão do Next.js é uma mudança estrutural grande
  demais pra decidir sozinho dentro de uma entrega visual, e o usuário
  explicitamente pediu pra não tratar `master`/16.2.10 como equivalente à imagem
  16.3.6). Isso **bloqueia o plano de implantação real** — ver critério E abaixo.
- **Nome do serviço/imagem de frontend** em `app.compose.prepared.json` — ainda não
  recebido. Sem isso não escrevo comandos de implantação fingindo saber o alvo.
- Login (`/login`) não foi tocado — fora do grupo `(dashboard)`, mantém seu visual
  atual; eu intencionalmente não ampliei o escopo pra essa página nesta rodada.

---

## Bloqueio atual (um único pedido, preciso)

**Nome do serviço de frontend e da imagem** em
`/opt/chroma-migration-20260927/app.compose.prepared.json` (só isso — não o compose
completo, sem `.env`, token ou senha) — é o único dado que falta pra eu preparar o
pacote de implantação real (critério E) em vez de um comando genérico.

---

## Critérios de conclusão (A–E) — status atual

- **A** (referência aprovada incorporada + Pessoal presente): **feito** — Sidebar,
  shell e as 3 rotas novas usam o desenho/wording aprovados; Pessoal visível e
  protegido como instruído.
- **B** (funcionalidades preservadas ou diferenças resolvidas): preservado tudo que
  já existia nesta branch (nenhuma rota/página removida, só um arquivo-bug
  corrigido); diferenças com `master` seguem documentadas, não resolvidas por
  decisão (não fazer merge amplo).
- **C** (testes/build/revisão visual): **feito** — 121/121 testes, build e lint
  limpos, 7 capturas reais revisadas.
- **D** (pacote com diff/hashes/base): branch `frontend/darius-os-visual`,
  commit-base `0fab8cb`; diff resumido acima; hash do commit desta entrega no
  histórico do git após o commit deste ciclo.
- **E** (plano de implantação frontend): **bloqueado** — falta o nome real do
  serviço/imagem.
