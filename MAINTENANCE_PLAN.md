# Plano de Manutenção — Dario OS

Rotinas recomendadas para manter o sistema saudável em operação contínua. Nenhuma destas rotinas está automatizada hoje além do que está explicitamente marcado — a maioria depende de agendamento manual (cron) até virarem automação de fato (ver `ROADMAP_v1.1.md`).

## Rotina diária

| Tarefa | Como | Automatizado? |
| --- | --- | --- |
| Backup do PostgreSQL | `scripts/backup.sh` | Script existe, mas o agendamento no cron é manual — ver abaixo |
| Checar `GET /health/ready` | Manual ou script externo simples | Não |
| Checar volume da fila de jobs (`GET /api/jobs`) por acúmulo anormal | Manual | Não |
| Revisar `checks.whatsapp` (sessão do WhatsApp ainda conectada) | Manual ou script externo | Não |

Agendar o backup diário, se ainda não estiver:
```bash
crontab -e
# adicionar:
0 3 * * * /caminho/para/ship-it/scripts/backup.sh >> /var/log/darioos-backup.log 2>&1
```

## Rotina semanal

| Tarefa | Como |
| --- | --- |
| Revisar métricas de custo de LLM (`darioos_agent_cost_usd_total{provider}` em `/metrics`) | Manual — não há alerta de orçamento configurado |
| Revisar taxa de erro por ferramenta (`darioos_agent_tool_calls_total{status="error"}`) | Manual |
| Conferir espaço em disco do host (containers + volumes + logs) | `df -h`, `docker system df` |
| Verificar se há jobs presos em `FAILED` com `last_error` recorrente | `GET /api/jobs` |
| Snapshot manual do Qdrant e do volume do OpenWA (ver `BACKUP.md`) | Manual, até virar script |

## Rotina mensal

| Tarefa | Como |
| --- | --- |
| Testar um restore de backup em ambiente isolado (não em produção) | Seguir `RESTORE.md` |
| Revisar e atualizar dependências (`backend/requirements.txt`, `frontend/package.json`) por CVEs conhecidas | `pip list --outdated`, `npm audit` |
| Revisar usuários com papel `admin`/`user` cadastrados (auto-registro está aberto — ver `PRODUCTION_APPROVAL.md` §11) | `GET /api/logs`/consulta direta ao banco |
| Revisar contatos/categorias acumuladas pelo Learning Engine, por consistência | `GET /api/contacts` |
| Purgar refresh tokens expirados (já ocorre automaticamente a cada novo login do usuário — conferir que não há acúmulo excessivo se logins forem raros) | Consulta ao banco |
| Rodar a suíte de testes contra a versão em produção (staging) antes de qualquer atualização maior | `pytest -q` no ambiente de CI/staging |

## Atualizações

- **Dependências do backend/frontend**: seguir a rotina mensal acima; nenhuma automação de atualização (tipo Dependabot) está configurada no repositório hoje.
- **Imagens de terceiros** (`postgres:16-alpine`, `redis:7-alpine`, `qdrant/qdrant:latest`, `n8nio/n8n:latest`, `openwa/wa-automate:latest`, `caddy:2-alpine`): `qdrant`, `n8n` e `openwa` usam a tag `latest` — isso significa que um `docker compose pull && docker compose up -d` pode trazer uma versão nova sem aviso. Recomendação: fixar versões explícitas nessas três imagens antes de depender de atualizações previsíveis (mudança de configuração, não de código da aplicação — fora do escopo deste release).
- **Deploy de uma nova versão do Dario OS**: seguir `RUNBOOK.md` ("Deploy de uma atualização").

## Limpeza

| O quê | Como | Frequência sugerida |
| --- | --- | --- |
| Backups de Postgres além da retenção | Já automático em `scripts/backup.sh` (mantém os 14 mais recentes) | N/A |
| Imagens Docker não utilizadas | `docker system prune -f` (cuidado: não remove volumes por padrão, mas confirme antes de usar `-a`) | Mensal |
| Logs de containers sem rotação configurada | Ver "Rotação de logs" abaixo | Contínuo, uma vez configurado |
| Tabela `logs` do Postgres (auditoria interna) sem TTL/expiração configurado | Nenhuma limpeza automática existe — cresce indefinidamente | Avaliar necessidade trimestralmente |

## Monitoramento

Ver `MONITORING.md` para o que já está instrumentado (`/metrics`, `/health/ready`, logs estruturados) e o que falta (stack de coleta/alertas). Até uma stack de alertas existir, a checagem de `/health/ready` e das métricas-chave listadas em `MONITORING.md` deve fazer parte da rotina diária/semanal acima.

## Renovação de certificados

**Automática** — o Caddy (`docker/caddy/Caddyfile`) renova o certificado TLS do Let's Encrypt sozinho, contanto que:
1. O volume `caddy_data` não seja apagado.
2. As portas 80/443 continuem acessíveis publicamente (necessário para o desafio ACME).
3. O DNS do domínio configurado (`DOMAIN` no `.env`) continue apontando para o host.

Nenhuma ação manual de rotina é necessária. Ver `RUNBOOK.md` se precisar forçar uma renovação.

## Rotação de logs

**Não configurada hoje** — o driver de log padrão do Docker (`json-file`) não tem limite de tamanho definido em nenhum serviço do `docker-compose.yml`. Até isso ser adicionado (mudança de configuração do Compose, fora do escopo deste release — ver `ROADMAP_v1.1.md`), a rotina recomendada:

```bash
# Verificar tamanho atual dos logs
docker inspect --format='{{.LogPath}}' $(docker compose -f docker/docker-compose.yml ps -q) | xargs du -sh

# Truncar manualmente se necessário (não afeta o container em execução)
truncate -s 0 <caminho-do-log>
```

Frequência recomendada até a automação existir: checagem semanal (rotina semanal acima).

## Verificação de integridade

| O quê | Como | Frequência |
| --- | --- | --- |
| Migrações do banco aplicadas corretamente (sem drift de schema) | `alembic check` dentro do container do backend | A cada deploy |
| Integridade dos backups do Postgres | `gunzip -t` no arquivo de dump (ver `BACKUP.md`) | A cada backup (diário) |
| Consistência entre `docs/architecture.md` e o código (documentação não fica desatualizada) | Revisão manual | A cada mudança arquitetural relevante |
| Testes automatizados passando | `pytest -q` (246 testes na v1.0.0) | A cada deploy/CI |
