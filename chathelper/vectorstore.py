"""Qdrant vector store wrapper (embedded local folder or remote server).

Embedded mode allows only one process to open the folder at a time, so run
ingestion while the server is stopped, or use a Qdrant server (set QDRANT_URL)
to do both at once.

Hybrid retrieval: collections created by this version store TWO vectors per
chunk — "dense" (the embedding model's semantic vector) and "lexical" (a
sparse term-frequency vector, see lexical.py). Searches run both and merge
the rankings with Reciprocal Rank Fusion (RRF) on the server: a chunk ranked
high by EITHER meaning or exact keywords makes the final top-K. Collections
created by older versions (one unnamed dense vector) are detected at runtime
and searched dense-only exactly as before — re-ingest a collection (delete +
ingest, see README) to upgrade it to hybrid.
"""
from __future__ import annotations

import time
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Fusion,
    FusionQuery,
    Modifier,
    PointStruct,
    Prefetch,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from chathelper import config
from chathelper.lexical import sparse_encode

_client: QdrantClient | None = None

# collection name -> "hybrid" | "legacy", resolved once per process.
_modes: dict[str, str] = {}

# collection name -> (exists, checked_at). Visitors pick the collection via
# the widget's client_id, so existence is checked per request; cache it so a
# burst of requests (or a flood of made-up ids) is not one Qdrant call each.
_known: dict[str, tuple[bool, float]] = {}
_KNOWN_TTL_S = {True: 300.0, False: 15.0}


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        if config.QDRANT_URL:
            _client = QdrantClient(
                url=config.QDRANT_URL,
                api_key=config.QDRANT_API_KEY or None,
            )
        else:
            config.ensure_data_dir()
            try:
                _client = QdrantClient(path=config.QDRANT_PATH)
            except RuntimeError as exc:
                if "already accessed by another instance" not in str(exc):
                    raise
                raise SystemExit(
                    f"Cannot open the vector store at '{config.QDRANT_PATH}' — it's "
                    "already open in another process (e.g. `chathelper serve` "
                    "is running). Embedded Qdrant only allows ONE process at a time.\n"
                    "Fix: stop that process first, then retry — or avoid this "
                    "entirely by running a real Qdrant server and setting QDRANT_URL "
                    "in .env (e.g. `docker run -p 6333:6333 qdrant/qdrant`), which "
                    "lets ingest and serve run at the same time."
                ) from exc
    return _client


def ensure_collection(client: QdrantClient, name: str | None = None) -> None:
    name = name or config.QDRANT_COLLECTION
    if not client.collection_exists(name):
        # Several ASGI workers may start at once. Treat a concurrent create by
        # another worker as success, but surface every other failure.
        try:
            client.create_collection(
                collection_name=name,
                vectors_config={"dense": VectorParams(size=config.EMBED_DIM,
                                                      distance=Distance.COSINE)},
                sparse_vectors_config={
                    "lexical": SparseVectorParams(modifier=Modifier.IDF)
                },
            )
        except Exception:
            if not client.collection_exists(name):
                raise
        _modes[name] = "hybrid"


def collection_known(client: QdrantClient, name: str) -> bool:
    """True if the collection exists. Unlike ensure_collection() this never
    creates anything: a request naming an unknown client_id must NOT be able
    to create collections (each costs Qdrant storage and would show up in
    the QA site), so the serving path uses this and only ingest creates."""
    now = time.monotonic()
    cached = _known.get(name)
    if cached is not None and now - cached[1] < _KNOWN_TTL_S[cached[0]]:
        return cached[0]
    exists = bool(client.collection_exists(name))
    _known[name] = (exists, now)
    return exists


def recreate_collection(client: QdrantClient, name: str | None = None) -> None:
    """Drop a collection (if present) and create it fresh in the current
    hybrid schema. Used by `chathelper ingest --replace` so a full re-crawl
    never leaves stale or duplicate chunks behind."""
    name = name or config.QDRANT_COLLECTION
    if client.collection_exists(name):
        client.delete_collection(name)
    _modes.pop(name, None)
    _known.pop(name, None)
    ensure_collection(client, name)


def point_id(url: str, index: int) -> str:
    """Deterministic point id for chunk `index` of a page: re-ingesting the
    same page overwrites its chunks in place instead of duplicating them."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{url}#chunk={index}"))


def _mode(client: QdrantClient, name: str) -> str:
    """'hybrid' (named dense + sparse lexical vectors) or 'legacy' (single
    unnamed dense vector, created by older versions). Cached per process."""
    if name not in _modes:
        info = client.get_collection(name)
        _modes[name] = "hybrid" if info.config.params.sparse_vectors else "legacy"
    return _modes[name]


def upsert(client: QdrantClient, vectors: list[list[float]], payloads: list[dict],
           name: str | None = None, ids: list[str] | None = None) -> None:
    """Store chunks. Pass `ids` (see point_id) to make the write idempotent;
    without them every point gets a random id, which duplicates on re-ingest."""
    name = name or config.QDRANT_COLLECTION
    hybrid = _mode(client, name) == "hybrid"
    if ids is None:
        ids = [str(uuid.uuid4()) for _ in vectors]

    def point(pid: str, v: list[float], p: dict) -> PointStruct:
        if hybrid:
            idx, vals = sparse_encode(p.get("text", ""))
            vector = {"dense": v, "lexical": SparseVector(indices=idx, values=vals)}
        else:
            vector = v  # legacy collection: keep writing its original schema
        return PointStruct(id=pid, vector=vector, payload=p)

    client.upsert(collection_name=name,
                  points=[point(i, v, p) for i, v, p in zip(ids, vectors, payloads)])


def search(client: QdrantClient, query_vector: list[float], top_k: int,
           name: str | None = None, query_text: str | None = None) -> list[dict]:
    """Top-K chunks for a query. On hybrid collections this runs BOTH a dense
    (semantic) and a lexical (exact-keyword) search and fuses the two rankings
    with Reciprocal Rank Fusion; on legacy collections it is a plain dense
    search. NOTE: RRF scores are rank-based (~0.01..0.03), not cosine — don't
    compare them against cosine thresholds."""
    name = name or config.QDRANT_COLLECTION

    if _mode(client, name) == "hybrid":
        idx, vals = sparse_encode(query_text or "")
        prefetch = [Prefetch(query=query_vector, using="dense", limit=top_k * 3)]
        if idx:  # a query with no word tokens has no lexical signal
            prefetch.append(Prefetch(query=SparseVector(indices=idx, values=vals),
                                     using="lexical", limit=top_k * 3))
        hits = client.query_points(
            collection_name=name, prefetch=prefetch,
            query=FusionQuery(fusion=Fusion.RRF), limit=top_k, with_payload=True,
        ).points
    else:
        hits = client.query_points(
            collection_name=name, query=query_vector, limit=top_k, with_payload=True,
        ).points
    return [{"score": h.score, **(h.payload or {})} for h in hits]
