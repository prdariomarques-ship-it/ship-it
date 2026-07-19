#!/usr/bin/env bash
# Backup verification watchdog for scripts/backup.sh. Runs shortly after
# darioos-backup.timer (see docker/systemd/darioos-backup-verify.{service,timer},
# installed by install-backup-timer.sh) and confirms last night's backup
# actually happened and produced usable files.
#
# Read-only: this script never modifies the backup, the databases, or any
# systemd unit. It only inspects state and writes its own report. Safe to
# re-run any number of times (idempotent) — each run just writes a new
# timestamped report file; nothing is overwritten or mutated.
#
# Checks performed, each reported as its own PASS/FAIL line:
#   1. darioos-backup.timer fired today
#   2. darioos-backup.service completed successfully (Result=success, exit 0)
#   3. Neither backup unit is in a persistent "failed" state
#   4. No journal entries at priority >= err for the backup service today
#   5. Expected backup files exist (>=1 Postgres dump, >=1 Qdrant snapshot)
#   6. Those files were created today
#   7. Those files are non-empty
#   8. Archive integrity: `gunzip -t` for the Postgres dump, best-effort
#      `tar -tf` for Qdrant snapshots (Qdrant's snapshot format isn't
#      guaranteed to be a plain tar across versions, so a tar-read failure
#      here is a warning, not a hard failure — size/non-corruption is)
#
# Scope note: the "no systemd failures" and "no journal errors" checks are
# scoped to darioos-backup.{service,timer} specifically, not a system-wide
# `systemctl --user --failed` sweep — this host also runs unrelated user
# services (spcx-monitor, signal-engine, renda-fixa-monitor) whose failures
# would be noise here, not signal.
#
# Telegram: optional. If TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set
# (e.g. via a project .env loaded through the systemd unit's
# EnvironmentFile=), a failure always sends a high-priority alert; a
# success only sends one if TELEGRAM_NOTIFY_ON_SUCCESS=true is also set.
# Unconfigured is a normal, supported state — the script just logs that
# it's skipping notification and relies on the report file instead. This
# repo's only pre-existing Telegram sender (work/send_fx_telegram.py)
# belongs to an unrelated project (different bot, different .env) and is
# intentionally NOT reused here.
set -uo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/darioos-backups}"
REPORT_DIR="$BACKUP_DIR/verify-reports"
TODAY=$(date +%Y%m%d)
TODAY_ISO=$(date +%Y-%m-%d)   # journalctl -S needs dashes; file globs need the compact form above
RUN_STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$REPORT_DIR"
REPORT_FILE="$REPORT_DIR/verify-$RUN_STAMP.log"

overall_ok=1
checks=()      # human-readable PASS/FAIL lines
fail_reasons=() # short reasons, collected for the Telegram alert

pass() { checks+=("[PASS] $1"); }
fail() { checks+=("[FAIL] $1"); overall_ok=0; fail_reasons+=("$1"); }
warn() { checks+=("[WARN] $1"); }

svc_prop() { systemctl --user show darioos-backup.service --property="$1" --value 2>/dev/null; }
timer_prop() { systemctl --user show darioos-backup.timer --property="$1" --value 2>/dev/null; }

# --- 1. Did the timer fire today? ---------------------------------------
last_trigger=$(timer_prop LastTriggerUSec)
last_trigger_date=""
if [[ -n "$last_trigger" && "$last_trigger" != "n/a" ]]; then
  last_trigger_date=$(date -d "$last_trigger" +%Y%m%d 2>/dev/null || echo "")
fi
if [[ "$last_trigger_date" == "$TODAY" ]]; then
  pass "Timer disparou hoje (darioos-backup.timer) — último disparo: $last_trigger"
else
  fail "Timer não disparou hoje (LastTriggerUSec='${last_trigger:-vazio}') — verifique 'systemctl --user list-timers darioos-backup.timer' e se lingering/user@$(id -u).service seguem ativos"
fi

# --- 2. Did the service complete successfully? ---------------------------
result=$(svc_prop Result)
exit_status=$(svc_prop ExecMainStatus)
start_ts=$(svc_prop ExecMainStartTimestamp)
end_ts=$(svc_prop ExecMainExitTimestamp)
duration="desconhecida"
if [[ -n "$start_ts" && -n "$end_ts" ]]; then
  start_epoch=$(date -d "$start_ts" +%s 2>/dev/null || echo "")
  end_epoch=$(date -d "$end_ts" +%s 2>/dev/null || echo "")
  if [[ -n "$start_epoch" && -n "$end_epoch" ]]; then
    duration="$((end_epoch - start_epoch))s"
  fi
fi

if [[ "$result" == "success" && "$exit_status" == "0" ]]; then
  pass "Serviço concluiu com sucesso (darioos-backup.service) — início: $start_ts, fim: $end_ts, duração: $duration"
else
  fail "Serviço não concluiu com sucesso (Result='${result:-vazio}', ExecMainStatus='${exit_status:-vazio}')"
fi

# --- 3. Persistent failed state on either unit? ---------------------------
svc_failed=$(systemctl --user is-failed darioos-backup.service 2>/dev/null || true)
timer_failed=$(systemctl --user is-failed darioos-backup.timer 2>/dev/null || true)
if [[ "$svc_failed" != "failed" && "$timer_failed" != "failed" ]]; then
  pass "Nenhuma falha persistente nas unidades de backup (service='$svc_failed', timer='$timer_failed')"
else
  fail "Unidade(s) em estado 'failed' — service='$svc_failed', timer='$timer_failed'"
fi

