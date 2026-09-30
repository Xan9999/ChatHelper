"""Configuration, loaded from environment / a local .env file.

Everything that varies per deployment lives here. Two ideas make this reusable
across many websites:

  * DATA_DIR is resolved relative to your current working directory, so each
    project folder gets its own embedded-Qdrant development data.
  * QDRANT_COLLECTION names the knowledge base. Give each website its own
    collection (via the --collection CLI flag or the env var) and one install
    can serve many sites.

The LLM and embedding endpoints are just OpenAI-compatible URLs, so this works
with llama.cpp, Ollama, or any compatible server — local or remote.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # read .env from the current working directory, if present


def _get(key: str, default: str) -> str:
    return os.getenv(key, default)


def _secret(key: str, default: str = "") -> str:
    """Read KEY, or KEY_FILE for a mounted Docker/Kubernetes secret."""
    file_path = os.getenv(f"{key}_FILE")
    if file_path:
        return Path(file_path).read_text(encoding="utf-8").strip()
    return os.getenv(key, default)


# Where a local install writes embedded-Qdrant data. Production uses a Qdrant
# service and PostgreSQL, so the application container itself stays stateless.
DATA_DIR = Path(_get("DATA_DIR", "data")).resolve()

# --- LLM (chat) endpoint — any OpenAI-compatible server ---
LLM_BASE_URL = _get("LLM_BASE_URL", "http://127.0.0.1:8080/v1")
LLM_API_KEY = _get("LLM_API_KEY", "sk-local")   # llama.cpp ignores the value
LLM_MODEL = _get("LLM_MODEL", "local-chat")
# Extra JSON fields merged into every chat completion request body. Defaults
# to disabling Qwen3's hybrid "thinking" mode (see agent.py), which is only
# understood by llama.cpp/vLLM-style servers. Hosted APIs like OpenAI's real
# api.openai.com reject unrecognized body fields, so set this to "{}" there.
LLM_EXTRA_BODY = json.loads(_get(
    "LLM_EXTRA_BODY", '{"chat_template_kwargs": {"enable_thinking": false}}'
))
# Seconds before a chat/embedding HTTP call is abandoned (connect + read gap
# between streamed tokens). A stuck model server must not hold a worker
# thread for the SDK's 10-minute default.
LLM_TIMEOUT = float(_get("LLM_TIMEOUT", "120"))
EMBED_TIMEOUT = float(_get("EMBED_TIMEOUT", "60"))

# --- Embedding endpoint ---
EMBED_BASE_URL = _get("EMBED_BASE_URL", "http://127.0.0.1:8081/v1")
EMBED_API_KEY = _get("EMBED_API_KEY", "sk-local")
EMBED_MODEL = _get("EMBED_MODEL", "local-embed")
# Defaults match the recommended bge-m3 model (1024-d, no task prefixes).
# nomic-embed-text is 768-d and needs "search_document: " / "search_query: ".
EMBED_DIM = int(_get("EMBED_DIM", "1024"))      # must match your embedding model
EMBED_DOC_PREFIX = _get("EMBED_DOC_PREFIX", "")
EMBED_QUERY_PREFIX = _get("EMBED_QUERY_PREFIX", "")

# --- Vector store (Qdrant) ---
# Empty QDRANT_URL -> embedded local folder (no server). Set it to use a server.
QDRANT_URL = _get("QDRANT_URL", "")
QDRANT_API_KEY = _secret("QDRANT_API_KEY")
QDRANT_PATH = _get("QDRANT_PATH", str(DATA_DIR / "qdrant"))
QDRANT_COLLECTION = _get("QDRANT_COLLECTION", "default")  # one per website

# --- PostgreSQL conversation/QA database ---
# DATABASE_URL is convenient outside Docker. In production, the POSTGRES_*
# values allow the password to come from a mounted secret file instead.
DATABASE_URL = _secret("DATABASE_URL")
POSTGRES_HOST = _get("POSTGRES_HOST", "127.0.0.1")
POSTGRES_PORT = int(_get("POSTGRES_PORT", "5432"))
POSTGRES_DB = _get("POSTGRES_DB", "chathelper")
POSTGRES_USER = _get("POSTGRES_USER", "chathelper")
POSTGRES_PASSWORD = _secret("POSTGRES_PASSWORD")
DB_POOL_MIN_SIZE = int(_get("DB_POOL_MIN_SIZE", "1"))
DB_POOL_MAX_SIZE = int(_get("DB_POOL_MAX_SIZE", "5"))
DB_POOL_TIMEOUT = float(_get("DB_POOL_TIMEOUT", "10"))
if DB_POOL_MIN_SIZE < 0 or DB_POOL_MAX_SIZE < max(1, DB_POOL_MIN_SIZE):
    raise ValueError("DB_POOL_MIN_SIZE/DB_POOL_MAX_SIZE define an invalid pool size")

# --- Retrieval / generation ---
TOP_K = int(_get("TOP_K", "3"))
CHUNK_SIZE = int(_get("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(_get("CHUNK_OVERLAP", "160"))
# Minimum retrieval score to keep a chunk. Only meaningful for LEGACY
# (dense-only) collections, where scores are cosine similarities; hybrid
# collections return rank-fusion scores on a different scale (~0.01-0.03),
# so leave this at 0 for them.
SCORE_THRESHOLD = float(_get("SCORE_THRESHOLD", "0.0"))
TEMPERATURE = float(_get("TEMPERATURE", "0.2"))
# Penalize repeated tokens — the main lever against degenerate loops (e.g. a
# model repeating the same sentence, sometimes drifting into another language
# mid-repeat). 0 = off; llama.cpp/OpenAI-compatible servers accept 0-2.
FREQUENCY_PENALTY = float(_get("FREQUENCY_PENALTY", "0.4"))
PRESENCE_PENALTY = float(_get("PRESENCE_PENALTY", "0.4"))
# Hard cap on answer length — bounds how far a runaway/looping generation can
# go before it's cut off, regardless of what caused it.
MAX_TOKENS = int(_get("MAX_TOKENS", "500"))
# Max characters of the visitor's current page injected into the prompt.
# Bigger = better "this page" answers but slower time-to-first-token (every
# ~4 chars is a prompt token the GPU must process before answering).
PAGE_MAX_CHARS = int(_get("PAGE_MAX_CHARS", "1500"))
# Rewrite follow-up messages into standalone search queries before retrieval
# (resolves 'how much does IT cost?' using the conversation). Costs one small
# extra LLM call per follow-up turn; first messages are never rewritten.
QUERY_REWRITE = _get("QUERY_REWRITE", "1") == "1"
CHAT_MAX_MESSAGE_CHARS = int(_get("CHAT_MAX_MESSAGE_CHARS", "4000"))
CHAT_HISTORY_MAX_ITEMS = int(_get("CHAT_HISTORY_MAX_ITEMS", "12"))
CHAT_RATE_LIMIT_PER_MINUTE = int(_get("CHAT_RATE_LIMIT_PER_MINUTE", "30"))
QA_LOGIN_RATE_LIMIT_PER_MINUTE = int(_get("QA_LOGIN_RATE_LIMIT_PER_MINUTE", "10"))
if CHAT_MAX_MESSAGE_CHARS < 1 or min(
    CHAT_HISTORY_MAX_ITEMS,
    CHAT_RATE_LIMIT_PER_MINUTE,
    QA_LOGIN_RATE_LIMIT_PER_MINUTE,
) < 0:
    raise ValueError("Chat message limit must be positive; other limits cannot be negative")
SITE_NAME = _get("SITE_NAME", "this website")
# Per-collection site names for multi-tenant serving, e.g.
#   SITE_NAMES=acme=Acme Shop,adr=Adrlandia
# The agent introduces itself as "assistant for <name>". Collections without
# an entry fall back to SITE_NAME.
_SITE_NAMES: dict[str, str] = {}
for _pair in _get("SITE_NAMES", "").split(","):
    if "=" in _pair:
        _k, _v = _pair.split("=", 1)
        if _k.strip() and _v.strip():
            _SITE_NAMES[_k.strip()] = _v.strip()


def site_name_for(collection: str | None) -> str:
    """Site name for a request's collection (None = the default collection)."""
    return _SITE_NAMES.get(collection or QDRANT_COLLECTION, SITE_NAME)


