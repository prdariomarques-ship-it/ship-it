# Roadmap — v1.1

Backlog organizado por prioridade. **Este documento não implementa nada** — é organização de backlog para decisão futura, conforme solicitado no pós-release da v1.0.

Prioridades:
- **P0** — risco de segurança/operação ainda aberto; deveria ser resolvido antes do próximo ciclo de crescimento de uso.
- **P1** — alto valor operacional, sem urgência imediata.
- **P2** — melhoria de produto/arquitetura, valor claro mas não crítico.
- **P3** — long-tail — vale fazer, sem pressão de tempo.

---

## P0

### P0-1 — Fechar o auto-registro aberto (`/api/auth/register`)
- **Descrição**: hoje qualquer pessoa pode criar uma conta de dashboard com papel `user` sem convite ou aprovação. Não afeta o canal de WhatsApp, mas amplia quem pode chamar `/api/chat`/`/api/agents/*/run`.
- **Benefício**: reduz a superfície de abuso da API autenticada; alinha com o modelo de "sistema de dono único" já documentado.
- **Complexidade**: baixa — adicionar um flag de convite/aprovação de admin, ou desativar o registro público por padrão.
- **Dependências**: nenhuma.
- **Risco**: baixo, mas requer decidir o fluxo de onboarding de novos usuários do dashboard antes de fechar totalmente.
- **Estimativa de esforço**: pequena (poucas horas).

### P0-2 — Atualizar `next` para uma versão sem as CVEs conhecidas
- **Descrição**: `next@14.2.21` tem vulnerabilidades conhecidas, incluindo uma classificada como crítica pelo advisory oficial (`npm audit`). Nenhum vetor de exploração foi identificado nesta aplicação especificamente (sem `middleware.ts`), mas é dívida de dependência.
- **Benefício**: elimina o risco residual e a necessidade de justificar a exceção em auditorias futuras.
- **Complexidade**: média — `next@16` é bump de major, pode exigir ajustes de API (App Router mudou entre versões).
- **Dependências**: nenhuma.
- **Risco**: médio — testar build/lint/comportamento do dashboard após o upgrade.
- **Estimativa de esforço**: pequena a média (1-2 dias, incluindo teste manual do dashboard).

### P0-3 — Configurar rotação de logs no Docker Compose
- **Descrição**: nenhum serviço do `docker-compose.yml` define `logging.options.max-size`/`max-file` — logs podem crescer indefinidamente e encher o disco do host (ver `MONITORING.md`).
- **Benefício**: elimina um risco real de indisponibilidade total (disco cheio derruba até o Postgres).
- **Complexidade**: baixa — mudança de configuração no Compose.
- **Dependências**: nenhuma.
- **Risco**: baixo.
- **Estimativa de esforço**: pequena (menos de um dia).

### P0-4 — Backup automatizado de Qdrant, OpenWA e n8n (não só Postgres)
- **Descrição**: `scripts/backup.sh` só cobre o Postgres. Memória semântica (Qdrant) e a sessão de WhatsApp (OpenWA) não têm backup automático — perda desses volumes é perda de dados permanente (memória) ou indisponibilidade manual (re-pareamento de sessão).
- **Benefício**: fecha a maior lacuna de continuidade de negócio identificada na auditoria final.
- **Complexidade**: média — criar `scripts/backup-full.sh` ou estender o existente, com snapshot dos volumes Docker relevantes.
- **Dependências**: nenhuma.
- **Risco**: baixo tecnicamente, alto se não for feito (dados irrecuperáveis em caso de perda de volume).
- **Estimativa de esforço**: pequena a média (1-2 dias, incluindo teste).

### P0-5 — Criar `scripts/restore.sh` e testar restore ponta a ponta
- **Descrição**: `RESTORE.md` documenta um procedimento manual, mas não existe um script, e nenhum restore foi testado de fato nesta auditoria.
- **Benefício**: reduz o tempo de recuperação (RTO) em um incidente real e valida que os backups realmente funcionam.
- **Complexidade**: média.
- **Dependências**: P0-4 (backup completo) para o script cobrir todos os volumes.
- **Risco**: alto se não for feito — um backup nunca testado pode não ser restaurável quando precisar.
- **Estimativa de esforço**: média (2-3 dias, incluindo teste em ambiente isolado).

---

## P1

