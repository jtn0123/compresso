#!/usr/bin/env python3

"""
tests.unit.test_route_offload_event_loop.py

Every v2 route body is declared `async def` while doing synchronous DB and file
work, so BaseApiHandler runs them in a worker thread. Driving each one with
`asyncio.run()` built and tore down a fresh event loop per API request; the
worker thread now keeps one reusable loop instead.

These tests pin that behaviour: the loop is per-thread, it is reused across
requests on the same thread, and a body still sees a running loop.
"""

import ast
import asyncio
import inspect
import pathlib
import threading

import pytest

from compresso.webserver.api_v2 import base_api_handler
from compresso.webserver.api_v2.base_api_handler import worker_event_loop


@pytest.fixture(autouse=True)
def clear_thread_loop():
    """Drop any loop this test module leaves on the main thread."""
    yield
    loop = getattr(base_api_handler._offload_thread_state, "loop", None)
    if loop is not None and not loop.is_closed():
        loop.close()
    if hasattr(base_api_handler._offload_thread_state, "loop"):
        del base_api_handler._offload_thread_state.loop


@pytest.mark.unittest
class TestWorkerEventLoop:
    def test_reuses_one_loop_for_repeated_calls_on_a_thread(self):
        assert worker_event_loop() is worker_event_loop()

    def test_gives_each_thread_its_own_loop(self):
        loops: dict[str, asyncio.AbstractEventLoop] = {}
        barrier = threading.Barrier(2)

        def capture(key: str) -> None:
            barrier.wait(timeout=10)
            loops[key] = worker_event_loop()

        threads = [threading.Thread(target=capture, args=(name,)) for name in ("a", "b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert len(loops) == 2
        assert loops["a"] is not loops["b"], "worker threads must not share a loop"

    def test_replaces_a_closed_loop(self):
        first = worker_event_loop()
        first.close()
        second = worker_event_loop()
        assert second is not first
        assert not second.is_closed()

    def test_drives_a_coroutine_to_completion(self):
        async def body() -> str:
            # A body that actually suspends must still work on the shared loop.
            await asyncio.sleep(0)
            return "done"

        loop = worker_event_loop()
        assert loop.run_until_complete(body()) == "done"
        # The same loop is still usable for the next request on this thread.
        assert loop.run_until_complete(body()) == "done"


@pytest.mark.unittest
class TestNoPerRequestLoopConstruction:
    def test_dispatch_no_longer_calls_asyncio_run(self):
        """asyncio.run() builds and destroys a loop; the dispatch path must not use it."""
        source = pathlib.Path(inspect.getsourcefile(base_api_handler) or "").read_text(encoding="utf-8")
        tree = ast.parse(source)

        offenders = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "asyncio"
        ]

        assert not offenders, (
            f"asyncio.run() reintroduced at base_api_handler.py line(s) {offenders}; "
            "use worker_event_loop() so the worker thread reuses one loop per thread."
        )
