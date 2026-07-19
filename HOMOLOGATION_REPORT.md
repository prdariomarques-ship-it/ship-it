# Homologação Funcional — Dario OS

Data: 2026-07-18. Homologação funcional completa, navegando a aplicação como um usuário real navegaria — sem procurar bugs de infraestrutura, sem implementar nada. Nenhum código foi alterado durante esta homologação.

## Metodologia

- **Entrada real do usuário**: `https://localhost/` (via Caddy, a mesma porta 80/443 que qualquer usuário acessaria — não `frontend:3000` direto).
- **Navegador real, não `curl`**: Chromium headless via Playwright (já instalado como devDependency do frontend, `frontend/node_modules/playwright` + `~/.cache/ms-playwright`), viewport 1440×900.
- **Login real pela UI**: preenchi o formulário em `/login` (não chamei a API direto). A senha da conta admin (`prdariomarques@gmail.com`, criada em `BOOTSTRAP_ADMIN.md`) precisou ser resetada porque a original nunca foi armazenada — mesmo processo já documentado ali (hash via `auth/password.hash_password()` direto no banco, não é mudança de código/schema).
- **Para cada uma das 27 telas**: naveguei, esperei a rede ficar ociosa (`networkidle`), capturei screenshot full-page, registrei erros de console (`console.error`, exceções não tratadas) e qualquer resposta HTTP `/api/*` com status ≥400, e medi o tempo entre o início da navegação e `networkidle`.
- **Script usado**: `qa_run.js` (Playwright), não commitado — ferramenta de execução desta homologação, não parte do produto.

## Resumo executivo

| | |
|---|---|
| Telas navegadas | 27 (+ tela de login) |
| HTTP 200 em todas | ✅ Sim — nenhum 404/500 |
| Erros de console (JS) | ✅ Zero em todas as 27 telas |
| Chamadas `/api/*` com erro (≥400) | ✅ Zero |
| Telas **reprovadas** (quebradas/não funcionais) | **0** |
| Telas **aprovadas sem ressalva** | 13 |
| Telas **aprovadas com ressalva** (funcionam, mas com gap de UX/incompletude) | 14 |

Nenhuma tela travou, deu erro ou falhou ao carregar. Os achados abaixo são todos de UX, consistência ou funcionalidade incompleta — não crashes.

## Validações específicas pedidas

| Item | Resultado |
|---|---|
| **Login** | ✅ Aprovado. Formulário simples (`E-mail`/`Senha`/`Entrar`), submissão real via `/api/auth/login`, redireciona para `/` corretamente. Sem validação client-side de formato de e-mail além do `type="email"` nativo do navegador — não testado além disso. |
| **Dashboard** (`/`) | ✅ Aprovado. Cards de resumo carregam dados reais (Contatos: 1, Mensagens: 1, resto 0 — consistente com o estado real do banco). |
| **Memory Timeline** (`/admin/timeline`) | ✅ Aprovado. As três colunas (desde ontem / desde o último login / 30 dias) carregam com dados reais e coerentes. |
| **Action Center** (`/admin/action-center`) | ✅ Aprovado. Todos os contadores em zero (estado real, sem ações pendentes) com estados vazios bem escritos, não parece "quebrado". |
| **AI Operator** (`/admin`) | ⚠️ Aprovado com ressalva — funciona e mostra dado real (WhatsApp "Online", todos os serviços "Online" exceto Google OAuth, esperado), mas foi a tela mais lenta de toda a homologação: **5.2s** até `networkidle` (a segunda mais lenta ficou em 3.5s). Ver achado #4. |
| **Configurações** | ⚠️ Duas telas distintas com esse nome, nenhuma totalmente satisfatória — ver achados #6 e #7. |
| **WhatsApp** (`/admin/whatsapp`) | ✅ Aprovado. Mostra "Conectado", `provider=openwa`, reflete corretamente o trabalho desta sessão (autenticação + fix do `health_check`). |
| **Health** | ✅ Aprovado. `GET /health` → `{"status":"ok"}`; `GET /health/ready` → `{"status":"ok","checks":{"database":"ok","redis":"ok","qdrant":"ok","whatsapp":"ok"}}`. `docker compose ps`: 11/11 serviços `Up`. |
| **Navegação completa** | ✅ Todas as 27 rotas carregaram (HTTP 200, zero erro de console/API). Ver tabela completa abaixo. |

## Tabela completa (todas as telas)

