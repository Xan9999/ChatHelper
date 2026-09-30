# ChatHelper

ChatHelper is a website chat assistant that crawls public pages, indexes them
in Qdrant, and answers questions using an OpenAI-compatible chat model. The
widget also sends the visitor's current page as context. PostgreSQL stores
conversation logs for the private QA review page. There is no product, order,
or live-commerce database integration.

The supported production deployment is a Linux VPS with Docker Compose. See
[DEPLOYMENT.md](DEPLOYMENT.md) for the step-by-step VPS guide, host prerequisites,
secrets, backups, upgrades, and recovery. Nothing in this repository has been
deployed to a server for you.

## Architecture

```text
visitor's browser → Caddy (public HTTPS) → ChatHelper / Uvicorn
                                           ├─ Qdrant (website knowledge)
                                           ├─ PostgreSQL (conversation logs)
                                           ├─ llama.cpp chat server
                                           └─ llama.cpp embedding server
```

Only Caddy publishes host ports (80 and 443). The app and its data/model
services are private to Docker networks. Caddy handles TLS certificates,
security headers, request-size limits, and streaming proxying; it is the
reverse proxy in front of the FastAPI app, not a replacement for FastAPI.
PostgreSQL and Qdrant have separate persistent Docker volumes, so rebuilding
or replacing the app container does not erase either database. Back up both
volumes' *contents* regularly; a volume by itself is not a backup.

Two Uvicorn workers are configured by default. Each worker has a PostgreSQL
connection pool; `APP_WORKERS × DB_POOL_MAX_SIZE` is the approximate maximum
connection count. `LLM_SLOTS` independently limits simultaneous model
generations. More HTTP workers cannot make a GPU model generate more answers
than its available slots.

## Install from Git for local development

Requirements: Python 3.10+, PostgreSQL, an OpenAI-compatible chat endpoint,
an embedding endpoint, and Qdrant (either a server or embedded mode for a
single-process local test). The production stack supplies all of these.

```bash
git clone https://github.com/Xan9999/ChatHelper.git
cd ChatHelper
./setup.sh                 # macOS/Linux
# or: .\setup.ps1          # Windows PowerShell
```

The CLI command, the pip package, and the Python import package are all named
`chathelper`.

For a local run, create `.env` with `chathelper init`, then set at least:

```dotenv
DATABASE_URL=postgresql://chathelper:YOUR_PASSWORD@127.0.0.1:5432/chathelper
LLM_BASE_URL=http://127.0.0.1:8080/v1
EMBED_BASE_URL=http://127.0.0.1:8081/v1
QDRANT_URL=http://127.0.0.1:6333
EMBED_DIM=1024
ALLOWED_ORIGINS=http://localhost:3000
QA_TOKEN=YOUR_LONG_RANDOM_TOKEN
QA_COOKIE_SECURE=0
```

Create the PostgreSQL database and user named in the URL before serving. Set
`EMBED_DIM` to the actual embedding model dimension and adjust the endpoint
URLs to your running services. See [.env.example](.env.example) for the other
settings. If you leave `QDRANT_URL` empty, local embedded Qdrant works only
with one process and cannot be used by ingestion and serving concurrently.

```bash
chathelper ingest https://example.com --collection example
chathelper serve --collection example
curl http://127.0.0.1:8000/health
```

`/` returns service metadata, not a preview page. `/health` confirms the
process is responding. `/ready` checks PostgreSQL, Qdrant, and both model
endpoints. The old preview and product/order examples were removed.

## Prepare a Linux VPS deployment

The provided Compose stack assumes an NVIDIA GPU, a driver and NVIDIA
Container Toolkit on the VPS, and two GGUF model files. It does not run
Passenger, SQLite, or a second public web server. If the VPS is CPU-only or
uses a hosted model API, adapt the model services before deployment.

```bash
git clone https://github.com/Xan9999/ChatHelper.git /srv/chathelper/app
cd /srv/chathelper/app
bash scripts/deploy.sh prepare    # creates private config and random secrets
# edit .env.production and place GGUF files in MODELS_DIR
bash scripts/deploy.sh validate   # checks inputs and Compose without starting
bash scripts/deploy.sh up         # starts only when you decide to deploy
```

`prepare` generates `.env.production` from
[.env.production.example](.env.production.example), plus separate PostgreSQL
administrator, limited app-login, and QA secret files. These are excluded from
Git and the image build. Review
the domain, email, absolute `MODELS_DIR`, model filenames, embedding dimension,
and `ALLOWED_ORIGINS` before running `up`. The domain must point to the VPS;
ports 80 and 443 must be reachable for automatic TLS. Do not publish 5432,
6333, 8000, 8080, or 8081.

