"""Create and download Qdrant collection snapshots for an offline backup."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

from chathelper import config, vectorstore


def _download_snapshot(collection: str, snapshot_name: str, destination: Path) -> None:
    base_url = config.QDRANT_URL.rstrip("/")
    url = (
        f"{base_url}/collections/{quote(collection, safe='')}/snapshots/"
        f"{quote(snapshot_name, safe='')}"
    )
    headers = {"api-key": config.QDRANT_API_KEY} if config.QDRANT_API_KEY else {}
    with requests.get(url, headers=headers, stream=True, timeout=(10, 600)) as response:
        response.raise_for_status()
        with destination.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output.write(chunk)


def backup(output_dir: Path) -> list[dict]:
    if not config.QDRANT_URL:
        raise RuntimeError("QDRANT_URL must point to the Qdrant server")
    output_dir.mkdir(parents=True, exist_ok=True)
    client = vectorstore.get_client()
    manifest: list[dict] = []
    for item in client.get_collections().collections:
        collection = item.name
        snapshot = client.create_snapshot(collection_name=collection, wait=True)
        if snapshot is None:
            raise RuntimeError(f"Qdrant did not create a snapshot for {collection}")
        filename = f"{quote(collection, safe='')}--{quote(snapshot.name, safe='')}"
        destination = output_dir / filename
        _download_snapshot(collection, snapshot.name, destination)
        manifest.append(
            {
                "collection": collection,
                "snapshot": snapshot.name,
                "file": filename,
                "bytes": destination.stat().st_size,
            }
        )
        try:
            client.delete_snapshot(
                collection_name=collection,
                snapshot_name=snapshot.name,
                wait=True,
            )
        except Exception as exc:
            print(
                f"WARNING: downloaded {snapshot.name}, but could not remove the "
                f"temporary server-side snapshot: {exc}"
            )

    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "qdrant_url": config.QDRANT_URL,
        "snapshots": manifest,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up every Qdrant collection")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    snapshots = backup(args.output)
    print(f"Downloaded {len(snapshots)} Qdrant collection snapshot(s).")


if __name__ == "__main__":
    main()
