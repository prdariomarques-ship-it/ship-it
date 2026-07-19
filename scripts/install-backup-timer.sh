#!/usr/bin/env bash
# Installs and enables the daily backup AND its verification watchdog as
# systemd --user timers — this project's convention for background jobs
# (see CLAUDE.md) — replacing the "register this manually in cron, it's not
# done anywhere" gap that BACKUP.md and PLATFORM_READINESS_REPORT_v1.3.1.md
# both flagged.
#
# Idempotent: safe to re-run after editing any of the unit files.
#
# Note: enabling the timer here is not enough on its own for the schedule
# to survive logout/reboot on WSL — that also requires
# `sudo loginctl enable-linger $USER` (one-time, requires a password, so
# it isn't run automatically by this script). See BACKUP.md for why.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"

mkdir -p "$UNIT_DIR"
cp "$REPO_DIR/docker/systemd/darioos-backup.service" "$UNIT_DIR/"
cp "$REPO_DIR/docker/systemd/darioos-backup.timer" "$UNIT_DIR/"
cp "$REPO_DIR/docker/systemd/darioos-backup-verify.service" "$UNIT_DIR/"
cp "$REPO_DIR/docker/systemd/darioos-backup-verify.timer" "$UNIT_DIR/"

systemctl --user daemon-reload
systemctl --user enable --now darioos-backup.timer
systemctl --user enable --now darioos-backup-verify.timer

echo "Timers instalados e ativados. Próximas execuções:"
systemctl --user list-timers darioos-backup.timer darioos-backup-verify.timer --no-pager
