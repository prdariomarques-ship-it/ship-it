# Auditoria Técnica — Fase 2 do Dario OS

Auditoria completa da arquitetura, seguida das correções implementadas. Todos os itens abaixo foram verificados no código (não são hipóteses) e todas as correções têm testes de regressão.

## 1. Débitos e problemas encontrados

### Confiabilidade (fila de jobs)
| # | Problema | Severidade |
| --- | --- | --- |
| 1 | Handler que falhava deixava a sessão SQLAlchemy suja; o registro do retry podia **commitar escrita parcial** do handler | Alta |
| 2 | Sem `FOR UPDATE SKIP LOCKED`: duas réplicas do backend **processariam o mesmo job duas vezes** | Alta |
| 3 | Job em `RUNNING` ficava **preso para sempre** se o processo caísse no meio da execução | Alta |

### Segurança
| # | Problema | Severidade |
| --- | --- | --- |
| 4 | Webhook do WhatsApp **totalmente aberto** — qualquer um podia injetar mensagens falsas | Alta |
| 5 | Backend subia em produção com `JWT_SECRET` padrão (`change-me-in-production`) | Alta |
| 6 | Login revelava existência de conta por **timing** (verificação de senha só rodava se o e-mail existisse) | Média |
| 7 | Sem headers de segurança no proxy (X-Frame-Options etc.) | Baixa |

### Performance / escalabilidade
| # | Problema | Severidade |
| --- | --- | --- |
| 8 | PBKDF2 (390k iterações, ~100ms) rodava **síncrono no event loop** — cada login/registro congelava todas as requisições concorrentes | Alta |
| 9 | Embedding (OpenAI + Qdrant, 2 chamadas externas) rodava **inline no hot path do webhook** — latência de terceiros na entrega de mensagem | Alta |
| 10 | `find_contact` e `add_prayer_request` carregavam **200 linhas para filtrar em Python** em vez de `ILIKE` no SQL | Média |
| 11 | Dashboard fazia **7 COUNTs sequenciais** (7 round trips) | Baixa (mitigado por cache) |
| 12 | Pool de conexões Postgres no default (5) sem configuração | Média |
| 13 | Fallback em memória do rate limiter crescia sem limite com IPs rotativos | Baixa |

### Observabilidade / arquitetura / DX
| # | Problema | Severidade |
| --- | --- | --- |
| 14 | Ordem dos middlewares fazia o Prometheus **não contar respostas 429** | Média |
| 15 | Probes (`/health`, `/metrics`) sujeitos a rate limit — um cliente abusivo podia **cegar o monitoramento** | Média |
| 16 | **Nenhum CI/CD** — nada validava PRs | Alta (DX) |
| 17 | Mensagens de **saída** não contavam para o resumo automático do contato (só as de entrada) — inconsistência de domínio | Média |
| 18 | Corrida na criação de contato: dois webhooks simultâneos do mesmo número novo → `IntegrityError` 500 | Média |
| 19 | Código duplicado: extração de mensagem estilo Baileys copiada em 2 providers (evolution, baileys) | Baixa |
| 20 | Settings mortas (`debug`, resquícios) e log de argumentos de tools (PII) em nível INFO | Baixa |
| 21 | Frontend: dois 401 simultâneos disparavam **duas rotações** do refresh token — a segunda falhava e deslogava o usuário | Média |
| 22 | Tabela `refresh_tokens` crescia sem limite (nenhuma limpeza de expirados) | Baixa |

Sem dependências desnecessárias no backend ou frontend (todas as libs de `requirements.txt` e `package.json` estão em uso).

## 2. Correções implementadas (todas com testes)

