# Product Discovery — Release 1.4

**Data:** 2026-07-20
**Metodologia:** leitura direta do código (backend + frontend), sem execução, sem alterações. Confirmações pontuais feitas com `grep`/leitura de arquivo nos achados mais decisivos antes de virar recomendação. **Consolidado a partir de dois levantamentos independentes** feitos na mesma janela de tempo — divergências entre eles foram verificadas de novo no código antes de entrar aqui, não apenas somadas.
**Não é este documento:** não substitui `ROADMAP_v1_5.md` nem `TECHNICAL_DEBT.md` — onde os achados aqui refinam uma estimativa ou descrição já registrada lá (principalmente GoalManager), isso está sinalizado explicitamente.

## Missão do ciclo

> Toda funcionalidade nova precisa responder: "isso economiza tempo do usuário ou reduz fricção?" Se não responder, não constrói.

O achado mais importante deste discovery não é uma funcionalidade nova — é que **o backend já sabe fazer mais coisa do que a UI deixa o usuário fazer**. A maior parte do valor de curto prazo deste ciclo está em *expor* capacidade que já existe, não em construir capacidade nova.

---

## Already delivers value

O que já funciona de ponta a ponta hoje, usável agora.

### Assistente via WhatsApp (agente `assistant`)
- **Problema que resolve:** ponto único de acesso, por texto, a agenda, tarefas, notas, Gmail, Google Calendar, Google Contacts, Google Drive, igreja, loja e metas — sem abrir nenhuma tela.
- **Usuário-alvo:** Dário, no dia a dia, pelo WhatsApp.
- **Estado atual:** em produção, **40 tools registradas** (contagem verificada diretamente em `agents/assistant_agent.py`, corrigindo uma contagem de 37 de um levantamento anterior). É o único agente que o pipeline do WhatsApp aciona — `orchestrator/pipeline.py:256` fixa `agent_name="assistant"` diretamente, confirmado por leitura do código. Os outros 4 agentes (`personal`, `church`, `store`, `content`) **nunca são alcançados pelo WhatsApp**, só por chamada de API direta.
- **Valor de negócio:** é o produto. Todo o resto gira em torno desse canal.

### Planejamento multi-etapa (`CognitivePlanner`)
- **Problema que resolve:** pedidos compostos ("marca uma reunião e avisa o João") viram um plano com várias etapas e dependências (`depends_on`), não só uma resposta de uma tacada.
- **Usuário-alvo:** Dário, em qualquer pedido não-trivial.
- **Estado atual:** já funcional, com fallback determinístico sem LLM se necessário (`orchestrator/planning.py`).
- **Valor de negócio:** alto — é a diferença entre um chatbot de FAQ e um assistente que executa.

### Memória semântica unificada (RAG)
- **Problema que resolve:** busca por significado (não só palavra-chave) sobre documentos indexados do Google Drive **e** sobre histórico de conversa/contato.
- **Usuário-alvo:** Dário perguntando "o que tinha naquele PDF sobre X" ou "o que sabemos sobre esse contato".
- **Estado atual:** pipeline já é agnóstico de fonte (`source` livre em `models/embedding.py`) — Drive é só uma das fontes possíveis, a coleção Qdrant é compartilhada. `GET /memory/search` já expõe isso via API. **Nenhuma UI usa esse endpoint** — `/admin/memory` mostra só contagem de pontos/vetores no Qdrant, sem campo de busca nenhum.
- **Valor de negócio:** alto, e reaproveitável sem custo extra (ver Quick Wins).

### GoalManager (criar + aprovar metas)
- **Problema que resolve:** registrar e aprovar metas pessoais com fluxo formal.
- **Usuário-alvo:** Dário.
- **Estado atual:** UI cobre só criação e aprovação — mas o **backend já suporta muito mais**, inclusive pelo próprio agente `assistant` via WhatsApp (`update_goal_progress_tool`, `complete_goal_tool` já estão entre as 40 tools) (ver Quick Wins).
- **Valor de negócio:** médio hoje, alto assim que a UI alcançar o backend.