# --- 4. Journal errors for today's run? -----------------------------------
# -q/--quiet: without it, journalctl prints a literal "-- No entries --"
# placeholder to stdout when nothing matches, which is non-empty and would
# otherwise be misread as "errors found".
journal_errors=$(journalctl --user -u darioos-backup.service -S "$TODAY_ISO 00:00:00" -p err --no-pager -q 2>/dev/null || true)
if [[ -z "$journal_errors" ]]; then
  pass "Nenhum erro (priority >= err) no journal de darioos-backup.service hoje"
else
  fail "Erros encontrados no journal de darioos-backup.service hoje (ver seção de journal abaixo)"
fi

# --- 5/6/7. Files exist, are from today, and are non-empty ---------------
shopt -s nullglob
pg_files=("$BACKUP_DIR"/darioos-"$TODAY"-*.sql.gz)
qdrant_files=("$BACKUP_DIR"/qdrant-*-"$TODAY"-*.snapshot)
shopt -u nullglob

if [[ ${#pg_files[@]} -gt 0 && ${#qdrant_files[@]} -gt 0 ]]; then
  pass "Arquivos esperados existem e são de hoje — Postgres: ${#pg_files[@]}; Qdrant: ${#qdrant_files[@]}"
else
  fail "Arquivos esperados ausentes para hoje — Postgres: ${#pg_files[@]} encontrado(s), Qdrant: ${#qdrant_files[@]} encontrado(s) (esperado >=1 de cada em $BACKUP_DIR)"
fi

total_bytes=0
empty_files=()
for f in "${pg_files[@]}" "${qdrant_files[@]}"; do
  size=$(stat -c%s "$f" 2>/dev/null || echo 0)
  total_bytes=$((total_bytes + size))
  [[ "$size" -eq 0 ]] && empty_files+=("$f")
done
if [[ ${#pg_files[@]} -eq 0 && ${#qdrant_files[@]} -eq 0 ]]; then
  fail "Não há arquivos para checar tamanho (nenhum encontrado)"
elif [[ ${#empty_files[@]} -eq 0 ]]; then
  pass "Todos os arquivos de hoje têm tamanho > 0"
else
  fail "Arquivo(s) com tamanho 0: ${empty_files[*]}"
fi

# --- 8. Archive integrity -------------------------------------------------
corrupt_files=()
for f in "${pg_files[@]}"; do
  if [[ -s "$f" ]] && ! gunzip -t "$f" 2>/dev/null; then
    corrupt_files+=("$f")
  fi
done
if [[ ${#pg_files[@]} -gt 0 ]]; then
  if [[ ${#corrupt_files[@]} -eq 0 ]]; then
    pass "Dump(s) do Postgres passaram em 'gunzip -t'"
  else
    fail "Dump(s) do Postgres corrompidos ('gunzip -t' falhou): ${corrupt_files[*]}"
  fi
fi

tar_ok=0
tar_checked=0
for f in "${qdrant_files[@]}"; do
  [[ -s "$f" ]] || continue
  tar_checked=$((tar_checked + 1))
  if tar -tf "$f" >/dev/null 2>&1; then
    tar_ok=$((tar_ok + 1))
  fi
done
if [[ "$tar_checked" -gt 0 ]]; then
  if [[ "$tar_ok" -eq "$tar_checked" ]]; then
    pass "Snapshot(s) do Qdrant passaram em 'tar -tf' ($tar_ok/$tar_checked)"
  else
    warn "Snapshot(s) do Qdrant não puderam ser lidos com 'tar -tf' ($tar_ok/$tar_checked) — formato pode não ser tar puro nesta versão do Qdrant; validado apenas por tamanho, não é tratado como falha"
  fi
fi

total_human=$(numfmt --to=iec --suffix=B "$total_bytes" 2>/dev/null || echo "${total_bytes}B")

# --- Assemble the report ---------------------------------------------------
overall_label="PASS"
[[ "$overall_ok" -eq 0 ]] && overall_label="FAIL"

{
  echo "=== Backup Verification Report — darioos-backup — $(date '+%Y-%m-%d %H:%M:%S %z') ==="
  printf '%s\n' "${checks[@]}"
  echo
  echo "Início da execução do backup: ${start_ts:-desconhecido}"
  echo "Fim da execução do backup:    ${end_ts:-desconhecido}"
  echo "Duração:                      $duration"
  echo "Tamanho total dos arquivos de hoje: $total_human"
  echo
  echo "Resultado geral: $overall_label"
  echo
  echo "--- journalctl --user -u darioos-backup.service (desde 00:00 de hoje) ---"
  journalctl --user -u darioos-backup.service --no-pager -S "$TODAY_ISO 00:00:00" 2>&1 || echo "(journal indisponível)"
} | tee "$REPORT_FILE"

echo
echo "Relatório salvo em: $REPORT_FILE"

# --- Optional Telegram notification ---------------------------------------
send_telegram() {
  local text="$1"
  if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]]; then
    echo "Telegram não configurado (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID ausentes) — pulando notificação."
    return 0
  fi
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl não encontrado — não é possível enviar notificação Telegram."
    return 0
  fi
  curl -fsS --max-time 10 \
    -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=${text}" \
    >/dev/null 2>&1 \
    && echo "Notificação Telegram enviada." \
    || echo "Falha ao enviar notificação Telegram (rede/token/chat inválido)."
}

if [[ "$overall_ok" -eq 1 ]]; then
  if [[ "${TELEGRAM_NOTIFY_ON_SUCCESS:-false}" == "true" ]]; then
    send_telegram "✅ Dario OS: backup de $(date +%d/%m/%Y) verificado com sucesso. Tamanho total: $total_human. Duração: $duration."
  fi
  exit 0
else
  reasons=$(printf '%s; ' "${fail_reasons[@]}")
  send_telegram "🚨 Dario OS: FALHA na verificação do backup de $(date +%d/%m/%Y). ${reasons} Relatório completo: $REPORT_FILE"
  exit 1
fi
