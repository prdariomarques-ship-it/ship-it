# Dario Platform — Roadmap de 24 Meses

Sequenciamento de evolução da Dario Platform a partir do Core (Dario OS
v1.2.0) já em produção. Um módulo por vez, cada um só começa depois do
anterior estar em uso real — não em paralelo, para não repetir o risco
de espalhar esforço fino demais (ver "Maiores riscos técnicos" abaixo).
Para o catálogo de módulos, ver `MODULE_CATALOG.md (raiz)`.

Este roadmap se apoia no `ROADMAP_v2.md` do Core (raiz do repositório),
que já sequencia v1.2.1 → v1.3.0 → v1.4.0 → v2.0.0 — os primeiros
trimestres aqui são esse roadmap, sem duplicá-lo.

## Sequenciamento

| Trimestre | Foco | Depende de |
|---|---|---|
| T1 (0–3m) | Fechar v1.2.1 (CSP/HSTS) e v1.3.0 (retry/circuit breaker Google) do Core. Formalizar processo de RFC/ADR (Research Lab v0, só processo, sem código). | Nada — já planejado em `ROADMAP_v2.md` |
| T2 (3–6m) | **Knowledge v1** — menor risco, maior reaproveitamento. Expandir base além do Google Drive, Prompt Library. | Core estável |
| T3 (6–9m) | **Automation v1** — expor Scheduler (já previsto em `ROADMAP_v2.md` v1.4.0), visibilidade de fila no Admin. | Core estável |
| T4 (9–12m) | **Business v1** — decisão sobre `church_agent`/`store_agent` primeiro (ver `ARCHITECTURE_DECISIONS.md (raiz) e ARCHITECTURE_FINAL.md (raiz)`); CRM real sobre Event Bus/Memory já existentes. | Decisão pendente sobre church/store; Knowledge para RAG de cliente |
| T5 (12–15m) | **Content Studio v1** — agente de copywriting + 1–2 canais (maior retorno primeiro), usando integrações Canva/Adobe já disponíveis. | Business (perfil de cliente alimenta conteúdo personalizado) |
| T6 (15–18m) | **Investments v1, escopo pessoal apenas** — carteira própria, sem servir terceiros, para adiar a questão regulatória. Primeira tarefa do trimestre: escolher provedor de dados de mercado (nenhum conectado ainda). | Nenhuma integração de mercado escolhida ainda |
| T7 (18–21m) | **Multi-Agent** (já previsto em `ROADMAP_v2.md` v2.0.0) — colaboração entre agentes de módulos diferentes, justificada pela primeira vez em escala real com 5+ verticais rodando. | Business + Content Studio maduros |
| T8 (21–24m) | Admin de plataforma completo — KPIs cruzados entre módulos, Self Healing/Memory Evolution (v2.0.0) aplicados com dado real de uso multi-módulo. | Todos os módulos acima em uso real |

Cada trimestre termina em um estado *shippable* e testado — nenhum
módulo fica "meio construído" enquanto o próximo começa.

## Maiores riscos técnicos

1. **Explosão de escopo.** Sete módulos novos é um projeto de anos, não
   de meses. Mitigação: um módulo por vez (regra deste roadmap), nunca
   em paralelo.
2. **Investments carrega peso regulatório potencial** se em algum
   momento passar de "carteira pessoal" para aconselhar/gerenciar
   dinheiro de terceiros — decisão jurídica, não de arquitetura. T6 adia
   isso escopando para uso pessoal apenas.
3. **Ambiguidade dono-único vs. multi-cliente.** O RBAC atual
   (`admin`/`user`) foi desenhado para um sistema pessoal; Business
   introduz "cliente" como sujeito de dado, não usuário do sistema —
   isolamento por cliente ainda não tem o mesmo rigor que
   `ToolContext.contact_id` já garante hoje (PROD-005).
4. **Colisão de modelo de dados** com `store_customers`/`church_members`
   já existentes — ver decisão pendente em
   `ARCHITECTURE_DECISIONS.md (raiz) e ARCHITECTURE_FINAL.md (raiz)`.
5. **Sprawl de Providers** sem a disciplina Strategy+Factory (AD-004) —
   risco maior em Content Studio, que prevê mais integrações externas
   que qualquer outro módulo.
6. **Dívida de teste escalando.** 555 testes de backend hoje cobrem
   essencialmente um produto. Sete módulos no mesmo rigor
   (`CONTRIBUTING.md`: "toda mudança de comportamento vem com teste") é
   investimento contínuo, não tarefa única — precisa entrar no
   orçamento de cada trimestre, não ser tratado como opcional depois.
7. **Complexidade do Orchestrator/Planner** com 15–20 agentes possíveis
   em vez dos 5 atuais — Multi-Agent (T7) existe para isso, mas até lá o
   Planner pode precisar de ajuste incremental.
8. **Superfície de segurança maior** — dados de cliente (Business) e
   dados financeiros (Investments) são muito mais sensíveis que
   histórico de WhatsApp. O isolamento técnico que já existe precisa se
   estender a esses domínios com o mesmo padrão, não um mais fraco.

## Maiores oportunidades estratégicas

1. **O padrão de plugin já é a vantagem competitiva** — provado 4 vezes
   no Core (WhatsApp, LLM, Google Workspace, Admin Dashboard). Adicionar
   um domínio novo é arquiteturalmente barato, não um risco a mitigar.
2. **Integrações já conectadas no ambiente de desenvolvimento
   aceleram Business e Content Studio de forma concreta**: HubSpot,
   Canva, Adobe, Figma, Gamma — meses de integração potencialmente
   evitados (ver `MODULE_CATALOG.md (raiz)`).
3. **Memory Manager + Event Bus já entregam a experiência cross-domain**
   que os fluxos de exemplo da visão pedem (contexto de cliente
   alimentando uma proposta, alimentando uma ideia de conteúdo) — é
   reaproveitamento de infraestrutura, não construção nova.
4. **Cultura de observabilidade desde o dia um** (Correlation ID,
   Prometheus, OpenTelemetry, Playwright, cobertura ≥90%) evita o
   retrabalho que normalmente consome o segundo ano de uma plataforma em
   crescimento.
5. **Disciplina de mudança mínima e documentação permanente já é
   hábito**, não exceção — o Research Lab (T1) formaliza o que o projeto
   já pratica desde a Sprint 1.
6. **Ser dono único da operação hoje é vantagem de velocidade.**
   Business e Investments podem nascer escopados para uso pessoal e
   ainda assim entregar valor real imediatamente — a complexidade de
   servir terceiros pode ser adiada até haver evidência de que vale a
   pena.
