# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

## [1.0.0] - 2026-07-10

Primeira versão do Dario OS — sistema operacional pessoal baseado em IA (WhatsApp, agenda, tarefas, loja, igreja e memória permanente).

### Adicionado

- Plataforma base: backend FastAPI (Python 3.12, SQLAlchemy 2 async, Alembic), dashboard Next.js 14, Docker Compose completo (Postgres, Redis, Qdrant, n8n, Caddy com HTTPS automático).
- 5 agentes de IA com function calling: `personal`, `church`, `store`, `content`, `assistant`.
- Memória permanente: Qdrant (busca semântica) + Postgres (histórico estruturado), com resumo automático de contato e preferências estruturadas.
- 4 Providers de WhatsApp plugáveis (Strategy + Factory): OpenWA, Baileys, Evolution API, WhatsApp Cloud API oficial — troca por configuração, sem mudar código.
- 5 Providers de LLM plugáveis: OpenAI, Anthropic, GLM, Gemini, Ollama.
- Autenticação JWT + refresh token rotativo + RBAC (admin/user).
- Fila de jobs durável (Postgres), com retry exponencial e claim atômico entre múltiplos workers.
- **Agent Registry** e **Tool Registry** com auto-descoberta por convenção de pasta — instalar um agente ou ferramenta nova nunca exige editar um arquivo central.
- **Event Bus** (pub/sub interno + fan-out best-effort via Redis).
- **AI Orchestrator**: ponto único de seleção de agente, execução, timeout e métricas.
- **Memory Manager**: fachada única sobre memória de curto prazo, longo prazo, conhecimento, preferências e resumo.
- **Fluxo WhatsApp ponta a ponta**: mensagem recebida → job → pipeline → agente → resposta → envio, sem depender de automação externa (n8n continua disponível em paralelo).
- **Cognitive Pipeline**: Intent Engine e Priority Engine (classificação por function calling, com degradação heurística honesta), Cognitive Planner (decompõe um pedido em até 5 etapas, escolhe o agente de cada uma, decide quando pedir confirmação), Response Validator (com retry bounded) e Learning Engine (tagueia domínios recorrentes do contato).
- Troca automática de provider de LLM em caso de falha (`LLM_FALLBACK_PROVIDER`).
- Prioridade de execução real: mensagens urgentes furam a fila de jobs.
- Observabilidade: logs estruturados em JSON, 16 métricas Prometheus, health/readiness com degradação graciosa por dependência.
- Documentação completa: `README.md`, `docs/architecture.md`, `docs/AGENTS.md`, `docs/TOOLS.md`, `docs/MEMORY.md`, `docs/WORKFLOWS.md`, `docs/api.md`, relatórios técnicos por fase.

### Corrigido

- `MissingGreenlet` no worker de jobs quando um lote continha múltiplos jobs e um deles falhava antes de outro.
- `AttributeError` em três Providers de WhatsApp (OpenWA, Baileys, Evolution) ao receber um payload malformado com `"data": null`.
- Falha de memória semântica (Qdrant indisponível) não protegida no carregamento de contexto do Cognitive Pipeline — derrubava o pipeline inteiro.
- Exceção levantada por um provider de LLM não disparava a degradação heurística de intenção/prioridade/planejamento.
- Job de envio de WhatsApp (`whatsapp.send_text`) pulava persistência e memória quando disparado pela fila (só o caminho via API fazia isso corretamente).

### Segurança

- **PROD-004**: `WEBHOOK_SECRET` passou a ser obrigatório em produção — o backend recusa o boot sem um valor forte (≥ 32 caracteres), mesmo padrão já aplicado a `JWT_SECRET`. `docker-compose.yml` exige a variável; `scripts/setup.sh` gera ambas automaticamente na primeira instalação.
- **PROD-005**: isolamento técnico de contato nas ferramentas `send_whatsapp_message` e `find_contact` — uma conversa só pode agir sobre o seu próprio contato, decidido em código (`ToolContext.contact_id`, nunca escolhido pelo LLM), não por instrução de prompt.
- Assinatura HMAC-SHA256 real para o provider oficial de WhatsApp (Meta, `X-Hub-Signature-256`).
- Hashing de senha PBKDF2-HMAC-SHA256 (390k iterações) com salt aleatório e comparação em tempo constante; timing equalizado para e-mail inexistente no login.
- Refresh tokens armazenados como hash SHA-256, rotativos, com rejeição de reuso.
- RBAC aplicado nas rotas administrativas (`/api/jobs`, `/api/logs`); CORS com allow-list explícita.
- Rate limiting por IP, reaproveitado como freio de loop/flood no auto-reply do WhatsApp.
- Deduplicação de mensagens de WhatsApp (idempotência por `external_id` + constraint única no banco).

### Testes

246 testes passando
92% de cobertura de linha

### Observações

Primeira versão aprovada para produção. Ver `PRODUCTION_APPROVAL.md` (auditoria final, 12 seções) e `PRODUCTION_BLOCKERS_RESOLVED.md` (correção dos dois bloqueadores encontrados) para o relatório completo. Notas de release detalhadas: `RELEASE_NOTES_v1.0.md`.