# Per-collection answer STYLE/tone guidance, appended to the system prompt,
# e.g.:
#   SITE_STYLES=acme=Rispondi in tono diretto e professionale, senza emoji.|adr=Tono cordiale e informale, puoi usare qualche emoji.
# Entries are separated by "|" (not ",") because a style instruction is free
# text and commonly contains commas itself, unlike the short SITE_NAMES
# values above. Collections without an entry get no extra guidance — the
# base SYSTEM_PROMPT alone still applies.
_SITE_STYLES: dict[str, str] = {}
for _pair in _get("SITE_STYLES", "").split("|"):
    if "=" in _pair:
        _k, _v = _pair.split("=", 1)
        if _k.strip() and _v.strip():
            _SITE_STYLES[_k.strip()] = _v.strip()


def site_style_for(collection: str | None) -> str:
    """Extra answer-style/tone instruction for a request's collection, or ''
    if none is configured."""
    return _SITE_STYLES.get(collection or QDRANT_COLLECTION, "")


# Directory of per-collection widget CSS overrides (full, arbitrary CSS —
# fonts, spacing, animations, dark mode, anything — not limited to the
# accent/position widget.js params). Served at GET /widget.css?client_id=...
# One file per collection: <WIDGET_STYLES_DIR>/<collection>.css. A collection
# with no file just gets no extra rules — the base widget look is unchanged.
WIDGET_STYLES_DIR = Path(_get("WIDGET_STYLES_DIR", "widget_styles")).resolve()
_COLLECTION_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def widget_style_path(collection: str | None) -> Path | None:
    """Path to a collection's CSS override file, or None if the name is
    invalid/unsafe or no such file exists. Validates against a strict
    allowlist BEFORE touching the filesystem — collection comes from a
    client-supplied query param, so this also guards against path traversal
    (e.g. '../../etc/passwd') rather than relying on Path resolution alone."""
    name = collection or QDRANT_COLLECTION
    if not _COLLECTION_NAME_RE.match(name):
        return None
    path = WIDGET_STYLES_DIR / f"{name}.css"
    return path if path.is_file() else None