| # | Rota | Tempo até `networkidle` | Status |
|---|---|---|---|
| — | `/login` | 2.9s | ✅ Aprovado |
| 1 | `/` (Dashboard) | 1.3s | ✅ Aprovado |
| 2 | `/admin` (AI Operator) | **5.2s** | ⚠️ Ressalva (performance) |
| 3 | `/admin/timeline` (Memory Timeline) | 1.6s | ✅ Aprovado |
| 4 | `/admin/action-center` (Action Center) | 3.5s | ✅ Aprovado |
| 5 | `/admin/briefing` (Daily Briefing) | 1.7s | ✅ Aprovado |
| 6 | `/admin/whatsapp` | 1.3s | ✅ Aprovado |
| 7 | `/admin/settings` | 1.5s | ⚠️ Ressalva (read-only por design) |
| 8 | `/admin/memory` | 1.4s | ⚠️ Ressalva (dado aparentemente inconsistente) |
| 9 | `/admin/logs` | 1.4s | ✅ Aprovado |
| 10 | `/admin/agents` | 1.6s | ✅ Aprovado |
| 11 | `/admin/executions` | 1.6s | ⚠️ Ressalva (job preso em "queued") |
| 12 | `/admin/google` | 1.2s | ✅ Aprovado (offline esperado, sem credenciais) |
| 13 | `/admin/metrics` | 1.4s | ⚠️ Ressalva (gráficos vazios numa visita única) |
| 14 | `/admin/system` | 1.4s | ⚠️ Ressalva (versão errada, build info ausente) |
| 15 | `/admin/tools` | 1.4s | ✅ Aprovado |
| 16 | `/admin/users` | 1.3s | ✅ Aprovado |
| 17 | `/agenda` | 1.2s | ⚠️ Ressalva (sem botão de criação) |
| 18 | `/analytics` | 1.1s | ⚠️ Ressalva (labels em inglês) |
| 19 | `/calendario` | 1.3s | ⚠️ Ressalva (sem botão de criação; redundante com Agenda) |
| 20 | `/configuracoes` | 1.1s | ⚠️ Ressalva (funcionalidade incompleta) |
| 21 | `/conversas` | 1.2s | ⚠️ Ressalva (contato mostrado como ID cru) |
| 22 | `/igreja` | 1.3s | ⚠️ Ressalva (sem botão de criação) |
| 23 | `/logs` | 1.2s | ⚠️ Ressalva (sem filtro, inundado de ruído) |
| 24 | `/loja` | 1.2s | ⚠️ Ressalva (sem botão de criação) |
| 25 | `/metas` | 1.1s | ✅ Aprovado (tem botão "Nova meta") |
| 26 | `/tarefas` | 1.1s | ⚠️ Ressalva (sem botão de criação) |

## Erros encontrados (por prioridade)

Nenhum é um crash ou funcionalidade quebrada — todos são UX, consistência ou incompletude.

### Prioridade Média

1. **Versão errada exibida para o usuário** — `/admin/system` mostra `Versão: 0.2.1`. O `CHANGELOG.md`/git tag atual é `v1.3.1`. Três fontes diferentes discordam (`app_version` hardcoded em `config.py`, `backend/VERSION.json` diz `1.3.0-rc1`, o tag diz `v1.3.1`) — já levantado em `RELEASE_SUMMARY_v1.3.1.md`, agora **confirmado visualmente**: um usuário real olhando essa tela vê um número errado. [`docs/qa/2026-07-18-homologacao/14_system.png`]
2. **`/admin/memory`: dado aparentemente contraditório** — card superior diz "Pontos no Qdrant: 88" (status green), mas a seção "Coleções (Qdrant)" pra `darioos_memory` mostra "Vetores: 0". Um usuário não tem como saber se isso é normal (os 88 pontos estão em outra coleção?) ou um problema. [`docs/qa/2026-07-18-homologacao/08_memory.png`]
3. **`/analytics` com labels em inglês, resto do app em português** — os mesmos dados que aparecem como "CONTATOS/MENSAGENS/TAREFAS PENDENTES" na tela Início (`/`) aparecem como "CONTACTS/MESSAGES/PENDING TASKS" em `/analytics`. [`docs/qa/2026-07-18-homologacao/01_dashboard_home.png` vs `18_analytics.png`]
4. **`/configuracoes` não entrega o que promete** — descrição da página: "Preferências e conexões do Dario OS." Conteúdo real: um texto estático sobre o endpoint da API e um botão "Sair". Nenhuma preferência, nenhuma conexão configurável ali. [`docs/qa/2026-07-18-homologacao/20_configuracoes.png`]
5. **Duas páginas "Logs" com capacidades muito diferentes** — `/admin/logs` tem filtro por nível (DEBUG/INFO/WARNING/ERROR), busca por texto e exportar. `/logs` (grupo dashboard) não tem nenhum filtro, e mostra uma lista longa (42+ linhas na primeira tela, sem paginação visível) inundada por `job:observation.tick` — exatamente o tipo de ruído que o `RELEASE_NOTES.md` documenta ter sido corrigido *na Timeline*, mas essa página antiga não recebeu a mesma correção. [`docs/qa/2026-07-18-homologacao/09_admin_logs.png` vs `23_logs.png`]

