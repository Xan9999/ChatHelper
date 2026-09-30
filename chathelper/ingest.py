"""Ingestion: crawl a website, chunk the text, embed it, store it in Qdrant.

Programmatic entry point is `crawl_and_ingest(url)`. The CLI (`chathelper
ingest <url>`) calls it. To also ingest free text from another database, shape
rows as {"text","url","title"} and pass them to `ingest_pages(...)`.
"""
from __future__ import annotations

import uuid
from collections import deque
from contextlib import contextmanager
from urllib.parse import parse_qsl, urldefrag, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from chathelper import config, vectorstore
from chathelper.llm import embed_texts

_HEADERS = {"User-Agent": "chathelper-ingest/1.0"}

# Links that can never be a page worth reading (PDFs are handled separately).
# Skipping them by extension saves one HTTP round-trip each; on a shop site
# images and downloads easily outnumber the actual pages.
_SKIP_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".ico", ".bmp",
    ".css", ".js", ".mjs", ".json", ".xml", ".rss", ".atom",
    ".zip", ".rar", ".7z", ".gz", ".tgz", ".tar", ".exe", ".dmg", ".msi",
    ".mp3", ".mp4", ".m4a", ".avi", ".mov", ".webm", ".ogg", ".wav",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods",
)
# Query parameters that do not produce a page worth indexing separately:
# tracking ids, and shop listing controls (sort order, page size, stock or
# price filters) that only re-arrange products already reachable elsewhere.
# Left in, the same listing is crawled once per variant and eats the budget.
_DROP_PARAM_PREFIXES = ("utm_", "filter_")
_DROP_PARAMS = {
    "fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "yclid",
    "igshid", "_ga", "_gl",
    "orderby", "per_page", "stock_status", "min_price", "max_price",
    "rating_filter", "add-to-cart", "replytocom",
}


def _drop_param(name: str) -> bool:
    name = name.lower()
    return name.startswith(_DROP_PARAM_PREFIXES) or name in _DROP_PARAMS


def _normalize_url(url: str) -> str:
    """Canonical URL for de-duplication: no fragment, lowercase scheme and
    host, '/' path for a bare host, tracking parameters removed. The query
    string is left byte-for-byte intact when nothing needs removing."""
    url = urldefrag(url.strip())[0]
    parts = urlparse(url)
    if parts.scheme not in ("http", "https"):
        return url
    query = parts.query
    if query:
        kept = [
            (k, v) for k, v in parse_qsl(query, keep_blank_values=True)
            if not _drop_param(k)
        ]
        if len(kept) != len(parse_qsl(query, keep_blank_values=True)):
            query = "&".join(f"{k}={v}" if v else k for k, v in kept)
    return urlunparse((parts.scheme.lower(), parts.netloc.lower(),
                       parts.path or "/", parts.params, query, ""))


def _site_key(url: str) -> str:
    """Host used for the same-site rule; 'www.' is ignored so a site that
    links to itself both with and without it is still crawled as one."""
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _skippable(url: str) -> bool:
    return urlparse(url).path.lower().endswith(_SKIP_EXTENSIONS)


def _read_capped(resp: requests.Response, limit: int) -> bytes | None:
    """Read a streamed response body, giving up (None) once it exceeds
    `limit` bytes — a huge or mislabelled file is never held in memory."""
    declared = resp.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        return None
    buf = bytearray()
    for chunk in resp.iter_content(chunk_size=256 * 1024):
        buf.extend(chunk)
        if len(buf) > limit:
            return None
    return bytes(buf)


def _extract_text_title(soup: BeautifulSoup) -> tuple[str, str]:
    """Strip noise tags and pull (visible_text, title) out of an already-parsed
    soup. Mutates `soup` in place (decomposes tags) — call this AFTER anything
    else that needs the original tree, e.g. link discovery."""
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "form"]):
        tag.decompose()
    lines = [ln.strip() for ln in soup.get_text(separator="\n").splitlines()]
    return "\n".join(ln for ln in lines if ln), title


def clean_html(html: str) -> tuple[str, str]:
    """Parse raw HTML and return (visible_text, title)."""
    return _extract_text_title(BeautifulSoup(html, "html.parser"))