# Directory of per-collection widget UI TEXT overrides (title, subtitle,
# placeholder, send-button label, unreachable-error message — any subset).
# Served at GET /widget-strings.json?client_id=... and merged client-side
# over the language-based defaults in widget.js. One file per collection:
# <WIDGET_STRINGS_DIR>/<collection>.json. A collection with no file just
# keeps the plain language defaults — nothing to configure for sites that
# don't need custom wording.
WIDGET_STRINGS_DIR = Path(_get("WIDGET_STRINGS_DIR", "widget_strings")).resolve()


def widget_strings_for(collection: str | None) -> dict:
    """Text-override dict for a collection (any subset of title/subtitle/
    placeholder/send/unreachable), or {} if none configured / the file is
    missing / invalid JSON. Same filename-safety allowlist as widget_style_path."""
    name = collection or QDRANT_COLLECTION
    if not _COLLECTION_NAME_RE.match(name):
        return {}
    path = WIDGET_STRINGS_DIR / f"{name}.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}

# --- CORS ---
# Comma-separated list of origins allowed to call /chat from a browser, e.g.
# "https://acme.com,https://www.acme.com". Empty (default) = allow any origin,
# fine for local testing but should be locked down before going live.
ALLOWED_ORIGINS = [o.strip() for o in _get("ALLOWED_ORIGINS", "").split(",") if o.strip()]

# --- Conversation logging + QA review site ---
# Every chat turn is logged to PostgreSQL. The review UI is disabled when
# QA_TOKEN is empty, while logging remains enabled.
QA_TOKEN = _secret("QA_TOKEN")
QA_COOKIE_SECURE = _get("QA_COOKIE_SECURE", "1") == "1"
# Interactive OpenAPI docs at /docs. Off by default: a public chat backend
# has no reason to advertise its route list. Set ENABLE_DOCS=1 locally.
ENABLE_DOCS = _get("ENABLE_DOCS", "0") == "1"

# --- Crawler ---
CRAWL_MAX_PAGES = int(_get("CRAWL_MAX_PAGES", "50"))
CRAWL_SAME_DOMAIN = _get("CRAWL_SAME_DOMAIN", "1") == "1"
# Also download linked PDF files (same-domain rule applies) and ingest their
# text. Detected by the .pdf URL extension. Set to 0 to skip PDFs entirely.
CRAWL_PDFS = _get("CRAWL_PDFS", "1") == "1"
CRAWL_PDF_MAX_MB = int(_get("CRAWL_PDF_MAX_MB", "20"))  # skip PDFs larger than this
# Skip HTML documents larger than this (a runaway page or a mislabelled
# download must not be pulled fully into memory).
CRAWL_MAX_PAGE_MB = int(_get("CRAWL_MAX_PAGE_MB", "5"))
# Render pages with a headless browser (runs JavaScript) so dynamically
# generated / single-page-app content is captured. Needs the optional
# Playwright dependency. Slower per page, but crawling only happens at ingest.
CRAWL_RENDER = _get("CRAWL_RENDER", "0") == "1"
# Strip lines repeated across many crawled pages (cookie banners, nav menus,
# footers) before chunking/embedding — see ingest.strip_boilerplate(). A line
# is boilerplate when it appears on >= BOILERPLATE_MIN_PAGES pages AND on
# >= BOILERPLATE_PAGE_FRACTION of all pages.
BOILERPLATE_STRIP = _get("BOILERPLATE_STRIP", "1") == "1"
BOILERPLATE_MIN_PAGES = int(_get("BOILERPLATE_MIN_PAGES", "4"))
BOILERPLATE_PAGE_FRACTION = float(_get("BOILERPLATE_PAGE_FRACTION", "0.3"))
CRAWL_RENDER_WAIT_MS = int(_get("CRAWL_RENDER_WAIT_MS", "5000"))  # network-idle wait per page


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
