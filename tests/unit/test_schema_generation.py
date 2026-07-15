#!/usr/bin/env python3

"""
tests.unit.test_schema_generation.py

Tests for OpenAPI schema generation and Swagger output.

"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# The apispec module may not be installed in the test environment.
# Mock it at the module level if needed.
apispec_available = True
try:
    import apispec  # noqa: F401
except ModuleNotFoundError:
    apispec_available = False


@pytest.mark.unittest
def test_checked_in_schema_contains_bounded_resumable_transfer_contract():
    schema_path = Path(__file__).parents[2] / "compresso" / "webserver" / "docs" / "api_schema_v2.json"
    paths = json.loads(schema_path.read_text(encoding="utf-8"))["paths"]

    assert "507" in paths["/transfer/session"]["post"]["responses"]
    assert "delete" in paths["/transfer/session/{transfer_id}"]
    assert paths["/upload/pending/file"]["post"]["deprecated"] is True
    assert "410" in paths["/upload/pending/file"]["post"]["responses"]
    assert "413" in paths["/upload/plugin/file"]["post"]["responses"]


@pytest.mark.unittest
def test_checked_in_schema_documents_health_discovery_and_terminal_state():
    schema_path = Path(__file__).parents[2] / "compresso" / "webserver" / "docs" / "api_schema_v2.json"
    schemas = json.loads(schema_path.read_text(encoding="utf-8"))["components"]["schemas"]
    progress = schemas["HealthCheckProgress"]["properties"]

    assert {
        "phase",
        "discovered",
        "discovery_complete",
        "cancelled",
        "error",
    }.issubset(progress)
    assert schemas["HealthCheckSummaryResponse"]["properties"]["scan_progress"] == {
        "$ref": "#/components/schemas/HealthCheckProgress"
    }


@pytest.mark.unittest
class TestCompressoSpecPlugin:
    @pytest.mark.skipif(not apispec_available, reason="apispec not installed")
    def test_operations_from_urlspec_yields_operations(self):
        from tornado.web import URLSpec

        from compresso.webserver.api_v2.schema.compresso import CompressoSpecPlugin

        handler_class = type(
            "MockHandler",
            (),
            {
                "routes": [
                    {
                        "path_pattern": r"/test/endpoint",
                        "supported_methods": ["GET"],
                        "call_method": "get_test",
                    },
                ],
            },
        )

        # Add a method with a YAML docstring
        def get_test(self):
            """
            Test endpoint
            ---
            description: A test endpoint.
            responses:
                200:
                    description: Success
            """

        handler_class.get_test = get_test

        urlspec = URLSpec(r"/test/endpoint", handler_class)
        plugin = CompressoSpecPlugin()
        operations = list(plugin._operations_from_urlspec(urlspec))
        assert len(operations) == 1
        assert "get" in operations[0]
        assert operations[0]["get"]["description"] == "A test endpoint."

    @pytest.mark.skipif(not apispec_available, reason="apispec not installed")
    def test_operations_from_urlspec_no_match(self):
        from tornado.web import URLSpec

        from compresso.webserver.api_v2.schema.compresso import CompressoSpecPlugin

        handler_class = type(
            "MockHandler",
            (),
            {
                "routes": [
                    {
                        "path_pattern": r"/other/endpoint",
                        "supported_methods": ["GET"],
                        "call_method": "get_other",
                    },
                ],
                "get_other": lambda self: None,
            },
        )

        urlspec = URLSpec(r"/test/endpoint", handler_class)
        plugin = CompressoSpecPlugin()
        operations = list(plugin._operations_from_urlspec(urlspec))
        assert len(operations) == 0


@pytest.mark.unittest
class TestFindAllHandlers:
    @pytest.mark.skipif(not apispec_available, reason="apispec not installed")
    def test_returns_handler_route_tuples(self):
        from compresso.webserver.api_v2.schema.swagger import find_all_handlers

        mock_handler = MagicMock()
        mock_handler.routes = [
            {"path_pattern": r"/test/route", "supported_methods": ["GET"], "call_method": "get_test"},
            {"path_pattern": r"/test/other", "supported_methods": ["POST"], "call_method": "post_test"},
        ]

        mock_module = MagicMock()
        mock_module.MockHandler = mock_handler
        mock_importlib = MagicMock()
        mock_importlib.import_module.return_value = mock_module

        with patch.dict(
            find_all_handlers.__globals__,
            {
                "list_all_handlers": MagicMock(return_value=["MockHandler"]),
                "importlib": mock_importlib,
            },
        ):
            result = find_all_handlers()

        assert len(result) == 2
        assert result[0][0] == r"/test/route"
        assert result[1][0] == r"/test/other"


@pytest.mark.unittest
class TestGenerateSwaggerFile:
    @pytest.mark.skipif(not apispec_available, reason="apispec not installed")
    @patch("compresso.webserver.api_v2.schema.swagger.find_all_handlers", return_value=[])
    @patch("builtins.open", new_callable=MagicMock)
    def test_generates_empty_spec_no_handlers(self, mock_open, _mock_find):
        from compresso.webserver.api_v2.schema.swagger import generate_swagger_file

        errors = generate_swagger_file()
        assert isinstance(errors, list)
        assert len(errors) == 0
        # Only the JSON spec is written now — the unused .yaml sidecar
        # was removed in v2.0-prep.
        assert mock_open.call_count == 1


@pytest.mark.unittest
class TestSwaggerConstants:
    @pytest.mark.skipif(not apispec_available, reason="apispec not installed")
    def test_api_version_is_string_two(self):
        from compresso.webserver.api_v2.schema.swagger import API_VERSION

        assert API_VERSION == "2"

    @pytest.mark.skipif(not apispec_available, reason="apispec not installed")
    def test_security_spec_contains_basic_auth(self):
        # OPENAPI_SPEC_SECURITY is a Python dict now (was a YAML string
        # parsed at import time). Walk into the structure rather than
        # relying on string containment.
        from compresso.webserver.api_v2.schema.swagger import OPENAPI_SPEC_SECURITY

        assert "BasicAuth" in OPENAPI_SPEC_SECURITY["components"]["securitySchemes"]
        assert OPENAPI_SPEC_SECURITY["components"]["securitySchemes"]["BasicAuth"]["scheme"] == "basic"
        assert {"BasicAuth": []} in OPENAPI_SPEC_SECURITY["security"]
        assert OPENAPI_SPEC_SECURITY["components"]["securitySchemes"]["ApiToken"] == {
            "type": "apiKey",
            "in": "header",
            "name": "X-Compresso-Api-Token",
        }
        assert {"ApiToken": []} in OPENAPI_SPEC_SECURITY["security"]
