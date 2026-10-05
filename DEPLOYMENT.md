# ChatHelper production deployment

This deployment is designed for one Linux VPS with Docker Engine, Docker
Compose v2, and root access for the initial host setup. A CPU-only VPS is
enough: chat answers come from the OpenAI API and embeddings run in a small
local CPU container. A GPU is needed only for the optional local chat model
profile. It does not run Passenger. Uvicorn serves FastAPI natively as ASGI.

## Architecture

```text
Internet
   │  TCP 80/443, UDP 443
   ▼
Caddy reverse proxy (automatic TLS)
   │  private Docker edge network
   ▼
ChatHelper / Uvicorn :8000
   │  internal Docker backend network
   ├── PostgreSQL :5432  ── volume: postgres_data
   │    └── one-shot db-init creates the limited app login
   ├── Qdrant :6333      ── volume: qdrant_data
   ├── llama.cpp embeddings :8081 (CPU, bge-m3; profile local-embed)
   └── ──────────────────────► OpenAI API (chat; key from a secret file)
        optional profile local-llm: llama.cpp chat :8080 on a GPU instead
```

Only Caddy publishes host ports. PostgreSQL, Qdrant, Uvicorn, and the
embedding server are not reachable directly from the internet. Caddy owns HTTPS,
certificate renewal, security headers, request-size enforcement, health-aware
proxying, and flushing streamed chat responses. Caddy automatically flushes
`text/event-stream` responses without a special buffering override. This keeps TLS
and public-network policy out of the application and lets app containers be
replaced without changing the public endpoint.

PostgreSQL contains only the `conversations` and `messages` tables used by chat
logging and `/qa`. The legacy product/order data and model tools are not part
of the production system. Qdrant remains the persistent website
knowledge database.

`conversations` stores one row per browser chat session (UUID, site/collection,
visitor page metadata, and start time). `messages` stores the ordered client
and agent turns, timestamps, reply latency, and any internal generation error;
its foreign key deletes message rows if their parent conversation is
deliberately deleted. The schema and indexes are created transactionally at
startup, with a PostgreSQL advisory lock so multiple Uvicorn workers can start
safely together. A one-shot `db-init` container creates a non-superuser
`chathelper_app` login; the administrator password is never mounted into the
ChatHelper app container.

## Host prerequisites

1. Point the DNS `A`/`AAAA` record for the configured `CHAT_DOMAIN` at the VPS.
2. Install Docker Engine and the Docker Compose plugin using their official
   instructions for the VPS OS. The NVIDIA driver and NVIDIA Container Toolkit
   are required only if you enable the `local-llm` profile.
3. Before enabling a firewall, allow the actual SSH port you use. Publicly
   allow only SSH, TCP 80, TCP 443, and optionally UDP 443 for HTTP/3.
4. Ensure no existing web server is using ports 80 or 443.
5. Put the embedding model `bge-m3-Q8_0.gguf` (about 600 MB) in a root-owned
   deployment directory such as `/srv/chathelper/models`; Compose mounts it
   read-only. Add the chat GGUF there too only for the `local-llm` profile.
6. Size the VPS for the embedding container: roughly 1 GB of RAM on top of
   the app, PostgreSQL, and Qdrant. Query embeddings take milliseconds on CPU;
   ingesting a site with thousands of pages is CPU-bound and slower than on a
   GPU, so run large crawls off-peak.

Do not expose ports 5432, 6333, 6334, 8000, 8080, or 8081 in the VPS firewall.
The Compose file intentionally uses `expose`, not `ports`, for those services.

## Model options

| `COMPOSE_PROFILES` | Chat | Embeddings | Notes |
|---|---|---|---|
| `local-embed` (default) | OpenAI API via `LLM_BASE_URL`, `LLM_MODEL` | bge-m3 in the CPU `embed` container | Existing collections (1024-d) keep working. |
| `local-embed,local-llm` | `llm` GPU container | same | Set `LLM_BASE_URL=http://llm:8080/v1`, `LLM_MODEL=local-chat`, `LLM_EXTRA_BODY` for the model. |
| empty | OpenAI API | OpenAI `text-embedding-3-small` | Set `EMBED_BASE_URL=https://api.openai.com/v1`, `EMBED_DIM=1536`; re-ingest every collection. |

The OpenAI key lives only in `secrets/llm_api_key.txt`; it is mounted into
the app container and read at startup. It is also used for hosted embeddings
and ignored by the local llama.cpp servers. Every visitor question, the
retrieved website text, and up to `PAGE_MAX_CHARS` of the visitor's current
page are sent to OpenAI with the default configuration.

## First-time preparation

```bash
git clone https://github.com/Xan9999/ChatHelper.git /srv/chathelper/app
cd /srv/chathelper/app
bash scripts/deploy.sh prepare
```

`prepare` creates:

- `.env.production` from the committed safe template;
- a random PostgreSQL administrator password in `secrets/postgres_password.txt`;
- a separate random app-login password in `secrets/app_db_password.txt`;
- a random QA login token in `secrets/qa_token.txt`;
- an empty `secrets/llm_api_key.txt` for the OpenAI API key;
- a private `backups/` directory.

