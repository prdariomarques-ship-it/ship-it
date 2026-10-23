#!/bin/bash
# EXPORTA conversas para análise de alucinação. SOMENTE LEITURA: um único SELECT, dentro de uma transação read-only. Não escreve no banco,
# não envia mensagens, não reinicia nada. Não imprime nem grava senha.
#
# Uso (na VPS):
#   export PG_CONTAINER=<nome do container do Postgres>   # veja com: docker ps
#   export PGUSER=<usuario>  PGDATABASE=<banco>            # os mesmos que o app usa; a senha, se houver, vem de PGPASSWORD no ambiente do container
#   bash exportar_conversas_somente_leitura.sh [dias=7] [saida=/root/conversas_dario_os.csv]
#   bash exportar_conversas_somente_leitura.sh --sql      # só mostra o SELECT, não executa
#
# O que sai: toda mensagem dos últimos N dias dos contatos que tiveram ao menos uma resposta automática do Gêmeo/agentes, com quem enviou
# (cliente / dono / automática). Números com 8+ dígitos são trocados por [número] ANTES de gravar o arquivo. Conteúdo cortado em 600 caracteres.
set -u
ONLY_SQL=0; [ "${1:-}" = "--sql" ] && { ONLY_SQL=1; shift; }
DIAS="${1:-7}"; OUT="${2:-/root/conversas_dario_os.csv}"
case "$DIAS" in ''|*[!0-9]*) echo "dias deve ser um número" >&2; exit 2;; esac
CORTE=$(date -u -d "-${DIAS} days" +%Y-%m-%dT%H:%M:%S) || { echo "não consegui calcular a data" >&2; exit 2; }
SQL="SELECT m.id, m.contact_id, c.name AS contato, m.whatsapp_instance AS linha, m.direction, m.media_type,
       CASE WHEN m.direction = 'INBOUND' THEN 'cliente'
            WHEN m.is_autopilot_reply THEN 'automatica'
            WHEN m.sent_by_human THEN 'dono'
            ELSE 'origem_nao_registrada' END AS autor,
       m.created_at, substr(replace(replace(m.content, chr(10), ' '), chr(13), ' '), 1, 600) AS texto
FROM messages m JOIN contacts c ON c.id = m.contact_id
WHERE m.created_at >= '$CORTE'
  AND m.contact_id IN (SELECT contact_id FROM messages WHERE is_autopilot_reply AND created_at >= '$CORTE')
ORDER BY m.contact_id, m.id"
[ "$ONLY_SQL" = 1 ] && { echo "$SQL"; exit 0; }
: "${PG_CONTAINER:?defina PG_CONTAINER (nome do container do Postgres)}"; : "${PGUSER:?defina PGUSER}"; : "${PGDATABASE:?defina PGDATABASE}"
umask 077
# `default_transaction_read_only=on` + READ ONLY: qualquer escrita falharia mesmo se o SQL fosse alterado.
printf 'BEGIN READ ONLY;\n\\copy (%s) TO STDOUT WITH CSV HEADER\nCOMMIT;\n' "$(printf '%s' "$SQL" | tr '\n' ' ')" \
  | docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' "$PG_CONTAINER" psql -X -q -v ON_ERROR_STOP=1 -U "$PGUSER" -d "$PGDATABASE" \
  | sed -E 's/[0-9][0-9 .()-]{6,}[0-9]/[número]/g' > "$OUT" || { echo "falhou; nada foi alterado no banco" >&2; rm -f "$OUT"; exit 1; }
echo "ok: $(($(wc -l < "$OUT") - 1)) mensagens em $OUT"
