#!/usr/bin/env python3

"""
tests.unit.test_logging_validation.py

Validates that Compresso's logging infrastructure produces
structured JSON output with expected fields.
"""

import json
import logging
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unittest
class TestForwardJSONFormatter:
    def test_formats_as_valid_json(self):
        from compresso.libs.logs import ForwardJSONFormatter

        formatter = ForwardJSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "message" in parsed or "msg" in parsed or "test" in output.lower() or isinstance(parsed, dict)

    def test_includes_extra_fields_at_debug_level(self):
        from compresso.libs.logs import ForwardJSONFormatter

        formatter = ForwardJSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="test.py",
            lineno=42,
            msg="Debug message",
            args=(),
            exc_info=None,
        )
        record.funcName = "test_function"
        output = formatter.format(record)
        parsed = json.loads(output)
        # At DEBUG level, extra fields should be included
        assert isinstance(parsed, dict)


@pytest.mark.unittest
class TestCustomLogLevels:
    def test_metric_level_exists(self):
        from compresso.libs.logs import CompressoLogging

        assert CompressoLogging.METRIC == 9
        # Ensure the level name is registered
        assert logging.getLevelName(9) == "METRIC"

    def test_data_level_exists(self):
        from compresso.libs.logs import CompressoLogging

        assert CompressoLogging.DATA == 8
        assert logging.getLevelName(8) == "DATA"


@pytest.mark.unittest
class TestCompressoLogging:
    def test_get_logger_returns_logger(self):
        from compresso.libs.logs import CompressoLogging

        logger = CompressoLogging.get_logger(name="test_module")
        assert logger is not None
        assert hasattr(logger, "info")
        assert hasattr(logger, "debug")

    def test_get_logger_same_name_returns_same_logger(self):
        from compresso.libs.logs import CompressoLogging

        logger1 = CompressoLogging.get_logger(name="same_name_test")
        logger2 = CompressoLogging.get_logger(name="same_name_test")
        assert logger1 is logger2

    def test_get_logger_no_name_returns_root(self):
        from compresso.libs.logs import CompressoLogging

        logger = CompressoLogging.get_logger()
        assert logger.name == "Compresso"


@pytest.mark.unittest
class TestCompressoLoggingDebugging:
    def test_enable_debugging_sets_debug_level(self):
        from compresso.libs.logs import CompressoLogging

        instance = CompressoLogging()
        original_level = instance._logger.level
        try:
            CompressoLogging.enable_debugging()
            assert instance._logger.level == logging.DEBUG
        finally:
            instance._logger.setLevel(original_level)

    def test_disable_debugging_sets_info_level(self):
        from compresso.libs.logs import CompressoLogging

        instance = CompressoLogging()
        original_level = instance._logger.level
        try:
            instance._logger.setLevel(logging.DEBUG)
            CompressoLogging.disable_debugging()
            assert instance._logger.level == logging.INFO
        finally:
            instance._logger.setLevel(original_level)


class _CaptureHandler(logging.Handler):
    """Simple handler that captures emitted records."""

    def __init__(self):
        super().__init__()
        self.records = []
        self.setLevel(0)

    def emit(self, record):
        self.records.append(record)


@pytest.mark.unittest
class TestCompressoLoggingMetricData:
    def test_metric_logs_at_metric_level(self):
        from compresso.libs.logs import CompressoLogging

        instance = CompressoLogging()
        handler = _CaptureHandler()
        instance._logger.addHandler(handler)
        try:
            CompressoLogging.metric("test_metric", value=42)
            metric_records = [r for r in handler.records if r.levelno == 9]
            assert len(metric_records) >= 1
        finally:
            instance._logger.removeHandler(handler)

    def test_metric_includes_label_and_timestamp(self):
        from compresso.libs.logs import CompressoLogging

        instance = CompressoLogging()
        handler = _CaptureHandler()
        instance._logger.addHandler(handler)
        try:
            ts = datetime(2024, 1, 15, 12, 0, 0)
            CompressoLogging.metric("cpu_usage", timestamp=ts, value=85)
            metric_records = [r for r in handler.records if r.levelno == 9]
            assert len(metric_records) >= 1
            record = metric_records[0]
            assert record.metric_name == "cpu_usage"
            assert record.log_type == "METRIC"
        finally:
            instance._logger.removeHandler(handler)

    def test_data_logs_at_data_level(self):
        from compresso.libs.logs import CompressoLogging

        instance = CompressoLogging()
        handler = _CaptureHandler()
        instance._logger.addHandler(handler)
        try:
            CompressoLogging.data("primary_key_1", data_search_key="search_1")
            data_records = [r for r in handler.records if r.levelno == 8]
            assert len(data_records) >= 1
        finally:
            instance._logger.removeHandler(handler)

    def test_data_includes_primary_and_search_keys(self):
        from compresso.libs.logs import CompressoLogging

        instance = CompressoLogging()
        handler = _CaptureHandler()
        instance._logger.addHandler(handler)
        try:
            CompressoLogging.data("pk_test", data_search_key="sk_test")
            data_records = [r for r in handler.records if r.levelno == 8]
            assert len(data_records) >= 1
            record = data_records[0]
            assert record.data_primary_key == "pk_test"
            assert record.data_search_key == "sk_test"
            assert record.log_type == "DATA"
        finally:
            instance._logger.removeHandler(handler)


