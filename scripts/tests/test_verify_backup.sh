#!/usr/bin/env bash
# Self-contained test suite for scripts/verify-backup.sh.
#
# Runs the REAL script end-to-end against several scenarios, with
# `systemctl`/`journalctl` replaced by fake executables (prepended onto
# PATH) so no actual systemd state is needed. Each scenario writes its own
# fixture files into a throwaway BACKUP_DIR and asserts the script's exit
# code and report content match what that scenario should produce.
#
# No test framework dependency (bats, etc.) — plain bash, matching this
# script's own footprint. Run directly: ./scripts/tests/test_verify_backup.sh
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
VERIFY_SCRIPT="$REPO_DIR/scripts/verify-backup.sh"
WORKDIR=$(mktemp -d)
FAKE_BIN="$WORKDIR/bin"
mkdir -p "$FAKE_BIN"

trap 'rm -rf "$WORKDIR"' EXIT

TODAY=$(date +%Y-%m-%d)
TODAY_COMPACT=$(date +%Y%m%d)
YESTERDAY=$(date -d "yesterday" +%Y-%m-%d)

# --- Fake systemctl / journalctl ------------------------------------------
cat > "$FAKE_BIN/systemctl" <<'FAKE_SYSTEMCTL'
#!/usr/bin/env bash
case "$*" in
  *"show darioos-backup.service --property=Result"*)
    echo "${FAKE_SVC_RESULT:-success}" ;;
  *"show darioos-backup.service --property=ExecMainStatus"*)
    echo "${FAKE_SVC_EXIT_STATUS:-0}" ;;
  *"show darioos-backup.service --property=ExecMainStartTimestamp"*)
    echo "${FAKE_SVC_START_TS:-}" ;;
  *"show darioos-backup.service --property=ExecMainExitTimestamp"*)
    echo "${FAKE_SVC_END_TS:-}" ;;
  *"show darioos-backup.timer --property=LastTriggerUSec"*)
    echo "${FAKE_TIMER_LAST_TRIGGER:-}" ;;
  *"is-failed darioos-backup.service"*)
    echo "${FAKE_SVC_IS_FAILED:-active}"
    [[ "${FAKE_SVC_IS_FAILED:-active}" == "failed" ]] && exit 0 || exit 1 ;;
  *"is-failed darioos-backup.timer"*)
    echo "${FAKE_TIMER_IS_FAILED:-active}"
    [[ "${FAKE_TIMER_IS_FAILED:-active}" == "failed" ]] && exit 0 || exit 1 ;;
  *)
    echo "fake systemctl: unhandled args: $*" >&2; exit 1 ;;
esac
FAKE_SYSTEMCTL

cat > "$FAKE_BIN/journalctl" <<'FAKE_JOURNALCTL'
#!/usr/bin/env bash
# Mirrors real journalctl's quirk: without -q/--quiet it prints a literal
# "-- No entries --" placeholder (non-empty!) when nothing matches. This
# caught a real bug once (script wasn't passing -q) — kept here so a future
# regression on that flag fails this suite instead of only real backups.
if [[ "$*" == *"-p err"* ]]; then
  if [[ -n "${FAKE_JOURNAL_ERRORS:-}" ]]; then
    echo "$FAKE_JOURNAL_ERRORS"
  elif [[ "$*" != *"-q"* && "$*" != *"--quiet"* ]]; then
    echo "-- No entries --"
  fi
else
  echo "${FAKE_JOURNAL_FULL:-(sem logs de teste)}"
fi
FAKE_JOURNALCTL

chmod +x "$FAKE_BIN/systemctl" "$FAKE_BIN/journalctl"

pass_count=0
fail_count=0

# assert_scenario NAME EXPECTED_EXIT [grep pattern expected in report]
run_scenario() {
  local name="$1" expected_exit="$2" grep_pattern="${3:-}"
  local backup_dir="$WORKDIR/backups-$name"
  mkdir -p "$backup_dir"

  "$SETUP_FIXTURES" "$backup_dir"

  local out
  out=$(PATH="$FAKE_BIN:$PATH" BACKUP_DIR="$backup_dir" bash "$VERIFY_SCRIPT" 2>&1)
  local actual_exit=$?

  local ok=1
  if [[ "$actual_exit" -ne "$expected_exit" ]]; then
    ok=0
    echo "FAIL: $name — esperado exit=$expected_exit, obtido exit=$actual_exit"
  fi
  if [[ -n "$grep_pattern" ]] && ! grep -q "$grep_pattern" <<<"$out"; then
    ok=0
    echo "FAIL: $name — saída não contém padrão esperado: $grep_pattern"
  fi

  if [[ "$ok" -eq 1 ]]; then
    echo "PASS: $name"
    pass_count=$((pass_count + 1))
  else
    fail_count=$((fail_count + 1))
    echo "--- saída de '$name' para depuração ---"
    echo "$out"
    echo "--- fim ---"
  fi
}