### P1-1 — Stack de monitoramento (Prometheus + Grafana + alertas mínimos)
- **Descrição**: `/metrics` já expõe tudo em formato Prometheus, mas nada coleta, armazena ou alerta hoje (ver `MONITORING.md`).
- **Benefício**: visibilidade proativa em vez de checagem manual; alertas para os cenários já mapeados em `INCIDENT_RESPONSE.md`.
- **Complexidade**: média — adicionar serviços ao `docker-compose.yml`, configurar scrape + regras de alerta básicas.
- **Dependências**: nenhuma.
- **Risco**: baixo.
- **Estimativa de esforço**: média (2-4 dias).

### P1-2 — `docker build`/`docker compose up` como etapa de CI
- **Descrição**: o CI atual (`.github/workflows/ci.yml`) roda lint + testes + migrações do backend e build do frontend, mas nunca constrói as imagens Docker nem sobe o Compose completo.
- **Benefício**: detecta quebras de Dockerfile/Compose antes do deploy, não durante.
- **Complexidade**: baixa a média.
- **Dependências**: nenhuma.
- **Risco**: baixo.
- **Estimativa de esforço**: pequena (1 dia).

### P1-3 — Fixar versões das imagens de terceiros (`latest` → tag explícita)
- **Descrição**: `qdrant/qdrant:latest`, `n8nio/n8n:latest` e `openwa/wa-automate:latest` usam a tag `latest` — um `pull` pode trazer uma versão nova sem aviso, quebrando compatibilidade silenciosamente.
- **Benefício**: atualizações previsíveis, deploys reprodutíveis.
- **Complexidade**: baixa.
- **Dependências**: nenhuma.
- **Risco**: baixo.
- **Estimativa de esforço**: pequena (poucas horas, incluindo teste de que as versões fixadas funcionam).

### P1-4 — Adicionar `.dockerignore` ao backend e frontend
- **Descrição**: nenhum dos dois tem `.dockerignore` — o `COPY . .` do `Dockerfile` do backend copia `.git/`, caches de teste/lint e outros artefatos de desenvolvimento para dentro da imagem.
- **Benefício**: imagens menores, sem artefatos de desenvolvimento ou possíveis dados sensíveis locais dentro do container de produção.
- **Complexidade**: baixa.
- **Dependências**: nenhuma.
- **Risco**: baixo.
- **Estimativa de esforço**: pequena (menos de um dia).

### P1-5 — Detecção de reuso de refresh token roubado
- **Descrição**: hoje o reuso de um refresh token já revogado é rejeitado, mas não aciona a revogação das demais sessões ativas do usuário — uma defesa em profundidade padrão contra token roubado.
- **Benefício**: reduz o impacto de um token vazado.
- **Complexidade**: baixa a média.
- **Dependências**: nenhuma.
- **Risco**: baixo.
- **Estimativa de esforço**: pequena a média (1-2 dias).

---

## P2

### P2-1 — Mecanismo de retomada de plano pendente de confirmação no Cognitive Pipeline
- **Descrição**: quando o Planner decide que um pedido precisa de confirmação (`needs_confirmation`), o pipeline pergunta e para — mas a próxima mensagem do contato não retoma automaticamente o plano pausado, vira uma nova classificação do zero.
- **Benefício**: fecha um fluxo de UX incompleto, torna o "pedir confirmação" genuinamente útil em vez de um beco sem saída.
- **Complexidade**: média — requer guardar estado de plano pendente associado ao contato e uma forma de reconhecer "sim"/"não" na próxima mensagem.
- **Dependências**: nenhuma nova infraestrutura (usa o que já existe: Memory Manager, Cognitive Pipeline).
- **Risco**: médio — precisa de cuidado para não interpretar mal uma mensagem não relacionada como confirmação.
- **Estimativa de esforço**: média (3-5 dias).

### P2-2 — Worker de jobs em container dedicado
- **Descrição**: hoje o worker roda embutido no processo da API. A fila já é Postgres-backed com claim atômico, então a extração é só infraestrutura, não lógica nova.
- **Benefício**: escalar a API e o processamento de jobs independentemente.
- **Complexidade**: baixa a média.
- **Dependências**: nenhuma.
- **Risco**: baixo.
- **Estimativa de esforço**: pequena a média (1-2 dias).