### Igreja e Loja (mini-CRMs)
- **Problema que resolve:** cadastro e consulta de membros de igreja (`ministries`, `prayer_requests`) e clientes de loja (`orders`) via CRUD genérico + tools de agente dedicadas.
- **Usuário-alvo:** Dário administrando esses dois contextos.
- **Estado atual:** confirmado ativo e real (não é resquício do schema `business/` removido) — mas raso, sem agregação sobre os dados.
- **Valor de negócio:** médio — funcional, mas sem insight (ver Medium Features).

### Operator Center (`/admin`)
- **Problema que resolve:** visibilidade operacional real — Ações Sugeridas por IA, jobs pendentes com retry/cancelar, Health Score, Observation Engine, memória, métricas, WhatsApp, usuários.
- **Usuário-alvo:** Dário como admin/operador do sistema.
- **Estado atual:** robusto, painel real, dados reais (nenhum mock encontrado).
- **Valor de negócio:** alto para operação — mas **inacessível a qualquer usuário não-admin** (ver Strategic Features, item multiusuário).

### Fila de jobs com retry
- **Problema que resolve:** execução assíncrona confiável (resumo de contato, embedding, etc.) com backoff e visibilidade via Action Center.
- **Usuário-alvo:** sistema/Dário indiretamente.
- **Estado atual:** maduro, já com UI de retry/cancelar conectada.
- **Valor de negócio:** infraestrutura sólida, habilita tudo o resto.

### Notas (CRUD completo, sem tela)
- **Problema que resolve:** capturar e consultar notas rapidamente.
- **Usuário-alvo:** Dário.
- **Estado atual:** `notes_router` (`api/routes.py`) é um CRUD completo (create/read/update/delete), já usado internamente pelo `ContentAgent` e pelo `personal_agent` para salvar rascunhos/lembretes. No frontend, "notas" aparece **apenas como um número** num `StatCard` da home e do Analytics — não existe página `/notas` para listar, criar, editar ou apagar.
- **Valor de negócio:** médio — funcional no backend, zero valor de produto hoje por falta de tela.

---

## Hidden capabilities

Implementado no backend, invisível ou quase inacessível para o usuário.

### Chat direto com os outros 4 agentes (`personal`, `church`, `store`, `content`)
- **Problema que resolve (se exposto):** hoje só `assistant` é alcançável (via WhatsApp); os outros 4 — incluindo o `ContentAgent`, que gera posts/roteiros/hashtags para Instagram, Facebook, YouTube, TikTok e LinkedIn — só respondem a chamada de API crua (`POST /agents/{agent_name}/run`, já existe e funciona) ou a testes automatizados. Não há **nenhuma** interface, nem admin nem de usuário final, onde alguém digita uma mensagem e fala com qualquer um desses 4.
- **Usuário-alvo:** Dário — testando/depurando no curto prazo; usando o `ContentAgent` de verdade no médio prazo (é o único destes 4 com um caso de uso de produto completo e imediato, os outros 3 são majoritariamente domínios que o `assistant` já cobre via WhatsApp).
- **Esforço para expor:** baixo — endpoint já existe, e o payload já aceita seleção de agente; a diferença entre "botão rodar agente" (ver Quick Win 4, escopo admin/debug) e uma superfície de chat de verdade (ver Medium Features) é de ambição de produto, não de trabalho de backend.
- **Valor de negócio:** alto especificamente para o `ContentAgent` (funcionalidade nova e vistosa); médio-baixo para `personal`/`church`/`store` isolados, já que o `assistant` cobre esses domínios pelo canal que já é usado todo dia.

