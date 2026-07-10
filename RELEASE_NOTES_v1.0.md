# Dario OS — Release Notes v1.0

Data do gate final: 2026-07-10
Branch: `claude/dario-os-platform-gcg6i2`

Esta é a build candidata a v1.0, cobrindo tudo entregue desde a fundação da plataforma até o Cognitive Pipeline. Ver `PRODUCTION_APPROVAL.md` para o veredito formal da auditoria final — **este release está atualmente REPROVADO para produção**; as notas abaixo descrevem o que a versão contém, não uma declaração de prontidão.

## Visão geral

Dario OS é um sistema operacional pessoal baseado em IA: centraliza WhatsApp, agenda, tarefas, loja, igreja e memória permanente em uma plataforma única, com agentes de IA que pensam antes de agir (classificam intenção e prioridade, planejam, executam ferramentas, validam a resposta e aprendem com a conversa).

## O que está incluído

### Plataforma (Fase 1)
- Backend FastAPI (Python 3.12, SQLAlchemy 2 async, Alembic) + Frontend Next.js 14 (dashboard).
- 5 agentes com function calling: `personal`, `church`, `store`, `content`, `assistant`.
- Memória permanente via Qdrant (busca semântica) + Postgres (histórico estruturado).
- 4 Providers de WhatsApp plugáveis: OpenWA, Baileys, Evolution API, WhatsApp Cloud API oficial.
- Autenticação JWT + refresh token rotativo + RBAC (admin/user).
- Fila de jobs durável (Postgres) com retry exponencial.
- Observabilidade: logs estruturados, Prometheus, health/readiness.
- Docker Compose completo (Postgres, Redis, Qdrant, n8n, Caddy com HTTPS automático).

### Auditoria de produção (Fase 2)
- Fila de jobs confiável para múltiplos workers (claim atômico `SKIP LOCKED`, recuperação de jobs travados).
- Hashing de senha fora do event loop, timing-safe; embedding fora do hot path da requisição.
- Correções de segurança e confiabilidade encontradas por auditoria dedicada.

### Consolidação arquitetural (Fase 3)
- **Agent Registry** e **Tool Registry** com auto-descoberta por convenção de pasta — instalar um agente ou uma ferramenta nova nunca exige editar um arquivo central.
- **Event Bus** (pub/sub interno + fan-out best-effort via Redis).
- **AI Orchestrator**: ponto único de seleção de agente, execução, timeout e métricas.
- **Memory Manager**: fachada única sobre memória de curto prazo, longo prazo, conhecimento e preferências.
- **Multi-LLM**: OpenAI, Anthropic, GLM, Gemini, Ollama — troca por configuração, sem mudar código.

### WhatsApp ponta a ponta + desacoplamento de Providers (Fase 4.1)
- Fluxo automático completo: mensagem recebida → job → AI Orchestrator → agente → resposta → envio, sem depender de automação externa.
- Deduplicação de mensagens, freio de loop/flood, timeout de agente, apologia automática em falha definitiva.
- Camada de Providers 100% desacoplada: modelo interno único (`InboundMessage`, `ConnectionEvent`, `DeliveryAck`), retry com backoff, métricas de disponibilidade, 36+ testes de compatibilidade provando que qualquer novo Provider funciona automaticamente.

### Cognitive Pipeline (Fase 4.2)
- Intent Engine e Priority Engine: classificação por function calling (múltiplas hipóteses com confiança), com degradação heurística honesta quando o LLM falha.
- Cognitive Planner: decompõe um pedido em até 5 etapas, escolhe o agente de cada uma, decide quando pedir confirmação humana.
- Response Validator com uma tentativa extra bounded antes de desistir.
- Learning Engine: tagueia domínios recorrentes do contato, deduplicado na escrita.
- Troca automática de provider LLM em caso de falha (`LLM_FALLBACK_PROVIDER`).
- Prioridade de execução real: mensagens urgentes furam a fila de jobs.

## Métricas da build

| Métrica | Valor |
| --- | --- |
| Testes automatizados | 231 (100% passando) |
| Cobertura de linha | 91% |
| Lint | limpo (`ruff check .`) |
| Migrações Alembic | 3, roundtrip verificado, sem drift de schema (`alembic check`) |
| Agentes | 5 |
| Ferramentas registradas | ~20 |
| Providers de WhatsApp | 4 |
| Providers de LLM | 5 |
| Métricas Prometheus | 16 |

## Bugs reais corrigidos ao longo do desenvolvimento

- `MissingGreenlet` no worker de jobs quando um lote continha múltiplos jobs e um deles falhava antes de outro (Fase 4.1).
- `AttributeError` em três Providers de WhatsApp (OpenWA, Baileys, Evolution) ao receber um payload malformado com `"data": null` (Fase 4.1 — complemento).
- Falha de memória semântica (Qdrant indisponível) não protegida no carregamento de contexto do Cognitive Pipeline — derrubava o pipeline inteiro (Fase 4.2, corrigido antes do merge).
- Exceção levantada por um provider LLM não disparava a degradação heurística de intenção/prioridade/planejamento — corrigido para os três engines (Fase 4.2).

## Como atualizar / instalar

```bash
./scripts/setup.sh
```

Ver `README.md` para configuração completa de variáveis de ambiente, e `docs/architecture.md` para o desenho arquitetural detalhado.

## Achados da auditoria final (bloqueadores)

A auditoria de release encontrou dois bloqueadores de segurança reais que impedem a aprovação desta build para produção — ambos pré-existentes na arquitetura de Providers/ferramentas, não introduzidos por esta release, mas nunca antes formalmente auditados sob essa ótica. Ver a seção "Critérios de Segurança" e "Limitações Conhecidas" em `PRODUCTION_APPROVAL.md` para os detalhes técnicos completos e o que precisa ser corrigido antes do próximo gate.

## Créditos

Construído em sessões incrementais (Fases 1 a 4.2) seguindo os princípios: simplicidade, robustez, desacoplamento, compatibilidade total entre fases, e nenhuma alegação não verificada por teste.
