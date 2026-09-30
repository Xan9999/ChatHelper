#!/usr/bin/env bash
# ChatHelper native install for a Linux host WITHOUT Docker (used on the
# AlmaLinux 8 / DirectAdmin server srv.tallweb.eu, where the LXC container
# cannot run Docker). Run as root. Idempotent: safe to re-run after a change.
#
# Installs: Python 3.12 venv + app (systemd: chathelper), PostgreSQL 16 from
# AppStream, Qdrant static binary (systemd: qdrant). Chat and embeddings come
# from the OpenAI API, so no model files are needed. The public HTTPS side is
# Apache: see deploy/native/apache-chathelper.conf.
#
# Afterwards:  paste the OpenAI key into /srv/chathelper/secrets/llm_api_key.txt
#              (one line), edit /srv/chathelper/app/.env, then
#              systemctl restart chathelper && curl -fsS http://127.0.0.1:8000/ready
set -Eeuo pipefail
step() { printf '\n===== %s =====\n' "$*"; }

BASE=${CH_BASE:-/srv/chathelper}
REPO=${CH_REPO:-https://github.com/Xan9999/ChatHelper.git}
APP=$BASE/app
VENV=$BASE/venv
SECRETS=$BASE/secrets
QDRANT_VERSION=${QDRANT_VERSION:-v1.19.0}

step "System packages"
PY=""
for candidate in python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1 || dnf -q list --available "$candidate" >/dev/null 2>&1; then
        PY="$candidate"; break
    fi
done
[ -n "$PY" ] || { echo "No python3.11/3.12 package available" >&2; exit 1; }
dnf install -y -q "$PY" "${PY}-pip" git curl tmux tar >/dev/null
echo "python: $($PY --version)"
if ! rpm -q postgresql-server >/dev/null 2>&1; then
    dnf -y -q module reset postgresql >/dev/null
    dnf -y -q module enable postgresql:16 >/dev/null
    dnf install -y -q postgresql-server postgresql >/dev/null
fi
psql --version

step "Users and directories"
getent group chathelper >/dev/null || groupadd --system chathelper
getent passwd chathelper >/dev/null || useradd --system --gid chathelper --home-dir "$BASE" --shell /sbin/nologin chathelper
getent passwd qdrant >/dev/null || useradd --system --home-dir "$BASE/qdrant" --shell /sbin/nologin qdrant
mkdir -p "$BASE" "$BASE/data" "$BASE/logs" "$BASE/qdrant/storage" "$BASE/qdrant/snapshots" "$SECRETS" "$BASE/backups" /opt/qdrant
chown -R chathelper:chathelper "$BASE/data" "$BASE/logs"
chown -R qdrant:qdrant "$BASE/qdrant"
chmod 700 "$SECRETS" "$BASE/backups"

step "PostgreSQL 16"
if [ ! -f /var/lib/pgsql/data/PG_VERSION ]; then
    postgresql-setup --initdb >/dev/null
fi
PGHBA=/var/lib/pgsql/data/pg_hba.conf
# RHEL's default uses ident for TCP; the app authenticates with a password.
sed -i -E 's/^(host\s+all\s+all\s+127\.0\.0\.1\/32\s+)(ident|md5)/\1scram-sha-256/; s/^(host\s+all\s+all\s+::1\/128\s+)(ident|md5)/\1scram-sha-256/' "$PGHBA"
grep -q "^password_encryption" /var/lib/pgsql/data/postgresql.conf || echo "password_encryption = scram-sha-256" >> /var/lib/pgsql/data/postgresql.conf
systemctl enable --now postgresql >/dev/null
systemctl reload postgresql
if [ ! -s "$SECRETS/app_db_password.txt" ]; then
    (umask 077; openssl rand -hex 24 > "$SECRETS/app_db_password.txt")
fi
DBPASS="$(cat "$SECRETS/app_db_password.txt")"
runuser -u postgres -- psql -v ON_ERROR_STOP=1 -q <<SQL
DO \$\$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'chathelper_app') THEN
        CREATE ROLE chathelper_app LOGIN;
    END IF;
END \$\$;
ALTER ROLE chathelper_app LOGIN PASSWORD '$DBPASS';
SELECT 'CREATE DATABASE chathelper OWNER chathelper_app'
 WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'chathelper')\gexec
SQL
runuser -u postgres -- psql -d chathelper -v ON_ERROR_STOP=1 -q -c "GRANT USAGE, CREATE ON SCHEMA public TO chathelper_app;"
PGPASSWORD="$DBPASS" psql -h 127.0.0.1 -U chathelper_app -d chathelper -tAc "select 'db login ok'"

