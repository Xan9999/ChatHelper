#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env.production"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
SECRETS_DIR="$ROOT_DIR/secrets"
COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

die() {
    echo "ERROR: $*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

env_value() {
    awk -F= -v wanted="$1" '
        $1 == wanted {
            sub(/^[^=]*=/, "")
            sub(/\r$/, "")
            print
            exit
        }
    ' "$ENV_FILE"
}

prepare() {
    require_command openssl
    mkdir -p "$SECRETS_DIR" "$ROOT_DIR/backups"
    chmod 700 "$SECRETS_DIR" "$ROOT_DIR/backups"
    if [[ ! -f "$ENV_FILE" ]]; then
        cp "$ROOT_DIR/.env.production.example" "$ENV_FILE"
        chmod 600 "$ENV_FILE"
        echo "Created $ENV_FILE; review every value before deployment."
    fi
    umask 077
    if [[ ! -s "$SECRETS_DIR/postgres_password.txt" ]]; then
        openssl rand -hex 32 > "$SECRETS_DIR/postgres_password.txt"
    fi
    if [[ ! -s "$SECRETS_DIR/app_db_password.txt" ]]; then
        openssl rand -hex 32 > "$SECRETS_DIR/app_db_password.txt"
    fi
    if [[ ! -s "$SECRETS_DIR/qa_token.txt" ]]; then
        openssl rand -hex 32 > "$SECRETS_DIR/qa_token.txt"
    fi
    echo "Secrets are ready in $SECRETS_DIR (never commit this directory)."
    echo "Edit $ENV_FILE, place model files in MODELS_DIR, then run:"
    echo "  bash scripts/deploy.sh validate"
}

validate() {
    require_command docker
    require_command awk
    [[ -s "$ENV_FILE" ]] || die "Missing $ENV_FILE; run prepare first"
    [[ -s "$SECRETS_DIR/postgres_password.txt" ]] || die "Missing PostgreSQL secret"
    [[ -s "$SECRETS_DIR/app_db_password.txt" ]] || die "Missing app database secret"
    [[ -s "$SECRETS_DIR/qa_token.txt" ]] || die "Missing QA secret"
    if grep -Eq '(^|=)(CHANGE_ME|example\.com|admin@example\.com)' "$ENV_FILE"; then
        die "Replace placeholder values in $ENV_FILE"
    fi
    local models_dir chat_model embed_model
    models_dir="$(env_value MODELS_DIR)"
    chat_model="$(env_value CHAT_MODEL_FILE)"
    embed_model="$(env_value EMBED_MODEL_FILE)"
    [[ "$models_dir" = /* ]] || die "MODELS_DIR must be an absolute path"
    [[ -r "$models_dir/$chat_model" ]] || die "Chat model not readable: $models_dir/$chat_model"
    [[ -r "$models_dir/$embed_model" ]] || die "Embedding model not readable: $models_dir/$embed_model"
    docker info >/dev/null
    "${COMPOSE[@]}" config --quiet
    echo "Compose configuration is valid."
}

validate_caddyfile() {
    # Parse the Caddyfile with the pinned Caddy image before (re)starting the
    # stack: a syntax error there would otherwise take the public endpoint
    # down while every other container keeps running.
    "${COMPOSE[@]}" run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile
}

up() {
    validate
    validate_caddyfile
    "${COMPOSE[@]}" pull --ignore-buildable
    "${COMPOSE[@]}" build --pull app
    "${COMPOSE[@]}" up -d --remove-orphans
    "${COMPOSE[@]}" ps
}

update() {
    validate
    bash "$ROOT_DIR/scripts/backup.sh"
    git -C "$ROOT_DIR" pull --ff-only
    validate_caddyfile
    "${COMPOSE[@]}" pull --ignore-buildable
    "${COMPOSE[@]}" build --pull app
    "${COMPOSE[@]}" up -d --remove-orphans
    "${COMPOSE[@]}" ps
}

case "${1:-help}" in
    prepare) prepare ;;
    validate) validate ;;
    up) up ;;
    update) update ;;
    backup) bash "$ROOT_DIR/scripts/backup.sh" ;;
    restart)
        validate
        "${COMPOSE[@]}" restart app caddy
        ;;
    status)
        validate
        "${COMPOSE[@]}" ps
        ;;
    logs)
        validate
        "${COMPOSE[@]}" logs -f --tail=200 "${2:-app}"
        ;;
    ingest)
        validate
        shift
        [[ $# -ge 1 ]] || die "Usage: $0 ingest URL [chathelper ingest options]"
        "${COMPOSE[@]}" run --rm app chathelper ingest "$@"
        ;;
    prune)
        validate
        shift
        [[ $# -ge 1 ]] || die "Usage: $0 prune --days N"
        "${COMPOSE[@]}" run --rm --no-deps app chathelper prune "$@"
        ;;
    down)
        validate
        "${COMPOSE[@]}" down
        echo "Containers removed; persistent volumes were preserved."
        ;;
    *)
        echo "Usage: $0 {prepare|validate|up|update|backup|restart|status|logs [service]|ingest URL [options]|prune --days N|down}"
        exit 2
        ;;
esac
