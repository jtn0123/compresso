#!/usr/bin/env python3

"""
tests.unit.test_downloads.py

Tests for the downloads module.
Covers: DownloadsLinks singleton, generate/get link, expiration.
DownloadsHandler is tested via tornado.testing.
"""

import os
import time
from unittest.mock import MagicMock, patch

import pytest
import tornado.testing
import tornado.web

from compresso.libs.singleton import SingletonType
from compresso.webserver.downloads import DownloadsHandler, DownloadsLinks


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


# ------------------------------------------------------------------
# DownloadsLinks
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestDownloadsLinks:
    def test_singleton_behavior(self):
        dl1 = DownloadsLinks()
        dl2 = DownloadsLinks()
        assert dl1 is dl2

    def test_generate_and_get_link(self):
        dl = DownloadsLinks()
        link_data = {"abspath": "/media/video.mp4", "basename": "video.mp4"}
        link_id = dl.generate_download_link(link_data)
        assert isinstance(link_id, str)
        assert len(link_id) > 0

        fetched = dl.get_download_link(link_id)
        assert fetched["abspath"] == "/media/video.mp4"
        assert fetched["basename"] == "video.mp4"

    def test_get_missing_link_returns_empty(self):
        dl = DownloadsLinks()
        result = dl.get_download_link("nonexistent-id")
        assert result == {}

    def test_expired_link_is_removed(self):
        dl = DownloadsLinks()
        link_data = {"abspath": "/media/old.mp4", "basename": "old.mp4"}
        link_id = dl.generate_download_link(link_data)

        # Manually expire the link
        dl._download_links[link_id]["expires"] = time.time() - 10

        result = dl.get_download_link(link_id)
        assert result == {}

    def test_multiple_links(self):
        dl = DownloadsLinks()
        id1 = dl.generate_download_link({"abspath": "/a.mp4", "basename": "a.mp4"})
        id2 = dl.generate_download_link({"abspath": "/b.mp4", "basename": "b.mp4"})
        assert id1 != id2
        assert dl.get_download_link(id1)["abspath"] == "/a.mp4"
        assert dl.get_download_link(id2)["abspath"] == "/b.mp4"

    def test_link_has_expiry(self):
        dl = DownloadsLinks()
        link_id = dl.generate_download_link({"abspath": "/test", "basename": "test"})
        link = dl._download_links[link_id]
        assert "expires" in link
        assert link["expires"] > time.time()

    def test_remove_expired_cleans_multiple(self):
        dl = DownloadsLinks()
        id1 = dl.generate_download_link({"abspath": "/a", "basename": "a"})
        id2 = dl.generate_download_link({"abspath": "/b", "basename": "b"})
        # Expire id1
        dl._download_links[id1]["expires"] = time.time() - 10
        # id2 should still be accessible
        result = dl.get_download_link(id2)
        assert result["abspath"] == "/b"
        # id1 should be gone
        assert dl.get_download_link(id1) == {}


# ------------------------------------------------------------------
# DownloadsHandler via tornado.testing
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestDownloadsHandler(tornado.testing.AsyncHTTPTestCase):
    __test__ = True

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()
        SingletonType._instances = {}

    def get_app(self):
        return tornado.web.Application(
            [
                (r"/downloads/(.*)", DownloadsHandler),
            ]
        )

    def runTest(self):
        pass

    def test_empty_abspath_returns_error_page(self):
        """An empty abspath triggers an error page (404 content)."""
        dl = DownloadsLinks()
        link_id = dl.generate_download_link({"abspath": "", "basename": ""})
        resp = self.fetch(f"/downloads/{link_id}")
        # The handler calls write_error(404) which renders an error page
        assert b"404" in resp.body

    def test_nonexistent_file_returns_error_page(self):
        dl = DownloadsLinks()
        link_id = dl.generate_download_link(
            {
                "abspath": "/nonexistent/file.mp4",
                "basename": "file.mp4",
            }
        )
        resp = self.fetch(f"/downloads/{link_id}")
        assert b"404" in resp.body

    def test_directory_returns_error_page(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            dl = DownloadsLinks()
            link_id = dl.generate_download_link(
                {
                    "abspath": tmpdir,
                    "basename": "mydir",
                }
            )
            resp = self.fetch(f"/downloads/{link_id}")
            assert b"403" in resp.body

    @patch("compresso.config.Config")
    @patch("compresso.libs.unmodels.Libraries")
    def test_serves_file_when_allowed(self, mock_libs, mock_config):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.txt")
            with open(filepath, "w") as f:
                f.write("hello world")

            dl = DownloadsLinks()
            link_id = dl.generate_download_link(
                {
                    "abspath": filepath,
                    "basename": "test.txt",
                }
            )

            mock_lib = MagicMock()
            mock_lib.path = tmpdir
            mock_libs.select.return_value = [mock_lib]
            mock_config.return_value.get_cache_path.return_value = tmpdir

            resp = self.fetch(f"/downloads/{link_id}")
            assert resp.code == 200
            assert b"hello world" in resp.body

    @patch("compresso.config.Config")
    @patch("compresso.libs.unmodels.Libraries")
    def test_forbidden_when_not_in_allowed_root(self, mock_libs, mock_config):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "secret.txt")
            with open(filepath, "w") as f:
                f.write("secret data")

            dl = DownloadsLinks()
            link_id = dl.generate_download_link(
                {
                    "abspath": filepath,
                    "basename": "secret.txt",
                }
            )

            mock_libs.select.return_value = []
            mock_config.return_value.get_cache_path.return_value = "/some/other/path"

            resp = self.fetch(f"/downloads/{link_id}")
            assert b"403" in resp.body
