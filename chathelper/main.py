"""FastAPI backend: streaming /chat endpoint, the widget, and the
private /qa conversation-review site (see qa.py)."""
from __future__ import annotations

from collections import deque
from contextlib import asynccontextmanager
import json
import re
import time
import uuid
from pathlib import Path

import requests as http_requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from starlette.concurrency import run_in_threadpool

from chathelper import config, qa, vectorstore
from chathelper.agent import run_chat


def _startup() -> None:
    config.ensure_data_dir()
    qa.init_db()
    vectorstore.ensure_collection(vectorstore.get_client())


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _startup()
    try:
        yield
    finally:
        qa.close_db()


app = FastAPI(
    title="ChatHelper",
    lifespan=_lifespan,
    docs_url="/docs" if config.ENABLE_DOCS else None,
    redoc_url=None,
    openapi_url="/openapi.json" if config.ENABLE_DOCS else None,
)

app.include_router(qa.router)

WIDGET_JS = Path(__file__).resolve().parent / "web" / "widget.js"
_COLLECTION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_RATE_HITS: dict[tuple[str, str], deque[float]] = {}
_LAST_RATE_CLEANUP = 0.0


def _rate_limited(bucket: str, client: str, limit: int) -> bool:
    """Small per-worker abuse guard; production edge limits can be stricter."""
    global _LAST_RATE_CLEANUP
    if limit == 0:
        return False
    now = time.monotonic()
    cutoff = now - 60
    key = (bucket, client)
    hits = _RATE_HITS.setdefault(key, deque())
    while hits and hits[0] <= cutoff:
        hits.popleft()
    if len(hits) >= limit:
        return True
    hits.append(now)
    if now - _LAST_RATE_CLEANUP >= 60:
        stale = [
            old_key
            for old_key, values in _RATE_HITS.items()
            if not values or values[-1] <= cutoff
        ]
        for old_key in stale:
            _RATE_HITS.pop(old_key, None)
        _LAST_RATE_CLEANUP = now
    return False


@app.middleware("http")
async def request_limits(request: Request, call_next):
    if request.method == "POST":
        if request.url.path == "/chat":
            bucket, limit = "chat", config.CHAT_RATE_LIMIT_PER_MINUTE
        elif request.url.path == "/qa/login":
            bucket, limit = "qa-login", config.QA_LOGIN_RATE_LIMIT_PER_MINUTE
        else:
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        if _rate_limited(bucket, client, limit):
            return JSONResponse(
                {"detail": "Too many requests; try again shortly."},
                status_code=429,
                headers={"Retry-After": "60"},
            )
    return await call_next(request)


