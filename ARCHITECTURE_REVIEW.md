# Architecture Review — PLATFORM_ARCHITECTURE.md

Revisão crítica do rascunho arquitetural da Dario Platform
(`PLATFORM_ARCHITECTURE.md`, não alterado por esta revisão). Objetivo:
validar antes de oficializar, não aprovar por cortesia — os pontos
abaixo incluem discordâncias reais com o documento, não só elogios.

---

## 1. Pontos fortes

**PF-1 — Reaplicação de padrão provado, não invenção de arquitetura nova.**
O documento resiste à tentação mais comum em exercícios de "visão de
plataforma": inventar uma camada de abstração nova. Em vez disso, aposta
em algo já testado 4 vezes no Core (Agent/Tool Registry, Provider
Strategy+Factory). Isso é uma escolha de engenharia madura, não
preguiça.

**PF-2 — Recusa deliberada de microsserviços.** A justificativa em
"Decisão de topologia" é concreta (sem time crescendo, sem necessidade
de escalar módulo isolado, operador único) em vez de genérica. Resiste a
um dos over-engineerings mais comuns em documentos de "arquitetura de
plataforma" escritos antes de haver usuários reais.

**PF-3 — Regra de dependência unidirecional é simples e verificável.**
"Core nunca importa de módulo" (linhas 51–56) é uma regra que pode virar
um lint de CI trivial (`grep`/AST check de import). Poucas regras de
arquitetura sobrevivem ao teste "dá para automatizar a verificação?" —
esta passa.

**PF-4 — Disciplina de migração (expand-contract) declarada antes de
qualquer módulo existir.** A maioria dos projetos só adota essa
disciplina depois da primeira migração quebrada em produção. Aqui está
sendo exigida preventivamente (linhas 238–246).

**PF-5 — O documento se autodenuncia em pelo menos um ponto real.** A
seção "Observabilidade" (linhas 263–268) identifica um gap genuíno (Flow
ID para fluxos multi-etapa) sem tentar escondê-lo atrás de "resolveremos
depois" vago — nomeia o mecanismo que falta e onde ele provavelmente
será resolvido. Isso é raro em documento de visão e deveria ser o padrão
para as seções de risco também (ver Pontos fracos).

**PF-6 — Sequenciamento do roadmap ancorado em reaproveitamento real, não
em prioridade idealizada.** T2/T3 (Knowledge, Automation) vêm primeiro
porque já têm seed no Core, não porque são "mais importantes" — decisão
pragmática, defensável.

---

## 2. Pontos fracos

**PF-FRACO-1 — "Automation" não está claro se é módulo ou extensão do
Core.** O texto diz explicitamente "evolução de jobs/+workflows/ já
existentes, **não pacote paralelo**" (linha 133), mas a tabela de
módulos (linha 80) e a árvore de diretórios (linhas 130–133) o tratam
como um módulo peer de Business/Investments, com diretório e router
próprios. O mapa de posse de dados (linha 216) reforça a ambiguidade:
é o único "módulo" sem tabela própria, usando `jobs` (tabela do Core)
diretamente — o que ou é uma exceção não justificada à regra de posse de
dados, ou é evidência de que Automation não é um módulo de verdade,
é Core sendo exposto. O documento não decide qual das duas coisas é.

**PF-FRACO-2 — "Knowledge" tem a mesma ambiguidade, por motivo
diferente.** Sua função central (busca) já existe inteiramente no
Memory Manager do Core; as tabelas próprias listadas
(`knowledge_sources`, `prompt_templates`) são metadado fino em cima de
uma capacidade que não é dele. Não é claramente errado modelar assim,
mas o documento não argumenta por que isso merece um módulo inteiro
(diretório, router, grupo de rotas de frontend) em vez de ser uma aba
nova dentro do Admin/Core existente.

**PF-FRACO-3 — Research Lab é tratado como módulo de produto quando é,
na prática, um processo de governança.** A própria seção reconhece isso
("sem agents/tools próprios inicialmente — processo, não automação",
linha 128), mas ainda assim recebe `models.py`, `repositories.py`,
`service.py`, `router.py` — a mesma arquitetura pesada de Business ou
Investments. Nada no documento demonstra que RFC/ADR precisam de banco
de dados e API antes de markdown-em-git ter se mostrado insuficiente —
e a estrutura `docs/architecture/`, `docs/governance/`, etc. criada
nesta mesma sessão já é, de fato, uma versão funcional de Research Lab
sem nenhuma linha de código.

