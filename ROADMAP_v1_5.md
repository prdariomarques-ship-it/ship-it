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

1. **Fluxo de "esqueci minha senha".** Hoje só existe troca de senha
   autenticada (`POST /auth/change-password`) — já causou intervenção
   manual direta no banco pelo menos uma vez (ver `BOOTSTRAP_ADMIN.md`).
   Sem esse fluxo, qualquer esquecimento de senha é um incidente manual.
   Fica dentro da estrutura de auth já existente (token de reset +
   endpoint novo), sem tocar no modelo de permissões. Esforço: 4-6h.
2. **GoalManager: edição, cancelamento e atualização de progresso.** A UI
   (`/metas`) hoje só cria e aprova metas — falta editar, cancelar,
   gerenciar dependências e atualizar progresso manualmente. É o núcleo de
   uma funcionalidade central do produto (metas) com uma lacuna de CRUD
   básica. Esforço: 1-2 dias (backend + frontend).

## Should Have

3. **Gmail: capacidade de escrita (enviar e-mail via agente).** Hoje é
   somente leitura. Habilitar envio abriria um caso de uso real (o
   assistente responder e-mails, não só lê-los) sem exigir um provider
   novo — mesma integração Gmail já existente, só uma capacidade a mais.
   Esforço: 1 dia.
4. **Google Calendar: edição de série de eventos recorrentes.** Hoje só
   eventos únicos são editáveis. Lacuna perceptível pra quem usa agenda
   recorrente de verdade (reuniões semanais, etc.). Esforço: 1-2 dias
   (a API do Google Calendar já suporta isso — o trabalho é na camada de
   integração existente, não uma reescrita).
5. **QR Code do WhatsApp exposto no Dashboard Administrativo.** Hoje
   reconectar o WhatsApp exige acesso direto ao container/logs — expor o
   QR code na UI elimina essa fricção operacional recorrente. Toca
   `providers/whatsapp/` para adicionar um método de obter o QR em cada
   provider, mas não muda a interface do provider nem adiciona
   abstração nova. Esforço: 1 dia.
6. **Dashboard Settings: sair do modo somente-leitura.** `/admin/settings`
   hoje só mostra configuração — permitir editar (mesmo que um subconjunto
   pequeno e seguro de opções) fecha uma expectativa óbvia de UX de uma
   página chamada "Settings". Esforço: 1 dia (escopo inicial pequeno:
   poucas opções não-sensíveis).

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

- Item 1 (forgot-password) é independente de tudo.
- Itens 2, 3, 4 são independentes entre si — cada um toca uma área de
  produto diferente (metas, e-mail, calendário).
- Item 5 (QR code) e item 6 (Settings editável) são independentes entre si
  e do resto.
- Itens 7-10 (Google Workspace) podem ser feitos em qualquer ordem; item 9
  (Docs/Sheets/Slides) é o de maior esforço do grupo.

## Paralelizável

Todos os itens Must Have e Should Have (1-6) podem rodar em paralelo entre
si — nenhum depende tecnicamente de outro. Itens 7-10 (Nice to Have) também
são paralelizáveis entre si e com o restante.
