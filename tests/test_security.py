"""Focused tests for request sanitizing, rate limiting, and QA sessions."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from chathelper import config, main, qa


def _request_with_cookie(value: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/qa",
            "headers": [(b"cookie", f"chathelper_qa={value}".encode("ascii"))],
            "client": ("127.0.0.1", 12345),
        }
    )


class RequestSafetyTests(unittest.TestCase):
    def test_history_keeps_only_safe_roles_and_bounds_content(self) -> None:
        with patch.object(config, "CHAT_HISTORY_MAX_ITEMS", 3), patch.object(
            config, "CHAT_MAX_MESSAGE_CHARS", 4
        ):
            cleaned = main._clean_history(
                [
                    {"role": "user", "content": "discarded by item limit"},
                    {"role": "system", "content": "unsafe"},
                    {"role": "assistant", "content": "abcdef"},
                    {"role": "user", "content": "okay"},
                ]
            )
        self.assertEqual(
            cleaned,
            [
                {"role": "assistant", "content": "abcd"},
                {"role": "user", "content": "okay"},
            ],
        )

    def test_rate_limit_opens_again_after_window(self) -> None:
        main._RATE_HITS.clear()
        main._LAST_RATE_CLEANUP = 0.0
        with patch.object(main.time, "monotonic", side_effect=[1.0, 2.0, 3.0, 63.0]):
            self.assertFalse(main._rate_limited("chat", "client", 2))
            self.assertFalse(main._rate_limited("chat", "client", 2))
            self.assertTrue(main._rate_limited("chat", "client", 2))
            self.assertFalse(main._rate_limited("chat", "client", 2))


class QaSessionTests(unittest.TestCase):
    def test_valid_signed_session_is_accepted(self) -> None:
        with patch.object(config, "QA_TOKEN", "test-secret"), patch.object(
            qa.time, "time", return_value=1_000
        ):
            qa._require_token(_request_with_cookie(qa._session_value(1_100)))

    def test_expired_or_tampered_session_is_rejected(self) -> None:
        with patch.object(config, "QA_TOKEN", "test-secret"), patch.object(
            qa.time, "time", return_value=1_000
        ):
            for value in (qa._session_value(999), "1100.not-a-valid-signature"):
                with self.subTest(value=value), self.assertRaises(HTTPException):
                    qa._require_token(_request_with_cookie(value))


if __name__ == "__main__":
    unittest.main()
