"""PostgreSQL conversation logging and the private QA review website."""
from __future__ import annotations

import hmac
import html
import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from chathelper import config

router = APIRouter()
Row = dict[str, Any]
_pool: ConnectionPool | None = None
_NO_STORE = {"Cache-Control": "no-store"}
_SESSION_SECONDS = 8 * 60 * 60
_PAGE_SIZE = 100  # conversations per QA list page


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is not None:
        return _pool

    connection_kwargs: dict[str, Any] = {"row_factory": dict_row}
    conninfo = config.DATABASE_URL
    if not conninfo:
        if not config.POSTGRES_PASSWORD:
            raise RuntimeError(
                "PostgreSQL is not configured: set DATABASE_URL, "
                "POSTGRES_PASSWORD, or POSTGRES_PASSWORD_FILE"
            )
        connection_kwargs.update(
            host=config.POSTGRES_HOST,
            port=config.POSTGRES_PORT,
            dbname=config.POSTGRES_DB,
            user=config.POSTGRES_USER,
            password=config.POSTGRES_PASSWORD,
        )

    _pool = ConnectionPool(
        conninfo=conninfo,
        kwargs=connection_kwargs,
        min_size=config.DB_POOL_MIN_SIZE,
        max_size=config.DB_POOL_MAX_SIZE,
        timeout=config.DB_POOL_TIMEOUT,
        open=False,
        name="chathelper-qa",
    )
    _pool.open(wait=True)
    return _pool


def init_db() -> None:
    """Create the logging schema safely when several workers start together."""
    with _get_pool().connection() as con:
        con.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("chathelper_schema_v1",))
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id          UUID PRIMARY KEY,
                collection  TEXT NOT NULL,
                site_name   TEXT NOT NULL,
                page_url    TEXT NOT NULL DEFAULT '',
                page_title  TEXT NOT NULL DEFAULT '',
                started_at  TIMESTAMPTZ NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                conversation_id UUID NOT NULL
                    REFERENCES conversations(id) ON DELETE CASCADE,
                role            TEXT NOT NULL CHECK (role IN ('client', 'agent')),
                content         TEXT NOT NULL,
                created_at      TIMESTAMPTZ NOT NULL,
                latency_ms      INTEGER,
                error           TEXT
            )
            """
        )
        con.execute(
            """CREATE INDEX IF NOT EXISTS idx_messages_conversation
               ON messages (conversation_id, id)"""
        )
        con.execute(
            """CREATE INDEX IF NOT EXISTS idx_conversations_collection_started
               ON conversations (collection, started_at DESC)"""
        )


def close_db() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def check_db() -> None:
    with _get_pool().connection() as con:
        con.execute("SELECT 1").fetchone()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def log_client_message(
    conversation_id: str,
    content: str,
    page_url: str = "",
    page_title: str = "",
    collection: str | None = None,
) -> None:
    cid = uuid.UUID(conversation_id)
    collection_name = collection or config.QDRANT_COLLECTION
    with _get_pool().connection() as con:
        con.execute(
            """INSERT INTO conversations
               (id, collection, site_name, page_url, page_title, started_at)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO NOTHING""",
            (
                cid,
                collection_name,
                config.site_name_for(collection_name),
                page_url,
                page_title,
                _now(),
            ),
        )
        con.execute(
            """INSERT INTO messages
               (conversation_id, role, content, created_at)
               VALUES (%s, %s, %s, %s)""",
            (cid, "client", content, _now()),
        )


def log_agent_message(
    conversation_id: str,
    content: str,
    latency_ms: int,
    error: str | None = None,
) -> None:
    with _get_pool().connection() as con:
        con.execute(
            """INSERT INTO messages
               (conversation_id, role, content, created_at, latency_ms, error)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (uuid.UUID(conversation_id), "agent", content, _now(), latency_ms, error),
        )


def prune_conversations(older_than_days: int) -> int:
    """Delete conversations that started more than `older_than_days` days
    ago; their messages go with them (ON DELETE CASCADE). Chat logs are
    personal data, so retention must be bounded — `chathelper prune --days N`
    runs this, typically from cron."""
    if older_than_days < 1:
        raise ValueError("older_than_days must be at least 1")
    with _get_pool().connection() as con:
        cursor = con.execute(
            "DELETE FROM conversations WHERE started_at < now() - make_interval(days => %s)",
            (older_than_days,),
        )
        return cursor.rowcount