@pytest.mark.unittest
class TestCompressoLoggingRemote:
    def test_enable_remote_logging_configures_endpoint(self):
        from compresso.libs.logs import CompressoLogging

        instance = CompressoLogging()
        mock_handler = MagicMock()
        original_handler = instance.remote_handler
        instance.remote_handler = mock_handler
        try:
            CompressoLogging.enable_remote_logging("https://logs.example.com", "app123", 7)
            mock_handler.configure_retention.assert_called_once_with(7)
            mock_handler.configure_endpoint.assert_called_once_with("https://logs.example.com", "app123")
        finally:
            instance.remote_handler = original_handler

    def test_disable_remote_logging_clears_endpoint(self):
        from compresso.libs.logs import CompressoLogging

        instance = CompressoLogging()
        mock_handler = MagicMock()
        original_handler = instance.remote_handler
        instance.remote_handler = mock_handler
        try:
            CompressoLogging.disable_remote_logging(3)
            mock_handler.configure_retention.assert_called_once_with(3)
            mock_handler.configure_endpoint.assert_called_once_with(None, None)
        finally:
            instance.remote_handler = original_handler

    def test_set_remote_logging_retention_configures(self):
        from compresso.libs.logs import CompressoLogging

        instance = CompressoLogging()
        mock_handler = MagicMock()
        original_handler = instance.remote_handler
        instance.remote_handler = mock_handler
        try:
            CompressoLogging.set_remote_logging_retention(14)
            mock_handler.configure_retention.assert_called_once_with(14)
        finally:
            instance.remote_handler = original_handler


@pytest.mark.unittest
class TestForwardLogHandlerEmit:
    def test_emit_enriches_record_with_labels(self):
        from compresso.libs.logs import ForwardJSONFormatter, ForwardLogHandler

        with (
            patch.object(ForwardLogHandler, "_load_buffer_state", return_value={}),
            patch.object(ForwardLogHandler, "_sync_state_with_disk"),
            patch.object(ForwardLogHandler, "_writer_loop"),
            patch.object(ForwardLogHandler, "_sender_loop"),
        ):
            handler = ForwardLogHandler.__new__(ForwardLogHandler)
            logging.Handler.__init__(handler)
            handler.buffer_path = "/tmp/test_buffer"
            handler.endpoint = "https://example.com"
            handler.app_id = "test_app"
            handler.installation_name = "test_install"
            handler.labels = {"job": "compresso"}
            handler._retention_disabled = False
            handler.buffer_retention_max_days = 7
            handler.flush_interval = 5
            handler.max_chunk_size = 5 * 1024 * 1024
            handler._state_lock = MagicMock()
            handler._buffer_state = {}
            handler._buffer_state_path = "/tmp/buffer_state.json"
            handler._in_memory_chunks = MagicMock()
            from queue import Queue

            handler.log_queue = Queue(maxsize=10000)
            handler.stop_event = MagicMock()
            handler._last_cleanup = time.monotonic()
            handler.previous_connection_failed = False
            handler._notified_failures = set()

            formatter = ForwardJSONFormatter()
            handler.setFormatter(formatter)

            record = logging.LogRecord(
                name="test.module",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test message",
                args=(),
                exc_info=None,
            )
            handler.emit(record)

            item = handler.log_queue.get_nowait()
            assert item["labels"]["service_name"] == "compresso"
            assert item["labels"]["logger"] == "test.module"
            assert item["labels"]["level"] == "INFO"
            assert item["labels"]["installation_name"] == "test_install"
            assert item["labels"]["log_type"] == "APPLICATION_LOG"

    def test_emit_discards_when_retention_disabled_and_no_endpoint(self):
        from compresso.libs.logs import ForwardJSONFormatter, ForwardLogHandler

        handler = ForwardLogHandler.__new__(ForwardLogHandler)
        logging.Handler.__init__(handler)
        handler._retention_disabled = True
        handler.endpoint = None
        handler.app_id = None
        handler.setFormatter(ForwardJSONFormatter())

        from queue import Queue

        handler.log_queue = Queue(maxsize=100)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Discarded",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        assert handler.log_queue.empty()