1. **Worker de jobs reescrito**: claim atômico em lote com `SELECT ... FOR UPDATE SKIP LOCKED` + um único commit (multi-worker seguro; SQLite ignora a cláusula sem prejuízo); `session.rollback()` antes de registrar falha (escrita parcial nunca é commitada); recuperação de jobs órfãos por tick (`JOBS_STALE_AFTER_SECONDS`, default 300s — re-enfileira se restam tentativas, falha se esgotadas).
2. **`WEBHOOK_SECRET`**: quando configurado, `/api/webhooks/whatsapp` exige `X-Webhook-Token` (comparação constant-time). Sem configurar, comportamento anterior preservado.
3. **Guard de produção**: o backend se recusa a subir com `ENVIRONMENT=production` e `JWT_SECRET` padrão ou < 32 chars.
4. **Hashing fora do event loop** (`asyncio.to_thread`) + hash dummy para logins de e-mails inexistentes (tempo constante, sem enumeração).
5. **Embedding via fila**: `record_interaction` enfileira `memory.embed` em vez de chamar OpenAI/Qdrant inline — o webhook responde em milissegundos e o embedding ganha retry de graça.
6. **Mensagens de saída** agora também disparam `contact.summarize` quando atingem o limiar.
7. **Corrida de contato**: `get_or_create_by_phone` captura `IntegrityError`, faz rollback e usa a linha vencedora.
8. **Busca por nome via SQL** (`ILIKE`) em contatos e membros da igreja (novo `ChurchMemberRepository`); dedup da extração Baileys em `providers/whatsapp/base.py`.
9. **Dashboard em 1 query** (scalar subqueries) em vez de 7.
10. **Middlewares reordenados** (métricas por fora — 429 agora é contado) e `/health*`/`/metrics` isentos de rate limit; poda do fallback em memória do limiter.
11. **Pool do Postgres configurável** (`DB_POOL_SIZE`/`DB_MAX_OVERFLOW`, defaults 10/20).
12. **Limpeza de refresh tokens expirados** a cada emissão de par (revogados permanecem até expirar, para auditoria).
13. **Frontend**: rotações de refresh concorrentes compartilham uma única promise (fim do logout espúrio).
14. **CI (GitHub Actions)**: lint + testes + migração upgrade/downgrade no backend; build do frontend.
15. **Headers de segurança no Caddy** (nosniff, X-Frame-Options DENY, Referrer-Policy, remoção do header Server).
16. Higiene: settings mortas removidas, log de tools em DEBUG (PII), `pytest-cov` adicionado.

## 3. Verificação

- **59 testes** (eram 46), todos verdes; **cobertura de 86%** do backend.
- Smoke test real: webhook 401 sem token / 200 com token; worker fazendo claim com `attempts` incrementado e retry com `last_error` registrado quando Qdrant/n8n estão fora; métricas contando inclusive respostas 401.
- Migração Alembic aplicada e revertida no CI e localmente.
- `ruff` limpo; `next build` sem erros.

## 4. Ganhos

- **Performance**: login/registro não bloqueiam mais o event loop (~100ms de PBKDF2 por requisição saíram do caminho de todas as outras); webhook de mensagem caiu de "latência OpenAI+Qdrant" para escrita local em banco; buscas de nome deixaram de carregar tabelas inteiras; dashboard com 1 round trip.
- **Escalabilidade**: múltiplas réplicas do backend agora podem rodar com segurança (claim de jobs com SKIP LOCKED, rate limit compartilhado via Redis, pool dimensionável). O caminho para workers dedicados já existe sem mudança de código.
- **Segurança**: webhook autenticável, boot bloqueado com secret fraca em produção, login em tempo constante, headers de proxy, tokens expirados purgados.
- **Confiabilidade**: nenhum job perdido por crash, nenhuma escrita parcial commitada, nenhum logout espúrio no frontend.

## 5. Riscos remanescentes (conhecidos e aceitos nesta fase)

1. **Tokens no `localStorage`** — vulnerável a XSS; a mitigação definitiva (cookies httpOnly + CSRF) é mudança de contrato e ficou para a Fase 3.
2. **Worker no processo da API** — adequado até centenas de jobs/min; extrair para container dedicado é trivial (mesma imagem, comando diferente) quando a carga justificar.
3. **`qdrant_client.search` deprecado** — funcional; migrar para `query_points` na próxima atualização da lib.
4. **Webhook depende de secret compartilhada** — providers com assinatura HMAC nativa (Cloud API) merecem validação de assinatura específica.
5. **Multi-tenancy** — contatos/igreja/loja são globais por design (instância pessoal). Para SaaS multiusuário real, seria preciso escopo por conta.

## 6. Recomendações para a próxima fase

Ver proposta de Fase 3 no final do PR/relatório de entrega: consolidar o produto (conversas em tempo real, resposta automática ponta a ponta, cookies httpOnly) antes de qualquer expansão de escopo.
