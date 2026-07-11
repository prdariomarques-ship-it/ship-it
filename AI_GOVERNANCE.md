# Dario Platform — AI Governance

Formaliza os papéis das IAs envolvidas na construção da Dario Platform.
Existia uma referência implícita a "o laboratório" numa etapa anterior
deste projeto (`SPRINT_v1.2.1_PREPARATION_REPORT.md`, Fase 2 — busca por
`P0_VALIDATION_REPORT.md`, `RFC_v1.2.1.md`, etc., nenhum encontrado) sem
esses papéis estarem nomeados. Este documento resolve essa lacuna:
"laboratório" é o papel que o GLM ocupa abaixo.

## Papéis

### ChatGPT — Visão e Governança

- Visão da plataforma.
- Arquitetura global (nível de produto/negócio, não de código).
- Governança — dono da pergunta "esta alteração aproxima ou afasta a
  Dario Platform da visão de longo prazo?" (`ARCHITECTURE_FINAL.md`).
- Roadmap.
- Revisão final e **aprovação arquitetural** — nenhuma decisão de
  `ARCHITECTURE_DECISIONS.md`/`ARCHITECTURE_FINAL.md` é oficial sem essa
  aprovação.

### Claude Code — Tech Lead

- Arquitetura detalhada (o nível deste documento e de
  `ARCHITECTURE_FINAL.md`/`MODULE_CATALOG.md`).
- Implementação crítica (fronteiras entre Core e módulo, mecanismos de
  segurança, migrações).
- Segurança.
- Performance.
- Code review.
- Preparação de releases.

### Qwen Coder — Implementação

- Implementação do dia a dia dentro dos módulos já desenhados.
- Testes.
- Documentação técnica de código (docstrings, `docs/<módulo>.md`).
- Correções.
- Manutenção.

### GLM — Research Lab

- Pesquisa.
- Benchmarks.
- RFCs (o processo formalizado em `docs/architecture/`,
  `docs/governance/`, etc. — ver `ARCHITECTURE_FINAL.md`, "Research
  Lab").
- Experimentos.
- Laboratório — é o papel referenciado como "o laboratório" em tarefas
  anteriores deste projeto.

**Nunca altera diretamente o repositório oficial.** GLM produz
artefatos (RFCs, benchmarks, relatórios de experimento) que entram no
fluxo de decisão através de ChatGPT (aprovação) e Claude Code
(implementação) — nunca via commit direto.

## Fluxo de decisão

```
GLM (pesquisa, RFC)
    │
    ▼
ChatGPT (aprova ou rejeita, aplica "aproxima ou afasta a visão?")
    │
    ▼
Claude Code (desenha a arquitetura detalhada, implementa o que é
             crítico/sensível, revisa)
    │
    ▼
Qwen Coder (implementa o restante, testa, documenta, mantém)
```

Um RFC que nunca recebeu aprovação de ChatGPT não vira arquitetura
oficial, mesmo que tecnicamente correto — a aprovação é o gate, não uma
formalidade.

## Quem pode alterar o repositório oficial

| Papel | Escreve no repositório? | Como |
|---|---|---|
| ChatGPT | Não | Aprova/rejeita; produz visão e roadmap fora do repositório de código |
| Claude Code | Sim, com aprovação prévia | Implementação crítica, sempre seguindo o mesmo protocolo já em uso nesta sessão: nenhum commit sem aprovação explícita do responsável humano pelo projeto |
| Qwen Coder | Sim, dentro do escopo já aprovado | Implementação de rotina dentro de um módulo/RFC já aprovado por ChatGPT e desenhado por Claude Code |
| GLM | **Nunca** | Só produz artefato de pesquisa; qualquer mudança de repositório passa por Claude Code ou Qwen Coder |

Esta tabela não substitui a aprovação humana final — Dario Marques Neto
continua sendo quem autoriza commit e push em qualquer fluxo, como já
estabelecido em todas as etapas anteriores deste projeto (Sprint v1.2.1,
consolidação pós-release v1.2.0, e esta própria sessão de arquitetura).

## Escopo de decisão por papel — o que cada um NÃO faz

- **ChatGPT não implementa.** Decide se algo deve ser construído, não
  como.
- **Claude Code não decide visão.** Traduz uma visão já aprovada em
  arquitetura executável e implementa a parte crítica — não redefine o
  que a plataforma é.
- **Qwen Coder não decide arquitetura.** Implementa dentro de limites já
  desenhados por Claude Code.
- **GLM não implementa nem aprova.** Só pesquisa e propõe.

## Referências

- `ARCHITECTURE_FINAL.md` — arquitetura consolidada que este documento
  de governança protege
- `ARCHITECTURE_MIGRATION_PLAN.md` — fases de execução, cada uma sujeita
  ao mesmo fluxo de aprovação descrito aqui
- `docs/governance/ENGINEERING_GUIDE.md` — práticas de engenharia que
  Claude Code e Qwen Coder seguem na implementação