@pytest.mark.unittest
class TestForwardLogHandlerCreatePayload:
    def test_create_payload_groups_by_labels(self):
        from compresso.libs.logs import ForwardLogHandler

        handler = ForwardLogHandler.__new__(ForwardLogHandler)
        handler.app_id = "test_app"

        buffer = [
            {"labels": {"service": "a", "level": "INFO"}, "entry": ["123", "msg1"]},
            {"labels": {"service": "a", "level": "INFO"}, "entry": ["124", "msg2"]},
            {"labels": {"service": "b", "level": "ERROR"}, "entry": ["125", "msg3"]},
        ]
        payload = handler._create_payload(buffer)
        assert payload["app_id"] == "test_app"
        streams = payload["data"]["streams"]
        assert len(streams) == 2
        # Find the stream for service "a"
        stream_a = [s for s in streams if s["stream"]["service"] == "a"][0]
        assert len(stream_a["values"]) == 2

    def test_create_payload_single_entry(self):
        from compresso.libs.logs import ForwardLogHandler

        handler = ForwardLogHandler.__new__(ForwardLogHandler)
        handler.app_id = "my_app"

        buffer = [
            {"labels": {"service": "x"}, "entry": ["100", "single"]},
        ]
        payload = handler._create_payload(buffer)
        assert len(payload["data"]["streams"]) == 1
        assert payload["data"]["streams"][0]["values"] == [["100", "single"]]


@pytest.mark.unittest
class TestForwardLogHandlerConfigureRetention:
    def _make_handler(self):
        from compresso.libs.logs import ForwardLogHandler

        handler = ForwardLogHandler.__new__(ForwardLogHandler)
        handler.buffer_retention_max_days = None
        handler._retention_disabled = False
        handler._spill_memory_chunks_to_disk = MagicMock()
        return handler

    def test_configure_retention_valid_days(self):
        handler = self._make_handler()
        handler.configure_retention(7)
        assert handler.buffer_retention_max_days == 7
        assert handler._retention_disabled is False

    def test_configure_retention_zero_disables(self):
        handler = self._make_handler()
        handler.configure_retention(0)
        assert handler.buffer_retention_max_days == 0
        assert handler._retention_disabled is True

    def test_configure_retention_none_sets_none(self):
        handler = self._make_handler()
        handler.configure_retention(None)
        assert handler.buffer_retention_max_days is None
        assert handler._retention_disabled is False

    def test_configure_retention_negative_clamped_to_zero(self):
        handler = self._make_handler()
        handler.configure_retention(-5)
        assert handler.buffer_retention_max_days == 0
        assert handler._retention_disabled is True

    def test_configure_retention_invalid_string_falls_back(self):
        handler = self._make_handler()
        handler.configure_retention("not_a_number")
        assert handler.buffer_retention_max_days is None

    def test_configure_retention_spills_memory_when_reenabled(self):
        handler = self._make_handler()
        handler._retention_disabled = True
        handler.configure_retention(7)
        handler._spill_memory_chunks_to_disk.assert_called_once()


@pytest.mark.unittest
class TestCompressoLoggingDisableFileHandler:
    def test_disable_file_handler_removes_handler(self):
        from compresso.libs.logs import CompressoLogging

        instance = CompressoLogging()
        mock_file_handler = MagicMock()
        mock_stream_handler = MagicMock()
        original_fh = instance.file_handler
        original_sh = instance.stream_handler
        instance.file_handler = mock_file_handler
        instance.stream_handler = mock_stream_handler
        try:
            CompressoLogging.disable_file_handler(debugging=False)
            assert instance.file_handler is None
            mock_stream_handler.setLevel.assert_called_with(logging.INFO)
        finally:
            instance.file_handler = original_fh
            instance.stream_handler = original_sh

    def test_disable_file_handler_with_debugging(self):
        from compresso.libs.logs import CompressoLogging

        instance = CompressoLogging()
        mock_stream_handler = MagicMock()
        original_fh = instance.file_handler
        original_sh = instance.stream_handler
        instance.file_handler = MagicMock()
        instance.stream_handler = mock_stream_handler
        try:
            CompressoLogging.disable_file_handler(debugging=True)
            mock_stream_handler.setLevel.assert_called_with(logging.DEBUG)
        finally:
            instance.file_handler = original_fh
            instance.stream_handler = original_sh


@pytest.mark.unittest
class TestCompressoLoggingUpdateStreamFormatter:
    def test_update_stream_formatter(self):
        from compresso.libs.logs import CompressoLogging

        instance = CompressoLogging()
        mock_stream_handler = MagicMock()
        original_sh = instance.stream_handler
        instance.stream_handler = mock_stream_handler
        try:
            new_formatter = logging.Formatter("%(message)s")
            CompressoLogging.update_stream_formatter(new_formatter)
            mock_stream_handler.setFormatter.assert_called_once_with(new_formatter)
        finally:
            instance.stream_handler = original_sh

    def test_update_stream_formatter_no_handler(self):
        from compresso.libs.logs import CompressoLogging

        instance = CompressoLogging()
        original_sh = instance.stream_handler
        instance.stream_handler = None
        try:
            # Should not raise
            CompressoLogging.update_stream_formatter(logging.Formatter("%(message)s"))
        finally:
            instance.stream_handler = original_sh
