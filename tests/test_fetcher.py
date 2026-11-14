"""Tests for fetcher.py. No real network is used: urllib is mocked."""

import os
import sys
import unittest
from unittest import mock
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fetcher


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


class TestFetcher(unittest.TestCase):
    def test_fetch_nas_status_returns_text(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(b"<xml/>")
            result = fetcher.fetch_nas_status()
        self.assertEqual(result, "<xml/>")
        req = urlopen.call_args[0][0]
        self.assertEqual(req.full_url, fetcher.NAS_STATUS_URL)
        self.assertEqual(req.get_header("User-agent"), fetcher.USER_AGENT)
        self.assertEqual(urlopen.call_args[1].get("timeout"), 15)

    def test_fetch_returns_none_on_url_error(self):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("down"),
        ):
            self.assertIsNone(fetcher.fetch_nas_status())

    def test_fetch_returns_none_on_empty_body(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(b"   \n")
            self.assertIsNone(fetcher.fetch_nas_status())

    def test_fetch_airport_status_normalizes_code(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = FakeResponse(b"{}")
            self.assertEqual(fetcher.fetch_airport_status("atl"), "{}")
        req = urlopen.call_args[0][0]
        self.assertIn("/ATL?", req.full_url)

    def test_fetch_airport_status_rejects_bad_code(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            self.assertIsNone(fetcher.fetch_airport_status("AT"))
            self.assertIsNone(fetcher.fetch_airport_status("ATL1"))
            self.assertIsNone(fetcher.fetch_airport_status(""))
            self.assertIsNone(fetcher.fetch_airport_status(None))
        urlopen.assert_not_called()

    def test_only_two_hosts_are_contacted(self):
        from urllib.parse import urlparse

        hosts = {
            urlparse(fetcher.NAS_STATUS_URL).hostname,
            urlparse(fetcher.AIRPORT_STATUS_URL.format(code="ATL")).hostname,
        }
        self.assertEqual(hosts, set(fetcher.ALLOWED_HOSTS))


if __name__ == "__main__":
    unittest.main()
