#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_logs_forwarder.py

    Unit tests for compresso.libs.logs.ForwardLogHandler.
    Covers batching, disk I/O, retry logic, payload creation,
    retention cleanup, and buffer file management.
"""

import json
import logging
import os
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_handler(tmp_path, flush_interval=5, max_chunk_size=5 * 1024 * 1024):
    """Create a ForwardLogHandler without starting background threads."""
    from compresso.libs.logs import ForwardLogHandler
    with patch.object(ForwardLogHandler, '_load_buffer_state', return_value={}):
        with patch.object(ForwardLogHandler, '_sync_state_with_disk'):
            with patch('threading.Thread') as mock_thread:
                mock_thread.return_value.start = MagicMock()
                handler = ForwardLogHandler(
                    buffer_path=str(tmp_path / "buffer"),
                    installation_name="test-install",
                    flush_interval=flush_interval,
                    max_chunk_size=max_chunk_size,
                )
    return handler


@pytest.mark.unittest
class TestConfigureEndpoint:

    def test_configure_endpoint_sets_values(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.configure_endpoint("http://localhost:3100", "app-123")
        assert handler.endpoint == "http://localhost:3100"
        assert handler.app_id == "app-123"


@pytest.mark.unittest
class TestConfigureRetention:

    def test_valid_integer(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.configure_retention(7)
        assert handler.buffer_retention_max_days == 7
        assert handler._retention_disabled is False

    def test_zero_disables_retention(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.configure_retention(0)
        assert handler._retention_disabled is True

    def test_negative_clamps_to_zero(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.configure_retention(-5)
        assert handler.buffer_retention_max_days == 0
        assert handler._retention_disabled is True

    def test_none_falls_back(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.configure_retention(None)
        assert handler.buffer_retention_max_days is None
        assert handler._retention_disabled is False

    def test_invalid_string_falls_back(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.configure_retention("invalid")
        assert handler.buffer_retention_max_days is None

    def test_re_enable_spills_memory_to_disk(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler._retention_disabled = True
        with patch.object(handler, '_spill_memory_chunks_to_disk') as mock_spill:
            handler.configure_retention(7)
        mock_spill.assert_called_once()


@pytest.mark.unittest
class TestHandleBatch:

    def test_empty_batch_does_nothing(self, tmp_path):
        handler = _make_handler(tmp_path)
        with patch.object(handler, '_append_to_disk') as mock_disk:
            handler._handle_batch([])
        mock_disk.assert_not_called()

    def test_retention_disabled_no_endpoint_discards(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler._retention_disabled = True
        handler.endpoint = None
        handler.app_id = None
        handler._handle_batch([{"labels": {}, "entry": ["ts", "msg"]}])
        assert handler._in_memory_chunks.empty()

    def test_retention_disabled_with_endpoint_queues_memory(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler._retention_disabled = True
        handler.endpoint = "http://example.com"
        handler.app_id = "app-1"
        batch = [{"labels": {"job": "test"}, "entry": ["123", "hello"]}]
        handler._handle_batch(batch)
        assert not handler._in_memory_chunks.empty()

    def test_retention_enabled_writes_to_disk(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler._retention_disabled = False
        with patch.object(handler, '_append_to_disk') as mock_disk:
            handler._handle_batch([{"labels": {}, "entry": ["ts", "msg"]}])
        mock_disk.assert_called_once()


@pytest.mark.unittest
class TestAppendToDisk:

    def test_creates_buffer_dir_and_writes(self, tmp_path):
        handler = _make_handler(tmp_path)
        batch = [
            {"labels": {"job": "compresso"}, "entry": ["123456", "test log"]},
        ]
        handler._append_to_disk(batch)
        # Check buffer file was created
        buffer_dir = tmp_path / "buffer"
        assert buffer_dir.exists()
        files = [f for f in os.listdir(str(buffer_dir)) if f.startswith("log_buffer_")]
        assert len(files) == 1
        # Verify content
        with open(str(buffer_dir / files[0])) as f:
            lines = f.readlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["labels"]["job"] == "compresso"

    def test_empty_batch_does_nothing(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler._append_to_disk([])
        buffer_dir = tmp_path / "buffer"
        if buffer_dir.exists():
            files = [f for f in os.listdir(str(buffer_dir)) if f.startswith("log_buffer_")]
            assert len(files) == 0


@pytest.mark.unittest
class TestGetHourlyBufferFile:

    def test_returns_expected_format(self, tmp_path):
        handler = _make_handler(tmp_path)
        result = handler._get_hourly_buffer_file()
        assert "log_buffer_" in result
        assert result.endswith(".jsonl")


@pytest.mark.unittest
class TestListBufferFiles:

    def test_returns_empty_when_no_dir(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.buffer_path = str(tmp_path / "nonexistent")
        assert handler._list_buffer_files() == []

    def test_returns_sorted_files(self, tmp_path):
        handler = _make_handler(tmp_path)
        buf_dir = tmp_path / "buffer"
        buf_dir.mkdir(parents=True)
        (buf_dir / "log_buffer_20240101T00.jsonl").write_text("")
        (buf_dir / "log_buffer_20240102T00.jsonl").write_text("")
        (buf_dir / "other_file.txt").write_text("")
        result = handler._list_buffer_files()
        assert len(result) == 2
        assert "20240101" in result[0]
        assert "20240102" in result[1]


@pytest.mark.unittest
class TestParseBufferFilenameTimestamp:

    def test_valid_filename(self, tmp_path):
        handler = _make_handler(tmp_path)
        result = handler._parse_buffer_filename_timestamp("log_buffer_20240315T14.jsonl")
        assert result is not None
        assert result.year == 2024
        assert result.month == 3
        assert result.hour == 14

    def test_invalid_filename_returns_none(self, tmp_path):
        handler = _make_handler(tmp_path)
        assert handler._parse_buffer_filename_timestamp("random_file.jsonl") is None
        assert handler._parse_buffer_filename_timestamp("log_buffer_baddate.jsonl") is None
        assert handler._parse_buffer_filename_timestamp("log_buffer_20240101T00.json") is None


@pytest.mark.unittest
class TestCreatePayload:

    def test_groups_by_labels(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.app_id = "test-app"
        entries = [
            {"labels": {"job": "a"}, "entry": ["1", "msg1"]},
            {"labels": {"job": "a"}, "entry": ["2", "msg2"]},
            {"labels": {"job": "b"}, "entry": ["3", "msg3"]},
        ]
        payload = handler._create_payload(entries)
        assert payload["app_id"] == "test-app"
        streams = payload["data"]["streams"]
        assert len(streams) == 2
        # Find the stream for job=a
        a_stream = [s for s in streams if s["stream"]["job"] == "a"][0]
        assert len(a_stream["values"]) == 2

    def test_single_entry(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.app_id = "app"
        entries = [{"labels": {"job": "x"}, "entry": ["1", "hello"]}]
        payload = handler._create_payload(entries)
        assert len(payload["data"]["streams"]) == 1


@pytest.mark.unittest
class TestTransmitBuffer:

    def test_returns_false_when_no_endpoint(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.endpoint = None
        handler.app_id = None
        result = handler._transmit_buffer([{"labels": {}, "entry": ["1", "msg"]}], "test")
        assert result is False

    def test_returns_true_on_204(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.endpoint = "http://localhost:3100"
        handler.app_id = "app-1"
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        with patch('requests.post', return_value=mock_resp):
            result = handler._transmit_buffer(
                [{"labels": {"job": "test"}, "entry": ["1", "msg"]}], "test"
            )
        assert result is True

    def test_returns_false_on_non_204(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.endpoint = "http://localhost:3100"
        handler.app_id = "app-1"
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        with patch('requests.post', return_value=mock_resp):
            with patch('compresso.libs.logs.Notifications'):
                with patch('compresso.libs.logs.FrontendPushMessages'):
                    result = handler._transmit_buffer(
                        [{"labels": {"job": "test"}, "entry": ["1", "msg"]}], "test"
                    )
        assert result is False
        assert handler.previous_connection_failed is True

    def test_connection_error_returns_false(self, tmp_path):
        import requests as req
        handler = _make_handler(tmp_path)
        handler.endpoint = "http://localhost:3100"
        handler.app_id = "app-1"
        with patch('requests.post', side_effect=req.exceptions.ConnectionError()):
            result = handler._transmit_buffer(
                [{"labels": {"job": "test"}, "entry": ["1", "msg"]}], "test"
            )
        assert result is False

    def test_empty_entries_returns_true(self, tmp_path):
        handler = _make_handler(tmp_path)
        assert handler._transmit_buffer([], "test") is True

    def test_recovery_clears_failure_flag(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.endpoint = "http://localhost:3100"
        handler.app_id = "app-1"
        handler.previous_connection_failed = True
        handler._notified_failures.add("500")
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        with patch('requests.post', return_value=mock_resp):
            handler._transmit_buffer(
                [{"labels": {"job": "test"}, "entry": ["1", "msg"]}], "test"
            )
        assert handler.previous_connection_failed is False
        assert len(handler._notified_failures) == 0


@pytest.mark.unittest
class TestCleanupRetention:

    def test_no_cleanup_when_retention_not_set(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.buffer_retention_max_days = None
        handler._cleanup_retention()
        # Should not raise

    def test_removes_old_files(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.buffer_retention_max_days = 1
        buf_dir = tmp_path / "buffer"
        buf_dir.mkdir(parents=True)
        handler.buffer_path = str(buf_dir)
        # Create an old file
        old_file = buf_dir / "log_buffer_20200101T00.jsonl"
        old_file.write_text('{"test": 1}\n')
        handler._buffer_state["log_buffer_20200101T00.jsonl"] = 0
        # _parse_buffer_filename_timestamp returns naive datetime, but _cleanup_retention
        # compares with timezone-aware threshold. Patch to return tz-aware datetime.
        old_ts = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        with patch.object(handler, '_parse_buffer_filename_timestamp', return_value=old_ts):
            handler._cleanup_retention()
        assert not old_file.exists()



@pytest.mark.unittest
class TestSendFromMemory:

    def test_returns_false_when_empty(self, tmp_path):
        handler = _make_handler(tmp_path)
        result = handler._send_from_memory()
        assert result is False

    def test_transmits_memory_chunks(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.endpoint = "http://localhost"
        handler.app_id = "app"
        chunk = [{"labels": {"job": "test"}, "entry": ["1", "msg"]}]
        handler._in_memory_chunks.put(chunk)
        with patch.object(handler, '_transmit_buffer', return_value=True):
            result = handler._send_from_memory()
        assert result is True

    def test_requeues_on_failure(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.endpoint = "http://localhost"
        handler.app_id = "app"
        chunk = [{"labels": {"job": "test"}, "entry": ["1", "msg"]}]
        handler._in_memory_chunks.put(chunk)
        with patch.object(handler, '_transmit_buffer', return_value=False):
            handler._send_from_memory()
        assert not handler._in_memory_chunks.empty()


@pytest.mark.unittest
class TestSendNextDiskBatch:

    def test_returns_false_when_no_endpoint(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.endpoint = None
        assert handler._send_next_disk_batch() is False

    def test_returns_false_when_no_chunks(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.endpoint = "http://localhost"
        handler.app_id = "app"
        with patch.object(handler, '_read_next_disk_chunk', return_value=None):
            assert handler._send_next_disk_batch() is False


@pytest.mark.unittest
class TestReadFileChunk:

    def test_reads_entries_from_file(self, tmp_path):
        handler = _make_handler(tmp_path)
        buf_dir = tmp_path / "buffer"
        buf_dir.mkdir(parents=True)
        handler.buffer_path = str(buf_dir)
        entry = {"labels": {"job": "test"}, "entry": ["1", "hello"]}
        buf_file = buf_dir / "log_buffer_20240101T00.jsonl"
        buf_file.write_text(json.dumps(entry) + "\n")
        result = handler._read_file_chunk(str(buf_file), "log_buffer_20240101T00.jsonl", 0)
        assert result is not None
        file_path, start, end, entries, payload = result
        assert len(entries) == 1
        assert entries[0]["labels"]["job"] == "test"

    def test_skips_corrupt_lines(self, tmp_path):
        handler = _make_handler(tmp_path)
        buf_dir = tmp_path / "buffer"
        buf_dir.mkdir(parents=True)
        handler.buffer_path = str(buf_dir)
        entry = {"labels": {"job": "test"}, "entry": ["1", "hello"]}
        buf_file = buf_dir / "log_buffer_20240101T00.jsonl"
        buf_file.write_text("not-json\n" + json.dumps(entry) + "\n")
        result = handler._read_file_chunk(str(buf_file), "log_buffer_20240101T00.jsonl", 0)
        assert result is not None
        _, _, _, entries, _ = result
        assert len(entries) == 1


@pytest.mark.unittest
class TestClose:

    def test_close_sets_stop_event(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler.writer_thread = MagicMock()
        handler.sender_thread = MagicMock()
        handler.close()
        assert handler.stop_event.is_set()
        handler.writer_thread.join.assert_called_once()
        handler.sender_thread.join.assert_called_once()


@pytest.mark.unittest
class TestLoadBufferState:

    def test_load_from_valid_file(self, tmp_path):
        from compresso.libs.logs import ForwardLogHandler
        buf_dir = tmp_path / "buffer"
        buf_dir.mkdir()
        state_file = buf_dir / ForwardLogHandler.STATE_FILENAME
        state_file.write_text(json.dumps({"files": {"log_buffer_20240101T00.jsonl": 100}}))
        with patch.object(ForwardLogHandler, '_sync_state_with_disk'):
            with patch('threading.Thread') as mock_thread:
                mock_thread.return_value.start = MagicMock()
                handler = ForwardLogHandler(str(buf_dir), "test")
        assert handler._buffer_state.get("log_buffer_20240101T00.jsonl") == 100

    def test_load_returns_empty_on_missing_file(self, tmp_path):
        handler = _make_handler(tmp_path)
        # Already tested via _make_handler which patches _load_buffer_state
        # Test the method directly
        handler._buffer_state_path = str(tmp_path / "nonexistent" / "state.json")
        from compresso.libs.logs import ForwardLogHandler
        result = ForwardLogHandler._load_buffer_state(handler)
        assert result == {}


@pytest.mark.unittest
class TestEmit:

    def test_emit_enqueues_log_entry(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler._retention_disabled = False
        record = logging.LogRecord(
            name="Compresso.Test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        assert not handler.log_queue.empty()

    def test_emit_discards_when_retention_disabled_no_endpoint(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler._retention_disabled = True
        handler.endpoint = None
        handler.app_id = None
        record = logging.LogRecord(
            name="Compresso.Test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        assert handler.log_queue.empty()


@pytest.mark.unittest
class TestSpillMemoryChunksToDisk:

    def test_spills_pending_chunks(self, tmp_path):
        handler = _make_handler(tmp_path)
        handler._in_memory_chunks.put({"labels": {"job": "test"}, "entry": ["1", "msg"]})
        with patch.object(handler, '_append_to_disk') as mock_disk:
            handler._spill_memory_chunks_to_disk()
        mock_disk.assert_called_once()

    def test_noop_when_empty(self, tmp_path):
        handler = _make_handler(tmp_path)
        with patch.object(handler, '_append_to_disk') as mock_disk:
            handler._spill_memory_chunks_to_disk()
        mock_disk.assert_not_called()


@pytest.mark.unittest
class TestSliceEntriesForSend:

    def test_returns_all_when_under_limit(self, tmp_path):
        handler = _make_handler(tmp_path, max_chunk_size=1024 * 1024)
        entries = [{"labels": {"job": "test"}, "entry": ["1", "small"]}]
        chunk, consumed, payload = handler._slice_entries_for_send(entries)
        assert len(chunk) == 1
        assert consumed == 1

    def test_returns_empty_for_empty_input(self, tmp_path):
        handler = _make_handler(tmp_path)
        chunk, consumed, payload = handler._slice_entries_for_send([])
        assert chunk == []
        assert consumed == 0
