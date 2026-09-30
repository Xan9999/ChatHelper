"""Vector retrieval: embed the query, search Qdrant, return the best chunks."""
from __future__ import annotations

from chathelper import config, vectorstore
from chathelper.llm import embed_text


def retrieve(query: str, top_k: int | None = None, collection: str | None = None) -> list[dict]:
    top_k = top_k or config.TOP_K
    client = vectorstore.get_client()
    # Never create a collection from the serving path — the name comes from
    # the visitor's client_id. Unknown collection = nothing to ground on.
    if not vectorstore.collection_known(client, collection or config.QDRANT_COLLECTION):
        return []
    query_vector = embed_text(query, kind="query")
    # query text goes along for the lexical half of hybrid search (see
    # vectorstore.search); legacy collections ignore it.
    hits = vectorstore.search(client, query_vector, top_k, collection, query_text=query)
    # Drop weak matches and exact-duplicate texts (e.g. the same page crawled
    # under two URLs) — every duplicate chunk is prompt-processing time wasted.
    seen: set[str] = set()
    out = []
    for h in hits:
        if h.get("score", 0.0) < config.SCORE_THRESHOLD:
            continue
        text = h.get("text", "")
        if text in seen:
            continue
        seen.add(text)
        out.append(h)
    return out
