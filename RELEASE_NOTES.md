# Dario OS — Release Notes v1.3.0-rc1

Data do gate: 2026-07-17
Branch: `master`
Versão anterior: v1.2.0 (2026-07-11) — ver `RELEASE_NOTES_v1.0.md`, `CHANGELOG.md` para o histórico completo.

Esta é a Release Candidate 1 (RC1) da v1.3.0, cobrindo o ciclo "Product Evolution": AI Operator Center, Memory & Timeline, Daily Briefing e Action Center. Auditoria completa em `RC1_AUDIT.md` — 1 achado crítico (não corrigido nesta RC), prontidão estimada em 82%. Nenhuma mudança de arquitetura backend além do estritamente necessário para cada funcionalidade — cada endpoint novo é justificado individualmente em `RC1_AUDIT.md`/`ACTION_CENTER.md`/`MEMORY_TIMELINE.md`.

## Visão geral

O dashboard administrativo (`/admin`) deixa de ser um painel de leitura e passa a responder três perguntas, nesta ordem: **o que aconteceu, o que eu devo fazer agora, e o sistema pode fazer isso por mim?** Tudo construído sobre dados que o dashboard já buscava — nenhuma nova fonte de dados, nenhum LLM no caminho crítico, nenhuma nova infraestrutura (scheduler, fila, orquestrador) além de uma extensão pontual em `GET /admin/logs` e um endpoint de auditoria (`POST /admin/actions/log`).

## O que está incluído

### AI Operator Center (`/admin`)
Substitui o antigo `SuggestedActionsPanel` por um centro de comando real. Toda recomendação (meta aguardando aprovação, tarefa atrasada, job falhado, conflito de agenda, meta em risco, WhatsApp desconectado, fonte de observação degradada, oportunidade, automação já em curso) é agrupada em 🔥 urgente / ⚠️ hoje / 💡 oportunidade / 🤖 automação, com motivo, confiança (tier fixo — 95/65/35 — nunca uma probabilidade inventada), impacto esperado e tempo estimado (ou "variável", nunca um número chutado). Responde "o que eu devo fazer agora" nos primeiros 5 segundos de tela. Detalhes: `AI_OPERATOR.md`.

### Memory & Timeline (`/admin/timeline`)
Transforma o log de auditoria bruto em memória operacional real, não um visualizador de log. Oito seções por assunto, cada evento com por-quê/consequência/entidades relacionadas/sugestão de acompanhamento. "O que mudou desde ontem", "desde meu último login" e "mudanças mais importantes" respondidas de verdade, com limites de dia-calendário reais (não uma janela deslizante de 48h). **Bug de produção real corrigido nesta fase**: o log de `job:observation.tick` (2 linhas a cada poucos minutos) podia empurrar eventos genuinamente raros para fora de uma página de 1000 linhas antes mesmo de chegar ao frontend — confirmado contra um banco demo com mais de 3000 linhas acumuladas. Corrigido com `exclude_source` filtrando dentro da query SQL. Detalhes: `MEMORY_TIMELINE.md`.

### Daily Briefing (`/admin/briefing`)
Um briefing executivo, não mais um dashboard: parágrafo de abertura construído a partir de contagens reais, resumo executivo, três colunas de prioridades/riscos/oportunidades com suporte a decisão ("por que agora", "consequência se ignorado"), plano de execução Manhã/Tarde/Noite (rotulado explicitamente como sugestão, nunca uma agenda imposta), e uma Saúde do Dia (0–100) com fórmula de seis fatores totalmente auditável na própria interface — nunca um número de caixa-preta. Detalhes: `DAILY_BRIEFING.md`.

### Action Center (`/admin/action-center`)
A peça que fecha o ciclo: a IA para de só recomendar e passa a executar. Cada recomendação expõe um workflow real — Concluir tarefa, Adiar 1 dia, Aprovar meta, Tentar novamente (job), Criar tarefa de acompanhamento, Agendar tempo — sobre endpoints que já existiam (`PATCH /tasks/{id}`, `POST /goals/{id}/approve`, `POST /admin/jobs/{id}/retry`, `POST /tasks`, `POST /calendar`). Toda ação é classificada `SAFE_AUTOMATIC` (um clique), `REQUIRES_CONFIRMATION` (dois cliques, com **Action Preview** completo: o que vai acontecer, o que é afetado, se pode ser desfeito, tempo estimado, efeitos colaterais, confiança de execução) ou `MANUAL_ONLY` (nunca executa sozinho — só um link e a explicação de por quê). Automation Score (ações concluídas hoje, minutos economizados, confirmações pendentes) vem só de execuções reais registradas — nunca de uma estimativa sem evidência. O histórico de execução aparece na Timeline já existente, sem subsistema novo. Detalhes: `ACTION_CENTER.md`.

## Métricas da build

| Métrica | Valor |
| --- | --- |
| Testes de backend | 883 (100% passando, +6 desde v1.2.0) |
| Testes de frontend | 231 (100% passando, +123 desde v1.2.0) |
| TypeScript (`tsc --noEmit`) | limpo |
| ESLint (`next lint`) | limpo, zero avisos |
| Build de produção (`next build`) | limpo, 27 rotas |
| Páginas admin novas | 3 (`/admin/timeline`, `/admin/briefing`, `/admin/action-center`) |
| Endpoints backend novos | 2 (`POST /admin/actions/log`; extensões de parâmetro em `GET /admin/logs`: `since`, `until`, `exclude_source`, `source_prefix`) |

## Bugs reais corrigidos ao longo do desenvolvimento

- `job:observation.tick` expulsando eventos raros de uma página de 1000 linhas antes de chegar ao frontend (Memory & Timeline).
- `buildCalendarEvents` nunca conseguia mostrar um evento "atualizado" na visão "Tudo" — `since === undefined` sempre caía no ramo "criado" (Memory & Timeline).
- Bug de fuso horário no plano de execução do Daily Briefing (`.getHours()` local em vez de `.getUTCHours()`).
- Race condition no Action Center: Automation Score e "Concluídas" mostravam dado desatualizado por até uma interação após uma ação bem-sucedida, porque a invalidação de query disparava antes do registro de auditoria fire-and-forget realmente ter sido gravado.
- `_TaskRepo` duplicado byte-a-byte em `agents/tools/productivity.py`, e quatro pontos reimplementando formatação de data já existente em `lib/format.ts` — ambos encontrados e corrigidos durante a auditoria RC1.

## Achados da auditoria RC1 ainda não corrigidos

Ver `RC1_AUDIT.md` para a lista completa. O único achado crítico: **o shell do painel admin (`AdminShell.tsx`) não tem sidebar responsiva para mobile** — em uma tela de ~375px, a sidebar sozinha ocupa cerca de dois terços da largura, sem mecanismo de recolher. Cada página individual usa breakpoints responsivos corretamente; o gap é estrutural, em um único componente. Não bloqueia o uso principal (desktop), mas deve ser o primeiro item do próximo ciclo se acesso via celular for esperado.

## Como atualizar

Nenhuma migração de banco nova, nenhuma variável de ambiente nova. `git pull`, rebuild dos containers `backend`/`frontend` normalmente:

```bash
docker compose up -d --build backend frontend
```

## Créditos

Construído em quatro fases incrementais (AI Operator Center → Memory & Timeline → Daily Briefing → Action Center) mais um ciclo de estabilização RC1, seguindo os mesmos princípios da v1.0: nenhuma infraestrutura nova sem justificativa concreta, nenhuma confiança fabricada, nenhuma alegação não verificada por teste.
