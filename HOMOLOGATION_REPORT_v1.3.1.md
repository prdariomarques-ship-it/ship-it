# Homologação Funcional (UAT) — Dario OS v1.3.1

Data: 2026-07-18. Fase de Homologação Funcional formal — o produto avaliado como um todo, não como componentes isolados. Nenhuma correção foi feita durante esta rodada; este relatório é para revisão antes de qualquer ação.

## Metodologia

- **Navegador real**: Chromium headless via Playwright, entrando por `https://localhost/` (Caddy, a mesma porta que um usuário real acessaria), login pela UI (não API direta).
- **Duas resoluções por tela**: desktop (1440×900) e mobile (390×844, iPhone-sized) — para cobrir "responsividade básica" como pedido.
- **Por tela**: navegação real (clique/redirect, não URL direta quando evitável), espera de rede ociosa, screenshot full-page nas duas resoluções, captura de erros de console/exceções JS, captura de qualquer resposta `/api/*` com status ≥400, tempo de carregamento.
- **17 fluxos pedidos**, mapeados pra rotas reais (alguns fluxos cobrem mais de uma tela): ver seção "Por módulo".
- Achados de UX visual (contraste, densidade, hierarquia) e o texto de cada tela foram lidos diretamente nos screenshots, não inferidos.

## Resumo executivo

| | |
|---|---|
| Módulos avaliados | 17 |
| Módulos **aprovados** (sem achado P0/P1) | 17 |
| Módulos **reprovados** (achado P0/P1, bloqueia ou quebra funcionalidade) | **0** |
| HTTP 200 em todas as rotas testadas | ✅ (exceto o redirect intencional `/logs` → `307`) |
| Erros de console/JS em qualquer tela | ✅ Zero |
| Chamadas `/api/*` com erro (≥400) | ✅ Zero |
| Achados novos nesta rodada (P2/P3) | 6 (detalhados abaixo) — nenhum inédito crítico; a maioria já registrada no relatório anterior e ainda não corrigida (por escopo, não por descuido) |

**Nenhum módulo bloqueia ou quebra o uso do produto.** Todos os achados abaixo são P2 (inconsistência de UX) ou P3 (polimento), não P0/P1.

## Por módulo