step "Qdrant $QDRANT_VERSION"
if [ ! -x /opt/qdrant/qdrant ] || ! /opt/qdrant/qdrant --version 2>/dev/null | grep -q "${QDRANT_VERSION#v}"; then
    curl -fsSL --retry 5 -o /tmp/qdrant.tar.gz \
        "https://github.com/qdrant/qdrant/releases/download/${QDRANT_VERSION}/qdrant-x86_64-unknown-linux-musl.tar.gz"
    tar -xzf /tmp/qdrant.tar.gz -C /opt/qdrant
    rm -f /tmp/qdrant.tar.gz
    chmod 755 /opt/qdrant/qdrant
fi
/opt/qdrant/qdrant --version

step "Application"
if [ ! -d "$APP/.git" ]; then
    git clone -q "$REPO" "$APP"
else
    git -C "$APP" pull -q --ff-only
fi
git -C "$APP" log -1 --format='%h %s'
[ -x "$VENV/bin/python" ] || $PY -m venv "$VENV"
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q -e "$APP"
"$VENV/bin/chathelper" --help | head -1
if [ ! -s "$SECRETS/qa_token.txt" ]; then
    (umask 077; openssl rand -hex 32 > "$SECRETS/qa_token.txt")
fi
[ -f "$SECRETS/llm_api_key.txt" ] || (umask 077; : > "$SECRETS/llm_api_key.txt")
chown -R chathelper:chathelper "$SECRETS"
chmod 600 "$SECRETS"/*.txt

if [ ! -f "$APP/.env" ]; then
cat > "$APP/.env" <<'ENV'
# ChatHelper production (native install). Secrets live in
# /srv/chathelper/secrets/*.txt and are referenced via *_FILE.
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY_FILE=/srv/chathelper/secrets/llm_api_key.txt
LLM_MODEL=gpt-4o-mini
LLM_EXTRA_BODY={}
LLM_TIMEOUT=120
EMBED_BASE_URL=https://api.openai.com/v1
EMBED_API_KEY_FILE=/srv/chathelper/secrets/llm_api_key.txt
EMBED_MODEL=text-embedding-3-large
EMBED_DIM=3072
EMBED_DOC_PREFIX=
EMBED_QUERY_PREFIX=
EMBED_TIMEOUT=60

QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=tallweb

POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=chathelper
POSTGRES_USER=chathelper_app
POSTGRES_PASSWORD_FILE=/srv/chathelper/secrets/app_db_password.txt
DB_POOL_MIN_SIZE=1
DB_POOL_MAX_SIZE=5
DB_POOL_TIMEOUT=10

SITE_NAME=Tallweb
SITE_NAMES=adr=Adrlandia,trgopromet=Trgopromet,alemo=ALEMO,ricambiribi=Ricambi Ribi
SITE_STYLES=
ALLOWED_ORIGINS=https://ricambiribi.com,https://www.ricambiribi.com,https://tallweb.net,https://www.tallweb.net
TOP_K=6
CHUNK_SIZE=800
CHUNK_OVERLAP=160
TEMPERATURE=0.2
FREQUENCY_PENALTY=0.4
PRESENCE_PENALTY=0.4
MAX_TOKENS=500
PAGE_MAX_CHARS=1500
QUERY_REWRITE=1
CHAT_MAX_MESSAGE_CHARS=4000
CHAT_HISTORY_MAX_ITEMS=12
CHAT_RATE_LIMIT_PER_MINUTE=30
QA_LOGIN_RATE_LIMIT_PER_MINUTE=10

QA_TOKEN_FILE=/srv/chathelper/secrets/qa_token.txt
QA_COOKIE_SECURE=1
ENABLE_DOCS=0

WIDGET_STYLES_DIR=/srv/chathelper/app/widget_styles
WIDGET_STRINGS_DIR=/srv/chathelper/app/widget_strings
DATA_DIR=/srv/chathelper/data

CRAWL_MAX_PAGES=200
CRAWL_SAME_DOMAIN=1
CRAWL_PDFS=1
CRAWL_PDF_MAX_MB=20
CRAWL_MAX_PAGE_MB=5
BOILERPLATE_STRIP=1
BOILERPLATE_MIN_PAGES=4
BOILERPLATE_PAGE_FRACTION=0.3
ENV
fi
chown root:chathelper "$APP/.env"
chmod 640 "$APP/.env"

step "systemd units"
install -m 644 "$APP/deploy/native/qdrant.service" /etc/systemd/system/qdrant.service
install -m 644 "$APP/deploy/native/chathelper.service" /etc/systemd/system/chathelper.service
systemctl daemon-reload
systemctl enable --now qdrant >/dev/null
systemctl enable chathelper >/dev/null
sleep 2
curl -fsS http://127.0.0.1:6333/collections | head -c 200; echo

step "Summary"
systemctl is-active postgresql qdrant | tr '\n' ' '; echo
ls -l "$SECRETS"
echo "Next: put the OpenAI key in $SECRETS/llm_api_key.txt, review $APP/.env, then:"
echo "  systemctl restart chathelper && curl -fsS http://127.0.0.1:8000/ready"
echo "Apache: install deploy/native/apache-chathelper.conf (see DEPLOYMENT.md, Path B)."