### `get_contact` do Google Contacts — testado, não conectado
- **Problema que resolve (se exposto):** "me mostra os detalhes desse contato" sem precisar buscar de novo.
- **Usuário-alvo:** Dário, via WhatsApp.
- **Esforço para expor:** trivial — provider já testado (inclusive teste de segurança contra path traversal), falta só uma tool wrapper (~10 linhas) e adicioná-la à lista de 40 tools do `assistant`.
- **Valor de negócio:** baixo-médio, mas custo quase zero.

### Preferências de memória (`get_preferences`/`set_preference`/`forget`) — sem endpoint HTTP
- **Problema que resolve (se exposto):** ver e corrigir o que o assistente "decidiu lembrar" sobre um contato, ou apagar uma memória errada.
- **Usuário-alvo:** Dário administrando a confiabilidade do assistente.
- **Esforço para expor:** baixo — métodos já existem em `memory/manager.py`, falta só rota.
- **Valor de negócio:** médio — é sobre confiança no sistema, não uma funcionalidade vistosa.

### `Plan.confidence` — calculado e descartado
- **Problema que resolve (se exposto):** saber quando o assistente "não tinha tanta certeza" antes de executar algo.
- **Usuário-alvo:** todo usuário, indiretamente (segurança/confiabilidade).
- **Esforço para expor:** o cálculo já existe; o esforço real é decidir *o que fazer* com a informação (ver Strategic Features).
- **Valor de negócio:** alto, mas é decisão de produto, não só código.

### Log de aprendizado por contato (`orchestrator/learning.py`)
- **Problema que resolve (se exposto):** um "sobre o que essa pessoa fala/precisa" por contato, construído a partir de dado que já é gravado a cada mensagem processada (o `LearningEngine` tagueia automaticamente o contato com categorias — `loja`/`igreja`/`pessoal`/`conteudo` — deduplicado por `MemoryManager.add_categories`) e nunca lido de volta em nenhuma tela.
- **Usuário-alvo:** Dário gerenciando relacionamentos recorrentes (igreja, loja, pessoal).
- **Esforço para expor:** médio — dado já existe, falta endpoint de leitura + agregação + UI.
- **Valor de negócio:** médio-alto — funcionalidade nova sem custo de captura.

### Busca por nome (Contacts/Church) — só o bot sabe fazer
- **Problema que resolve (se exposto):** achar um contato/membro no dashboard sem folhear página por página.
- **Usuário-alvo:** Dário usando o dashboard (não o WhatsApp).
- **Esforço para expor:** baixo — `search_by_name` já existe no repositório, falta `?q=` na rota + campo de busca.
- **Valor de negócio:** médio-alto, fricção clara e resolvível rápido.

### Ferramentas proativas que só respondem, nunca avisam
- **O que é:** `detect_pending_email_actions_tool` e `check_google_calendar_availability_tool` (ambas entre as 40 tools do `assistant`) só rodam se o Dário pensar em perguntar durante uma conversa.
- **Usuário-alvo:** todo usuário — é o núcleo da missão "assistente que as pessoas usam todo dia".
- **Esforço para expor:** alto — não é só rodar a tool sozinha, é decidir *quando vale interromper* (ver Strategic Features).
- **Valor de negócio:** muito alto — é provavelmente o maior salto de percepção de valor disponível neste ciclo.

---

## Quick Wins (1–2 dias)

### 1. GoalManager: editar/cancelar/atualizar progresso na UI
- **Problema resolvido:** hoje `/metas` só cria e aprova; o usuário não consegue cancelar uma meta obsoleta nem atualizar progresso manualmente pela tela (embora já consiga via WhatsApp, ver acima).
- **Usuário-alvo:** Dário, gestão pessoal de metas.
- **Complexidade estimada:** **baixa, corrigida a partir de uma estimativa anterior de "1-2 dias, backend + frontend"**: o backend já expõe `PATCH /{id}/status`, `PATCH /{id}/progress`, `POST`/`DELETE /{id}/dependencies` e `GET /{id}/history` (confirmado em `backend/goals/router.py:177-227`). `/metas` (`frontend/app/(dashboard)/metas/page.tsx`) só chama `GET /goals` e `POST /goals/{id}/approve`. É trabalho de frontend puro, ~1 dia. (Falta ainda um `PATCH /{id}` genérico para editar título/descrição/prazo — esse sim é backend novo, mas pequeno.)
- **Valor de negócio:** alto — fecha um CRUD básico já anunciado como funcionalidade central do produto.