| # | Módulo | Rota(s) | Status | Observações |
|---|---|---|---|---|
| 1 | Login | `/login` | ✅ Aprovado | Formulário simples, funciona em desktop e mobile, submete e redireciona corretamente. |
| 2 | Dashboard inicial | `/` | ✅ Aprovado | Dados reais corretos (Contatos: 1, Mensagens: 1). Mobile ok. |
| 3 | Conversas | `/conversas` | ✅ Aprovado com ressalva | **P2** (achado #1 abaixo): tabela estoura a largura no mobile; **P2** (achado já conhecido, não corrigido): contato mostrado como ID cru. |
| 4 | Memory Timeline | `/admin/timeline` | ✅ Aprovado | As 3 colunas empilham perfeitamente no mobile — melhor comportamento responsivo observado nesta rodada. |
| 5 | Analytics | `/analytics` | ✅ Aprovado | Labels em português (corrigido na rodada anterior), confirmado ainda correto após redeploy. |
| 6 | Agenda | `/agenda` | ✅ Aprovado com ressalva | **P2** (achado já conhecido): sem botão de criar evento. Estado vazio, não testável com dado real. |
| 7 | Tarefas | `/tarefas` | ✅ Aprovado com ressalva | **P2**: sem botão de criar tarefa (Metas tem o padrão equivalente). |
| 8 | Loja | `/loja` | ✅ Aprovado com ressalva | **P2**: sem botão de criar cliente. |
| 9 | Igreja | `/igreja` | ✅ Aprovado com ressalva | **P2**: sem botão de criar membro. |
| 10 | Calendário | `/calendario` | ✅ Aprovado com ressalva | **P2**: sem botão de criar; sobreposição conceitual com Agenda não esclarecida (achado #4 abaixo). |
| 11 | Configurações | `/configuracoes` + `/admin/settings` | ✅ Aprovado | Ambas corrigidas na rodada anterior — confirmado ainda corretas após redeploy. |
| 12 | WhatsApp | `/admin/whatsapp` | ✅ Aprovado | "Conectado", provider=openwa. Mobile ok. |
| 13 | Google Workspace | `/admin/google` | ✅ Aprovado | Desconectado corretamente reportado (sem credenciais configuradas — esperado). Mobile ok. Botões "Reconnect" não clicados (disparariam OAuth real). |
| 14 | Administração | `/admin` + 8 subpáginas (Agents, Tools, Users, Metrics, System, Briefing, Action Center, Memory) | ✅ Aprovado com ressalva | **P2** (achado #2 abaixo): tabelas com muitas colunas (ex: Tools) estouram no mobile. **P3**: Commit/Branch/Tag ainda "não disponível" em System (achado já conhecido, não corrigido). Drawer mobile testado e **funciona** (abre/fecha corretamente, clique real, não só CSS). |
| 15 | Logs | `/admin/logs` (+ `/logs` redireciona) | ✅ Aprovado | Redirect confirmado (`307`) funcionando ao vivo. Filtro/busca/exportar ok em mobile. **P3**: mensagem de log truncada em uma linha no mobile, sem quebra. |
| 16 | Execuções | `/admin/executions` | ✅ Aprovado | Investigado o achado anterior de job "preso em queued" — **não é bug** (achado #6 abaixo, com evidência do banco). |
| 17 | Busca global | — | ⚪ Não existe | Confirmado por busca no código-fonte (nenhuma rota/componente de busca). Nenhum fluxo existente depende disso — não implementado, por regra desta fase. |

## Achados desta rodada (novos ou reavaliados)

### P2 — Inconsistência de UX

1. **Tabelas estouram a largura no mobile, sem indicação de scroll.** `/conversas` (`ResourceTable`, usado também por Agenda/Loja/Tarefas/Igreja) e `/admin/tools` (tabela do design system admin) — confirmado visualmente: colunas à direita ficam cortadas na borda da tela em 390px, sem barra de rolagem visível nem indicação de que há mais conteúdo. Afeta **os dois** sistemas de design do produto, não é isolado a uma página. Screenshot: `docs/qa/2026-07-18-uat/03_conversas__conversas__mobile.png`, `14_administracao__admin_tools__mobile.png`.
2. **Navegação mobile do grupo "dashboard" sem indicação visual de que rola horizontalmente.** A sidebar vira uma barra horizontal com `overflow-x: auto` abaixo de 860px (`styles/globals.css:90-108`) — **testei e confirmei que funciona** (rolagem revela Analytics/Logs/Configurações/Admin, `docs/qa/2026-07-18-uat/mobile_nav_scrolled_right.png`), mas não há nenhum indício visual (gradiente, seta, "mais →") de que dá pra rolar. Um usuário real pode não descobrir sozinho que 9 dos 12 itens do menu estão fora da tela inicial. Contraste: a área `/admin/*` tem um menu-hambúrguer com drawer completo (testado, funciona) — as duas áreas do produto resolvem o mesmo problema de forma bem diferente.
3. **`/analytics` teve seu achado de idioma corrigido; achados de UX antigos ainda presentes, não corrigidos nesta rodada** (fora do escopo desta homologação, que é registrar antes de corrigir): sem botão de criação em Agenda/Calendário/Tarefas/Loja/Igreja; `/conversas` mostra o contato como ID numérico cru.
4. **Agenda e Calendário parecem cobrir o mesmo conceito** ("Seus eventos e compromissos" vs. "Seus eventos organizados por dia") sem diferença de funcionalidade visível (ambos vazios, não dá pra confirmar comportamento real com dado). Precisa de decisão de produto, não é algo que eu deva unificar sozinho.

### P3 — Polimento

5. Mensagem de log cortada em uma linha no mobile (`/admin/logs`), sem quebra de texto.
6. **Reavaliado, não é bug**: o job `observation.tick` que aparecia "preso em queued" no relatório anterior — confirmei direto no banco (`jobs` table): cada job é criado `QUEUED` no início do ciclo (~5 min) e só vira `SUCCEEDED` no exato momento em que o próximo é criado. Ou seja, ele passa **o ciclo inteiro** mostrando "queued" por design, não é uma trava. Único nitpick: o rótulo "queued" é um pouco enganoso pra algo que na prática está "rodando" — puramente semântico, não funcional.
7. Cabeçalho do admin no mobile ("atenção necessária") quebra em duas linhas, ficando um pouco espremido ao lado do ícone de hambúrguer/voltar — não quebra, só fica visualmente apertado.
8. Header do admin no mobile mostra o e-mail completo (`prdariomarques@gmail.com`) ao lado do "atenção necessária" já quebrado em 2 linhas — competição de espaço, não testei se teria uma versão mais compacta.

## Screenshots

55 capturas em `docs/qa/2026-07-18-uat/` — nomeadas `<fluxo>__<rota>__<desktop|mobile>.png`, mais `mobile_nav_scrolled_right.png` e `admin_mobile_drawer_open.png` (evidência de que os dois padrões de navegação mobile funcionam de fato, não só na teoria).

## Percentual estimado de conclusão do produto

**~88%.**

Como cheguei nisso: zero achados P0/P1 em qualquer um dos 17 fluxos pedidos — tudo carrega, navega e funciona sem erro. O que falta pra 100% é inteiramente polimento e consistência (P2/P3): dois sistemas de design coexistindo sem convergência, um padrão de ação (criar item) presente em 1 de 6 telas de listagem equivalentes, tabelas que não se adaptam a mobile, e uma decisão de produto pendente (Agenda vs. Calendário). Nenhum desses impede um usuário de operar o sistema hoje — todos são sobre o quão polida e consistente é a experiência, não sobre se ela funciona.

## Recomendação

Nenhuma correção nesta rodada, conforme pedido. Se for corrigir a seguir, sugiro nesta ordem (maior impacto de UX por menor risco primeiro):
1. Indicação visual de scroll na navegação mobile do grupo dashboard (achado #2) — mudança pequena, resolve uma navegação genuinamente não-descobrível.
2. Scroll horizontal contido (com indicação) nas tabelas em mobile (achado #1) — mesmo padrão, dois lugares.
3. Decisão de produto sobre Agenda vs. Calendário (achado #4) antes de mexer em qualquer um dos dois.
4. Botão de criar nas 5 telas que não têm (replicar o padrão já existente em Metas) — maior escopo, ainda assim baixo risco por já ter um exemplo funcionando no próprio produto.
