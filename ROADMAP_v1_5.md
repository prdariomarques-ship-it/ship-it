# Roadmap — v1.5

Preparado no fechamento oficial da migração Next.js 16 (2026-07-20), ao
final do ciclo v1.4. Diferente do v1.4 (predominantemente hardening/débito
técnico), este ciclo prioriza **exclusivamente funcionalidade e melhoria de
produto** — nenhum item aqui exige mudança de arquitetura, novo
provider/registry, ou refactor estrutural. Onde uma melhoria de produto
tocaria em algo mais estrutural, isso está sinalizado explicitamente e
recomendado para avaliação separada, não incluído neste ciclo.

Fonte: limitações de domínio documentadas em `TECHNICAL_DEBT.md` (seção
"Limitações de domínio, aceitas por decisão de escopo") e itens Nice to
Have não iniciados do `ROADMAP_v1_4.md`.

## Must Have

Todos os itens abaixo foram concluídos — ver `RELEASE_1_4.md` e
`RELEASE_1_4_POSTMORTEM.md` para o relatório completo de certificação.

1. ~~**Fluxo de "esqueci minha senha".**~~ **Concluído** — modelo de
   entrega: admin gera um token de uso único
   (`POST /admin/users/{id}/password-reset-token`), repassado fora de
   banda (WhatsApp, verbalmente); nunca logado. Rate limiting dedicado e
   piso de tempo constante contra enumeração de e-mail. Páginas
   `/esqueci-senha` e `/redefinir-senha`. Commits `e2e4d99`, `393bac9`.
2. ~~**GoalManager: edição, cancelamento e atualização de progresso.**~~
   **Concluído** — edição, cancelamento, progresso, dependências e
   histórico, backend + frontend. Commit `6583a43`.

## Should Have

3. ~~**Gmail: capacidade de escrita (enviar e-mail via agente).**~~
   **Concluído** — deliberadamente reply-only (`reply_to_email_thread`),
   nunca compor e-mail novo para endereço arbitrário (mesmo princípio
   PROD-005 do WhatsApp). Escopo `gmail.send` adicionado; contas
   conectadas antes desta mudança precisam reconectar. Commit `08e7895`.
4. ~~**Google Calendar: edição de série de eventos recorrentes.**~~
   **Concluído** — criar evento com `recurrence` (RRULE); editar/excluir
   com `scope="this_event"` (padrão) ou `scope="all_events"` (série
   inteira, resolvida pro evento mestre). "Este evento e os seguintes"
   ficou deliberadamente fora do escopo — ver itens 27-29 abaixo.
   Commits `19f8e82`, `c533ffa`.
5. ~~**QR Code do WhatsApp exposto no Dashboard Administrativo.**~~
   **Concluído** — link direto para a página de pareamento do próprio
   openwa (não existe endpoint REST de QR, confirmado contra o gateway
   real); novo campo `OPENWA_PUBLIC_QR_URL`. Commit `cb8632a`.
6. ~~**Dashboard Settings: sair do modo somente-leitura.**~~ **Concluído**
   — `auto_reply_enabled` agora é editável (`GET`/`PATCH
   /admin/settings`), com efeito imediato e persistência através de
   restarts (tabela nova `app_settings`). `jobs_enabled`/providers
   continuam somente leitura, por decisão de escopo explícita (ver
   `docs/DASHBOARD.md`). **Implementado e validado na certificação final
   (`RELEASE_1_4_POSTMORTEM.md`); aguardando commit/push explícito do
   fundador.**

## Nice to Have

7. **"Última sincronização" para Gmail/Calendar/Contacts.** Hoje só o
   Google Drive mostra isso — os outros três são *read-through* (sem
   índice próprio), então não há dado de sync real para exibir sem
   introduzir cache/índice, o que seria estrutural. Alternativa de baixo
   risco: mostrar "consultado pela última vez às HH:MM" (timestamp da
   última chamada bem-sucedida à API), não um "sync" de verdade. Esforço:
   meio dia.
8. **Google Contacts: paginação completa além de 1000 contatos.** Hoje
   `search_google_contacts` lista até 1000 por chamada. Só relevante para
   quem tem agenda muito maior que isso — baixo impacto pro uso pessoal
   atual. Esforço: meio dia.
9. **Google Drive: suporte a Google Docs/Sheets/Slides nativos.** Hoje só
   PDF/DOCX/TXT/Markdown/CSV são indexados; Docs/Sheets/Slides são
   recusados explicitamente. Ampliar exigiria a API de export do Google
   Workspace (converter pra um formato indexável) — mais esforço que os
   outros itens desta lista, mas ainda dentro da integração já existente,
   sem provider novo. Esforço: 2-3 dias.
10. **Indexação de documentos maiores no Drive.** Hoje cada arquivo é
    indexado até ~30 pedaços (~45 mil caracteres); o restante de um
    documento grande não entra. Aumentar o limite é uma mudança de
    configuração/paginação, não estrutural. Esforço: meio dia + validação
    de custo (mais chunks = mais chamadas de embedding).

## Fora deste ciclo — precisa de design antes de virar item de roadmap

Estes tocam o **Cognitive Pipeline** (Planner/LearningEngine) e são valiosos,
mas cada um é grande o bastante para merecer uma sessão de design própria
antes de virar trabalho de implementação — incluí-los diretamente aqui
seria subestimar o esforço real ou arriscar um refactor não planejado:

- Planner gerar e comparar planos alternativos antes de executar.
- Detecção de contradições entre etapas do mesmo plano.
- Estimar custo/tempo de um plano *antes* da execução (hoje só é medido
  depois).
- `LearningEngine` realimentar falhas passadas em decisões de planejamento
  futuras (hoje só atualiza categorias de contato).

Recomendação: tratar como uma proposta técnica separada (não v1.5), com
escopo e limites definidos antes de estimar esforço.

## Dependências entre itens

- Itens 1-6 (Must Have + Should Have) — todos concluídos, ver acima.
- Itens 7-10 (Google Workspace) podem ser feitos em qualquer ordem; item 9
  (Docs/Sheets/Slides) é o de maior esforço do grupo.

## Paralelizável

Itens 7-10 (Nice to Have) são paralelizáveis entre si.

## Status ao final do ciclo (Release 1.4, 2026-07-21)

- **Must Have:** 2/2 concluídos.
- **Should Have:** 4/4 concluídos.
- **Nice to Have:** 0/4 iniciados (itens 7-10 seguem no backlog, nenhum é
  bloqueante).
- Mais 3 itens entregues fora deste roadmap original: busca semântica de
  memória, módulo de Notas dedicado, busca em Contacts/Church.
- Ver `RELEASE_1_4.md`/`RELEASE_1_4_POSTMORTEM.md` para o relatório
  completo de certificação, e `ROADMAP_v1_4.md` (itens 27-29) para o
  débito técnico aceito ao fechar a edição de série recorrente do Google
  Calendar.