On Windows, Docker Desktop with the WSL 2 backend can validate/build this
Linux stack locally, but production deployment remains Linux. WSL 2 requires
firmware virtualization and Windows features to be enabled. Use the Docker
installer's `--wsl-default-data-root` option or its Resources settings to put
container data on D: if you need that on a Windows test machine.

## Index a site and embed the widget

After the production stack is healthy:

```bash
bash scripts/deploy.sh ingest https://tallweb.net \
  --collection tallweb --site-name Tallweb --max-pages 200
```

The collection name is the public widget `client_id`. Put this snippet in the
site's footer, replacing the hostname and collection as needed:

```html
<script>
!function(d,u,i,l,p,a){
  var s=d.createElement("script"); s.async=1;
  s.src=u+"?client_id="+encodeURIComponent(i)+"&language="+encodeURIComponent(l)
    +(p?"&position="+encodeURIComponent(p):"")
    +(a?"&accent="+encodeURIComponent(a):"");
  var h=d.getElementsByTagName("script")[0]; h.parentNode.insertBefore(s,h);
}(document,"https://chat.tallweb.net/widget.js","tallweb","en");
</script>
```

`language` changes widget labels (`en`, `it`, `sl`); the assistant responds in
the visitor's question language. Optional `position` (`left`/`right`) and
`accent` (hex color) customize the appearance. Per-collection CSS and UI text
can also be committed under `widget_styles/<client_id>.css` and
`widget_strings/<client_id>.json`. Set `ALLOWED_ORIGINS` to the exact origins
hosting the widget, e.g. `https://tallweb.net,https://www.tallweb.net`.

The `client_id` is a selector, not an authentication mechanism: collections
should contain only content safe for public visitors. A `client_id` that does
not name an existing collection is rejected with HTTP 404; visitors cannot
create collections. Crawled prices and availability can become stale;
re-ingest after significant site changes.

Re-ingesting is safe to repeat: each chunk's Qdrant id is derived from its
page URL and position, so a re-crawled page overwrites its own chunks instead
of duplicating them. Pages that disappeared from the site keep their old
chunks until you do a full refresh, which drops and recreates the collection
only after the new crawl has succeeded:

```bash
bash scripts/deploy.sh ingest https://tallweb.net --collection tallweb --replace
```

Collections created by versions before hybrid retrieval (dense-only) are still
served, but `--replace` is also the way to upgrade them to the current schema.

## PostgreSQL and QA review

The app creates two PostgreSQL tables at startup:

| Table | Used for |
|---|---|
| `conversations` | One UUID per chat session, collection/site, visitor page, and start time. |
| `messages` | Ordered client/agent turns, timestamps, reply latency, and internal errors. |

Both tables are used only for logging and `/qa`, not for answering product or
order questions. Qdrant holds the crawled website knowledge used for answers.
PostgreSQL connection pooling and transaction-safe schema initialization allow
multiple app workers to share the same durable database.
The Compose stack creates a dedicated non-superuser `chathelper_app` role;
the app container never receives PostgreSQL's administrator password.
Existing local SQLite conversation files are left untouched and are not
automatically imported into PostgreSQL.

Open `https://chat.tallweb.net/qa/login` and enter the generated QA token to
review conversations. Login uses a short-lived, signed, HttpOnly, Secure
cookie; the token is never placed in a URL. If `QA_TOKEN` is empty, the review
page is disabled but logging continues. Chat text may contain personal data:
restrict access and define a retention policy.

## Operations and safety

```bash
bash scripts/deploy.sh status
bash scripts/deploy.sh logs app
bash scripts/deploy.sh backup
bash scripts/deploy.sh prune --days 90
bash scripts/deploy.sh update
bash scripts/deploy.sh down
```

`backup` produces a PostgreSQL custom-format dump and downloaded Qdrant
snapshots with SHA-256 checksums. Copy completed backups off the VPS and test
restores on a separate instance. `prune` deletes logged conversations older
than the given number of days (chat logs are personal data; pick a retention
period and run this from cron). `update` backs up first, then performs a
fast-forward-only Git pull and rebuild. `down` preserves persistent volumes;
do not add `--volumes` unless you intentionally want to destroy data.

The app bounds message length and history, rejects injected system roles,
applies basic per-worker request limits, times out stuck model calls, and does
not return internal errors to visitors. For a public high-traffic site, also
use edge/CDN rate limiting and monitor model queueing, disk, RAM/VRAM, and
database pool usage. The model can still make mistakes; review answers before
relying on them.

If the chat model is a hosted API (`LLM_BASE_URL=https://api.openai.com/v1`),
every visitor question, the retrieved site text, and up to `PAGE_MAX_CHARS`
of the page the visitor is viewing are sent to that provider. State this in
the site's privacy notice, or keep the model local.

## Running the tests

```bash
pip install -e ".[dev]"
python -m unittest discover -s tests
```

The tests need no running services: model, Qdrant, and PostgreSQL calls are
stubbed, and the Compose file is checked statically.
