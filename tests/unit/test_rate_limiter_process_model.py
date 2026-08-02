#!/usr/bin/env python3

"""
tests.unit.test_rate_limiter_process_model.py

The API rate limiter keeps its sliding-window counters in process memory, so
its configured limits are only exact while the UI server runs as a single
process. These tests pin that assumption in place: if the web server ever gains
a pre-forked or multi-instance start path, the limiter has to move to shared
state first, and this suite is what makes that requirement visible.
"""

import ast
import inspect
import pathlib

import pytest

from compresso.libs import uiserver
from compresso.webserver.api_v2.rate_limiter import RateLimiter, get_rate_limiter

# Tornado APIs that hand a listening socket to more than one process.
MULTI_PROCESS_CALLS = frozenset({"fork_processes", "bind_sockets", "start_subprocess"})


def _uiserver_tree() -> ast.Module:
    source = pathlib.Path(inspect.getsourcefile(uiserver) or "").read_text(encoding="utf-8")
    return ast.parse(source)


@pytest.mark.unittest
class TestSingleProcessAssumption:
    def test_uiserver_never_forks_the_listening_socket(self):
        called = set()
        for node in ast.walk(_uiserver_tree()):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in MULTI_PROCESS_CALLS:
                called.add(name)

        assert not called, (
            f"uiserver now calls {sorted(called)}, which serves requests from more than one process. "
            "RateLimiter counters are per-process, so its limits would be multiplied by the process "
            "count. Move the limiter to shared state before landing this."
        )

    def test_uiserver_never_requests_multiple_server_processes(self):
        for node in ast.walk(_uiserver_tree()):
            if isinstance(node, ast.keyword) and node.arg == "num_processes":
                pytest.fail(
                    "uiserver passes num_processes to the HTTP server. RateLimiter counters are "
                    "per-process; move the limiter to shared state before landing this."
                )

    def test_limiter_is_a_process_local_singleton(self):
        """The limiter must stay a single shared instance inside this process."""
        assert get_rate_limiter() is get_rate_limiter()


@pytest.mark.unittest
class TestLimiterCountsPerProcess:
    def test_two_instances_do_not_share_counters(self):
        """Documents the multiplication that a forked server would produce."""
        first = RateLimiter()
        second = RateLimiter()

        for _ in range(RateLimiter.STRICT_LIMIT):
            allowed, _, _ = first.check_rate_limit("10.0.0.1", "/preview/create")
            assert allowed

        blocked, _, _ = first.check_rate_limit("10.0.0.1", "/preview/create")
        assert not blocked

        # A second process would start from an empty window for the same client.
        allowed_again, _, _ = second.check_rate_limit("10.0.0.1", "/preview/create")
        assert allowed_again, "separate limiter instances share no state — this is why one process is required"