### 2. Busca semântica de memória na UI
- **Problema resolvido:** não dá pra perguntar "o que sabemos sobre X" sem ir direto no banco vetorial.
- **Usuário-alvo:** Dário.
- **Complexidade estimada:** trivial a baixa — `GET /memory/search` já existe e funciona; `/admin/memory` já é a página certa, só falta um campo de busca.
- **Valor de negócio:** alto pelo esforço quase nulo.

### 3. Tool de detalhe de contato (Google Contacts)
- **Problema resolvido:** pedir "me mostra os detalhes do contato X" hoje não tem caminho direto — o agente teria que buscar de novo.
- **Usuário-alvo:** Dário, via WhatsApp.
- **Complexidade estimada:** trivial (horas) — provider já testado e seguro, falta só a tool wrapper.
- **Valor de negócio:** baixo-médio, mas ROI altíssimo pelo custo quase zero.

### 4. Busca por nome em Contacts/Church no dashboard
- **Problema resolvido:** hoje é preciso folhear páginas manualmente; o próprio bot já sabe buscar por nome, o dashboard não.
- **Usuário-alvo:** Dário usando o dashboard.
- **Complexidade estimada:** baixa — `search_by_name` já existe no repositório (`repositories/contact.py`, `repositories/church.py`), falta expor `?q=` na rota de listagem (`api/crud.py`) + campo de busca na tela.
- **Valor de negócio:** médio-alto, fricção de uso real e resolvível rápido.

### 5. Página de Notas
- **Problema resolvido:** notas existem (contador na home/analytics), mas não têm nenhuma tela para listar, criar, editar ou apagar.
- **Usuário-alvo:** Dário.
- **Complexidade estimada:** baixa — `notes_router` já é CRUD completo, zero trabalho de backend.
- **Valor de negócio:** médio.

### 6. Botão "rodar agente" em `/admin/agents`
- **Problema resolvido:** hoje a tela só lista agentes (`frontend/app/admin/agents/page.tsx`, 34 linhas, sem nenhuma chamada `POST`); testar `personal`/`church`/`store`/`content` exige API crua.
- **Usuário-alvo:** Dário testando/operando agentes.
- **Complexidade estimada:** baixa — endpoint já existe (`POST /agents/{agent_name}/run`, `backend/agents/router.py:46`).
- **Valor de negócio:** médio, ferramenta operacional — **não confundir com uma superfície de chat de produto** (ver Medium Features, item 1a); este item é um botão de debug numa tela de admin, não uma experiência de uso diário.

### 7. QR code do WhatsApp no Dashboard Administrativo
- (Já mapeado no `ROADMAP_v1_5.md`, item 5 — mantido aqui por coerência do discovery.)
- **Problema resolvido:** reconectar sessão hoje exige acesso a container/logs.
- **Usuário-alvo:** Dário.
- **Complexidade estimada:** baixa (~1 dia).
- **Valor de negócio:** alto — fricção operacional recorrente.

### 8. Endpoint simples para preferências de memória (ver/apagar)
- **Problema resolvido:** hoje não dá pra ver nem corrigir uma preferência ou "lembrança" errada guardada sobre um contato.
- **Usuário-alvo:** Dário administrando a confiabilidade da memória do assistente.
- **Complexidade estimada:** baixa — métodos já existem em `memory/manager.py` (`get_preferences`, `set_preference`, `forget`), falta só rota HTTP fina em cima deles.
- **Valor de negócio:** médio — confiança no sistema, evita "o assistente lembrou errado e não dá pra corrigir".

---

## Medium Features (1 semana)

