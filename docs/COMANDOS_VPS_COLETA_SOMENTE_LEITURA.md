# VPS — coleta SOMENTE LEITURA para destravar as correções dos agentes do WhatsApp

Objetivo: trazer o que falta (código real do agente da Loja, cadeia Alembic, estado do banco e evidência do incidente de autoria) para
corrigir os agentes **sobre o que roda de verdade**. **Não implanta nada, não reinicia nada, não altera banco.** O único lugar onde
algo é escrito é uma pasta nova (`$OUT`). Rode **um bloco por vez** e confira a saída antes do próximo.

Cuidados:
- A VPS tem pouca RAM livre (~268 MB, swap alta, segundo o `SESSION_TRACKING.md`). Rode `free -m` antes; se estiver sufocada, pule os
  blocos 5–6 (Alembic dentro do container) e envie só os arquivos.
- Nada abaixo imprime senha/token: variáveis de ambiente saem **só pelo nome**. Ainda assim, **leia os arquivos gerados antes de
  enviar** e troque por `***` qualquer dado pessoal (telefones já saem só com os 4 últimos dígitos). Nunca cole tokens no chat.
- Os nomes `darioos-evolution-backend-1`, `darioos_cutover_20260927` e o caminho do Compose vêm do `SESSION_TRACKING.md` (nada foi
  lido da VPS por mim). O bloco 1 confirma se ainda valem.

## 0. Variáveis e pasta de saída
```bash
BK=darioos-evolution-backend-1
COMPOSE=/opt/chroma-migration-20260927/app.compose.prepared.json
OUT=/root/coleta-agentes-$(date +%Y%m%d-%H%M); mkdir -p "$OUT" && cd "$OUT" && pwd
free -m | tee memoria.txt
```

## 1. O que está rodando (confirma nomes, imagem e digest)
```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' | tee docker_ps.txt
docker inspect "$BK" --format 'imageid={{.Image}} config_image={{.Config.Image}} started={{.State.StartedAt}}' | tee imagem_backend.txt
docker inspect "$BK" --format '{{json .Mounts}}' > mounts_backend.json           # confirma: sem bind mount de código
docker inspect "$BK" --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' | tee compose_label.txt
ls -l "$COMPOSE" | tee compose_arquivo.txt
```

## 2. Variáveis de ambiente — só os NOMES, e o valor apenas das chaves não secretas
```bash
docker exec "$BK" sh -c 'env | cut -d= -f1 | sort' > env_nomes.txt
docker exec "$BK" sh -c 'env | grep -E "^(ENVIRONMENT|AUTO_REPLY_ENABLED|STORE_WHATSAPP_ENABLED|EVOLUTION_INSTANCE|EVOLUTION_PERSONAL_INSTANCE|WHATSAPP_PROVIDER|JOBS_[A-Z_]*)="' | tee env_flags.txt
```

## 3. Código real dentro da imagem (hash e cópia dos arquivos que faltam)
```bash
APP=$(docker exec "$BK" python -c "import jobs,os;print(os.path.dirname(os.path.dirname(jobs.__file__)))"); echo "$APP" | tee app_dir.txt
# onde estão os arquivos que faltam (fora de site-packages)
docker exec "$BK" sh -c "find $APP -type f \( -name planner.py -o -name store_agent.py -o -name descriptions.py -o -name context.py -o -name config.py \) | grep -v site-packages" | tee onde_estao.txt
# hashes de TODOS os .py do aplicativo (para comparar com a coleta anterior e com a candidata)
docker exec "$BK" sh -c "cd $APP && find . -name '*.py' -not -path './tests/*' | sort | xargs sha256sum" > sha256_todos_py.txt
grep -E "jobs/handlers.py|webhooks/router.py" sha256_todos_py.txt | tee hashes_handlers_router.txt   # coleta anterior: handlers d49034ee…, router 7da0966f…
# copia os arquivos pedidos (ajuste a lista com o que o 'onde_estao.txt' mostrou)
mkdir -p codigo && while read -r f; do mkdir -p "codigo/$(dirname "$f")"; docker cp "$BK:$f" "codigo/$f"; done < onde_estao.txt
```