### P2-3 — Combinar intenção + prioridade + planejamento em uma única chamada LLM
- **Descrição**: hoje são até 3 chamadas LLM independentes por mensagem antes da execução do agente — deliberado por simplicidade/testabilidade, mas é custo/latência real (ver `docs/fase4.2-relatorio.md` §8).
- **Benefício**: reduz latência e custo por mensagem, se o volume de produção justificar.
- **Complexidade**: média — requer redesenhar o schema de function calling combinado sem perder a testabilidade individual dos três engines.
- **Dependências**: dados reais de volume/custo em produção para justificar (ver P1-1, monitoramento).
- **Risco**: médio — pode reduzir a qualidade de cada decisão individual se malfeito.
- **Estimativa de esforço**: média (3-5 dias).

### P2-4 — Pipeline de ingestão de documentos para `knowledge_search`
- **Descrição**: `knowledge_search` existe e funciona (consultado pelo Cognitive Pipeline desde a Fase 4.2), mas não há nenhum jeito de carregar conhecimento real além da tool genérica `store_memory`.
- **Benefício**: torna a "consulta a conhecimento" do pipeline útil de verdade (documentos, políticas, catálogos).
- **Complexidade**: média a alta — upload, chunking, resumo, vetorização.
- **Dependências**: nenhuma nova infraestrutura (Qdrant e Memory Manager já suportam).
- **Risco**: médio.
- **Estimativa de esforço**: média a grande (1-2 semanas).

---

## P3

### P3-1 — Teste de carga formal
- **Descrição**: nenhum teste de carga (k6, locust) foi executado; os limites reais de capacidade sob concorrência não são conhecidos.
- **Benefício**: estabelece limites conhecidos antes que um pico de uso os descubra em produção.
- **Complexidade**: média.
- **Dependências**: ambiente de staging equivalente a produção.
- **Risco**: baixo.
- **Estimativa de esforço**: média (3-5 dias).

### P3-2 — Type-checking estático no backend (mypy ou pyright)
- **Descrição**: o backend usa type hints extensivamente (Pydantic, SQLAlchemy 2 typed) mas nenhuma ferramenta de checagem estática está configurada no CI — mitigado hoje por 92% de cobertura de teste e validação de runtime do Pydantic.
- **Benefício**: captura uma classe de bugs antes da execução, sem depender só de teste.
- **Complexidade**: baixa a média — a base já é bem tipada, o trabalho é principalmente configuração e resolução dos erros iniciais.
- **Dependências**: nenhuma.
- **Risco**: baixo.
- **Estimativa de esforço**: pequena a média (2-3 dias para configurar e limpar o backlog inicial de erros).

### P3-3 — Síntese de resposta multi-etapa via LLM
- **Descrição**: hoje a resposta de um plano com múltiplas etapas é uma concatenação simples dos textos de cada etapa, não uma síntese fluida.
- **Benefício**: resposta final mais natural em pedidos compostos.
- **Complexidade**: baixa — uma chamada LLM adicional, opcional/feature-flag.
- **Dependências**: nenhuma.
- **Risco**: baixo (custo/latência extra, mitigável com feature flag).
- **Estimativa de esforço**: pequena (1-2 dias).

### P3-4 — Consolidar documentos markdown redundantes na raiz do repositório
- **Descrição**: `RELEASE_NOTES_v1.0.md` e `CHANGELOG.md` têm sobreposição de conteúdo (o que está incluído na v1.0). Não é um problema funcional, mas gera duplicidade de manutenção.
- **Benefício**: menos risco de os documentos divergirem com o tempo.
- **Complexidade**: baixa.
- **Dependências**: nenhuma.
- **Risco**: nenhum.
- **Estimativa de esforço**: pequena (poucas horas).

### P3-5 — Padronizar nomenclatura da pasta `docs/`
- **Descrição**: `docs/` mistura convenções — nomes em inglês por assunto (`AGENTS.md`, `TOOLS.md`, `MEMORY.md`, `WORKFLOWS.md`, `architecture.md`) e nomes em português por fase histórica (`fase3-relatorio.md`, `fase4.1-relatorio.md`, `fase4.2-relatorio.md`, `auditoria-fase2.md`). Funciona (os relatórios por fase são registro histórico, não referência viva), mas é inconsistente para quem navega o diretório pela primeira vez.
- **Benefício**: navegação mais previsível para novos colaboradores.
- **Complexidade**: baixa.
- **Dependências**: nenhuma.
- **Risco**: nenhum (mudança cosmética).
- **Estimativa de esforço**: pequena (poucas horas — considerar mover os relatórios de fase para uma subpasta `docs/history/` em vez de renomear).