### 1. Chat de produto para o `ContentAgent` (e, secundariamente, `personal`/`church`/`store`)
- **Problema resolvido:** o `ContentAgent` — geração de posts/roteiros/hashtags para 5 redes sociais — é uma funcionalidade de produto completa e vistosa, hoje inacessível fora de chamada de API crua. Diferente do item "Quick Win 6" (botão de debug no admin), isto é uma superfície de uso diário: escolher um agente, conversar, ver o histórico da conversa.
- **Usuário-alvo:** Dário, criando conteúdo para redes sociais sem sair do Dario OS.
- **Complexidade estimada:** média (2-3 dias) — componente de chat, seletor de agente, histórico de conversa no cliente, estado de loading/erro. Backend não muda nada (`POST /chat` já aceita `agent` no payload).
- **Valor de negócio:** alto, concentrado quase todo no `ContentAgent` — os outros 3 agentes deste grupo (`personal`/`church`/`store`) já têm seus domínios cobertos pelo `assistant` via WhatsApp, então o ganho incremental de expô-los aqui é menor do que parece à primeira vista.

### 1a. `/conversas` virar inbox de verdade
- **Problema resolvido:** hoje é uma tabela crua de mensagens (sem agrupar por contato, sem thread, sem responder dali) — pra responder alguém, o jeito é abrir o WhatsApp mesmo. É o maior gap de UX identificado neste discovery, justamente porque o canal primário do produto é conversa.
- **Usuário-alvo:** Dário querendo gerenciar conversas sem estar sempre no celular.
- **Complexidade estimada:** média — o endpoint de envio já existe (`api/whatsapp.py`), o trabalho é de agregação (agrupar mensagens por contato) e UI de thread/reply.
- **Valor de negócio:** alto — é o uso diário mais natural de "assistente que as pessoas usam toda hora", hoje ausente.

### 2. Home do usuário com ações, não só contadores
- **Problema resolvido:** `/` hoje é 7 `StatCard`s estáticos sem contexto nem próxima ação, enquanto o Operator Center (admin) já tem Ações Sugeridas, Health Score, Observation Engine — tudo invisível pra quem não é admin.
- **Usuário-alvo:** qualquer usuário não-admin (se houver intenção de mais gente usando) — ou o próprio Dário, se preferir uma home mais acionável que o painel de operação bruto.
- **Complexidade estimada:** média — dado já existe via `/dashboard/summary` e endpoints de observation/metrics; é composição de UI, não captura de dado novo.
- **Valor de negócio:** alto se houver múltiplos usuários previstos; médio se for só o Dário (nesse caso, prioridade real é a decisão estratégica de multiusuário — ver abaixo — antes de investir aqui).

### 3. Painel "sinal por contato" a partir do log do LearningEngine
- **Problema resolvido:** o sistema já grava intent/prioridade/categoria a cada mensagem processada e nunca reaproveita esse histórico — daria uma mini-timeline real de "do que essa pessoa mais fala/precisa".
- **Usuário-alvo:** Dário gerenciando contatos recorrentes (igreja, loja, pessoal).
- **Complexidade estimada:** média — precisa de endpoint de leitura + agregação + tela, mas a captura de dado já está pronta (zero custo de coleta).
- **Valor de negócio:** médio-alto — funcionalidade nova de valor real "de graça" sobre dado que já existe.

### 4. Gmail: capacidade de envio
- (Já no `ROADMAP_v1_5.md`, item 3 — mantido por coerência.)
- **Problema resolvido:** hoje é só leitura; enviar e-mail pelo assistente é um caso de uso real novo.
- **Usuário-alvo:** Dário.
- **Complexidade estimada:** média (~1 dia técnico, mas exige desenho de confirmação antes de enviar — não é só a chamada de API).
- **Valor de negócio:** alto, mas é a única desta lista com risco real de consequência irreversível no mundo real (e-mail errado, pra pessoa errada).