def _is_pdf_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def _fetch_pdf_page(url: str) -> dict | None:
    """Download a PDF and extract its text, returning a {"url","title","text"}
    page dict like the HTML path produces, or None if it can't be read.

    PDFs are static files, so this uses a plain HTTP GET even during rendered
    (Playwright) crawls. Detection is by the .pdf URL extension — a PDF served
    from an extensionless URL is not picked up."""
    try:
        from pypdf import PdfReader
    except ImportError:
        print(f"  skip {url}: pypdf not installed (pip install pypdf)")
        return None

    import io

    limit = config.CRAWL_PDF_MAX_MB * 1024 * 1024
    try:
        with requests.get(url, headers=_HEADERS, timeout=30, stream=True) as resp:
            resp.raise_for_status()
            data = _read_capped(resp, limit)
    except requests.RequestException as exc:
        print(f"  skip {url}: {exc}")
        return None
    if data is None:
        print(f"  skip {url}: PDF larger than {config.CRAWL_PDF_MAX_MB} MB")
        return None

    try:
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(filter(None, (pg.extract_text() for pg in reader.pages)))
    except Exception as exc:  # pypdf raises many exception types on bad files
        print(f"  skip {url}: unreadable PDF ({exc})")
        return None

    lines = [ln.strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    if not text:
        # Scanned/image-only PDF — no text layer to extract.
        print(f"  skip {url}: PDF has no extractable text")
        return None

    meta_title = (reader.metadata.title or "").strip() if reader.metadata else ""
    title = meta_title or urlparse(url).path.rsplit("/", 1)[-1]
    return {"url": url, "title": title, "text": text}


def strip_boilerplate(pages: list[dict]) -> list[dict]:
    """Remove lines that repeat across many pages (cookie banners, nav menus,
    footers) BEFORE chunking/embedding.

    Why: crawled pages carry the same navigation/footer/cookie text on every
    page. Left in, that text (a) gets embedded into every chunk's vector,
    pulling all vectors toward each other and blurring retrieval, and (b)
    wastes prompt tokens on text the model should never quote. Structural
    stripping at parse time (nav/footer tags) catches most of it, but themes
    that render menus in plain divs — or per-page cookie notices — slip
    through; this frequency-based pass catches those.

    A line counts as boilerplate when it appears (exactly, whitespace-trimmed)
    on at least BOILERPLATE_MIN_PAGES pages AND on at least
    BOILERPLATE_PAGE_FRACTION of all crawled pages. With fewer than
    BOILERPLATE_MIN_PAGES pages total there is no reliable frequency signal,
    so nothing is stripped."""
    if len(pages) < config.BOILERPLATE_MIN_PAGES:
        return pages

    page_counts: dict[str, int] = {}
    for pg in pages:
        for line in set(ln.strip() for ln in pg["text"].splitlines() if ln.strip()):
            page_counts[line] = page_counts.get(line, 0) + 1

    threshold = max(config.BOILERPLATE_MIN_PAGES,
                    int(len(pages) * config.BOILERPLATE_PAGE_FRACTION))
    boilerplate = {ln for ln, n in page_counts.items() if n >= threshold}
    if not boilerplate:
        return pages

    out = []
    removed_chars = 0
    for pg in pages:
        kept = [ln for ln in pg["text"].splitlines() if ln.strip() not in boilerplate]
        cleaned = "\n".join(kept).strip()
        removed_chars += len(pg["text"]) - len(cleaned)
        if cleaned:  # a page that was ONLY boilerplate carries no information
            out.append({**pg, "text": cleaned})
    print(f"Boilerplate: removed {len(boilerplate)} repeated lines "
          f"(~{removed_chars} chars) across {len(pages)} pages; "
          f"{len(pages) - len(out)} empty pages dropped.")
    return out


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    chunks, i, n = [], 0, len(text)
    step = max(1, size - overlap)
    while i < n:
        piece = text[i:i + size].strip()
        if piece:
            chunks.append(piece)
        i += step
    return chunks


@contextmanager
def _static_fetcher():
    """Yield a fetch(url)->html function backed by ONE reused HTTP connection
    (requests.Session), rather than opening a fresh TCP+TLS connection for
    every page — roughly 2x faster per page after the first on real sites."""
    with requests.Session() as session:
        session.headers.update(_HEADERS)
        limit = config.CRAWL_MAX_PAGE_MB * 1024 * 1024

        def fetch(url: str) -> bytes | None:
            # Returns raw bytes: BeautifulSoup detects the charset itself
            # (meta tag / BOM), which beats requests' ISO-8859-1 fallback
            # for pages that omit a charset header.
            try:
                with session.get(url, timeout=15, stream=True) as resp:
                    if "text/html" not in resp.headers.get("content-type", ""):
                        return None
                    data = _read_capped(resp, limit)
            except requests.RequestException as exc:
                print(f"  skip {url}: {exc}")
                return None
            if data is None:
                print(f"  skip {url}: page larger than {config.CRAWL_MAX_PAGE_MB} MB")
            return data

        yield fetch


@contextmanager
def _rendered_fetcher():
    """Yield a fetch(url)->html function backed by a headless Chromium browser.

    Runs each page's JavaScript and waits for it to settle, so client-rendered
    (single-page-app) content and JS-built links are captured. Requires the
    optional Playwright dependency:
        pip install "chathelper[render]"
        playwright install chromium
    """
    try:
        # Optional dependency (the [render] extra); guarded so a plain install works.
        from playwright.sync_api import (  # pyright: ignore[reportMissingImports]
            Error as PlaywrightError,
            TimeoutError as PlaywrightTimeout,
            sync_playwright,
        )
    except ImportError as exc:
        raise SystemExit(
            "Rendered crawling needs Playwright. Install it with:\n"
            '  pip install "chathelper[render]"\n'
            "  playwright install chromium"
        ) from exc

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True)
        except PlaywrightError as exc:
            raise SystemExit(
                f"Could not launch Chromium: {exc}\n"
                "Did you run `playwright install chromium`?"
            ) from exc
        page = browser.new_page(user_agent=_HEADERS["User-Agent"])

        def fetch(url: str) -> str | None:
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if resp is not None:
                    ctype = (resp.headers or {}).get("content-type", "")
                    if ctype and "text/html" not in ctype:
                        return None
                # Let client-side rendering / XHR settle (best-effort).
                try:
                    page.wait_for_load_state("networkidle", timeout=config.CRAWL_RENDER_WAIT_MS)
                except PlaywrightTimeout:
                    pass
                return page.content()
            except PlaywrightTimeout:
                print(f"  skip {url}: render timeout")
                return None
            except PlaywrightError as exc:
                print(f"  skip {url}: {exc}")
                return None

        try:
            yield fetch
        finally:
            browser.close()


