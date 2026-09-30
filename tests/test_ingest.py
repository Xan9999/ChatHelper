"""Crawler hygiene and idempotent ingestion — pure functions, no network."""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from chathelper import config, ingest, vectorstore


class UrlNormalizationTests(unittest.TestCase):
    def test_tracking_params_and_fragment_are_removed(self) -> None:
        url = "https://Shop.example.com/p/1?utm_source=fb&color=red&fbclid=abc#reviews"
        self.assertEqual(ingest._normalize_url(url), "https://shop.example.com/p/1?color=red")

    def test_untouched_query_string_is_kept_verbatim(self) -> None:
        url = "https://example.com/search?q=a%20b&page=2"
        self.assertEqual(ingest._normalize_url(url), url)

    def test_bare_host_gets_root_path(self) -> None:
        self.assertEqual(ingest._normalize_url("https://example.com"), "https://example.com/")

    def test_same_site_ignores_www(self) -> None:
        self.assertEqual(ingest._site_key("https://www.example.com/a"), ingest._site_key("https://example.com/b"))
        self.assertNotEqual(ingest._site_key("https://example.com"), ingest._site_key("https://other.com"))

    def test_binary_links_are_skipped_but_pdfs_are_not(self) -> None:
        self.assertTrue(ingest._skippable("https://example.com/img/logo.PNG"))
        self.assertTrue(ingest._skippable("https://example.com/files/archive.zip?dl=1"))
        self.assertFalse(ingest._skippable("https://example.com/catalog.pdf"))
        self.assertFalse(ingest._skippable("https://example.com/products"))


class CappedDownloadTests(unittest.TestCase):
    def test_declared_or_actual_size_over_limit_returns_none(self) -> None:
        declared = Mock(headers={"content-length": "999"})
        self.assertIsNone(ingest._read_capped(declared, limit=100))

        streamed = Mock(headers={})
        streamed.iter_content.return_value = [b"x" * 60, b"y" * 60]
        self.assertIsNone(ingest._read_capped(streamed, limit=100))

    def test_small_body_is_returned_whole(self) -> None:
        resp = Mock(headers={"content-length": "6"})
        resp.iter_content.return_value = [b"abc", b"def"]
        self.assertEqual(ingest._read_capped(resp, limit=100), b"abcdef")


class IdempotentIngestTests(unittest.TestCase):
    def test_point_ids_are_stable_per_url_and_chunk(self) -> None:
        self.assertEqual(vectorstore.point_id("https://e.com/a", 0), vectorstore.point_id("https://e.com/a", 0))
        self.assertNotEqual(vectorstore.point_id("https://e.com/a", 0), vectorstore.point_id("https://e.com/a", 1))
        self.assertNotEqual(vectorstore.point_id("https://e.com/a", 0), vectorstore.point_id("https://e.com/b", 0))

    def test_ingest_pages_passes_deterministic_ids(self) -> None:
        client = Mock()
        pages = [{"url": "https://e.com/a", "title": "A", "text": "x" * 1000}]
        with patch.object(vectorstore, "get_client", return_value=client), patch.object(
            vectorstore, "ensure_collection"
        ), patch.object(vectorstore, "upsert") as upsert, patch.object(
            ingest, "embed_texts", side_effect=lambda texts, kind: [[0.0] for _ in texts]
        ), patch.object(config, "CHUNK_SIZE", 800), patch.object(config, "CHUNK_OVERLAP", 160):
            total = ingest.ingest_pages(pages)
        self.assertEqual(total, 2)
        ids = upsert.call_args.kwargs["ids"]
        self.assertEqual(ids, [vectorstore.point_id("https://e.com/a", 0), vectorstore.point_id("https://e.com/a", 1)])

    def test_collection_known_never_creates_and_caches_positives(self) -> None:
        client = Mock()
        client.collection_exists.return_value = True
        vectorstore._known.clear()
        self.assertTrue(vectorstore.collection_known(client, "site"))
        self.assertTrue(vectorstore.collection_known(client, "site"))
        client.collection_exists.assert_called_once_with("site")
        client.create_collection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
