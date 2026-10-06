# ChatHelper

ChatHelper is a website chat assistant that crawls public pages, indexes them
in Qdrant, and answers questions using an OpenAI-compatible chat model. The
widget also sends the visitor's current page as context. PostgreSQL stores
conversation logs for the private QA review page. There is no product, order,
or live-commerce database integration.

Two deployment paths are documented in [DEPLOYMENT.md](DEPLOYMENT.md): Docker
Compose for a dedicated Linux VPS (Path A), and a native systemd install for an
existing hosting server where Docker is unavailable and Apache already owns
ports 80/443 (Path B, the current production on `srv.tallweb.eu`).

## Architecture

```text
visitor's browser → Caddy (public HTTPS) → ChatHelper / Uvicorn
                                           ├─ Qdrant (website knowledge)
                                           ├─ PostgreSQL (conversation logs)
                                           ├─ chat model: OpenAI API (default)
                                           │             or local llama.cpp on a GPU
                                           └─ embeddings: local llama.cpp on CPU (default)
                                                         or OpenAI API
```

Only Caddy publishes host ports (80 and 443). The app and its data/model
services are private to Docker networks. Caddy handles TLS certificates,
security headers, request-size limits, and streaming proxying; it is the
reverse proxy in front of the FastAPI app, not a replacement for FastAPI.
PostgreSQL and Qdrant have separate persistent Docker volumes, so rebuilding
or replacing the app container does not erase either database. Back up both
volumes' *contents* regularly; a volume by itself is not a backup.

The default production configuration needs no GPU: chat answers come from the
OpenAI API (key in a secret file) and embeddings from a small local llama.cpp
CPU container running bge-m3, so the collections you already ingested keep
working. The local GPU chat model is an optional Compose profile.

Two Uvicorn workers are configured by default. Each worker has a PostgreSQL
connection pool; `APP_WORKERS × DB_POOL_MAX_SIZE` is the approximate maximum
connection count. With the hosted chat API, how many answers generate at once
is bounded by your OpenAI rate limits; with the local model profile it is
`LLM_SLOTS`, and more HTTP workers cannot exceed it.

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

A CPU-only Linux VPS with Docker Engine and Compose v2 is enough for the
default configuration. The stack does not run Passenger, SQLite, or a second
public web server. Model containers are Compose profiles selected with
`COMPOSE_PROFILES` in `.env.production`:

| `COMPOSE_PROFILES` | Chat | Embeddings | Host needs |
|---|---|---|---|
| `local-embed` (default) | OpenAI API | bge-m3 in a CPU llama.cpp container | `bge-m3-Q8_0.gguf` in `MODELS_DIR` |
| `local-embed,local-llm` | local GGUF on a GPU | same | NVIDIA driver, Container Toolkit, chat GGUF |
| empty | OpenAI API | OpenAI `text-embedding-3-small` | nothing local; every site must be re-ingested (1536-d vectors) |

```bash
git clone https://github.com/Xan9999/ChatHelper.git /srv/chathelper/app
cd /srv/chathelper/app
bash scripts/deploy.sh prepare    # creates private config and random secrets
# paste the OpenAI key into secrets/llm_api_key.txt, edit .env.production,
# put bge-m3-Q8_0.gguf into MODELS_DIR
bash scripts/deploy.sh validate   # checks inputs and Compose without starting
bash scripts/deploy.sh up         # starts only when you decide to deploy
```

