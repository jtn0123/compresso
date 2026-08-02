#!/usr/bin/env python3

"""
tests.unit.test_api_version_routing.py

API v1 was removed. The router must answer its paths with an explicit 410 so an
un-migrated client can tell a removed version from a mistyped URL, and it must
only ever resolve handler modules for versions on the allowlist — the version
segment comes straight off the request path.
"""

import importlib
from unittest.mock import MagicMock, patch

import pytest

from compresso.webserver.api_request_router import (
    REMOVED_API_VERSIONS,
    SUPPORTED_API_VERSIONS,
    APIRequestRouter,
    Handle404,
    HandleRemovedApiVersion,
)


def _router() -> APIRequestRouter:
    with patch("compresso.webserver.api_request_router.config.Config", return_value=MagicMock()):
        return APIRequestRouter(MagicMock())


def _resolve(path: str) -> type:
    """Return the handler class the router selects for a path."""
    router = _router()
    request = MagicMock()
    request.path = path
    request.headers = {}
    router.app.get_handler_delegate.side_effect = lambda _request, handler, **kwargs: handler
    return router.find_handler(request)


@pytest.mark.unittest
class TestRemovedVersions:
    def test_v1_is_recorded_as_removed_not_supported(self):
        assert "v1" in REMOVED_API_VERSIONS
        assert "v1" not in SUPPORTED_API_VERSIONS

    @pytest.mark.parametrize(
        "module",
        [
            "compresso.webserver.api_v1.base_api_handler",
            "compresso.webserver.api_v1.pending_api",
            "compresso.webserver.api_v1.session_api",
        ],
    )
    def test_v1_handler_modules_are_gone(self, module):
        # Asserting on submodules rather than the package catches a stale
        # __pycache__ directory, which still imports as a namespace package.
        with pytest.raises(ImportError):
            importlib.import_module(module)

    @pytest.mark.parametrize(
        "path",
        [
            "/compresso/api/v1/pending/list",
            "/compresso/api/v1/history/list",
            "/compresso/api/v1/session/state",
        ],
    )
    def test_v1_paths_route_to_the_gone_handler(self, path):
        assert _resolve(path) is HandleRemovedApiVersion


@pytest.mark.unittest
class TestVersionAllowlist:
    def test_v2_still_routes_to_a_real_handler(self):
        handler = _resolve("/compresso/api/v2/pending/list")
        assert handler is not Handle404
        assert handler is not HandleRemovedApiVersion

    @pytest.mark.parametrize(
        "version",
        [
            # A version segment that names another importable module under
            # compresso.webserver must not be turned into an import.
            "request_router",
            "v3",
            "V2",
            "",
            "..",
        ],
    )
    def test_unknown_versions_404_without_resolving_a_handler_module(self, version):
        with patch("compresso.webserver.api_request_router.importlib.import_module") as mock_import:
            assert _resolve(f"/compresso/api/{version}/pending/list") is Handle404

        # `patch` itself imports the module it targets, so only versioned
        # handler packages are interesting here.
        api_imports = [
            call.args[0]
            for call in mock_import.call_args_list
            if call.args and str(call.args[0]).startswith("compresso.webserver.api_v")
        ]
        assert not api_imports, f"unknown version segment reached an import of {api_imports}"
