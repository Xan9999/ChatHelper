"""Qdrant backup behavior without a running Qdrant service."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from chathelper import backup_qdrant, config


class BackupTests(unittest.TestCase):
    def test_downloads_every_collection_and_cleans_server_snapshots(self) -> None:
        client = Mock()
        client.get_collections.return_value = SimpleNamespace(
            collections=[SimpleNamespace(name="site_one")]
        )
        client.create_snapshot.return_value = SimpleNamespace(name="snapshot-1.snapshot")

        def fake_download(_collection, _name, destination):
            destination.write_bytes(b"snapshot contents")

        with tempfile.TemporaryDirectory() as temporary, patch.object(
            config, "QDRANT_URL", "http://qdrant:6333"
        ), patch.object(backup_qdrant.vectorstore, "get_client", return_value=client), patch.object(
            backup_qdrant, "_download_snapshot", side_effect=fake_download
        ):
            output = Path(temporary)
            result = backup_qdrant.backup(output)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(result), 1)
            self.assertEqual(manifest["snapshots"][0]["bytes"], len(b"snapshot contents"))
            self.assertTrue((output / result[0]["file"]).is_file())

        client.delete_snapshot.assert_called_once_with(
            collection_name="site_one", snapshot_name="snapshot-1.snapshot", wait=True
        )


if __name__ == "__main__":
    unittest.main()