`prepare` generates `.env.production` from
[.env.production.example](.env.production.example), random PostgreSQL
administrator, limited app-login and QA secret files, and an empty
`secrets/llm_api_key.txt` for the OpenAI key. These are excluded from Git and
the image build. Review the domain, email, `LLM_MODEL`, `COMPOSE_PROFILES`,
absolute `MODELS_DIR` and `EMBED_MODEL_FILE`, `EMBED_DIM`, and
`ALLOWED_ORIGINS` before running `up`. The domain must point to the VPS;
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
}(document,"https://srv.tallweb.eu/widget.js","tallweb","en");
</script>
```

The address must end in `/widget.js`; a bare hostname returns the JSON status
page and the browser refuses to run it as a script. Set `ALLOWED_ORIGINS` to
the exact origins hosting the widget, e.g.
`https://tallweb.net,https://www.tallweb.net`, and restart the app after
changing it. Labels, colours, position, per-site CSS and texts are covered in
[Customizing the widget](#customizing-the-widget).

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

## Customizing the widget

One `widget.js` serves every site. What a visitor sees is decided, in this
order of effort, by the snippet's query parameters, an optional per-site CSS
file, an optional per-site text file, and two `.env` settings that shape the
answers themselves.

### 1. Snippet parameters

The wrapper in the snippet above takes up to six arguments:
`(document, widgetUrl, client_id, language, position, accent)`. They end up as
query parameters on the script URL, which is what the widget actually reads,
so a hand-written `<script src="https://srv.tallweb.eu/widget.js?client_id=tallweb&language=it&position=left&accent=%23f17023">`
works just as well.

| Parameter | Values | Default | Effect |
|---|---|---|---|
| `client_id` | collection name | the server's `QDRANT_COLLECTION` | Which site's knowledge base answers, and which CSS/text overrides load. Unknown names get HTTP 404. |
| `language` | `en`, `it`, `sl` | `en` | Language of the widget's own labels only. The assistant always answers in the language the visitor writes in. |
| `position` | `left`, `right` | `right` | Bottom corner for the button and the panel. |
| `accent` | hex colour `#rgb` to `#rrggbbaa`, URL-encoded (`%23f17023`) | `#3b5bdb` | Header, send button, visitor bubbles and link colour. Malformed values are ignored. |
| `sources` | `1` | off | Shows the "Sources: [1] [2]" links under each answer. A testing aid, hidden for visitors; see [5. The sources line](#5-the-sources-line). |

### 2. Per-site CSS: `widget_styles/<client_id>.css`

For anything beyond a colour and a corner, add a stylesheet named exactly
after the `client_id` (letters, digits, `-`, `_`). The widget links
`GET /widget.css?client_id=<client_id>` right after its own base styles, so
plain rules win the cascade without `!important`. A site without a file gets
an empty stylesheet and the default look.

Every element the widget creates carries the `chathelper-` prefix, so host
page styles never collide with it:

| Hook | What it is |
|---|---|
| `#chathelper-toggle` | the floating round button |
| `#chathelper-panel` | the chat window (`.open` while visible) |
| `.chathelper-hdr` | panel header; the `<small>` inside is the subtitle |
| `.chathelper-msgs` | scrolling message area |
| `.chathelper-msg.user` / `.chathelper-msg.bot` | one message row; `.chathelper-bubble` inside is the bubble |
| `.chathelper-sources` | the "Sources: [1] [2]" line under an answer |
| `.chathelper-composer` | the input row (`input` and `button` inside) |

The base stylesheet defines these custom properties on `:root`; reassigning
them is usually enough:

| Variable | Default | Used for |
|---|---|---|
| `--chathelper-accent` | `#3b5bdb` | header, buttons, visitor bubbles, links |
| `--chathelper-bg` | `#fff` | panel background |
| `--chathelper-fg` | `#1a1a2e` | text colour |
| `--chathelper-muted` | `#6b7280` | sources line |
| `--chathelper-panel` | `#f7f8fa` | message-area background |

Example, the file shipped for one site:

```css
/* widget_styles/ricambiribi.css */
:root { --chathelper-accent: #d4321c; }
#chathelper-panel { border-radius: 4px; }
#chathelper-toggle { background-image: url(https://ricambiribi.com/wp-content/uploads/logo-icon.png);
                     background-size: 60%; background-repeat: no-repeat; background-position: center; }
```

### 3. Per-site texts: `widget_strings/<client_id>.json`

Any subset of five keys, merged over the `language` defaults. Keys you leave
out keep the default for that language. Served at
`GET /widget-strings.json?client_id=<client_id>` and applied as plain text,
never as HTML.

```json
{
  "title": "Ricambi Ribi",
  "subtitle": "Chiedi dei ricambi per il tuo mezzo",
  "placeholder": "Scrivi qui la tua domanda...",
  "send": "Invia",
  "unreachable": "Assistente non raggiungibile al momento."
}
```

`title` and `subtitle` are the header, `placeholder` the empty input,
`send` the button, `unreachable` the message shown when the backend cannot be
reached. These change labels only; the answers are governed by the next point.

### 4. Name and tone of the answers (`.env`)

`SITE_NAMES=ricambiribi=Ricambi Ribi,adr=Adrlandia` tells the assistant whose
site it speaks for (it says "we", never "their website"). `SITE_STYLES`
appends a free-text tone instruction per site, entries separated by `|`
because the text itself may contain commas:

```dotenv
SITE_STYLES=ricambiribi=Tono diretto e professionale, senza emoji.|adr=Tono cordiale, puoi usare qualche emoji.
```

Both live in the server's `.env` (`/srv/chathelper/app/.env` on the native
install, `.env.production` for Compose) and need `systemctl restart chathelper`
(or `deploy.sh restart`) to apply.

### 5. The sources line

Under every answer the backend sends the pages it retrieved, ranked best
first, and the widget can show them as a "Sources: [1] [2] [3]" line of links.
This is a testing aid for checking *why* the assistant answered as it did; it
is hidden from visitors by default and the answer text never contains a
sources list either. Three ways to control it, from broadest to narrowest:

| Scope | How | Notes |
|---|---|---|
| Whole site | add `&sources=1` to the script URL | The six-argument wrapper has no slot for it (it builds the query itself), so use the plain tag form: `<script async src="https://srv.tallweb.eu/widget.js?client_id=tallweb&language=it&sources=1"></script>` |
| One browser, any site | in that site's browser console run `localStorage.setItem("chathelper.sources", "1")`, then reload | Nothing on the client site changes; only that browser shows the links. `"0"` forces them off even where the snippet has `sources=1`. `localStorage.removeItem("chathelper.sources")` goes back to the snippet's setting. |
| Appearance | CSS on `.chathelper-sources` and its `a` elements | Default colour comes from `--chathelper-muted`, links from `--chathelper-accent`. Example: `.chathelper-sources { display: none; }` hides it unconditionally; `.chathelper-sources a { font-weight: 600; }` restyles the numbers. |

The browser setting always wins over the snippet. The sources event is sent
regardless of these switches, so enabling the line never changes what the
model is asked or how it answers. Each link is the crawled page the excerpt
came from; `[1]` is the strongest match. Sources are not stored in the QA
conversation log.

### How changes reach visitors

CSS and JSON files are read on every request, so on the native server they
apply as soon as they are in `/srv/chathelper/app/widget_styles` or
`widget_strings`, normally via commit, push and `git pull`; no restart. Browsers
cache them for 60 seconds and `widget.js` itself for 5 minutes. Check a file is
being served with:

```bash
curl -s "https://srv.tallweb.eu/widget.css?client_id=ricambiribi"
curl -s "https://srv.tallweb.eu/widget-strings.json?client_id=ricambiribi"
```

If a site's own optimizer rewrites or defers scripts (LiteSpeed Cache, WP
Rocket, Autoptimize), exclude `srv.tallweb.eu` from its JavaScript
optimization, or embed a plain tag instead of the wrapper:

```html
<script async data-no-optimize="1" src="https://srv.tallweb.eu/widget.js?client_id=alemo&language=it"></script>
```

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

Open `https://srv.tallweb.eu/qa/login` and enter the generated QA token to
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