**PF-FRACO-4 — `church_agent` não tem lugar em lugar nenhum da
taxonomia, e o documento trata isso como se fosse a mesma pergunta que
`store_agent`.** "Decisões pendentes" (linha 336) agrupa os dois agentes
numa frase só ("church_agent/store_agent... evoluem para dentro de
business/... ou ficam como estão"), mas são domínios diferentes:
`store_agent` é comercial e se encaixa na descrição de Business ("CRM,
Pipeline, Clientes"); `church_agent` é pastoral/comunitário e não se
encaixa em **nenhum** dos 7 módulos listados — não é cliente, não é
conteúdo, não é conhecimento. Tratar os dois como uma decisão única
mascara que um deles (church) não tem resposta na taxonomia atual,
correta ou não.

**PF-FRACO-5 — Nenhuma definição de onde vivem os contratos (`Protocol`)
de Provider por categoria.** A seção "Providers — governança" (linhas
219–236) exige que toda integração implemente um `Protocol` documentado,
mas não diz se `CRMProvider`, `MarketDataProvider`, `DesignProvider`,
`PublishingProvider` são definidos dentro do próprio módulo (então cada
módulo reinventa a forma do contrato) ou centralizados em algum lugar
verificável. Sem isso, "Strategy+Factory obrigatório" é uma regra social,
não uma regra estrutural — nada no desenho impede um módulo futuro de
pular a abstração.

**PF-FRACO-6 — Duas fontes de verdade já existem para o mesmo
conteúdo.** `PLATFORM_ARCHITECTURE.md` (este arquivo) e a árvore
`docs/architecture/`, `docs/modulos/`, `docs/roadmap/`,
`docs/governance/` criada na mesma sessão contêm, hoje, a mesma
informação distribuída de duas formas diferentes. Isso é exatamente o
tipo de duplicação que a "Governança técnica" do próprio documento
(linhas 293–299) deveria pegar se fosse aplicada a si mesma.

---

## 3. Riscos

**RISCO-1 (alto) — Event Bus é "best-effort", mas o documento o usa como
canal default para fluxos de negócio críticos.** O Event Bus do Core
(fan-out via Redis, sem garantia de entrega — comportamento herdado, não
alterado por este documento) foi desenhado para notificação interna
(`agent.selected`, `job.failed`). O Fluxo 1 do catálogo de eventos
(linhas 176–183) encadeia `business.proposal_requested` →
`content_studio.presentation_generated` → `business.followup_scheduled`
→ `business.report_generated` inteiramente via esse mesmo canal — mas
agora o "evento perdido" não é mais "uma métrica não incrementou", é "um
cliente nunca recebeu a proposta e ninguém percebeu". O documento não
distingue notificação (aceitável perder) de etapa obrigatória de
processo de negócio (não aceitável perder), e não propõe nenhum
mecanismo de saga/compensação/timeout para quando uma etapa do meio da
cadeia falha silenciosamente.

**RISCO-2 (médio-alto) — Dependência circular de runtime entre Business
e Content Studio, sem política de falha.** O Fluxo 1 exige que Business
publique um evento, espere (implicitamente) o Content Studio responder
com outro evento, para então continuar seu próprio fluxo. O roadmap
(T5) também declara Content Studio dependente de Business. Isso não é
uma dependência circular de import (a regra de dependência do Core
continua válida), mas é uma dependência circular de **fluxo de
controle** entre dois módulos igualmente novos — se Content Studio
atrasar ou cair, o processo de Business trava num estado indefinido, e o
documento não define o que acontece nesse caso.

**RISCO-3 (médio) — Um único Postgres para 7 módulos com perfis de
carga muito diferentes**, sem estratégia de connection pool, read
replica, ou particionamento discutida. `embeddings` já é uma tabela
compartilhada e pesada hoje (Core); o documento adiciona Knowledge como
mais um consumidor dela e Investments/Content Studio como potenciais
geradores de volume alto (séries temporais de cenário macro, conteúdo
gerado) sem qualquer menção a limite de escala.

**RISCO-4 (médio) — "Manifest" de módulo para o Admin pode virar
acoplamento oculto.** Se cada módulo expõe um status muito diferente
(negócios em pipeline vs. valor de carteira vs. posts publicados), o
Admin (Core) corre risco real de precisar de código específico por
módulo para renderizar isso de forma útil — o que na prática seria Core
"conhecendo" a forma interna de cada módulo, uma violação de fato da
regra de dependência mesmo sem um `import` explícito no código.

**RISCO-5 (médio) — Planner do Cognitive Pipeline degrada com contagem
de agentes, e o mecanismo concreto não está nomeado.** O próprio
documento lista isso como risco (linha 322), mas sem dizer *como* ele se
manifesta: o Planner hoje decide qual agente usar listando os agentes
disponíveis no prompt enviado ao LLM — 15–20 agentes em vez de 5 não é
só "mais complexo", é mais tokens por chamada, mais chance de escolha
errada, e provavelmente mais latência por decisão. Vale nomear o
mecanismo, não só o sintoma.

**RISCO-6 (baixo, mas concreto e imediato) — Deriva entre
`PLATFORM_ARCHITECTURE.md` e `docs/{architecture,modulos,roadmap,governance}/`
já é possível a partir de agora**, porque são dois lugares editáveis
independentemente com o mesmo conteúdo. Isso não é risco futuro — já é
verdade hoje, com os dois conjuntos de arquivo em estado *draft* e sem
mecanismo de sincronização.

---

## 4. Sugestões de melhoria

**SUG-1 — Decidir explicitamente: Automation é módulo ou é Core.** Se a
resposta é "é uma extensão da fila de jobs existente", tratar como tal
(sem diretório de módulo próprio, sem posição na tabela de módulos como
peer de Business) — reduz de 7 para 6 módulos reais, e remove a exceção
não justificada na regra de posse de dados.

**SUG-2 — Adiar Knowledge como módulo próprio até haver evidência de
necessidade.** Começar como uma aba/feature dentro do Admin existente
(ele já lê `embeddings`/Google Drive hoje para a página Memory). Criar
`knowledge/` como pacote independente só quando a superfície justificar
router e frontend próprios.

**SUG-3 — Não codificar Research Lab. Ele já existe.** A estrutura
`docs/architecture/`, `docs/governance/`, `docs/modulos/`,
`docs/roadmap/` criada nesta sessão é, literalmente, uma implementação
v0 funcional de Research Lab, com zero linha de código. Recomendo tratar
"criar `research_lab/` com `models.py`/`router.py`" como um item de
roadmap explicitamente condicional — só construir se o processo baseado
em markdown+git se mostrar insuficiente (ex.: volume de RFCs justificar
busca/filtro estruturado).

**SUG-4 — Separar a decisão sobre `church_agent` da decisão sobre
`store_agent`.** São perguntas diferentes: uma é "este agente comercial
vira o seed de Business" (decisão de arquitetura), a outra é "onde este
domínio pastoral/comunitário mora numa taxonomia que não tem essa
categoria" (decisão de escopo de produto que talvez exija uma 9ª
categoria, ou aceitar que nem todo Agent do Core precisa migrar para um
módulo de plataforma).

**SUG-5 — Definir onde vivem os `Protocol`s de Provider por categoria.**
Recomenda-se um contrato mínimo compartilhado no Core (análogo a como
`LLMProvider`/`WhatsAppProvider` já funcionam) que todo Provider de
módulo declare implementar — transforma "Strategy+Factory obrigatório"
de regra social em regra estruturalmente verificável.

**SUG-6 — Para os Fluxos 1 e 2, nomear explicitamente qual etapa é
"notificação" (Event Bus, best-effort aceitável) e qual etapa é "negócio
crítico" (deveria passar pela fila de jobs durável do Core, que já tem
retry e persistência, em vez do Event Bus).** Isso não exige nenhuma
infraestrutura nova — é usar a ferramenta certa (`jobs`, não `events`)
para a garantia que cada etapa realmente precisa.

