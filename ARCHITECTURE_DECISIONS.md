# Dario Platform — Architecture Decisions

Resolução dos problemas identificados em `ARCHITECTURE_REVIEW.md`
(nenhum arquivo existente foi alterado para produzir este documento —
nem `PLATFORM_ARCHITECTURE.md`, nem `ARCHITECTURE_REVIEW.md`, nem a
árvore em `docs/`). Cada item segue: Problema → Alternativas possíveis →
Prós → Contras → Solução recomendada → Justificativa técnica.

Nenhuma decisão aqui foi implementada em código. São recomendações para
aprovação — a oficialização de qualquer uma delas nos documentos-fonte
depende de autorização explícita numa etapa futura.

---

## DEC-1 — Fronteira entre Automation e Knowledge

*(resolução prioritária, pedida explicitamente)*

### Problema

`PLATFORM_ARCHITECTURE.md` trata Automation e Knowledge como módulos de
plataforma peer a Business/Investments (diretório, router e posição
próprios na tabela de módulos), mas o próprio texto de Automation admite
ser "evolução de jobs/+workflows/ já existentes, não pacote paralelo", e
Knowledge depende quase inteiramente do Memory Manager do Core para sua
função central. O mapa de posse de dados reforça a ambiguidade:
Automation é o único "módulo" sem nenhuma tabela própria.

### Alternativas possíveis

**A. Manter os dois como módulos completos de plataforma** (estado atual do documento).
**B. Reclassificar os dois como extensão do Core** — sem diretório de módulo, sem posição na tabela de módulos, crescem dentro de `jobs/`, `workflows/`, `memory/` e do Admin existente.
**C. Híbrido por critério objetivo**: um candidato é módulo de plataforma se, e somente se, possuir ao menos uma tabela de dado genuinamente nova; caso contrário, é Core.
**D. Módulo "satélite"**: pacote de código separado por organização, mas classificado como Core para efeito da regra de dependência (module pode ser importado por Core sem violar AD-002).

### Prós e contras

| Alternativa | Prós | Contras |
|---|---|---|
| A | Consistência visual com os demais módulos; não exige retrabalho no documento | Perpetua a ambiguidade já identificada; Automation fica com uma exceção não justificada na regra de posse de dados |
| B | Remove a ambiguidade por completo; Admin (Core) pode exibir os dois sem tensão com AD-002 | Knowledge perde alguma autonomia de evolução futura se crescer além de metadado fino |
| C | Critério objetivo, reaplicável a qualquer módulo futuro (não só estes dois) sem decisão caso a caso | Exige revisitar a classificação se um "módulo Core" começar a acumular tabelas próprias com o tempo |
| D | Preserva a opção de "promover" para módulo completo sem reescrever import paths | Introduz uma terceira categoria (nem Core puro, nem módulo) — mais uma coisa para todo colaborador entender |

### Solução recomendada

**Alternativa C**, aplicada assim:

- **Automation deixa de ser módulo de plataforma.** Zero tabela própria
  hoje (confirmado no mapa de posse de dados) → é Core. Cresce dentro de
  `jobs/`/`workflows/` existentes e do Admin, exatamente como o próprio
  Admin já cresceu de escopo na Sprint 4 sem virar "módulo novo".
- **Knowledge permanece módulo de plataforma**, mas deliberadamente
  mínimo no lançamento: possui tabelas próprias reais
  (`knowledge_sources`, `prompt_templates`), que não pertencem a nenhum
  domínio do Core hoje — isso é o que justifica módulo, não o volume de
  funcionalidade.

### Justificativa técnica

