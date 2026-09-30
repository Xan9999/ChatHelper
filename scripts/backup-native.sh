#!/usr/bin/env bash
# Backup for the native (non-Docker) install: PostgreSQL custom-format dump +
# a downloaded snapshot of every Qdrant collection + SHA-256 checksums, in
# /srv/chathelper/backups/<UTC timestamp>/. Keeps the newest KEEP backups.
# Run as root (cron). Copy the directory off the server regularly.
set -Eeuo pipefail
umask 077
BASE=${CH_BASE:-/srv/chathelper}
KEEP=${KEEP:-14}
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BASE/backups/$TS"
mkdir -p "$OUT/qdrant"

echo "Backing up PostgreSQL..."
runuser -u postgres -- pg_dump -d chathelper --format=custom > "$OUT/postgres.dump"

echo "Creating and downloading Qdrant snapshots..."
(cd "$BASE/app" && "$BASE/venv/bin/python" -m chathelper.backup_qdrant "$OUT/qdrant")

(cd "$OUT" && sha256sum postgres.dump qdrant/* > SHA256SUMS)
echo "Backup complete: $OUT"

# Prune old backups, newest first, keeping $KEEP.
ls -1dt "$BASE"/backups/*/ 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -rf