### 5. Google Calendar: edição de série recorrente
- (Já no `ROADMAP_v1_5.md`, item 4 — mantido por coerência.)
- **Problema resolvido:** hoje só eventos únicos são editáveis; quem usa agenda recorrente de verdade sente essa lacuna.
- **Usuário-alvo:** Dário.
- **Complexidade estimada:** média (1-2 dias).
- **Valor de negócio:** médio-alto.

### 6. Agregados úteis para Igreja/Loja
- **Problema resolvido:** hoje `prayer_requests`/`orders` são JSON crus sem nenhuma visão agregada ("quantos pedidos de oração pendentes", "quantos pedidos em aberto") — dado existe, insight não.
- **Usuário-alvo:** Dário administrando esses dois contextos.
- **Complexidade estimada:** média — queries de agregação sobre os JSONs + endpoint + exposição (tela ou resposta de agente).
- **Valor de negócio:** médio, **condicional**: vale confirmar com o Dário o quanto esses dois módulos são usados ativamente hoje antes de investir — não achamos evidência de uso real no código (fora de existirem e funcionarem).

---

## Strategic Features

Capacidades grandes que mudam o produto, não só adicionam uma tela.

### 1. Confiança do plano (`Plan.confidence`) influenciando execução
- **Problema resolvido:** hoje todo plano executa com a mesma "segurança" — um plano de baixa confiança do LLM roda igual a um óbvio, sem sinalizar risco.
- **Usuário-alvo:** todo usuário, ganho de confiabilidade sistêmica.
- **Complexidade estimada:** alta — não é ler o campo (isso é trivial), é desenhar o comportamento: abortar? pedir confirmação extra? só logar pra revisão? Decisão de produto, não só engenharia.
- **Valor de negócio:** alto — segurança e previsibilidade são o que fazem alguém confiar num assistente que age sozinho, em vez de checar tudo depois.

### 2. Superfícies proativas (o assistente avisa, não só responde)
- **Problema resolvido:** hoje "ações pendentes de e-mail" e "disponibilidade de agenda" só existem se o Dário pensar em perguntar. A missão do release é "assistente usado todo dia" — proatividade é o que realmente entrega isso, não só responder bem quando perguntado.
- **Usuário-alvo:** todo usuário.
- **Complexidade estimada:** alta — precisa de agendamento periódico + lógica de "vale a pena interromper agora" + proteção contra spam (o sistema já tem um precedente de rate-limit em `AUTO_REPLY_MAX_PER_CONTACT_PER_MINUTE`, reaproveitável como padrão).
- **Valor de negócio:** muito alto — provavelmente o maior salto de percepção de valor disponível hoje, e o que mais diretamente responde à missão declarada do ciclo.

### 3. Multiusuário de verdade
- **Problema resolvido:** hoje quase todo valor real de gestão (Ações Sugeridas, Health Score, jobs, observabilidade) está atrás do gate de admin — se a intenção é ter família ou outras pessoas usando o Dario OS, a experiência delas hoje seria muito mais pobre que a do Dário.
- **Usuário-alvo:** depende inteiramente de uma decisão de produto ainda não tomada.
- **Complexidade estimada:** alta.
- **Valor de negócio:** **não avaliável sem antes confirmar a intenção** — não recomendo investir aqui sem primeiro confirmar com o Dário se há usuários além dele previstos para o produto. Citado aqui porque a arquitetura atual (single-tenant de fato, mesmo com role admin/user) é uma decisão que fica mais cara de reverter quanto mais o produto cresce.

### 4. Comparar múltiplos planos antes de executar
- **Problema resolvido:** hoje o primeiro plano gerado é o executado, sem avaliar alternativas — mesmo em pedidos ambíguos onde a primeira interpretação pode não ser a melhor.
- **Usuário-alvo:** cenários de pedido ambíguo (uma fração do uso real, não a maioria).
- **Complexidade estimada:** alta.
- **Valor de negócio:** médio-alto — **nota importante:** o `ROADMAP_v1_5.md` listava isso como "fora do ciclo, precisa de design" citando falta de suporte multi-etapa; este discovery confirma que o multi-etapa **já existe e funciona** (`CognitivePlanner` com `depends_on`). O trabalho real que falta é só *gerar e comparar candidatos*, não construir a base — escopo menor do que o roadmap estimava, mas ainda não trivial.

