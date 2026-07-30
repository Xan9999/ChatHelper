"""Conversation logging + a private QA review website.

Every /chat turn is recorded in a small SQLite database (CONVERSATIONS_DB,
one file under DATA_DIR): the client's message, the agent's full streamed
reply, per-reply latency, and conversation metadata (site, collection, the
page the visitor was on, timestamps). A conversation's duration is the time
between its first and last message; the widget groups turns with a random
conversation id it generates per chat session.

Review site (private): set QA_TOKEN in .env, then open
    /qa?token=<QA_TOKEN>                    all conversations, every site
    /qa/<collection>?token=<QA_TOKEN>       one site only, e.g. /qa/alemo
    /qa/<conversation-id>?token=<QA_TOKEN>  a single transcript
for the human-readable transcript (Client: ... / Agent: ...), or download it
as plain text. With QA_TOKEN empty the /qa routes are disabled (secure by
default) — logging itself still happens.
"""
from __future__ import annotations

import hmac
import html
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from website_ai_helper import config

router = APIRouter()


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------

def _conn() -> sqlite3.Connection:
    config.ensure_data_dir()
    con = sqlite3.connect(config.CONVERSATIONS_DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")  # tolerate several serve processes
    return con


def init_db() -> None:
    con = _conn()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id          TEXT PRIMARY KEY,
            collection  TEXT,
            site_name   TEXT,
            page_url    TEXT,
            page_title  TEXT,
            started_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL REFERENCES conversations(id),
            role            TEXT NOT NULL,      -- 'client' | 'agent'
            content         TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            latency_ms      INTEGER,            -- agent messages only
            error           TEXT                -- set if the reply failed
        );
        CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);
        """
    )
    con.commit()
    con.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_client_message(conversation_id: str, content: str,
                       page_url: str = "", page_title: str = "",
                       collection: str | None = None) -> None:
    con = _conn()
    con.execute(
        """INSERT OR IGNORE INTO conversations
           (id, collection, site_name, page_url, page_title, started_at)
           VALUES (?,?,?,?,?,?)""",
        (conversation_id, collection or config.QDRANT_COLLECTION, config.SITE_NAME,
         page_url, page_title, _now()),
    )
    con.execute(
        "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?,?,?,?)",
        (conversation_id, "client", content, _now()),
    )
    con.commit()
    con.close()


def log_agent_message(conversation_id: str, content: str,
                      latency_ms: int, error: str | None = None) -> None:
    con = _conn()
    con.execute(
        """INSERT INTO messages (conversation_id, role, content, created_at, latency_ms, error)
           VALUES (?,?,?,?,?,?)""",
        (conversation_id, "agent", content, _now(), latency_ms, error),
    )
    con.commit()
    con.close()


# --------------------------------------------------------------------------
# Private QA review site
# --------------------------------------------------------------------------

def _require_token(request: Request) -> str:
    """Return the valid token, or raise. Disabled entirely when unconfigured."""
    if not config.QA_TOKEN:
        raise HTTPException(
            status_code=403,
            detail="QA review site is disabled. Set QA_TOKEN in .env to enable it.",
        )
    supplied = request.query_params.get("token", "")
    if not hmac.compare_digest(supplied, config.QA_TOKEN):
        raise HTTPException(status_code=401, detail="Missing or invalid ?token=")
    return supplied


def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


def _conversation_rows(collection: str | None = None) -> list[sqlite3.Row]:
    con = _conn()
    where = "WHERE c.collection = ?" if collection is not None else ""
    params = (collection,) if collection is not None else ()
    rows = con.execute(
        f"""SELECT c.id, c.collection, c.site_name, c.page_url, c.started_at,
                  COUNT(m.id)                          AS n_messages,
                  MIN(m.created_at)                    AS first_at,
                  MAX(m.created_at)                    AS last_at,
                  (SELECT content FROM messages
                    WHERE conversation_id = c.id AND role = 'client'
                    ORDER BY id LIMIT 1)               AS first_message,
                  SUM(CASE WHEN m.error IS NOT NULL THEN 1 ELSE 0 END) AS n_errors
             FROM conversations c
             JOIN messages m ON m.conversation_id = c.id
             {where}
            GROUP BY c.id
            ORDER BY last_at DESC""",
        params,
    ).fetchall()
    con.close()
    return rows


def _distinct_collections() -> list[str]:
    con = _conn()
    rows = con.execute(
        "SELECT DISTINCT collection FROM conversations ORDER BY collection"
    ).fetchall()
    con.close()
    return [r["collection"] for r in rows if r["collection"]]


def _duration_of(row: sqlite3.Row) -> float:
    try:
        first = datetime.fromisoformat(row["first_at"])
        last = datetime.fromisoformat(row["last_at"])
        return (last - first).total_seconds()
    except (TypeError, ValueError):
        return 0.0


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


def _sites_nav(token: str, current: str | None = None) -> str:
    """'Sites:' link strip to jump between per-collection QA pages."""
    collections = _distinct_collections()
    if not collections:
        return ""
    links = []
    for c in collections:
        label = html.escape(config.site_name_for(c))
        if c == current:
            links.append(f"<strong>{label}</strong>")
        else:
            links.append(f"<a href='/qa/{c}?token={token}'>{label}</a>")
    return f"<p class='meta'>Sites: {' · '.join(links)}</p>"


def _rows_table_html(rows: list[sqlite3.Row], token: str, show_collection: bool) -> str:
    if not rows:
        return "<p class='meta'>No conversations yet.</p>"
    cols = "<th>Site / collection</th>" if show_collection else ""
    parts = [f"<table><tr><th>Started</th>{cols}<th>Msgs</th>"
             "<th>Duration</th><th>First message</th><th></th></tr>"]
    for r in rows:
        err = " <span class='err'>⚠ errors</span>" if r["n_errors"] else ""
        preview = html.escape((r["first_message"] or "")[:90])
        site_col = (f"<td>{html.escape(r['site_name'] or '')} / "
                    f"{html.escape(r['collection'] or '')}</td>") if show_collection else ""
        parts.append(
            f"<tr><td>{html.escape(r['started_at'] or '')}</td>{site_col}"
            f"<td>{r['n_messages']}</td>"
            f"<td>{_fmt_duration(_duration_of(r))}{err}</td>"
            f"<td>{preview}</td>"
            f"<td><a href='/qa/{r['id']}?token={token}'>view</a> · "
            f"<a href='/qa/{r['id']}/transcript.txt?token={token}'>txt</a></td></tr>"
        )
    parts.append("</table>")
    return "".join(parts)


@router.get("/qa", response_class=HTMLResponse)
def qa_list(request: Request) -> HTMLResponse:
    token = _require_token(request)
    rows = _conversation_rows()
    body = [
        f"<style>{_PAGE_CSS}</style><h1>Conversations ({len(rows)})</h1>",
        "<p class='meta'>All times UTC. Duration = first to last message.</p>",
        _sites_nav(token),
        _rows_table_html(rows, token, show_collection=True),
    ]
    return HTMLResponse("".join(body))


def _collection_page(collection: str, token: str) -> HTMLResponse:
    rows = _conversation_rows(collection=collection)
    site = html.escape(config.site_name_for(collection))
    body = [
        f"<style>{_PAGE_CSS}</style>",
        f"<p><a href='/qa?token={token}'>&larr; all conversations</a></p>",
        f"<h1>{site} — {html.escape(collection)} ({len(rows)})</h1>",
        "<p class='meta'>All times UTC. Duration = first to last message.</p>",
        _sites_nav(token, current=collection),
        _rows_table_html(rows, token, show_collection=False),
    ]
    return HTMLResponse("".join(body))


def _load_conversation(cid: str) -> tuple[sqlite3.Row, list[sqlite3.Row]]:
    con = _conn()
    conv = con.execute("SELECT * FROM conversations WHERE id = ?", (cid,)).fetchone()
    msgs = con.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (cid,)
    ).fetchall()
    con.close()
    if conv is None:
        raise HTTPException(status_code=404, detail="No such conversation")
    return conv, msgs


@router.get("/qa/{key}", response_class=HTMLResponse)
def qa_detail_or_collection(key: str, request: Request) -> HTMLResponse:
    """`key` is either a conversation id (-> single transcript) or a
    collection name (-> that site's conversation list, e.g. /qa/alemo).
    Conversation ids are checked first; any other value is treated as a
    collection filter (an unknown/empty one just renders "no conversations
    yet" rather than a 404, since a collection that exists in Qdrant but has
    no chats yet is a perfectly normal state)."""
    token = _require_token(request)
    try:
        conv, msgs = _load_conversation(key)
    except HTTPException:
        return _collection_page(key, token)
    cid = key
    dur = 0.0
    if len(msgs) >= 2:
        dur = (datetime.fromisoformat(msgs[-1]["created_at"])
               - datetime.fromisoformat(msgs[0]["created_at"])).total_seconds()
    body = [
        f"<style>{_PAGE_CSS}</style>",
        f"<p><a href='/qa?token={token}'>&larr; all conversations</a></p>",
        f"<h1>Conversation {html.escape(cid[:8])}…</h1>",
        "<p class='meta'>"
        f"Site: {html.escape(conv['site_name'] or '')} / {html.escape(conv['collection'] or '')}<br>"
        f"Started: {html.escape(conv['started_at'] or '')} UTC &nbsp;·&nbsp; "
        f"Duration: {_fmt_duration(dur)} &nbsp;·&nbsp; Messages: {len(msgs)}<br>"
        f"Visitor page: {html.escape(conv['page_url'] or '(none)')}"
        "</p>",
    ]
    for m in msgs:
        who = "Client" if m["role"] == "client" else "Agent"
        lat = (f"<span class='lat'>{m['latency_ms']} ms</span>"
               if m["latency_ms"] is not None else "")
        err = (f"<div class='err'>error: {html.escape(m['error'])}</div>"
               if m["error"] else "")
        body.append(
            f"<div class='turn {m['role']}'><span class='who'>{who}:</span>{lat}"
            f"<br>{html.escape(m['content'])}{err}</div>"
        )
    return HTMLResponse("".join(body))


@router.get("/qa/{cid}/transcript.txt", response_class=PlainTextResponse)
def qa_transcript_txt(cid: str, request: Request) -> PlainTextResponse:
    _require_token(request)
    conv, msgs = _load_conversation(cid)
    dur = 0.0
    if len(msgs) >= 2:
        dur = (datetime.fromisoformat(msgs[-1]["created_at"])
               - datetime.fromisoformat(msgs[0]["created_at"])).total_seconds()
    lines = [
        f"Conversation: {cid}",
        f"Site: {conv['site_name']} / {conv['collection']}",
        f"Visitor page: {conv['page_url'] or '(none)'}",
        f"Started: {conv['started_at']} UTC",
        f"Duration: {_fmt_duration(dur)}",
        f"Messages: {len(msgs)}",
        "-" * 60,
    ]
    for m in msgs:
        who = "Client" if m["role"] == "client" else "Agent"
        lines.append(f"{who}: {m['content']}")
        if m["error"]:
            lines.append(f"  [error: {m['error']}]")
        lines.append("")
    return PlainTextResponse("\n".join(lines))
