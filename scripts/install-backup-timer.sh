#!/usr/bin/env bash
# Installs and enables the daily backup as a systemd --user timer — this
# project's convention for background jobs (see CLAUDE.md) — replacing the
# "register this manually in cron, it's not done anywhere" gap that
# BACKUP.md and PLATFORM_READINESS_REPORT_v1.3.1.md both flagged.
#
# Idempotent: safe to re-run after editing the unit files.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"

mkdir -p "$UNIT_DIR"
cp "$REPO_DIR/docker/systemd/darioos-backup.service" "$UNIT_DIR/"
cp "$REPO_DIR/docker/systemd/darioos-backup.timer" "$UNIT_DIR/"

systemctl --user daemon-reload
systemctl --user enable --now darioos-backup.timer

echo "Timer instalado e ativado. Próxima execução:"
systemctl --user list-timers darioos-backup.timer --no-pager