**SUG-7 — Especificar o schema mínimo do `manifest.py`** (ex.:
`{module, version, status, headline_metric}` fixo, sem campos livres por
módulo) antes de qualquer módulo o implementar — evita que o Admin
acumule conhecimento implícito da forma interna de cada módulo.

---

## 5. Mudanças recomendadas antes do primeiro commit

1. **Resolver PF-FRACO-6 primeiro, antes de qualquer outra mudança de
   conteúdo**: decidir se `PLATFORM_ARCHITECTURE.md` continua sendo a
   fonte única (e a árvore em `docs/` é removida ou vira só um índice
   que aponta para ele) ou se a árvore em `docs/` passa a ser a fonte
   única (e `PLATFORM_ARCHITECTURE.md` vira um resumo executivo curto
   com links). Commitar os dois como estão hoje oficializa uma
   duplicação.
2. Aplicar SUG-1 e SUG-2 — reclassificar Automation e Knowledge antes de
   qualquer módulo entrar em implementação, não depois. Mudar isso
   depois de código existir é retrabalho; mudar agora é edição de texto.
3. Aplicar SUG-6 no catálogo de eventos — marcar cada evento do Fluxo 1 e
   do Fluxo 2 como "notificação" ou "etapa crítica", e redirecionar as
   críticas para a fila de jobs em vez do Event Bus.
4. Registrar RISCO-1 e RISCO-2 como ADR próprio (não apenas um risco
   listado) em `docs/architecture/ARCHITECT_DECISIONS.md`, já que têm
   impacto direto no desenho do Automation/Event Bus — riscos dessa
   magnitude merecem decisão registrada, não só menção.
5. Aplicar SUG-4 — separar a decisão pendente de `church_agent` da de
   `store_agent` explicitamente, em vez de uma única entrada combinada.
6. Não commitar `research_lab/` como diretório de código no backend
   (SUG-3) até essa decisão ser tomada explicitamente — nada no roadmap
   exige isso antes de T1.

Nenhuma dessas mudanças foi aplicada por esta revisão — `PLATFORM_ARCHITECTURE.md`
permanece exatamente como estava. Este documento (`ARCHITECTURE_REVIEW.md`)
também não foi commitado nem enviado ao remoto.