def _bfs_crawl(start_url: str, max_pages: int, same_domain: bool, fetch) -> list[dict]:
    """Breadth-first crawl using the given `fetch(url)->html|None` function
    (html may be str or bytes; BeautifulSoup accepts both)."""
    start_url = _normalize_url(start_url)
    seen: set[str] = set()
    queue: deque[str] = deque([start_url])
    site = _site_key(start_url)
    pages: list[dict] = []

    while queue and len(pages) < max_pages:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)

        if _is_pdf_url(url):
            if not config.CRAWL_PDFS:
                continue
            pdf_page = _fetch_pdf_page(url)
            if pdf_page:
                pages.append(pdf_page)
                print(f"[{len(pages)}/{max_pages}] {url} ({len(pdf_page['text'])} chars) [pdf]")
            continue  # PDFs contribute no links to follow

        html = fetch(url)
        if not html:
            continue

        # Parse once. Discover links from the ORIGINAL tree first — nav/header/
        # footer often hold site navigation and _extract_text_title() strips
        # those tags out (it mutates `soup` in place).
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            nxt = _normalize_url(urljoin(url, a["href"]))
            if not nxt.startswith(("http://", "https://")):
                continue
            if same_domain and _site_key(nxt) != site:
                continue
            if _skippable(nxt):
                continue
            if nxt not in seen:
                queue.append(nxt)

        text, title = _extract_text_title(soup)
        if text:
            pages.append({"url": url, "title": title, "text": text})
            print(f"[{len(pages)}/{max_pages}] {url} ({len(text)} chars)")
        # time.sleep(0.1)  # be polite

    return pages