## 4. Cadeia Alembic — arquivos (não executa nada)
```bash
docker exec "$BK" sh -c "ls -1 $APP/alembic/versions | sort" > alembic_arquivos.txt
docker exec "$BK" sh -c "cd $APP/alembic/versions && sha256sum *.py" > alembic_sha256.txt
```

## 5. Alembic — versão atual do banco (leitura; usa a RAM do container)
```bash
docker exec "$BK" sh -c "cd $APP && alembic current && alembic heads" 2>&1 | tee alembic_current_heads.txt
```

## 6. Banco (somente SELECT, transação somente leitura)
```bash
DB=$(docker ps --format '{{.Names}}' | grep -i -E 'postgres|db' | head -1); echo "$DB" | tee db_container.txt
PGU=$(docker exec "$DB" printenv POSTGRES_USER); DBN=darioos_cutover_20260927
q() { docker exec -i "$DB" psql -U "$PGU" -d "$DBN" -v ON_ERROR_STOP=1 -P pager=off -c "$1"; }
{
q "BEGIN READ ONLY; SELECT version_num FROM alembic_version; COMMIT;"
q "SELECT to_regclass('public.conversation_controls') AS controle_conversa, to_regclass('public.conversation_send_intents') AS reservas, to_regclass('public.conversation_receipts') AS recibos;"
q "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_name IN ('messages','contacts') ORDER BY 1, ordinal_position;"
q "SELECT direction, sent_by_human, whatsapp_instance, count(*), min(created_at)::date AS desde, max(created_at)::date AS ate FROM messages GROUP BY 1,2,3 ORDER BY 1,2,3;"
q "SELECT name, status, count(*) FROM jobs GROUP BY 1,2 ORDER BY 1,2;"
q "SELECT source, level, count(*) FROM logs WHERE created_at > now() - interval '48 hours' GROUP BY 1,2 ORDER BY 3 DESC LIMIT 40;"
} 2>&1 | tee banco_estado.txt
```

## 7. Incidente de autoria (Flávio/Micael) — evidência mínima, telefones mascarados
```bash
{
q "SELECT id, name, 'xxxx'||right(phone,4) AS fone FROM contacts WHERE name ILIKE ANY (ARRAY['%flávio%','%flavio%','%micael%']) ORDER BY id;"
q "SELECT m.id, m.contact_id, m.direction, m.sent_by_human, m.is_autopilot_reply, m.whatsapp_instance, m.created_at, left(regexp_replace(m.content, '[0-9]{8,}', '#', 'g'), 100) AS inicio
   FROM messages m JOIN contacts c ON c.id = m.contact_id
   WHERE c.name ILIKE ANY (ARRAY['%flávio%','%flavio%','%micael%']) ORDER BY m.contact_id, m.created_at DESC LIMIT 60;"
} 2>&1 | tee incidente_autoria.txt
```

## 8. Empacota e confere
```bash
cd .. && tar czf "$(basename "$OUT").tgz" "$(basename "$OUT")" && sha256sum "$(basename "$OUT").tgz" && ls -l "$(basename "$OUT").tgz"
```
Revise `env_flags.txt`, `banco_estado.txt` e `incidente_autoria.txt` antes de enviar (mensagens de clientes). Envie o `.tgz` e o hash.

## O que eu faço com o resultado (prioridade: agentes do WhatsApp)
1. Comparo `sha256_todos_py.txt` com a coleta anterior e com a candidata; se `handlers.py`/`router.py` mudaram, refaço os patches da PR #63 sobre o código real.
2. Leio `store_agent.py`, `planner.py`, `descriptions.py` e `context.py` reais: causa do incidente de autoria, origem da frase "sou o assistente" repetida, e aplico `report_unknown`, a pausa antes da geração e a barreira de retomada **nesses** arquivos.
3. Confronto `alembic_*` e `banco_estado.txt` com `c8f3a1d27b40` e `e610080001..3`: só então proponho a ordem de migração.
4. **Só depois** monto os comandos da janela (backup, ponto de retorno por digest, aplicação, validação e rollback), tirados desses dados — não de suposições. A janela e o rollback continuam dependendo da sua aprovação.