def _clean_history(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or config.CHAT_HISTORY_MAX_ITEMS == 0:
        return []
    cleaned: list[dict[str, str]] = []
    for item in value[-config.CHAT_HISTORY_MAX_ITEMS:]:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            continue
        content = item.get("content")
        if isinstance(content, str):
            cleaned.append(
                {
                    "role": item["role"],
                    "content": content[: config.CHAT_MAX_MESSAGE_CHARS],
                }
            )
    return cleaned


def _clean_current_page(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    url = value.get("url")
    title = value.get("title")
    page_text = value.get("text")
    return {
        "url": url[:2048] if isinstance(url, str) else "",
        "title": title[:512] if isinstance(title, str) else "",
        "text": page_text[: config.PAGE_MAX_CHARS] if isinstance(page_text, str) else "",
    }


# Add CORS last so it wraps the rate-limit middleware as well; browser clients
# then receive readable 429 responses. Empty origins are for local testing only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS or ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/")
def index(request: Request) -> Response:
    # An embed snippet that points at the bare host instead of /widget.js is a
    # common copy-paste slip; the browser then refuses JSON as a script. Send
    # such requests to the widget, keeping client_id/language in the query.
    # document.currentScript.src still holds the original URL, so the widget
    # reads its parameters exactly as if /widget.js had been used directly.
    if "client_id" in request.query_params:
        return RedirectResponse(f"/widget.js?{request.url.query}", status_code=302)
    return JSONResponse(
        {
            "service": "ChatHelper",
            "status": "ok",
            "widget": "/widget.js",
            "health": "/health",
        }
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _check_model_endpoint(base_url: str, api_key: str) -> None:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    response = http_requests.get(
        f"{base_url.rstrip('/')}/models",
        headers=headers,
        timeout=5,
    )
    response.raise_for_status()


@app.get("/ready")
def ready() -> dict:
    """Readiness check used by Docker and the reverse proxy."""
    qa.check_db()
    vectorstore.get_client().get_collections()
    _check_model_endpoint(config.LLM_BASE_URL, config.LLM_API_KEY)
    _check_model_endpoint(config.EMBED_BASE_URL, config.EMBED_API_KEY)
    return {"status": "ready"}


@app.get("/widget.js")
def widget_js() -> FileResponse:
    # Loaded via a single <script src="/widget.js?client_id=...&language=...">
    # snippet — it reads its own query string client-side, so this file is
    # static and safely cacheable across every client site.
    return FileResponse(
        WIDGET_JS, media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=300"},
    )


@app.get("/widget.css")
def widget_css(request: Request) -> PlainTextResponse:
    # Per-collection CSS override, e.g. <script src=".../widget.js?client_id=X">
    # pairs with a GET .../widget.css?client_id=X the widget links to right
    # after its own base styles — full arbitrary CSS, not limited to the
    # accent/position widget.js params. A collection with no override file
    # just gets an empty (but valid, cacheable) stylesheet: zero behavior
    # change from before this endpoint existed.
    collection = (request.query_params.get("client_id") or "").strip() or None
    path = config.widget_style_path(collection)
    css = path.read_text(encoding="utf-8") if path else ""
    return PlainTextResponse(
        css, media_type="text/css",
        headers={"Cache-Control": "public, max-age=60"},
    )


@app.get("/widget-strings.json")
def widget_strings(request: Request) -> JSONResponse:
    # Per-collection UI text override (title/subtitle/placeholder/send/
    # unreachable — any subset), merged client-side over the language
    # defaults in widget.js. A collection with no override file just gets
    # {}, i.e. no change from plain language-based defaults.
    collection = (request.query_params.get("client_id") or "").strip() or None
    overrides = config.widget_strings_for(collection)
    return JSONResponse(overrides, headers={"Cache-Control": "public, max-age=60"})


@app.post("/chat")
async def chat(request: Request) -> Response:
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        return JSONResponse({"detail": "Request body must be JSON."}, status_code=400)
    if not isinstance(body, dict) or not isinstance(body.get("message"), str):
        return JSONResponse({"detail": "message must be a string."}, status_code=422)
    message = body["message"].strip()
    if not message:
        return JSONResponse({"detail": "message cannot be empty."}, status_code=422)
    if len(message) > config.CHAT_MAX_MESSAGE_CHARS:
        return JSONResponse({"detail": "message is too long."}, status_code=413)
    history = _clean_history(body.get("history"))
    current_page = _clean_current_page(body.get("current_page"))
    # client_id doubles as the Qdrant collection name — one per site (see the
    # existing --collection ingest convention). Empty/absent = this install's
    # default single-tenant collection (QDRANT_COLLECTION in .env).
    raw_collection = body.get("client_id")
    if raw_collection is not None and not isinstance(raw_collection, str):
        return JSONResponse({"detail": "client_id must be a string."}, status_code=422)
    collection = (raw_collection or "").strip() or None
    if collection and not _COLLECTION_RE.fullmatch(collection):
        return JSONResponse({"detail": "Invalid client_id."}, status_code=422)
    if collection:
        # Only collections created by `chathelper ingest` are served. A
        # made-up client_id must neither create a collection nor be logged.
        try:
            known = await run_in_threadpool(
                vectorstore.collection_known, vectorstore.get_client(), collection
            )
        except Exception:
            known = True  # Qdrant trouble surfaces as a chat error below, not a 404
        if not known:
            return JSONResponse({"detail": "Unknown client_id."}, status_code=404)
    # The widget generates one id per chat session so turns group into a
    # conversation; direct API callers without one get a fresh id per turn.
    raw_id = body.get("conversation_id")
    raw_conversation_id = raw_id.strip() if isinstance(raw_id, str) else ""
    try:
        conversation_id = str(uuid.UUID(raw_conversation_id))
    except (ValueError, AttributeError):
        conversation_id = str(uuid.uuid4())

    t0 = time.time()
    try:  # QA logging must never break the chat itself
        await run_in_threadpool(
            qa.log_client_message,
            conversation_id,
            message,
            current_page.get("url", ""),
            current_page.get("title", ""),
            collection,
        )
    except Exception:
        pass

    def event_stream():
        answer_parts: list[str] = []
        error: str | None = None
        try:
            for event in run_chat(message, history, current_page, collection):
                if event.get("type") == "token":
                    answer_parts.append(event["text"])
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            error = str(exc)[:2000]
            public_message = "The assistant is temporarily unavailable."
            yield f"data: {json.dumps({'type': 'error', 'message': public_message})}\n\n"
        finally:  # runs even if the client disconnects mid-stream
            try:
                qa.log_agent_message(conversation_id, "".join(answer_parts),
                                     int((time.time() - t0) * 1000), error)
            except Exception:
                pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
