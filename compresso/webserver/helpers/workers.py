#!/usr/bin/env python3

"""
compresso.workers.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     11 Aug 2021, (10:45 AM)

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

from compresso.libs.foreman import Foreman
from compresso.libs.uiserver import CompressoRunningThreads


def _foreman() -> Foreman:
    foreman = CompressoRunningThreads().get_compresso_running_thread("foreman")
    if foreman is None:
        raise RuntimeError("Foreman thread is not registered")
    return foreman


def pause_worker_by_id(worker_id: str) -> bool:
    """
    Pause a worker given that worker's ID

    :param worker_id:
    :return:
    """
    return _foreman().pause_worker_thread(worker_id)


def pause_all_workers() -> bool:
    """
    Pause all workers

    :return:
    """
    return _foreman().pause_all_worker_threads()


def resume_worker_by_id(worker_id: str) -> bool:
    """
    Resume a worker given that worker's ID

    :param worker_id:
    :return:
    """
    return _foreman().resume_worker_thread(worker_id)


def resume_all_workers() -> bool:
    """
    Resume all workers

    :return:
    """
    return _foreman().resume_all_worker_threads()


def terminate_worker_by_id(worker_id: str) -> bool:
    """
    Terminate a worker given that worker's ID

    :param worker_id:
    :return:
    """
    return _foreman().terminate_worker_thread(worker_id)


def terminate_all_workers() -> bool:
    """
    Terminate all workers

    :return:
    """
    return _foreman().terminate_all_worker_threads()