### Prioridade Baixa

6. **`/admin/settings` é somente leitura**, claramente sinalizado na própria tela ("read-only", "Edição fica fora do escopo desta sprint") — não é um bug escondido, mas é uma funcionalidade incompleta por design que vale registrar como tal.
7. **`/admin/system`: Commit/Branch/Tag = "não disponível"** — a página promete "Versão, build e uso de recursos" mas os três campos de build ficam vazios; metadado de build não está sendo injetado na imagem.
8. **`/admin/executions`: um job `observation.tick` ficou "queued" por >3 minutos** no momento da captura, enquanto todo o histórico visível mostra esse mesmo job completando em 42–162ms. Pode ser só o instante da captura (o próximo ciclo ainda não tinha rodado) — não investiguei mais fundo por estar fora do escopo desta homologação (comportamento de infraestrutura), só registro que a tela mostrou isso.
9. **Gráficos de série (`/admin/metrics`, recursos de `/admin/system`) mostram "Coletando dados..." permanentemente numa visita única** — são taxas calculadas no navegador a partir de contadores acumulados do Prometheus, e precisam de duas leituras consecutivas pra aparecer. Comportamento esperado para uma sessão de um único carregamento (como esta homologação), não necessariamente um bug para um usuário que deixa a aba aberta — mas vale considerar um estado vazio mais explicativo.
10. **Sem botão de criação em `/agenda`, `/calendario`, `/tarefas`, `/loja`, `/igreja`** — todas mostram só "Nenhum X cadastrado", sem nenhuma ação visível para adicionar um item. Em contraste, `/metas` tem um botão "Nova meta" bem visível. Não sei se as outras são alimentadas só via WhatsApp/agente — mas, se são, a tela não diz isso, e se não são, falta a ação.
11. **`/conversas`: coluna "Contato" mostra o ID numérico cru** (`1`), não nome ou telefone — dificulta identificar quem é o contato sem abrir outra tela.
12. **`/agenda` e `/calendario` parecem cobrir o mesmo conceito** (eventos) com descrições quase idênticas ("Seus eventos e compromissos" vs "Seus eventos organizados por dia") — não ficou claro, só navegando, qual a diferença real entre as duas.
13. **Inconsistência visual entre os dois "grupos" do app** — as páginas mais antigas (Início, Conversas, Agenda, Calendário, Tarefas, Metas, Loja, Igreja, Analytics, Logs, Configurações) usam layout bem mais simples que as páginas `/admin/*` mais novas (AI Operator Center, Timeline, Action Center — com cards, ícones e texto de apoio nos estados vazios). Não é um bug, mas o produto claramente tem duas "gerações" de UI convivendo.

## Screenshots

Todas em `docs/qa/2026-07-18-homologacao/` (28 arquivos, PNG full-page):

`00_login.png`, `00b_post_login.png`, `01_dashboard_home.png`, `02_admin_ai_operator.png`, `03_memory_timeline.png`, `04_action_center.png`, `05_daily_briefing.png`, `06_whatsapp.png`, `07_settings.png`, `08_memory.png`, `09_admin_logs.png`, `10_agents.png`, `11_executions.png`, `12_google.png`, `13_metrics.png`, `14_system.png`, `15_tools.png`, `16_users.png`, `17_agenda.png`, `18_analytics.png`, `19_calendario.png`, `20_configuracoes.png`, `21_conversas.png`, `22_igreja.png`, `23_logs.png`, `24_loja.png`, `25_metas.png`, `26_tarefas.png`.

## Nota final

Nenhuma implementação foi feita durante esta homologação — apenas navegação, captura de evidência e registro. A senha da conta admin foi resetada como parte da preparação (necessário para o login real pela UI) usando o mesmo processo já documentado em `BOOTSTRAP_ADMIN.md`; a senha atual foi entregue a você separadamente no chat, não fica armazenada em nenhum arquivo.
