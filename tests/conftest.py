#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    compresso.conftest.py

    Written by:               Josh.5 <jsunnex@gmail.com>
    Date:                     05 May 2020, (7:09 AM)

    Copyright:
           Copyright (C) Josh Sunnex - All Rights Reserved

           Permission is hereby granted, free of charge, to any person obtaining a copy
           of this software and associated documentation files (the "Software"), to deal
           in the Software without restriction, including without limitation the rights
           to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
           copies of the Software, and to permit persons to whom the Software is
           furnished to do so, subject to the following conditions:

           The above copyright notice and this permission notice shall be included in all
           copies or substantial portions of the Software.

           THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
           EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
           MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
           IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
           DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
           OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
           OR OTHER DEALINGS IN THE SOFTWARE.

"""

import gc
import logging
import os
import shutil
import sys
import tempfile
import threading
import warnings

import pytest
from unittest.mock import patch

from compresso.libs.unmodels.lib import Database
from compresso.libs.unmodels import Libraries, Tags
from compresso.libs.unmodels.tasks import Tasks
from compresso.libs.unmodels.workergroups import WorkerGroups, WorkerGroupTags
from compresso.libs.unmodels.workerschedules import WorkerSchedules

LibraryTags = Libraries.tags.get_through_model()


def _is_compresso_thread(thread):
    module = getattr(thread.__class__, "__module__", "")
    return module.startswith("compresso.")


def _stop_thread_if_supported(thread):
    if hasattr(thread, "stop"):
        try:
            thread.stop()
        except Exception as exc:
            warnings.warn("Failed to stop leaked thread {}: {}".format(thread.name, exc), RuntimeWarning)

    redundant_flag = getattr(thread, "redundant_flag", None)
    if redundant_flag is not None and hasattr(redundant_flag, "set"):
        redundant_flag.set()

    paused_flag = getattr(thread, "paused_flag", None)
    if paused_flag is not None and hasattr(paused_flag, "clear"):
        paused_flag.clear()

    event = getattr(thread, "event", None)
    if event is not None and hasattr(event, "set"):
        try:
            event.set()
        except Exception:
            pass

    try:
        thread.join(timeout=1)
    except Exception as exc:
        warnings.warn("Failed to join leaked thread {}: {}".format(thread.name, exc), RuntimeWarning)


def pytest_configure(config):
    """
    Custom pytest markers to separate the tests

    :param config:
    :return:
    """
    config.addinivalue_line("markers", "unittest: Unit tests.")
    config.addinivalue_line("markers", "integrationtest: Integration test.")


@pytest.fixture(autouse=sys.version_info >= (3, 13))
def collect_cyclic_garbage():
    """
    Python 3.13 builds large cyclic graphs during long pytest runs in this
    suite. Collecting after each test keeps memory bounded and avoids the
    late-session GC stalls we were seeing around handler-heavy files.
    """
    yield
    gc.collect()


@pytest.fixture(autouse=True)
def cleanup_compresso_threads():
    """
    Ensure tests do not leak long-lived Compresso threads into later tests.
    Those leaks are especially expensive in long Python 3.13 runs where they
    keep large object graphs reachable and amplify GC pauses.
    """
    baseline = {thread.ident for thread in threading.enumerate()}
    yield

    for thread in list(threading.enumerate()):
        if thread.ident in baseline:
            continue
        if thread is threading.main_thread():
            continue
        if not thread.is_alive():
            continue
        if not _is_compresso_thread(thread):
            continue
        _stop_thread_if_supported(thread)

    gc.collect()


@pytest.fixture
def tmp_config():
    path = tempfile.mkdtemp(prefix='compresso_test_')
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def mock_logging():
    logger = logging.getLogger('compresso_test')
    with patch('compresso.libs.logs.CompressoLogging.get_logger', return_value=logger):
        yield logger


@pytest.fixture
def in_memory_db(tmp_config):
    db_file = os.path.join(tmp_config, 'test.db')
    database_settings = {
        "TYPE": "SQLITE",
        "FILE": db_file,
        "MIGRATIONS_DIR": os.path.join(tmp_config, 'migrations'),
    }
    db_connection = Database.select_database(database_settings)
    db_connection.create_tables([
        Tasks,
        Libraries,
        LibraryTags,
        Tags,
        WorkerGroups,
        WorkerGroupTags,
        WorkerSchedules,
    ])
    db_connection.execute_sql('SELECT 1')
    yield db_connection
    db_connection.close()