Um critério binário e verificável ("tem tabela própria nova? então é
módulo; não tem? então é Core") é reaplicável para qualquer módulo
futuro sem precisar de outra rodada de revisão arquitetural — resolve
não só este caso, mas estabelece a regra geral que faltava. Reduz a
contagem de módulos de 7 para 6, o que também reduz superfície de teste,
CI e RBAC a manter (ver `ARCHITECTURE_REVIEW.md`, riscos de
escalabilidade de dívida de teste).

---

## DEC-2 — Classificação definitiva dos agentes existentes

*(resolução prioritária, pedida explicitamente)*

### Problema

`PLATFORM_ARCHITECTURE.md` trata a migração de `church_agent` e
`store_agent` como uma única decisão pendente, mas não classifica
nenhum dos 5 agentes do Core (`personal`, `church`, `store`, `content`,
`assistant`) de forma definitiva contra a nova taxonomia de módulos. Sem
isso, não há como saber se um agente novo, no futuro, nasce em `agents/`
(Core) ou em `<módulo>/agents/`.

### Alternativas possíveis

**A. Migrar todos os 5 agentes para dentro de algum módulo de plataforma**, esvaziando `agents/` do Core.
**B. Não migrar nenhum agora — manter os 5 em Core indefinidamente**, e só agentes genuinamente novos nascem em módulo.
**C. Critério por escopo da Visão**: um agente migra para módulo de plataforma se, e somente se, seu domínio estiver listado na Visão como "operação profissional" (trabalho, clientes, investimentos, conteúdo, pesquisa, automações, documentos, conhecimento, negócios, produtividade); do contrário, permanece Core.

### Prós e contras

| Alternativa | Prós | Contras |
|---|---|---|
| A | "Core" fica conceitualmente puro (só infraestrutura, zero agente de domínio) | Migração forçada sem critério pode empurrar `church`/`personal` para módulos onde não se encaixam de verdade (ver `ARCHITECTURE_REVIEW.md`, PF-FRACO-4) |
| B | Zero risco de migração prematura ou errada | Adia indefinidamente uma decisão que Business (T4) e Content Studio (T5) já precisam, no roadmap, para não duplicar `store_agent`/`content_agent` |
| C | Usa um critério que já está escrito na própria Visão, não um critério novo inventado agora; decide os 5 de uma vez, com regra clara para agentes futuros | Exige aceitar que nem todo agente do Core "pertence" à Platform — alguns ficam permanentemente pessoais/estruturais |

### Solução recomendada

**Alternativa C.** Aplicando o critério da Visão ("operação **profissional**") a cada agente:

| Agente | Domínio real | Está na lista da Visão? | Classificação | Quando |
|---|---|---|---|---|
| `assistant` | Gateway WhatsApp + Google Workspace | Estruturalmente ligado ao Core (pipeline, OAuth) | **Core, permanente** | — |
| `personal` | Agenda/tarefas/notas internas | Produtividade pessoal, não "operação profissional" de terceiros | **Core, permanente** | — |
| `church` | Oração, escalas, cultos, membros | Comunitário/pastoral — não é nenhum dos 11 itens da Visão | **Core, permanente** | — |
| `store` | Produtos, pedidos, clientes, orçamentos | Coincide com o escopo de Business ("CRM, Pipeline, Clientes") | **Migra para `business/agents/`** | Quando Business v1 for construído (T4) |
| `content` | Conteúdo para redes sociais, pesquisa, documentos | Coincide com o escopo de Content Studio | **Migra para `content_studio/agents/`** | Quando Content Studio v1 for construído (T5) |

`store_customers` é o seed literal de `Client` em Business, confirmando
a migração de `store_agent`. `church_agent` não tem seed em nenhum
módulo listado — porque, pelo critério da própria Visão, ele nunca foi
destinado a um.

### Justificativa técnica

A pergunta "este agente pertence a um módulo?" agora tem uma resposta
mecânica (está na lista de 11 itens da Visão?) em vez de uma avaliação
caso a caso sujeita a opinião. `church_agent` deixa de ser um problema
sem resposta (PF-FRACO-4) e passa a ser evidência correta de que a
taxonomia é para domínios profissionais — o gap não era da taxonomia,
era da leitura anterior que tratava os 5 agentes como um bloco só.
`store_agent`/`content_agent` ganham uma migração com gatilho explícito
(o próprio marco do roadmap onde o módulo-alvo é construído), evitando
tanto migração prematura quanto esquecimento.

---

## DEC-3 — Política oficial para eventos críticos do Event Bus

*(resolução prioritária, pedida explicitamente)*

### Problema

O Event Bus do Core é fan-out best-effort (sem garantia de entrega),
desenhado para notificação interna. `PLATFORM_ARCHITECTURE.md` o usa
como canal default para os Fluxos 1 e 2 do catálogo de eventos, que
incluem etapas de negócio que não podem simplesmente desaparecer (ex.:
`business.proposal_requested` → `content_studio.presentation_generated`
→ `business.followup_scheduled`). Isso cria também uma dependência
circular de runtime entre Business e Content Studio sem política de
falha definida.

### Alternativas possíveis

**A. Manter tudo no Event Bus e construir um coordenador de saga/compensação por cima** — nova peça de infraestrutura.
**B. Adicionar garantia de entrega ao próprio Event Bus** (persistir evento antes do fan-out, exigir ack do consumidor) — o Event Bus vira, na prática, uma segunda fila.
**C. Classificar cada transição por criticidade e usar o mecanismo certo para cada uma**: notificação (Event Bus, perda aceitável) vs. etapa obrigatória (fila de jobs durável do Core, que já tem persistência, retry com backoff e claim atômico).

### Prós e contras

| Alternativa | Prós | Contras |
|---|---|---|
| A | Resolve o problema sem duplicar semântica de fila | Constrói infraestrutura nova (coordenador de saga) que o projeto não tem hoje — alto custo, alto risco de bug em código de coordenação distribuída |
| B | Um canal só para tudo, mais simples de explicar | Reimplementa, com outro nome, exatamente o que a fila de jobs já faz — duplicação de infraestrutura, não simplificação |
| C | Zero infraestrutura nova — reaproveita a fila de jobs já comprovada em produção (`whatsapp.process_inbound`, retry, `job.failed` → mensagem de desculpas) | Exige revisar/anotar, evento por evento, qual categoria cada um é — trabalho de especificação, não de código |

### Solução recomendada

**Alternativa C**, formalizada como regra:

> **Toda transição de estado que, se perdida, deixa o sistema num
> estado observável como inconsistente por um humano (cliente sem
> proposta, relatório não gerado, follow-up nunca agendado) é modelada
> como Job — nunca como evento do Event Bus.** O Event Bus continua
> disponível, em paralelo, só para observabilidade/reação opcional
> (métricas, Admin, integrações "seria bom mas não obrigatório").

Reclassificação concreta do Fluxo 1: `business.proposal_requested`
dispara um job (`business.generate_proposal`), processado por um
handler registrado em Content Studio (`@job_handler(...)`, mesmo padrão
já usado hoje) — herda retry, persistência e falha tratada
automaticamente. O evento `business.proposal_requested` continua sendo
publicado no Event Bus, mas só para quem quiser observar, não para
carregar a obrigação de a proposta ser gerada.

Isso resolve, no mesmo movimento, a dependência circular de runtime
(RISCO-2): não é mais Business "esperando" um evento de Content Studio
via pub/sub — é uma cadeia de jobs com falha e retry explícitos, o
mesmo padrão já usado e testado no auto-reply do WhatsApp.

### Justificativa técnica

Zero infraestrutura nova — a fila de jobs já resolve exatamente o
problema (persistência, retry exponencial, tratamento de falha
definitiva) que um coordenador de saga resolveria do zero. É a mesma
disciplina de "reaproveitar o que já existe" que justificou todo o
resto da arquitetura da plataforma (ver `docs/architecture/MASTER_CONTEXT.md`,
"Princípio arquitetural central"). O Event Bus permanece fiel ao seu
propósito original (notificação leve), em vez de ser esticado para uma
responsabilidade que não foi desenhado para carregar.

---

## DEC-4 — Fonte oficial única da arquitetura

*(resolução prioritária, pedida explicitamente)*

### Problema

`PLATFORM_ARCHITECTURE.md` (raiz, monolítico) e a árvore
`docs/architecture/`, `docs/modulos/`, `docs/roadmap/`,
`docs/governance/` contêm, hoje, o mesmo conteúdo distribuído de duas
formas diferentes — duas fontes de verdade já divergem no momento em que
qualquer uma for editada sem a outra.

### Alternativas possíveis

**A. `PLATFORM_ARCHITECTURE.md` vira a fonte única**, e a árvore em `docs/` é removida ou reduzida a um índice.
**B. A árvore em `docs/` vira a fonte única**, e `PLATFORM_ARCHITECTURE.md` vira um resumo executivo curto, com links.
**C. Manter os dois permanentemente sincronizados manualmente.**

### Prós e contras

| Alternativa | Prós | Contras |
|---|---|---|
| A | Um único arquivo, fácil de ler de ponta a ponta | Cresce sem limite conforme a plataforma cresce — o padrão que o resto do projeto já evitou (`docs/` do Core já é dividido por assunto: `AGENTS.md`, `TOOLS.md`, `EMAIL.md`, etc., nunca um arquivo único) |
| B | Consistente com a convenção já estabelecida no projeto (`docs/*.md` por assunto + `README.md`/documento-índice apontando para eles) | Exige reescrever `PLATFORM_ARCHITECTURE.md` para virar índice, em vez de conteúdo completo |
| C | Nenhum arquivo perde conteúdo | É a própria causa raiz do problema (RISCO-6), não uma solução — rejeitada |

### Solução recomendada

**Alternativa B.** `docs/architecture/`, `docs/modulos/`,
`docs/roadmap/`, `docs/governance/` passam a ser a fonte oficial.
`PLATFORM_ARCHITECTURE.md` é reduzido, numa etapa de implementação
futura (não nesta), a um documento curto de entrada — visão em um
parágrafo e uma tabela de links para os quatro documentos — no mesmo
espírito de como a seção "Documentação" do `README.md` já indexa
`docs/*.md` sem duplicar o conteúdo de cada um.

### Justificativa técnica

O projeto já resolveu esta mesma pergunta para a documentação do Core
(um arquivo por assunto em `docs/`, indexado por `README.md`) — não há
razão técnica para a documentação da Platform adotar um padrão
diferente do que o resto do repositório já usa e mantém há várias
sprints sem drift. Consistência de convenção reduz a carga cognitiva de
quem já conhece o projeto.

---

## DEC-5 — Research Lab: módulo de produto ou processo de governança?

### Problema

Research Lab recebe, em `PLATFORM_ARCHITECTURE.md`, a mesma arquitetura
pesada de Business/Investments (`models.py`, `repositories.py`,
`service.py`, `router.py`) mesmo o texto reconhecendo que é "processo,
não automação". A estrutura `docs/` já criada nesta sessão é, na
prática, uma versão funcional de Research Lab sem nenhuma linha de
código.

### Alternativas possíveis

**A. Manter como módulo de produto completo desde o início.**
**B. Começar como processo puro (markdown + git, o que já existe hoje), promover a módulo de produto só com evidência de necessidade.**

### Prós e contras

| Alternativa | Prós | Contras |
|---|---|---|
| A | UI de busca/filtro de RFCs desde o dia um | Constrói banco, API e frontend para um volume de dado (RFCs, ADRs) que provavelmente cabe em dezenas de arquivos markdown por anos |
| B | Zero custo de construção — já existe hoje, funcionando | Sem busca estruturada até haver volume que justifique |

### Solução recomendada

**Alternativa B.** Research Lab não entra na lista de módulos a
codificar em `backend/`. O gatilho de promoção (definido agora, para não
depender de julgamento subjetivo depois): revisar quando o número de
RFCs/ADRs ativos ultrapassar um volume que markdown+busca de texto não
resolva mais razoavelmente (ordem de grandeza: dezenas de documentos
correntes, não centena).

### Justificativa técnica

Consistente com "toda alteração deve ser mínima e justificada" — não há
evidência hoje de que markdown+git seja insuficiente. Construir a versão
pesada antes de provar a necessidade é o oposto do princípio central da
plataforma (reaproveitar antes de construir).

---

## DEC-6 — Onde vivem os contratos (`Protocol`) de Provider por módulo

### Problema

Nenhuma definição de se `CRMProvider`, `MarketDataProvider`,
`DesignProvider`, `PublishingProvider` são declarados dentro de cada
módulo (sem padronização entre eles) ou centralizados de forma
verificável.

### Alternativas possíveis

**A. Cada módulo declara seu próprio `Protocol` internamente, sem padrão comum.**
**B. Um marcador mínimo compartilhado no Core** (ex.: `PlatformProvider`, um `Protocol` vazio ou quase vazio que todo Provider de módulo deve implementar) **, mantendo o contrato específico de cada categoria dentro do módulo.**

### Prós e contras

| Alternativa | Prós | Contras |
|---|---|---|
| A | Módulos totalmente independentes, zero acoplamento até com um marcador | "Obrigatório usar Strategy+Factory" vira regra social — nada barra um módulo futuro de pular a abstração |
| B | Torna a disciplina estruturalmente verificável (um lint/teste pode checar `isinstance(provider, PlatformProvider)`) | Um pingo de acoplamento a mais: todo módulo importa esse marcador do Core |

### Solução recomendada

**Alternativa B.** O marcador é deliberadamente mínimo (não define
métodos de negócio, só uma interface vazia ou com metadado genérico como
`provider_name`) — não viola AD-002 em espírito, porque não é o Core
dependendo de módulo, é o inverso (módulo depende de um contrato de
Core), que já é permitido.

### Justificativa técnica

O mesmo raciocínio de PF-FRACO-5 no `ARCHITECTURE_REVIEW.md`: sem um
ponto estrutural de verificação, "todo Provider deve seguir
Strategy+Factory" é intenção, não garantia. Um marcador mínimo custa
quase nada e fecha essa lacuna.

---

## DEC-7 — Estratégia de escala de dados (Postgres único)

### Problema

Sete módulos com perfis de carga potencialmente muito diferentes
(transacional em Business, série temporal em Investments, blob-like em
Content Studio) compartilham um único Postgres, sem estratégia de
connection pool, read replica ou particionamento discutida.

### Alternativas possíveis

**A. Definir agora uma estratégia de escala (replica, particionamento).**
**B. Manter Postgres único, revisar só com evidência real de contenção, com gatilho definido antecipadamente.**

### Solução recomendada

**Alternativa B.** Não há, hoje, nenhum módulo implementado nem dado
real — desenhar infraestrutura de escala para uma carga hipotética é
over-engineering. Gatilho de revisão definido agora: p95 de latência de
query em qualquer tabela de módulo ultrapassando um limiar perceptível
pelo usuário, ou uma tabela de módulo ultrapassando volume que torne
`VACUUM`/backup diário (`scripts/backup.sh`) impraticável.

### Justificativa técnica

Consistente com a decisão já tomada de não ir para microsserviços
prematuramente (AD-001 em `docs/architecture/ARCHITECT_DECISIONS.md`) —
mesma lógica aplicada a dados: a opção de particionar/replicar mais
tarde continua aberta, contanto que os módulos não façam suposições que
a impeçam (ex.: nenhum JOIN cross-módulo, já proibido por AD-002/regra
de posse de dados).

---

## DEC-8 — Schema do `manifest.py` para o Admin

### Problema

Sem um schema fixo, o Admin (Core) corre risco de precisar de código
específico por módulo para interpretar cada manifest — acoplamento
oculto que não aparece como `import` mas existe na prática.

### Alternativas possíveis

**A. Schema livre por módulo.**
**B. Schema mínimo fixo e obrigatório**, ex.: `{module, version, status, headline_metric}` — sem campos livres adicionais na v1.

### Solução recomendada

**Alternativa B.** Um schema fixo, por menor que seja, é o que permite
ao Admin renderizar qualquer módulo novo sem código adicional —
exatamente o mesmo princípio de auto-descoberta já usado no Agent/Tool
Registry, aplicado um nível acima.

### Justificativa técnica

Resolve RISCO-4 do `ARCHITECTURE_REVIEW.md` na raiz: a ameaça não era o
`manifest.py` existir, era ele não ter forma garantida.

---

## DEC-9 — Mitigação da degradação do Planner com mais agentes

### Problema

O Cognitive Planner decide qual agente usar listando os agentes
disponíveis no prompt enviado ao LLM. Com 15–20 agentes (todos os
módulos maduros) em vez de 5 hoje, isso tende a aumentar tokens por
chamada, latência e chance de escolha errada.

### Alternativas possíveis

**A. Resolver agora, antes de qualquer módulo existir.**
**B. Adiar até Multi-Agent (T7 do roadmap), com um gatilho de revisão explícito, para não resolver um problema de escala que ainda não existe.**
**C. Introduzir já um pré-filtro de duas etapas (roteamento barato por regra/heurística antes de perguntar ao LLM entre um subconjunto pequeno).**

### Solução recomendada

**Alternativa B**, com gatilho definido: revisar quando o número de
agentes registrados ultrapassar 8–10 (ainda dentro de Business +
Content Studio, antes de Investments). Não implementar C
preventivamente — não há evidência hoje de degradação real, e a
correção antecipada de um problema hipotético é o tipo de "melhoria
aproveitando que está mexendo" que as regras desta sessão pedem para
evitar.

### Justificativa técnica

O próprio Multi-Agent (T7) já é o marco do roadmap dedicado a repensar
como agentes são selecionados e colaboram — resolver o mesmo problema
duas vezes (uma vez cedo, de forma pontual, outra vez em T7, de forma
estrutural) é desperdício. Nomear o gatilho agora evita que o risco seja
esquecido sem exigir ação prematura.

---

## Resumo das decisões

| # | Decisão | Recomendação |
|---|---|---|
| DEC-1 | Automation vs Knowledge | Automation → Core; Knowledge → módulo mínimo. Critério geral: módulo = tem tabela própria nova |
| DEC-2 | Classificação de agentes | `assistant`/`personal`/`church` → Core permanente; `store`→Business (T4); `content`→Content Studio (T5) |
| DEC-3 | Eventos críticos | Etapa obrigatória → fila de jobs; notificação → Event Bus. Resolve também a dependência circular Business↔Content Studio |
| DEC-4 | Fonte oficial | `docs/{architecture,modulos,roadmap,governance}/` vira fonte única; `PLATFORM_ARCHITECTURE.md` vira índice curto (mudança a aplicar em etapa futura) |
| DEC-5 | Research Lab | Não codificar agora — já existe como processo em `docs/` |
| DEC-6 | Contratos de Provider | Marcador mínimo compartilhado no Core (`PlatformProvider`) |
| DEC-7 | Escala de dados | Postgres único, gatilho de revisão definido, sem ação agora |
| DEC-8 | Schema do manifest | Fixo e mínimo, não livre |
| DEC-9 | Escala do Planner | Adiar para T7 (Multi-Agent), gatilho em 8–10 agentes |

Nenhuma decisão foi aplicada aos documentos-fonte. Aguardando aprovação
para oficializar.
