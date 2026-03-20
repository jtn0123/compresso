#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_logs_extended.py

    Unit tests for compresso.libs.logs — ForwardJSONFormatter, ForwardLogHandler,
    and CompressoLogging custom methods.
"""

import logging
import time

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_compresso_logging():
    """Reset CompressoLogging singleton state between tests."""
    from compresso.libs.logs import CompressoLogging
    SingletonType._instances = {}
    CompressoLogging._instance = None
    CompressoLogging._configured = False
    CompressoLogging._log_path = None
    CompressoLogging.stream_handler = None
    CompressoLogging.file_handler = None
    CompressoLogging.remote_handler = None
    yield
    SingletonType._instances = {}
    CompressoLogging._instance = None
    CompressoLogging._configured = False
    CompressoLogging._log_path = None
    CompressoLogging.stream_handler = None
    CompressoLogging.file_handler = None
    CompressoLogging.remote_handler = None
    # Clean up any handlers added to the Compresso logger
    root_logger = logging.getLogger("Compresso")
    root_logger.handlers.clear()
    root_logger.setLevel(logging.WARNING)


# ------------------------------------------------------------------
# ForwardJSONFormatter tests
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestForwardJSONFormatter:

    def _make_record(self, name='TestLogger', level=logging.INFO, msg='test message'):
        """Create a LogRecord for testing."""
        record = logging.LogRecord(
            name=name,
            level=level,
            pathname='test.py',
            lineno=42,
            msg=msg,
            args=(),
            exc_info=None,
        )
        return record

    def test_json_record_adds_levelname(self):
        from compresso.libs.logs import ForwardJSONFormatter
        formatter = ForwardJSONFormatter()
        record = self._make_record(level=logging.WARNING)
        extra = {}
        result = formatter.json_record('test message', extra, record)
        assert result['levelname'] == 'WARNING'

    def test_json_record_adds_time(self):
        from compresso.libs.logs import ForwardJSONFormatter
        formatter = ForwardJSONFormatter()
        record = self._make_record()
        extra = {}
        result = formatter.json_record('msg', extra, record)
        assert 'time' in result

    def test_json_record_debug_level_adds_context(self):
        from compresso.libs.logs import ForwardJSONFormatter
        formatter = ForwardJSONFormatter()
        record = self._make_record(name='DebugTest', level=logging.DEBUG)
        # Set the logger's effective level to DEBUG
        logger = logging.getLogger('DebugTest')
        logger.setLevel(logging.DEBUG)
        extra = {}
        result = formatter.json_record('debug msg', extra, record)
        assert 'filename' in result
        assert 'funcName' in result
        assert 'lineno' in result
        assert 'module' in result
        assert 'name' in result
        assert 'thread' in result
        assert 'threadName' in result
        # Restore
        logger.setLevel(logging.WARNING)

    def test_json_record_info_level_no_debug_context(self):
        from compresso.libs.logs import ForwardJSONFormatter
        formatter = ForwardJSONFormatter()
        record = self._make_record(name='InfoTest', level=logging.INFO)
        logger = logging.getLogger('InfoTest')
        logger.setLevel(logging.INFO)
        extra = {}
        result = formatter.json_record('info msg', extra, record)
        assert 'filename' not in result
        assert 'funcName' not in result
        logger.setLevel(logging.WARNING)

    def test_json_record_with_metric_timestamp(self):
        from compresso.libs.logs import ForwardJSONFormatter
        formatter = ForwardJSONFormatter()
        record = self._make_record()
        ts = str(time.time())
        extra = {'metric_timestamp': ts}
        result = formatter.json_record('msg', extra, record)
        assert 'time' in result
        # Should be an ISO format string
        assert isinstance(result['time'], str)
        assert 'T' in result['time']

    def test_json_record_with_data_timestamp(self):
        from compresso.libs.logs import ForwardJSONFormatter
        formatter = ForwardJSONFormatter()
        record = self._make_record()
        ts = str(time.time())
        extra = {'data_timestamp': ts}
        result = formatter.json_record('msg', extra, record)
        assert 'time' in result

    def test_json_record_invalid_timestamp_fallback(self):
        from compresso.libs.logs import ForwardJSONFormatter
        formatter = ForwardJSONFormatter()
        record = self._make_record()
        extra = {'metric_timestamp': 'not_a_number'}
        result = formatter.json_record('msg', extra, record)
        # Should still have a 'time' key (fallback to datetime.now)
        assert 'time' in result


# ------------------------------------------------------------------
# ForwardLogHandler tests
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestForwardLogHandler:

    @pytest.fixture
    def handler(self, tmp_path):
        """Create a ForwardLogHandler with a temp buffer path."""
        from compresso.libs.logs import ForwardLogHandler
        handler = ForwardLogHandler(
            buffer_path=str(tmp_path / 'buffer'),
            installation_name='test-install',
            flush_interval=1,
        )
        yield handler
        handler.stop_event.set()
        handler.log_queue.put(None)
        handler.writer_thread.join(timeout=2)
        handler.sender_thread.join(timeout=2)

    def test_init_creates_handler(self, handler):
        assert handler.installation_name == 'test-install'
        assert handler.endpoint is None
        assert handler.app_id is None

    def test_configure_endpoint(self, handler):
        handler.configure_endpoint('http://example.com', 'app-123')
        assert handler.endpoint == 'http://example.com'
        assert handler.app_id == 'app-123'

    def test_configure_retention_valid(self, handler):
        handler.configure_retention(7)
        assert handler.buffer_retention_max_days == 7
        assert handler._retention_disabled is False

    def test_configure_retention_zero_disables(self, handler):
        handler.configure_retention(0)
        assert handler.buffer_retention_max_days == 0
        assert handler._retention_disabled is True

    def test_configure_retention_none_fallback(self, handler):
        handler.configure_retention(None)
        assert handler.buffer_retention_max_days is None

    def test_configure_retention_invalid_string(self, handler):
        handler.configure_retention('abc')
        assert handler.buffer_retention_max_days is None

    def test_configure_retention_negative_clamped_to_zero(self, handler):
        handler.configure_retention(-5)
        assert handler.buffer_retention_max_days == 0
        assert handler._retention_disabled is True

    def test_emit_discards_when_retention_disabled_no_endpoint(self, handler):
        handler.configure_retention(0)
        handler.configure_endpoint(None, None)
        record = logging.LogRecord(
            name='Test', level=logging.INFO, pathname='t.py',
            lineno=1, msg='test', args=(), exc_info=None,
        )
        handler.emit(record)
        # Should not raise, message is silently discarded
        assert handler.log_queue.qsize() == 0

    def test_emit_enqueues_when_retention_enabled(self, handler):
        handler.configure_retention(7)
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        record = logging.LogRecord(
            name='Test', level=logging.INFO, pathname='t.py',
            lineno=1, msg='queued', args=(), exc_info=None,
        )
        handler.emit(record)
        assert handler.log_queue.qsize() >= 1

    def test_emit_enqueues_when_endpoint_set(self, handler):
        handler.configure_retention(0)
        handler.configure_endpoint('http://example.com', 'app-1')
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        record = logging.LogRecord(
            name='Test', level=logging.INFO, pathname='t.py',
            lineno=1, msg='remote', args=(), exc_info=None,
        )
        handler.emit(record)
        assert handler.log_queue.qsize() >= 1

    def test_create_payload_groups_by_labels(self, handler):
        entries = [
            {'labels': {'service_name': 'compresso', 'level': 'INFO'}, 'entry': ['123', 'msg1']},
            {'labels': {'service_name': 'compresso', 'level': 'INFO'}, 'entry': ['124', 'msg2']},
            {'labels': {'service_name': 'compresso', 'level': 'ERROR'}, 'entry': ['125', 'msg3']},
        ]
        payload = handler._create_payload(entries)
        assert 'app_id' in payload
        assert 'data' in payload
        streams = payload['data']['streams']
        # Two distinct label sets -> two streams
        assert len(streams) == 2

    def test_parse_buffer_filename_timestamp(self, handler):
        ts = handler._parse_buffer_filename_timestamp('log_buffer_20240101T12.jsonl')
        assert ts is not None
        assert ts.year == 2024
        assert ts.month == 1
        assert ts.hour == 12

    def test_parse_buffer_filename_invalid(self, handler):
        assert handler._parse_buffer_filename_timestamp('random_file.txt') is None
        assert handler._parse_buffer_filename_timestamp('log_buffer_invalid.jsonl') is None


# ------------------------------------------------------------------
# CompressoLogging tests
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestCompressoLogging:

    def test_get_logger_returns_logger(self):
        from compresso.libs.logs import CompressoLogging
        logger = CompressoLogging.get_logger(name='TestModule')
        assert logger.name == 'Compresso.TestModule'

    def test_get_logger_without_name_returns_root(self):
        from compresso.libs.logs import CompressoLogging
        logger = CompressoLogging.get_logger()
        assert logger.name == 'Compresso'

    def test_singleton_returns_same_instance(self):
        from compresso.libs.logs import CompressoLogging
        c1 = CompressoLogging()
        c2 = CompressoLogging()
        assert c1 is c2

    def test_enable_debugging_sets_debug_level(self):
        from compresso.libs.logs import CompressoLogging
        instance = CompressoLogging()
        CompressoLogging.enable_debugging()
        assert instance._logger.level == logging.DEBUG

    def test_disable_debugging_sets_info_level(self):
        from compresso.libs.logs import CompressoLogging
        instance = CompressoLogging()
        CompressoLogging.enable_debugging()
        CompressoLogging.disable_debugging()
        assert instance._logger.level == logging.INFO

    def test_metric_logs_at_metric_level(self):
        from compresso.libs.logs import CompressoLogging
        instance = CompressoLogging()
        # Add a handler to capture the log
        captured = []

        class CaptureHandler(logging.Handler):
            def emit(self, record):
                captured.append(record)

        capture = CaptureHandler()
        capture.setLevel(CompressoLogging.METRIC)
        instance._logger.addHandler(capture)
        instance._logger.setLevel(CompressoLogging.DATA)

        ts = datetime(2024, 1, 15, 12, 0, 0)
        CompressoLogging.metric('cpu_usage', timestamp=ts, value=85.5)

        assert len(captured) >= 1
        record = captured[-1]
        assert record.levelno == CompressoLogging.METRIC
        assert 'cpu_usage' in record.getMessage()
        assert hasattr(record, 'log_type')
        assert record.log_type == 'METRIC'

        instance._logger.removeHandler(capture)

    def test_data_logs_at_data_level(self):
        from compresso.libs.logs import CompressoLogging
        instance = CompressoLogging()
        captured = []

        class CaptureHandler(logging.Handler):
            def emit(self, record):
                captured.append(record)

        capture = CaptureHandler()
        capture.setLevel(CompressoLogging.DATA)
        instance._logger.addHandler(capture)
        instance._logger.setLevel(CompressoLogging.DATA)

        ts = datetime(2024, 1, 15, 12, 0, 0)
        CompressoLogging.data('file-abc123', data_search_key='video.mkv', timestamp=ts, status='processed')

        assert len(captured) >= 1
        record = captured[-1]
        assert record.levelno == CompressoLogging.DATA
        assert record.getMessage() == 'DATA STREAM'
        assert record.data_primary_key == 'file-abc123'
        assert record.data_search_key == 'video.mkv'
        assert record.log_type == 'DATA'

        instance._logger.removeHandler(capture)

    def test_metric_without_timestamp_uses_now(self):
        from compresso.libs.logs import CompressoLogging
        instance = CompressoLogging()
        captured = []

        class CaptureHandler(logging.Handler):
            def emit(self, record):
                captured.append(record)

        capture = CaptureHandler()
        capture.setLevel(CompressoLogging.METRIC)
        instance._logger.addHandler(capture)
        instance._logger.setLevel(CompressoLogging.DATA)

        CompressoLogging.metric('test_metric', value=1)
        assert len(captured) >= 1
        assert hasattr(captured[-1], 'metric_timestamp')

        instance._logger.removeHandler(capture)

    def test_data_without_timestamp_uses_now(self):
        from compresso.libs.logs import CompressoLogging
        instance = CompressoLogging()
        captured = []

        class CaptureHandler(logging.Handler):
            def emit(self, record):
                captured.append(record)

        capture = CaptureHandler()
        capture.setLevel(CompressoLogging.DATA)
        instance._logger.addHandler(capture)
        instance._logger.setLevel(CompressoLogging.DATA)

        CompressoLogging.data('pk-1')
        assert len(captured) >= 1
        assert hasattr(captured[-1], 'data_timestamp')

        instance._logger.removeHandler(capture)

    def test_custom_level_names_registered(self):
        from compresso.libs.logs import CompressoLogging
        CompressoLogging()
        assert logging.getLevelName(CompressoLogging.METRIC) == 'METRIC'
        assert logging.getLevelName(CompressoLogging.DATA) == 'DATA'

    def test_configure_sets_up_handlers(self, tmp_path):
        from compresso.libs.logs import CompressoLogging
        instance = CompressoLogging()

        settings = MagicMock()
        settings.get_log_path.return_value = str(tmp_path)
        settings.get_debugging.return_value = False
        settings.get_installation_name.return_value = 'test-install'

        instance.configure(settings)

        assert instance._configured is True
        assert instance.file_handler is not None
        assert instance.remote_handler is not None
        assert instance.stream_handler is not None

        # Clean up the remote handler threads
        instance.remote_handler.stop_event.set()
        instance.remote_handler.log_queue.put(None)
        instance.remote_handler.writer_thread.join(timeout=2)
        instance.remote_handler.sender_thread.join(timeout=2)

    def test_configure_only_runs_once(self, tmp_path):
        from compresso.libs.logs import CompressoLogging
        instance = CompressoLogging()

        settings = MagicMock()
        settings.get_log_path.return_value = str(tmp_path)
        settings.get_debugging.return_value = False
        settings.get_installation_name.return_value = 'test'

        instance.configure(settings)
        first_handler = instance.file_handler
        instance.configure(settings)
        # Handler should not change on second call
        assert instance.file_handler is first_handler

        # Clean up
        instance.remote_handler.stop_event.set()
        instance.remote_handler.log_queue.put(None)
        instance.remote_handler.writer_thread.join(timeout=2)
        instance.remote_handler.sender_thread.join(timeout=2)
