#!/usr/bin/env python3

"""
tests.unit.test_docs_api.py

Tests for the docs API handler endpoints.
Covers: get_privacy_policy (git changelog + fallback), get_logs_as_zip,
_generate_changelog_from_git helper.
"""

import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from compresso.libs.singleton import SingletonType
from compresso.webserver.api_v2.docs_api import ApiDocsHandler, _generate_changelog_from_git
from tests.unit.api_test_base import ApiTestBase


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _mock_initialize(self, **kwargs):
    self.session = MagicMock()
    self.params = kwargs.get("params")
    self.compresso_data_queues = {}


# ------------------------------------------------------------------
# _generate_changelog_from_git
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestGenerateChangelogFromGit:
    @patch("compresso.webserver.api_v2.docs_api.subprocess")
    def test_not_a_git_repo(self, mock_subprocess):
        result = MagicMock()
        result.returncode = 1
        mock_subprocess.run.return_value = result
        assert _generate_changelog_from_git() is None

    @patch("compresso.webserver.api_v2.docs_api.subprocess")
    def test_with_tags(self, mock_subprocess):
        calls = []

        def run_side_effect(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if "rev-parse" in cmd:
                result.stdout = ".git"
            elif "tag" in cmd:
                result.stdout = "v1.0|2024-01-01\nv0.9|2023-12-01\n"
            elif "log" in cmd:
                if "HEAD" in " ".join(cmd):
                    result.stdout = "- Fix bug (abc123)"
                else:
                    result.stdout = "- Initial feature (def456)"
            calls.append(cmd)
            return result

        mock_subprocess.run.side_effect = run_side_effect
        mock_subprocess.SubprocessError = Exception
        lines = _generate_changelog_from_git()
        assert lines is not None
        assert any("Changelog" in line for line in lines)

    @patch("compresso.webserver.api_v2.docs_api.subprocess")
    def test_no_tags(self, mock_subprocess):
        calls = []

        def run_side_effect(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if "rev-parse" in cmd:
                result.stdout = ".git"
            elif "tag" in cmd:
                result.stdout = ""
            elif "log" in cmd:
                result.stdout = "- Recent commit (abc123)"
            calls.append(cmd)
            return result

        mock_subprocess.run.side_effect = run_side_effect
        mock_subprocess.SubprocessError = Exception
        lines = _generate_changelog_from_git()
        assert lines is not None
        assert any("Recent Changes" in line for line in lines)

    @patch("compresso.webserver.api_v2.docs_api.subprocess")
    def test_subprocess_error(self, mock_subprocess):
        mock_subprocess.run.side_effect = OSError("not found")
        mock_subprocess.SubprocessError = Exception
        assert _generate_changelog_from_git() is None


# ------------------------------------------------------------------
# Get privacy policy (changelog)
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiDocsHandler, "initialize", _mock_initialize)
class TestDocsApiPrivacyPolicy(ApiTestBase):
    __test__ = True
    handler_class = ApiDocsHandler

    @patch("compresso.webserver.api_v2.docs_api._generate_changelog_from_git")
    def test_get_changelog_from_git(self, mock_gen):
        mock_gen.return_value = ["# Changelog\n", "## v1.0\n"]
        resp = self.get_json("/docs/privacypolicy")
        assert resp.code == 200
        data = self.parse_response(resp)
        assert "content" in data

    @patch("compresso.webserver.api_v2.docs_api._generate_changelog_from_git", return_value=None)
    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data="# Privacy Policy\nContent here.\n"))
    def test_get_changelog_fallback_file(self, _exists, _gen):
        resp = self.get_json("/docs/privacypolicy")
        assert resp.code == 200

    @patch("compresso.webserver.api_v2.docs_api._generate_changelog_from_git", return_value=None)
    @patch("os.path.exists", return_value=False)
    def test_get_changelog_no_content(self, _exists, _gen):
        resp = self.get_json("/docs/privacypolicy")
        assert resp.code == 500

    @patch("compresso.webserver.api_v2.docs_api._generate_changelog_from_git")
    def test_get_changelog_exception(self, mock_gen):
        mock_gen.side_effect = Exception("error")
        resp = self.get_json("/docs/privacypolicy")
        assert resp.code == 500


# ------------------------------------------------------------------
# Get logs as zip
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiDocsHandler, "initialize", _mock_initialize)
class TestDocsApiLogsZip(ApiTestBase):
    __test__ = True
    handler_class = ApiDocsHandler

    @patch("compresso.webserver.helpers.documents.generate_log_files_zip")
    def test_get_logs_zip_success(self, mock_gen):
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
            f.write(b"PK\x03\x04fakecontent")
            tmp_path = f.name
        try:
            mock_gen.return_value = tmp_path
            resp = self.get_json("/docs/logs/zip")
            assert resp.code == 200
        finally:
            os.unlink(tmp_path)

    @patch("compresso.webserver.helpers.documents.generate_log_files_zip")
    def test_get_logs_zip_error(self, mock_gen):
        mock_gen.side_effect = Exception("error")
        resp = self.get_json("/docs/logs/zip")
        assert resp.code == 500