make_valid_pg_dump() {
  echo "fake pg dump content" | gzip > "$1"
}

make_valid_qdrant_snapshot() {
  local dummy="$WORKDIR/dummy.txt"
  echo "dummy" > "$dummy"
  tar -cf "$1" -C "$WORKDIR" "$(basename "$dummy")"
}

# --- Scenario 1: everything healthy ---------------------------------------
export FAKE_SVC_RESULT=success FAKE_SVC_EXIT_STATUS=0
export FAKE_SVC_START_TS="$TODAY 03:00:00" FAKE_SVC_END_TS="$TODAY 03:00:12"
export FAKE_TIMER_LAST_TRIGGER="$TODAY 03:00:00"
export FAKE_SVC_IS_FAILED=active FAKE_TIMER_IS_FAILED=active
export FAKE_JOURNAL_ERRORS=""
SETUP_FIXTURES() {
  make_valid_pg_dump "$1/darioos-${TODAY_COMPACT}-030000.sql.gz"
  make_valid_qdrant_snapshot "$1/qdrant-darioos_memory-${TODAY_COMPACT}-030005.snapshot"
}
export -f SETUP_FIXTURES make_valid_pg_dump make_valid_qdrant_snapshot
SETUP_FIXTURES=SETUP_FIXTURES
run_scenario "tudo_saudavel" 0 "Resultado geral: PASS"

# --- Scenario 2: timer never fired today ----------------------------------
export FAKE_TIMER_LAST_TRIGGER="$YESTERDAY 03:00:00"
SETUP_FIXTURES() {
  make_valid_pg_dump "$1/darioos-${TODAY_COMPACT}-030000.sql.gz"
  make_valid_qdrant_snapshot "$1/qdrant-darioos_memory-${TODAY_COMPACT}-030005.snapshot"
}
export -f SETUP_FIXTURES
run_scenario "timer_nao_disparou" 1 "Timer não disparou hoje"
export FAKE_TIMER_LAST_TRIGGER="$TODAY 03:00:00"

# --- Scenario 3: service failed --------------------------------------------
export FAKE_SVC_RESULT=failed FAKE_SVC_EXIT_STATUS=1
SETUP_FIXTURES() {
  make_valid_pg_dump "$1/darioos-${TODAY_COMPACT}-030000.sql.gz"
  make_valid_qdrant_snapshot "$1/qdrant-darioos_memory-${TODAY_COMPACT}-030005.snapshot"
}
export -f SETUP_FIXTURES
run_scenario "servico_falhou" 1 "não concluiu com sucesso"
export FAKE_SVC_RESULT=success FAKE_SVC_EXIT_STATUS=0

# --- Scenario 4: no files created for today --------------------------------
SETUP_FIXTURES() { :; }
export -f SETUP_FIXTURES
run_scenario "arquivos_ausentes" 1 "Arquivos esperados ausentes"

# --- Scenario 5: corrupt Postgres dump --------------------------------------
SETUP_FIXTURES() {
  echo "isto nao e um gzip valido" > "$1/darioos-${TODAY_COMPACT}-030000.sql.gz"
  make_valid_qdrant_snapshot "$1/qdrant-darioos_memory-${TODAY_COMPACT}-030005.snapshot"
}
export -f SETUP_FIXTURES
run_scenario "dump_corrompido" 1 "gunzip -t.*falhou\|corrompidos"

# --- Scenario 6: journal has errors -----------------------------------------
export FAKE_JOURNAL_ERRORS="Jul 20 03:00:05 backup.sh[123]: Traceback (most recent call last): ERROR"
SETUP_FIXTURES() {
  make_valid_pg_dump "$1/darioos-${TODAY_COMPACT}-030000.sql.gz"
  make_valid_qdrant_snapshot "$1/qdrant-darioos_memory-${TODAY_COMPACT}-030005.snapshot"
}
export -f SETUP_FIXTURES
run_scenario "erros_no_journal" 1 "Erros encontrados no journal"
export FAKE_JOURNAL_ERRORS=""

# --- Scenario 7: unit in persistent failed state ---------------------------
export FAKE_SVC_IS_FAILED=failed
SETUP_FIXTURES() {
  make_valid_pg_dump "$1/darioos-${TODAY_COMPACT}-030000.sql.gz"
  make_valid_qdrant_snapshot "$1/qdrant-darioos_memory-${TODAY_COMPACT}-030005.snapshot"
}
export -f SETUP_FIXTURES
run_scenario "unidade_em_estado_failed" 1 "estado 'failed'"
export FAKE_SVC_IS_FAILED=active

echo
echo "=== Resumo: $pass_count passou, $fail_count falhou ==="
[[ "$fail_count" -eq 0 ]]
