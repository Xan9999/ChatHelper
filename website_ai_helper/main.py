"""FastAPI backend: streaming /chat endpoint, the demo widget, and the
private /qa conversation-review site (see qa.py)."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse

from website_ai_helper import config, qa, structured, vectorstore
from website_ai_helper.agent import run_chat

app = FastAPI(title="Website-AI-helper")

# Allow the widget to POST from your site's domain. Set ALLOWED_ORIGINS in
# .env to a comma-separated list before going live; empty = allow any origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(qa.router)

WIDGET = Path(__file__).resolve().parent / "web" / "widget.html"
WIDGET_JS = Path(__file__).resolve().parent / "web" / "widget.js"


@app.on_event("startup")
def _startup() -> None:
    config.ensure_data_dir()
    structured.init_demo_db()
    qa.init_db()
    vectorstore.ensure_collection(vectorstore.get_client())


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WIDGET)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "collection": config.QDRANT_COLLECTION}


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
async def chat(request: Request) -> StreamingResponse:
    body = await request.json()
    message = (body.get("message") or "").strip()
    history = body.get("history") or []
    current_page = body.get("current_page") or {}
    # client_id doubles as the Qdrant collection name — one per site (see the
    # existing --collection ingest convention). Empty/absent = this install's
    # default single-tenant collection (QDRANT_COLLECTION in .env).
    collection = (body.get("client_id") or "").strip() or None
    # The widget generates one id per chat session so turns group into a
    # conversation; direct API callers without one get a fresh id per turn.
    conversation_id = (body.get("conversation_id") or "").strip() or str(uuid.uuid4())

    t0 = time.time()
    try:  # QA logging must never break the chat itself
        qa.log_client_message(conversation_id, message,
                              current_page.get("url", ""), current_page.get("title", ""),
                              collection)
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
            error = str(exc)
            yield f"data: {json.dumps({'type': 'error', 'message': error})}\n\n"
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