It does not start or deploy anything. Paste the OpenAI key (one line, no
quotes) and edit the configuration:

```bash
printf '%s' 'sk-...' > secrets/llm_api_key.txt
nano .env.production
```

At minimum, verify `CHAT_DOMAIN`, `ACME_EMAIL`, `LLM_MODEL`,
`COMPOSE_PROFILES`, `MODELS_DIR` and `EMBED_MODEL_FILE`, `EMBED_DIM`, and
`ALLOWED_ORIGINS`. `ALLOWED_ORIGINS` contains the websites embedding the
widget, not the ChatHelper backend domain.

Keep `.env.production`, `secrets/`, `backups/`, and model files outside Git.
Back up the four secret files separately in an encrypted password manager or
offline secret store. Rotating the OpenAI key is safe at any time: replace the
file's contents and run `bash scripts/deploy.sh restart`.
Do not replace the administrator-password file after PostgreSQL has initialized:
the on-disk database password does not change when the file changes. Rotate
database passwords with an explicit SQL change and coordinated container
restart, or restore into a new stack.

## Validate without deploying

```bash
cd /srv/chathelper/app
bash scripts/deploy.sh validate
```

This checks the required files and runs `docker compose config --quiet`. It
does not create containers.

## Start the production stack

Once you are ready to deploy:

```bash
bash scripts/deploy.sh up
bash scripts/deploy.sh status
bash scripts/deploy.sh logs app
```

The first startup creates the PostgreSQL schema and the default Qdrant
collection. Caddy waits for ChatHelper's `/ready` check before proxying.
Certificate issuance requires working public DNS and inbound ports 80/443.

Verify:

```bash
curl -fsS https://srv.tallweb.eu/health
curl -fsS https://srv.tallweb.eu/ready
```

`/health` is process liveness. `/ready` verifies PostgreSQL, Qdrant, the chat
API, and the embedding endpoint.

## Ingest website content

```bash
bash scripts/deploy.sh ingest https://tallweb.net \
  --collection tallweb \
  --site-name Tallweb \
  --max-pages 200
```

Ingestion uses the same private Qdrant and embedding containers as the running
app and can run while the app is serving. Re-running the same command
overwrites the chunks of re-crawled pages in place (chunk ids are derived
from page URL and position). To also drop pages that no longer exist on the
site, add `--replace`: the collection is recreated only after the crawl has
completed successfully, so a failed crawl never empties a live collection.
Visitors asking during the few seconds of the swap get answers without
website context rather than an error.

Only collections created by `ingest` are served. A widget `client_id` that
names a non-existent collection receives HTTP 404 and is not logged.

## QA review

Read the generated login token on the VPS only when needed:

```bash
sudo cat secrets/qa_token.txt
```

Open `https://srv.tallweb.eu/qa/login` and submit that token. ChatHelper
stores only a derived, HttpOnly, Secure session cookie for eight hours. The
secret is sent in a POST body rather than a URL, keeping it out of access logs
and browser history.

Conversation text is user-provided personal data. Restrict access, establish a
retention policy, and comply with the privacy rules applicable to the sites
using the widget. Enforce the retention period with:

```bash
bash scripts/deploy.sh prune --days 90
```

which deletes conversations (and their messages) that started more than the
given number of days ago. A root crontab line such as

```cron
15 4 * * * cd /srv/chathelper/app && bash scripts/deploy.sh prune --days 90 >> /var/log/chathelper-prune.log 2>&1
```

runs it nightly. Take a backup before the first run if you are unsure about
the period.

## Concurrency

`APP_WORKERS` controls independent Uvicorn processes. Each owns a PostgreSQL
pool of at most `DB_POOL_MAX_SIZE`, so the maximum possible database
connections are approximately:

```text
APP_WORKERS × DB_POOL_MAX_SIZE
```

With the default hosted chat API, the number of answers generating at once is
bounded by your OpenAI rate limits and each worker's thread pool, not by a
local GPU. With the `local-llm` profile, `LLM_SLOTS` controls concurrent
generations and extra chats wait when all slots are occupied; keep `LLM_CTX`
near `LLM_SLOTS × 4096`, subject to GPU memory. Start with two app workers,
then load-test and observe CPU, RAM, latency, database pool waits, and API
errors or model queueing before increasing them.

## Backups

Run:

```bash
bash scripts/deploy.sh backup
```

This creates a timestamped directory under `backups/` containing:

- a PostgreSQL custom-format dump;
- a downloaded snapshot of every Qdrant collection;
- SHA-256 checksums.

No existing backup is deleted. Copy each completed backup off the VPS. A
backup stored only on the same disk is not disaster recovery. Downloaded
Qdrant snapshots are removed from Qdrant after each successful download so
temporary server-side copies do not consume storage indefinitely. If cleanup
fails, the command warns and retains the downloaded backup.

Test restores on a separate disposable stack. Do not discover that backups
are unusable during an incident. PostgreSQL dumps can be inspected with
`pg_restore --list`; Qdrant snapshots are restored through Qdrant's snapshot
recovery API. Restoration overwrites or replaces data and is deliberately not
automated by the deployment script.