def crawl(start_url: str, max_pages: int, same_domain: bool, render: bool = False) -> list[dict]:
    """Breadth-first crawl within `max_pages`.

    render=False -> fast static HTTP GET (default).
    render=True  -> headless browser that executes JavaScript, capturing
                    dynamically generated pages and JS-built navigation links.
    """
    if render:
        with _rendered_fetcher() as fetch:
            return _bfs_crawl(start_url, max_pages, same_domain, fetch)
    with _static_fetcher() as fetch:
        return _bfs_crawl(start_url, max_pages, same_domain, fetch)


def ingest_pages(pages: list[dict], batch_size: int = 32) -> int:
    client = vectorstore.get_client()
    vectorstore.ensure_collection(client)

    texts: list[str] = []
    payloads: list[dict] = []
    ids: list[str] = []
    total = 0

    def flush() -> None:
        nonlocal total, texts, payloads, ids
        if not texts:
            return
        vectors = embed_texts(texts, kind="document")
        vectorstore.upsert(client, vectors, payloads, ids=ids)
        total += len(texts)
        print(f"  ...stored {total} chunks")
        texts, payloads, ids = [], [], []

    for pg in pages:
        url = pg.get("url", "")
        for index, chunk in enumerate(
            chunk_text(pg["text"], config.CHUNK_SIZE, config.CHUNK_OVERLAP)
        ):
            texts.append(chunk)
            payloads.append({"text": chunk, "url": url, "title": pg.get("title", "")})
            # Deterministic per (url, chunk index): re-ingesting a page
            # overwrites its chunks instead of adding duplicates. Rows
            # without a URL cannot be identified, so they get random ids.
            ids.append(vectorstore.point_id(url, index) if url else str(uuid.uuid4()))
            if len(texts) >= batch_size:
                flush()
    flush()
    return total


def crawl_and_ingest(url: str, render: bool | None = None, replace: bool = False) -> int:
    """Crawl `url` and store it in the configured collection.

    replace=True drops the collection and recreates it right before storing
    (never before the crawl, so a failed crawl cannot destroy existing
    data). Without it, chunks of re-crawled pages are overwritten in place
    but pages that vanished from the site keep their old chunks."""
    render = config.CRAWL_RENDER if render is None else render
    config.ensure_data_dir()

    # Fail fast on a locked/unavailable vector store OR an unreachable
    # embedding server BEFORE crawling — a long crawl finishing only to fail
    # at the embed/store step wastes real time (a 176-page crawl once died
    # exactly this way because only Qdrant was checked).
    client = vectorstore.get_client()
    try:
        embed_texts(["connectivity check"])
    except Exception as exc:
        raise SystemExit(
            f"Embedding server unreachable at {config.EMBED_BASE_URL} ({exc}).\n"
            "Start it first (scripts/start-embeddings.ps1 or .sh) — refusing "
            "to crawl until embedding works, so no crawl time is wasted."
        ) from exc

    mode = "rendered/JS" if render else "static"
    print(f"Crawling {url} (max {config.CRAWL_MAX_PAGES} pages, {mode}) "
          f"into collection '{config.QDRANT_COLLECTION}'...")
    pages = crawl(url, config.CRAWL_MAX_PAGES, config.CRAWL_SAME_DOMAIN, render=render)
    if config.BOILERPLATE_STRIP:
        pages = strip_boilerplate(pages)
    if replace:
        if not pages:
            raise SystemExit(
                "Crawl produced no pages — keeping the existing collection "
                f"'{config.QDRANT_COLLECTION}' instead of replacing it with nothing."
            )
        print(f"Replacing collection '{config.QDRANT_COLLECTION}' (dropping old chunks)...")
        vectorstore.recreate_collection(client)
    print(f"Crawled {len(pages)} pages. Embedding + storing...")
    total = ingest_pages(pages)
    print(f"Done. Ingested {total} chunks into '{config.QDRANT_COLLECTION}'.")
    return total


def main() -> None:
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m chathelper.ingest <start_url>")
        raise SystemExit(1)
    crawl_and_ingest(sys.argv[1])


if __name__ == "__main__":
    main()
