#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env.production"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$ROOT_DIR/backups/$TIMESTAMP"
COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

[[ -s "$ENV_FILE" ]] || { echo "Missing $ENV_FILE" >&2; exit 1; }
mkdir -p "$BACKUP_DIR/qdrant"
chmod 700 "$BACKUP_DIR"

echo "Backing up PostgreSQL..."
"${COMPOSE[@]}" exec -T postgres sh -c \
    'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
    > "$BACKUP_DIR/postgres.dump"

echo "Creating and downloading Qdrant snapshots..."
"${COMPOSE[@]}" run --rm --no-deps \
    --user "$(id -u):$(id -g)" \
    -v "$BACKUP_DIR:/backup" \
    app python -m chathelper.backup_qdrant /backup/qdrant

(cd "$BACKUP_DIR" && sha256sum postgres.dump qdrant/* > SHA256SUMS)
echo "Backup complete: $BACKUP_DIR"
echo "Copy this directory to storage outside the VPS. No old backups were deleted."
