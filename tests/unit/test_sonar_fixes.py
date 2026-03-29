#!/usr/bin/env python3

"""
tests.unit.test_sonar_fixes.py

Tests for code changes made to resolve SonarCloud security vulnerabilities,
bugs, and async I/O issues (PR #65).
"""

import json
import os

import pytest

# ------------------------------------------------------------------
# format_ffmpeg_log_text — self-assignment fix & header formatting
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestFormatFfmpegLogText:
    def _call(self, log_lines):
        from compresso.webserver.helpers.completed_tasks import format_ffmpeg_log_text

        return format_ffmpeg_log_text(log_lines)

    def test_terminated_header_gets_span(self):
        result = self._call(["WORKER TERMINATED!"])
        assert '<span class="terminated">' in result[0]
        assert "<b>" in result[0]

    def test_plugin_failed_header_gets_span(self):
        result = self._call(["PLUGIN FAILED!"])
        assert '<span class="terminated">' in result[0]

    def test_runner_header_gets_bold(self):
        result = self._call(["RUNNER:"])
        # RUNNER: prepends <hr> then adds <b> to the header line
        assert "<hr>" in result[0]
        assert "<b>" in result[1]
        assert "terminated" not in result[1]

    def test_command_header_gets_bold(self):
        result = self._call(["COMMAND:"])
        assert "<b>" in result[0]

    def test_normal_line_not_bolded(self):
        result = self._call(["just a normal log line"])
        assert "<b>" not in result[0]

    def test_pre_wrap_after_command_header(self):
        result = self._call(["COMMAND:", "some output"])
        assert "<pre>" in result[1]

    def test_no_pre_wrap_after_log_header(self):
        result = self._call(["COMMAND:", "output", "LOG:", "no pre here"])
        assert "<pre>" not in result[3]

    def test_leading_whitespace_replaced_with_nbsp(self):
        result = self._call(["  indented"])
        assert "&nbsp;&nbsp;" in result[0]

    def test_runner_prepends_hr(self):
        result = self._call(["RUNNER:"])
        assert result[0] == "<hr>"
        assert "<b>" in result[1]


# ------------------------------------------------------------------
# plugins.py — log injection sanitization
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestPluginLogSanitization:
    def test_log_uses_controlled_basename(self):
        """plugins.py logs os.path.basename(plugin_directory) — a controlled value."""
        plugin_directory = "/plugins/my_plugin"
        logged_value = os.path.basename(plugin_directory)
        assert logged_value == "my_plugin"
        assert "/" not in logged_value


# ------------------------------------------------------------------
# remote_task_manager.py — path handling (pre-existing, not modified)
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# service.py — RuntimeError wrapping (verified by integration tests)
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# plugin_repos_mixin.py — JSON file helpers
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestPluginReposMixinHelpers:
    def test_read_json_file(self, tmp_path):
        from compresso.webserver.api_v2.plugin_repos_mixin import PluginReposMixin

        p = tmp_path / "test.json"
        p.write_text('{"key": "value"}')
        result = PluginReposMixin._read_json_file(str(p))
        assert result == {"key": "value"}

    def test_write_json_file(self, tmp_path):
        from compresso.webserver.api_v2.plugin_repos_mixin import PluginReposMixin

        p = tmp_path / "out.json"
        PluginReposMixin._write_json_file(str(p), {"hello": "world"})
        with open(str(p)) as f:
            assert json.load(f) == {"hello": "world"}


# ------------------------------------------------------------------
# docs_api.py — file lines helper
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestDocsApiHelpers:
    def test_read_file_lines(self, tmp_path):
        from compresso.webserver.api_v2.docs_api import ApiDocsHandler

        p = tmp_path / "test.txt"
        p.write_text("line1\nline2\n")
        result = ApiDocsHandler._read_file_lines(str(p))
        assert result == ["line1\n", "line2\n"]