---

## Priorização quantitativa (Impacto / Esforço / Risco)

Escala 1-5 (Impacto: 5 = maior valor percebido; Esforço: 5 = mais trabalho; Risco: 5 = mais risco). **Score = Impacto×2 − Esforço − Risco.**

| # | Feature | Impacto | Esforço | Risco | Score |
|---|---|---|---|---|---|
| 1 | GoalManager completo (editar/cancelar/progresso) | 4 | 1 | 1 | **6** |
| 2 | Busca semântica de memória na UI | 3 | 1 | 1 | **4** |
| 3 | Busca por nome em Contacts/Church | 3 | 1 | 1 | **4** |
| 4 | Tool de detalhe de contato (Google Contacts) | 2 | 1 | 1 | **2** |
| 5 | Página de Notas | 3 | 2 | 1 | **3** |
| 6 | Endpoint de preferências de memória | 3 | 2 | 1 | **3** |
| 7 | QR Code do WhatsApp no Dashboard | 3 | 2 | 2 | **2** |
| 8 | Chat de produto (ContentAgent + demais) | 4 | 3 | 1 | **4** |
| 9 | Botão "rodar agente" em `/admin/agents` (debug) | 2 | 2 | 2 | **0** |
| 10 | Envio de e-mail via Gmail | 4 | 3 | 3 | **2** |
| 11 | Edição de série recorrente (Calendar) | 3 | 3 | 2 | **1** |

Itens de Medium/Strategic com escopo grande demais para pontuar de forma
honesta numa escala de 1-5 dias (inbox de conversas, home acionável,
confiança do plano, superfícies proativas, multiusuário, comparação de
planos) ficam de fora desta tabela — são decisões de produto antes de
serem estimativas de esforço, como o discovery já observa em cada um.

---

## Resposta direta: as 5 funcionalidades de maior ROI

1. **GoalManager completo** (score 6) — o maior score da lista **depois da
   correção**: backend quase inteiro já pronto (inclusive acessível hoje
   via WhatsApp), falta essencialmente só a tela.
2. **Busca semântica de memória** (score 4) — `GET /memory/search` já
   existe, esforço mínimo, zero risco.
3. **Busca por nome em Contacts/Church** (score 4) — mesmo padrão: dado e
   lógica já prontos no repositório, só falta expor.
4. **Chat de produto para o ContentAgent** (score 4) — maior esforço deste
   grupo de topo (2-3 dias), mas é a única entrada nesta lista que cria
   uma funcionalidade de produto inteiramente nova e vistosa, não só
   destrava um CRUD.
5. **Página de Notas** (score 3, empatada com preferências de memória) —
   escolhida à frente por ser uma funcionalidade mais visível no dia a dia
   do que uma tela de administração de memória.

## Resumo de priorização sugerida

Nenhuma decisão de priorização foi tomada aqui além do ranking quantitativo
acima — a leitura qualitativa continua sendo decisão do Dário:

- **Maior ROI imediato:** GoalManager e as duas buscas (memória,
  contatos/igreja) — backend pronto, é só destravar frontend.
- **Maior alinhamento com a missão do release** ("assistente usado todo
  dia"): `/conversas` virar inbox de verdade e Superfícies proativas — são
  os dois itens que mais diretamente atacam "as pessoas usam de verdade",
  não só "o sistema é capaz de".
- **Decisão que precisa ser tomada antes de codar qualquer coisa
  relacionada:** multiusuário — não é uma feature pra estimar, é uma
  pergunta pro Dário responder primeiro.
