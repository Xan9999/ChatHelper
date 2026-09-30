"""Command-line interface: `chathelper <ingest|serve|init>`.

Designed so ONE install serves MANY websites — give each site its own
collection with --collection and point the widget at the right server.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

_ENV_TEMPLATE = """\
# ChatHelper configuration. All values are optional (sane defaults shown).

# Chat + embedding endpoints (any OpenAI-compatible server: llama.cpp, Ollama, ...)
LLM_BASE_URL=http://127.0.0.1:8080/v1
EMBED_BASE_URL=http://127.0.0.1:8081/v1
# Must match the embedding model: bge-m3 = 1024 (recommended, no prefixes);
# nomic-embed-text = 768 with EMBED_DOC_PREFIX="search_document: " and
# EMBED_QUERY_PREFIX="search_query: ".
EMBED_DIM=1024
EMBED_DOC_PREFIX=
EMBED_QUERY_PREFIX=

# Vector store: empty QDRANT_URL = embedded local folder; else a Qdrant server URL
QDRANT_URL=
QDRANT_API_KEY=
QDRANT_COLLECTION=default

# PostgreSQL conversation logging (required by `serve`)
DATABASE_URL=postgresql://chathelper:change-me@127.0.0.1:5432/chathelper
QA_TOKEN=
QA_COOKIE_SECURE=0

# Identity + retrieval tuning
SITE_NAME=this website
TOP_K=3
CHUNK_SIZE=800
CRAWL_MAX_PAGES=50
"""


def _cmd_init(_args: argparse.Namespace) -> None:
    path = Path(".env")
    if path.exists():
        print(".env already exists — not overwriting.")
        return
    path.write_text(_ENV_TEMPLATE, encoding="utf-8")
    print(f"Wrote {path.resolve()}. Edit it, then run `chathelper ingest <url>`.")


def _cmd_ingest(args: argparse.Namespace) -> None:
    if args.collection:
        os.environ["QDRANT_COLLECTION"] = args.collection
    if args.max_pages is not None:
        os.environ["CRAWL_MAX_PAGES"] = str(args.max_pages)
    if args.all_domains:
        os.environ["CRAWL_SAME_DOMAIN"] = "0"
    if args.render:
        os.environ["CRAWL_RENDER"] = "1"
    if args.site_name:
        os.environ["SITE_NAME"] = args.site_name
    # Import AFTER setting env so config picks up the overrides.
    from chathelper.ingest import crawl_and_ingest
    crawl_and_ingest(args.url, replace=args.replace)


def _cmd_prune(args: argparse.Namespace) -> None:
    from chathelper import qa
    deleted = qa.prune_conversations(args.days)
    print(f"Deleted {deleted} conversation(s) older than {args.days} days "
          "(their messages were removed with them).")


def _cmd_serve(args: argparse.Namespace) -> None:
    if args.collection:
        os.environ["QDRANT_COLLECTION"] = args.collection
    if args.site_name:
        os.environ["SITE_NAME"] = args.site_name
    # HTTPS: needed whenever the widget is embedded on an https:// site
    # (browsers block plain-http scripts on https pages, and a TLS request
    # hitting a plain-HTTP server logs "Invalid HTTP request received").
    certfile = args.ssl_certfile or os.getenv("SSL_CERTFILE") or None
    keyfile = args.ssl_keyfile or os.getenv("SSL_KEYFILE") or None
    import uvicorn
    uvicorn.run("chathelper.main:app", host=args.host, port=args.port,
                ssl_certfile=certfile, ssl_keyfile=keyfile)


def main() -> None:
    p = argparse.ArgumentParser(
        prog="chathelper",
        description="Website RAG chatbot with durable conversation logging.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest", help="Crawl a website and embed it into a collection.")
    pi.add_argument("url", help="Start URL, e.g. https://example.com")
    pi.add_argument("--collection", help="Knowledge-base name (one per site).")
    pi.add_argument("--max-pages", type=int, help="Max pages to crawl.")
    pi.add_argument("--all-domains", action="store_true", help="Follow links off the start domain.")
    pi.add_argument("--render", action="store_true",
                    help="Render pages with a headless browser (runs JavaScript) to "
                         "capture dynamic/SPA content. Needs the [render] extra.")
    pi.add_argument("--site-name", help="Human name of the site (used in answers).")
    pi.add_argument("--replace", action="store_true",
                    help="Drop and recreate the collection before storing, so a full "
                         "re-crawl leaves no stale chunks. Only happens after a "
                         "successful crawl.")
    pi.set_defaults(func=_cmd_ingest)

    ps = sub.add_parser("serve", help="Run the chatbot API and widget script.")
    ps.add_argument("--collection", help="Which knowledge base to answer from.")
    ps.add_argument("--site-name", help="Human name of the site (used in answers).")
    ps.add_argument("--host", default="127.0.0.1")
    ps.add_argument("--port", type=int, default=8000)
    ps.add_argument("--ssl-certfile", help="PEM certificate chain — serve HTTPS (or env SSL_CERTFILE).")
    ps.add_argument("--ssl-keyfile", help="PEM private key — serve HTTPS (or env SSL_KEYFILE).")
    ps.set_defaults(func=_cmd_serve)

    pn = sub.add_parser("init", help="Write a starter .env in the current folder.")
    pn.set_defaults(func=_cmd_init)

    pp = sub.add_parser("prune", help="Delete logged conversations older than N days "
                                      "(data-retention policy).")
    pp.add_argument("--days", type=int, required=True,
                    help="Delete conversations that started more than this many days ago.")
    pp.set_defaults(func=_cmd_prune)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
