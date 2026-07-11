# Disaster Recovery — Sprint 5

Consolida `BACKUP.md`, `RESTORE.md` e `INCIDENT_RESPONSE.md` (já
existentes, não alterados por esta sprint) em um plano único de
recuperação de desastre, e registra o que a observabilidade desta sprint
melhora na detecção/diagnóstico de incidentes.

## Escopo de dados a proteger

| Dado | Onde vive | Coberto por backup automatizado? |
|---|---|---|
| Contatos, mensagens, tarefas, notas, execuções de agente, usuários, tokens | PostgreSQL | ✅ `scripts/backup.sh`, diário se agendado no cron do host |
| Memória semântica (embeddings) | Qdrant | ❌ sem backup automatizado hoje |
| Fila de jobs / cache / rate-limit state | Redis | ❌ não é preciso — dado efêmero/recomputável |
| Segredos (`JWT_SECRET`, `WEBHOOK_SECRET`, credenciais OAuth) | `.env` no host | ❌ fora do escopo de backup de dados — gerenciar via cofre de segredos do operador |

**Gap real, documentado, não corrigido nesta sprint**: o volume do Qdrant
não tem backup automatizado. Perder o volume do Qdrant sem um Postgres
íntegro para reconstruir a partir de `embeddings` (a tabela Postgres que
guarda o texto original) significaria perda permanente de memória
semântica. Como `Embedding.content` fica em Postgres (coberto por
backup), uma reconstrução manual do índice Qdrant a partir do Postgres é
teoricamente possível mas não há script pronto para isso hoje —
recomendação de backlog para uma sprint futura.

## RTO / RPO (objetivos, não SLAs contratuais — este é um sistema pessoal/single-tenant)

- **RPO (Recovery Point Objective)**: até 24h de dados Postgres perdidos no
  pior caso, se o backup diário estiver agendado conforme `BACKUP.md`
  recomenda (não é automático por padrão — precisa ser configurado no cron
  do host operador).
- **RTO (Recovery Time Objective)**: tipicamente minutos para os cenários
  de container caído (`INCIDENT_RESPONSE.md`, seções 1–4), até ~1h para um
  restore completo de Postgres a partir de backup (`RESTORE.md`).

## Fluxo de resposta a um desastre

1. **Detectar** — `GET /health/ready`, alertas do Prometheus (`/metrics`),
   ou um usuário reportando erro. Com esta sprint, todo erro reportado por
   um usuário carrega um `X-Request-ID` correlacionável nos logs
   estruturados — reduz o tempo de diagnóstico ao permitir filtrar logs
   por uma única requisição em vez de vasculhar por timestamp aproximado.
2. **Classificar** — usar `INCIDENT_RESPONSE.md` para identificar o
   cenário (Postgres/Redis/Qdrant/WhatsApp/Google indisponível, etc.) e o
   impacto real (algumas dependências degradam graciosamente, só Postgres
   derruba o sistema).
3. **Conter/mitigar** — seguir a ação específica do cenário em
   `INCIDENT_RESPONSE.md`.
4. **Restaurar dados, se necessário** — seguir `RESTORE.md`.
5. **Post-mortem** — usar o `X-Request-ID` das requisições afetadas
   (quando aplicável) para reconstruir a linha do tempo exata via logs
   estruturados.

## O que esta sprint mudou para disaster recovery

Nada na lógica de backup/restore/failover foi alterado (fora do escopo:
"não alterar comportamento funcional existente"). A melhoria é puramente
de **diagnóstico**: Correlation ID + logging estruturado (ver
`OBSERVABILITY_GUIDE.md`) tornam mais rápido entender *o que* aconteceu
durante um incidente, mas não mudam *como* reagir a ele — os playbooks de
`INCIDENT_RESPONSE.md` continuam sendo a referência operacional.
