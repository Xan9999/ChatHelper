#!/bin/sh
# Give ChatHelper its own non-superuser role on every fresh deployment.
set -eu

export PGPASSWORD="$(cat /run/secrets/postgres_password)"
database="${POSTGRES_DB:-chathelper}"

if ! psql -h postgres -U postgres -d "$database" -tAc \
    "SELECT 1 FROM pg_roles WHERE rolname = 'chathelper_app'" | grep -qx 1; then
    psql -h postgres -U postgres -d "$database" -v ON_ERROR_STOP=1 \
        -c 'CREATE ROLE chathelper_app LOGIN'
fi

psql -h postgres -U postgres -d "$database" -v ON_ERROR_STOP=1 \
    -v "database=$database" \
    -v "app_password=$(cat /run/secrets/app_db_password)" <<'SQL'
ALTER ROLE chathelper_app LOGIN PASSWORD :'app_password';
GRANT CONNECT ON DATABASE :"database" TO chathelper_app;
GRANT USAGE, CREATE ON SCHEMA public TO chathelper_app;
SQL