## Safe upgrades

```bash
bash scripts/deploy.sh update
```

The update action validates configuration, creates a database backup, performs
a fast-forward-only Git pull, pulls pinned service images, rebuilds the app,
and reconciles the stack. Review release notes and update the pinned versions
in `.env.production` intentionally; avoid floating `latest` tags.

Stopping containers without deleting data:

```bash
bash scripts/deploy.sh down
```

Never add `--volumes` to `docker compose down` unless you deliberately intend
to destroy PostgreSQL, Qdrant, and Caddy certificate state.

## Path B — existing hosting server without Docker (the current production)

`srv.tallweb.eu` is an AlmaLinux 8 **DirectAdmin** server running inside an
LXC container: Apache already owns ports 80/443, and the container's read-only
cgroup and `/sys` mounts make Docker unusable. Production therefore runs
natively. Chat **and** embeddings come from the OpenAI API
(`text-embedding-3-large`, 3072-d), so no model files or GPU are involved;
collections were re-ingested on the server in that schema.

| Component | How it runs | Where |
|---|---|---|
| App (Uvicorn, 2 workers, `127.0.0.1:8000`) | systemd `chathelper.service`, user `chathelper` | code `/srv/chathelper/app`, venv `/srv/chathelper/venv`, config `/srv/chathelper/app/.env` |
| PostgreSQL 16 | AppStream module, systemd `postgresql`, scram auth on loopback | `/var/lib/pgsql/data`, db `chathelper`, role `chathelper_app` |
| Qdrant 1.19 | static binary, systemd `qdrant.service`, user `qdrant`, loopback only | `/opt/qdrant/qdrant`, data `/srv/chathelper/qdrant` |
| Public HTTPS | Apache vhosts for the hostname, DirectAdmin's Let's Encrypt certificate | `/etc/httpd/conf/extra/chathelper.conf`, included from `httpd-includes.conf` |
| Secrets (0600, owner `chathelper`) | plain files referenced via `*_FILE` | `/srv/chathelper/secrets/{llm_api_key,app_db_password,qa_token}.txt` |

Install or re-apply everything except Apache with
[scripts/install-native.sh](scripts/install-native.sh) (idempotent, run as
root). The Apache vhost is [deploy/native/apache-chathelper.conf](deploy/native/apache-chathelper.conf);
install it with:

```bash
cp deploy/native/apache-chathelper.conf /etc/httpd/conf/extra/chathelper.conf
grep -q chathelper.conf /etc/httpd/conf/extra/httpd-includes.conf \
  || echo "Include conf/extra/chathelper.conf" >> /etc/httpd/conf/extra/httpd-includes.conf
httpd -t && systemctl reload httpd
```

The vhost keeps `/.well-known/acme-challenge/` on disk so DirectAdmin's
hostname-certificate renewal keeps working, disables the global DEFLATE filter
for `/chat` so the event stream is not buffered, and caps request bodies at
1 MB. CSF already allows 80/443; the app, PostgreSQL and Qdrant listen on
loopback only.

Day-to-day operations (as root):

```bash
systemctl status chathelper qdrant postgresql
journalctl -u chathelper -n 100 -f
curl -fsS https://srv.tallweb.eu/ready

# ingest / refresh a site. /usr/local/bin/chathelper (installed by
# install-native.sh) switches to the app user, enters the app directory and
# uses the venv; use tmux for large crawls.
chathelper ingest https://www.ricambiribi.com --collection ricambiribi --site-name "Ricambi Ribi" --max-pages 500

# update to the latest commit
cd /srv/chathelper/app && git pull --ff-only && /srv/chathelper/venv/bin/pip install -q -e . && systemctl restart chathelper

# backup (PostgreSQL dump + Qdrant snapshots, keeps the newest 14) and retention
bash /srv/chathelper/app/scripts/backup-native.sh
chathelper prune --days 90
```

Suggested root crontab:

```cron
15 3 * * * bash /srv/chathelper/app/scripts/backup-native.sh >> /srv/chathelper/logs/backup.log 2>&1
15 4 * * * runuser -u chathelper -- bash -c 'cd /srv/chathelper/app && /srv/chathelper/venv/bin/chathelper prune --days 90' >> /srv/chathelper/logs/prune.log 2>&1
```

The QA token is `cat /srv/chathelper/secrets/qa_token.txt`; sign in at
`https://srv.tallweb.eu/qa/login`. Rotate the OpenAI key by replacing the
contents of `llm_api_key.txt` and running `systemctl restart chathelper`.

## Reverse-proxy and CDN notes

If Cloudflare is added later, it sits before Caddy:

```text
Visitor → Cloudflare → Caddy → ChatHelper
```

Caddy should remain the TLS endpoint on the VPS. ChatHelper includes a basic
per-worker request guard, but a distributed rate limit is still best applied
at the CDN or firewall. Configure Cloudflare's SSL mode to validate the origin
certificate, and restrict origin firewall traffic only after confirming ACME
renewal and trusted-proxy handling. The standard Caddy image in this stack
does not claim to provide an application rate-limit plugin.