def _session_value(expires_at: int) -> str:
    signature = hmac.new(
        config.QA_TOKEN.encode("utf-8"),
        f"chathelper-qa-session-v1:{expires_at}".encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"{expires_at}.{signature}"


def _require_token(request: Request) -> None:
    if not config.QA_TOKEN:
        raise HTTPException(
            status_code=403,
            detail="QA review site is disabled. Set QA_TOKEN to enable it.",
        )
    supplied = request.cookies.get("chathelper_qa", "")
    try:
        expires_text, supplied_signature = supplied.split(".", 1)
        expires_at = int(expires_text)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Sign in at /qa/login")
    expected_signature = _session_value(expires_at).split(".", 1)[1]
    if expires_at < int(time.time()) or not hmac.compare_digest(
        supplied_signature, expected_signature
    ):
        raise HTTPException(status_code=401, detail="Sign in at /qa/login")


def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


def _conversation_rows(collection: str | None = None, page: int = 1) -> list[Row]:
    """One page of conversation summaries, newest activity first. Paged so
    the QA site stays fast after months of logging instead of rendering
    every conversation ever recorded on one page."""
    where = "WHERE c.collection = %s" if collection is not None else ""
    params: tuple = (collection,) if collection is not None else ()
    params += (_PAGE_SIZE, (max(1, page) - 1) * _PAGE_SIZE)
    with _get_pool().connection() as con:
        rows = con.execute(
            f"""SELECT c.id, c.collection, c.site_name, c.page_url, c.started_at,
                       COUNT(m.id) AS n_messages,
                       MIN(m.created_at) AS first_at,
                       MAX(m.created_at) AS last_at,
                       (SELECT content FROM messages
                         WHERE conversation_id = c.id AND role = 'client'
                         ORDER BY id LIMIT 1) AS first_message,
                       SUM(CASE WHEN m.error IS NOT NULL THEN 1 ELSE 0 END) AS n_errors
                  FROM conversations c
                  JOIN messages m ON m.conversation_id = c.id
                  {where}
                 GROUP BY c.id
                 ORDER BY last_at DESC
                 LIMIT %s OFFSET %s""",
            params,
        ).fetchall()
    return list(rows)


def _conversation_count(collection: str | None = None) -> int:
    where = "WHERE collection = %s" if collection is not None else ""
    params = (collection,) if collection is not None else ()
    with _get_pool().connection() as con:
        row = con.execute(
            f"SELECT COUNT(*) AS n FROM conversations {where}", params
        ).fetchone()
    return int(row["n"]) if row else 0


def _page_arg(request: Request) -> int:
    try:
        return max(1, int(request.query_params.get("page", "1")))
    except ValueError:
        return 1


def _pager_html(base: str, page: int, n_rows: int) -> str:
    """Newer/older links. `base` is a server-built path, never user input."""
    links = []
    if page > 1:
        links.append(f"<a href='{base}?page={page - 1}'>&larr; newer</a>")
    if n_rows >= _PAGE_SIZE:
        links.append(f"<a href='{base}?page={page + 1}'>older &rarr;</a>")
    if not links:
        return ""
    return f"<p class='meta'>Page {page} &nbsp;·&nbsp; {' · '.join(links)}</p>"


def _distinct_collections() -> list[str]:
    with _get_pool().connection() as con:
        rows = con.execute(
            "SELECT DISTINCT collection FROM conversations ORDER BY collection"
        ).fetchall()
    return [row["collection"] for row in rows if row["collection"]]


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _duration_of(row: Row) -> float:
    try:
        return (_as_datetime(row["last_at"]) - _as_datetime(row["first_at"])).total_seconds()
    except (TypeError, ValueError):
        return 0.0


def _fmt_timestamp(value: Any) -> str:
    try:
        return _as_datetime(value).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return str(value or "")


_PAGE_CSS = """
body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
       margin: 0 auto; max-width: 880px; padding: 24px; color: #1a1a2e; }
h1 { font-size: 22px; } a { color: #3b5bdb; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #e5e7eb;
         vertical-align: top; }
th { background: #f7f8fa; } tr:hover td { background: #fafbff; }
.meta { color: #6b7280; font-size: 13px; margin-bottom: 18px; }
.err { color: #b91c1c; font-weight: 600; }
.turn { margin: 14px 0; padding: 10px 14px; border-radius: 10px; white-space: pre-wrap; }
.client { background: #eef1ff; } .agent { background: #f4f4f5; }
.who { font-weight: 700; margin-right: 6px; }
.lat { color: #6b7280; font-size: 12px; margin-left: 8px; }
"""


def _sites_nav(current: str | None = None) -> str:
    collections = _distinct_collections()
    if not collections:
        return ""
    links = []
    for collection in collections:
        label = html.escape(config.site_name_for(collection))
        if collection == current:
            links.append(f"<strong>{label}</strong>")
        else:
            key = quote(collection, safe="")
            links.append(f"<a href='/qa/{key}'>{label}</a>")
    return f"<p class='meta'>Sites: {' · '.join(links)}</p>"


def _rows_table_html(rows: list[Row], show_collection: bool) -> str:
    if not rows:
        return "<p class='meta'>No conversations yet.</p>"
    cols = "<th>Site / collection</th>" if show_collection else ""
    parts = [
        f"<table><tr><th>Started</th>{cols}<th>Msgs</th>"
        "<th>Duration</th><th>First message</th><th></th></tr>"
    ]
    for row in rows:
        warning = " <span class='err'>⚠ errors</span>" if row["n_errors"] else ""
        preview = html.escape((row["first_message"] or "")[:90])
        site_col = (
            f"<td>{html.escape(row['site_name'] or '')} / "
            f"{html.escape(row['collection'] or '')}</td>"
            if show_collection
            else ""
        )
        cid = str(row["id"])
        parts.append(
            f"<tr><td>{html.escape(_fmt_timestamp(row['started_at']))}</td>{site_col}"
            f"<td>{row['n_messages']}</td>"
            f"<td>{_fmt_duration(_duration_of(row))}{warning}</td>"
            f"<td>{preview}</td>"
            f"<td><a href='/qa/{cid}'>view</a> · "
            f"<a href='/qa/{cid}/transcript.txt'>txt</a></td></tr>"
        )
    parts.append("</table>")
    return "".join(parts)


@router.get("/qa/login", response_class=HTMLResponse)
def qa_login() -> HTMLResponse:
    if not config.QA_TOKEN:
        raise HTTPException(status_code=403, detail="QA review site is disabled.")
    return HTMLResponse(
        f"<style>{_PAGE_CSS}</style><h1>ChatHelper QA</h1>"
        "<form method='post' action='/qa/login'>"
        "<label>QA token<br><input type='password' name='token' required "
        "autocomplete='current-password'></label> "
        "<button type='submit'>Sign in</button></form>",
        headers=_NO_STORE,
    )


@router.post("/qa/login")
async def qa_login_submit(request: Request) -> RedirectResponse:
    if not config.QA_TOKEN:
        raise HTTPException(status_code=403, detail="QA review site is disabled.")
    form = parse_qs((await request.body()).decode("utf-8", errors="replace"))
    supplied = (form.get("token") or [""])[0]
    if not hmac.compare_digest(supplied, config.QA_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid QA token")
    expires_at = int(time.time()) + _SESSION_SECONDS
    response = RedirectResponse("/qa", status_code=303, headers=_NO_STORE)
    response.set_cookie(
        "chathelper_qa",
        _session_value(expires_at),
        httponly=True,
        secure=config.QA_COOKIE_SECURE,
        samesite="strict",
        max_age=_SESSION_SECONDS,
        path="/qa",
    )
    return response


@router.post("/qa/logout")
def qa_logout() -> RedirectResponse:
    response = RedirectResponse("/qa/login", status_code=303, headers=_NO_STORE)
    response.delete_cookie("chathelper_qa", path="/qa")
    return response


@router.get("/qa", response_class=HTMLResponse)
def qa_list(request: Request) -> HTMLResponse:
    _require_token(request)
    page = _page_arg(request)
    rows = _conversation_rows(page=page)
    return HTMLResponse(
        "".join(
            [
                f"<style>{_PAGE_CSS}</style><h1>Conversations ({_conversation_count()})</h1>",
                "<p class='meta'>All times UTC. Duration = first to last message.</p>",
                "<form method='post' action='/qa/logout'><button>Sign out</button></form>",
                _sites_nav(),
                _rows_table_html(rows, show_collection=True),
                _pager_html("/qa", page, len(rows)),
            ]
        ),
        headers=_NO_STORE,
    )


def _collection_page(collection: str, page: int = 1) -> HTMLResponse:
    rows = _conversation_rows(collection=collection, page=page)
    return HTMLResponse(
        "".join(
            [
                f"<style>{_PAGE_CSS}</style>",
                "<p><a href='/qa'>&larr; all conversations</a></p>",
                f"<h1>{html.escape(config.site_name_for(collection))} — "
                f"{html.escape(collection)} ({_conversation_count(collection)})</h1>",
                "<p class='meta'>All times UTC. Duration = first to last message.</p>",
                _sites_nav(current=collection),
                _rows_table_html(rows, show_collection=False),
                _pager_html(f"/qa/{quote(collection, safe='')}", page, len(rows)),
            ]
        ),
        headers=_NO_STORE,
    )


def _load_conversation(cid: str) -> tuple[Row, list[Row]]:
    try:
        conversation_id = uuid.UUID(cid)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="No such conversation") from exc
    with _get_pool().connection() as con:
        conversation = con.execute(
            "SELECT * FROM conversations WHERE id = %s", (conversation_id,)
        ).fetchone()
        messages = con.execute(
            "SELECT * FROM messages WHERE conversation_id = %s ORDER BY id",
            (conversation_id,),
        ).fetchall()
    if conversation is None:
        raise HTTPException(status_code=404, detail="No such conversation")
    return conversation, list(messages)


@router.get("/qa/{key}", response_class=HTMLResponse)
def qa_detail_or_collection(key: str, request: Request) -> HTMLResponse:
    _require_token(request)
    try:
        conversation, messages = _load_conversation(key)
    except HTTPException:
        return _collection_page(key, _page_arg(request))

    duration = 0.0
    if len(messages) >= 2:
        duration = (
            _as_datetime(messages[-1]["created_at"])
            - _as_datetime(messages[0]["created_at"])
        ).total_seconds()
    body = [
        f"<style>{_PAGE_CSS}</style>",
        "<p><a href='/qa'>&larr; all conversations</a></p>",
        f"<h1>Conversation {html.escape(key[:8])}…</h1>",
        "<p class='meta'>"
        f"Site: {html.escape(conversation['site_name'] or '')} / "
        f"{html.escape(conversation['collection'] or '')}<br>"
        f"Started: {html.escape(_fmt_timestamp(conversation['started_at']))} UTC &nbsp;·&nbsp; "
        f"Duration: {_fmt_duration(duration)} &nbsp;·&nbsp; Messages: {len(messages)}<br>"
        f"Visitor page: {html.escape(conversation['page_url'] or '(none)')}"
        "</p>",
    ]
    for message in messages:
        who = "Client" if message["role"] == "client" else "Agent"
        latency = (
            f"<span class='lat'>{message['latency_ms']} ms</span>"
            if message["latency_ms"] is not None
            else ""
        )
        error = (
            f"<div class='err'>error: {html.escape(message['error'])}</div>"
            if message["error"]
            else ""
        )
        body.append(
            f"<div class='turn {message['role']}'><span class='who'>{who}:</span>{latency}"
            f"<br>{html.escape(message['content'])}{error}</div>"
        )
    return HTMLResponse("".join(body), headers=_NO_STORE)


@router.get("/qa/{cid}/transcript.txt", response_class=PlainTextResponse)
def qa_transcript_txt(cid: str, request: Request) -> PlainTextResponse:
    _require_token(request)
    conversation, messages = _load_conversation(cid)
    duration = 0.0
    if len(messages) >= 2:
        duration = (
            _as_datetime(messages[-1]["created_at"])
            - _as_datetime(messages[0]["created_at"])
        ).total_seconds()
    lines = [
        f"Conversation: {cid}",
        f"Site: {conversation['site_name']} / {conversation['collection']}",
        f"Visitor page: {conversation['page_url'] or '(none)'}",
        f"Started: {_fmt_timestamp(conversation['started_at'])} UTC",
        f"Duration: {_fmt_duration(duration)}",
        f"Messages: {len(messages)}",
        "-" * 60,
    ]
    for message in messages:
        who = "Client" if message["role"] == "client" else "Agent"
        lines.append(f"{who}: {message['content']}")
        if message["error"]:
            lines.append(f"  [error: {message['error']}]")
        lines.append("")
    return PlainTextResponse("\n".join(lines), headers=_NO_STORE)
