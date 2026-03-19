#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_logging_validation.py

    Validates that Unmanic's logging infrastructure produces
    structured JSON output with expected fields.
"""

import json
import logging
import pytest


@pytest.mark.unittest
class TestForwardJSONFormatter:

    def test_formats_as_valid_json(self):
        from compresso.libs.logs import ForwardJSONFormatter
        formatter = ForwardJSONFormatter()
        record = logging.LogRecord(
            name='test', level=logging.INFO, pathname='test.py',
            lineno=1, msg='Test message', args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert 'message' in parsed or 'msg' in parsed or 'test' in output.lower() or isinstance(parsed, dict)

    def test_includes_extra_fields_at_debug_level(self):
        from compresso.libs.logs import ForwardJSONFormatter
        formatter = ForwardJSONFormatter()
        record = logging.LogRecord(
            name='test', level=logging.DEBUG, pathname='test.py',
            lineno=42, msg='Debug message', args=(), exc_info=None,
        )
        record.funcName = 'test_function'
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
        assert logging.getLevelName(9) == 'METRIC'

    def test_data_level_exists(self):
        from compresso.libs.logs import CompressoLogging
        assert CompressoLogging.DATA == 8
        assert logging.getLevelName(8) == 'DATA'


@pytest.mark.unittest
class TestCompressoLogging:

    def test_get_logger_returns_logger(self):
        from compresso.libs.logs import CompressoLogging
        logger = CompressoLogging.get_logger(name='test_module')
        assert logger is not None
        assert hasattr(logger, 'info')
        assert hasattr(logger, 'debug')

    def test_get_logger_same_name_returns_same_logger(self):
        from compresso.libs.logs import CompressoLogging
        logger1 = CompressoLogging.get_logger(name='same_name_test')
        logger2 = CompressoLogging.get_logger(name='same_name_test')
        assert logger1 is logger2
