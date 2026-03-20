#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_schema_generation.py

    Tests for OpenAPI schema generation and Swagger output.

"""

import sys

import pytest
from unittest.mock import patch, MagicMock

# The apispec module may not be installed in the test environment.
# Mock it at the module level if needed.
apispec_available = True
try:
    import apispec  # noqa: F401
except ModuleNotFoundError:
    apispec_available = False


@pytest.mark.unittest
class TestCompressoSpecPlugin:

    @pytest.mark.skipif(not apispec_available, reason="apispec not installed")
    def test_operations_from_urlspec_yields_operations(self):
        from compresso.webserver.api_v2.schema.compresso import CompressoSpecPlugin
        from tornado.web import URLSpec

        handler_class = type('MockHandler', (), {
            'routes': [
                {
                    'path_pattern': r'/test/endpoint',
                    'supported_methods': ['GET'],
                    'call_method': 'get_test',
                },
            ],
        })
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
            pass
        handler_class.get_test = get_test

        urlspec = URLSpec(r'/test/endpoint', handler_class)
        plugin = CompressoSpecPlugin()
        operations = list(plugin._operations_from_urlspec(urlspec))
        assert len(operations) == 1
        assert 'get' in operations[0]
        assert operations[0]['get']['description'] == 'A test endpoint.'

    @pytest.mark.skipif(not apispec_available, reason="apispec not installed")
    def test_operations_from_urlspec_no_match(self):
        from compresso.webserver.api_v2.schema.compresso import CompressoSpecPlugin
        from tornado.web import URLSpec

        handler_class = type('MockHandler', (), {
            'routes': [
                {
                    'path_pattern': r'/other/endpoint',
                    'supported_methods': ['GET'],
                    'call_method': 'get_other',
                },
            ],
            'get_other': lambda self: None,
        })

        urlspec = URLSpec(r'/test/endpoint', handler_class)
        plugin = CompressoSpecPlugin()
        operations = list(plugin._operations_from_urlspec(urlspec))
        assert len(operations) == 0


@pytest.mark.unittest
class TestFindAllHandlers:

    @pytest.mark.skipif(not apispec_available, reason="apispec not installed")
    @patch('compresso.webserver.api_v2.schema.swagger.importlib')
    @patch('compresso.webserver.api_v2.schema.swagger.list_all_handlers')
    def test_returns_handler_route_tuples(self, mock_list_handlers, mock_importlib):
        from compresso.webserver.api_v2.schema.swagger import find_all_handlers

        mock_handler = MagicMock()
        mock_handler.routes = [
            {'path_pattern': r'/test/route', 'supported_methods': ['GET'], 'call_method': 'get_test'},
            {'path_pattern': r'/test/other', 'supported_methods': ['POST'], 'call_method': 'post_test'},
        ]
        mock_list_handlers.return_value = ['MockHandler']

        mock_module = MagicMock()
        setattr(mock_module, 'MockHandler', mock_handler)
        mock_importlib.import_module.return_value = mock_module

        result = find_all_handlers()
        assert len(result) == 2
        assert result[0][0] == r'/test/route'
        assert result[1][0] == r'/test/other'


@pytest.mark.unittest
class TestGenerateSwaggerFile:

    @pytest.mark.skipif(not apispec_available, reason="apispec not installed")
    @patch('compresso.webserver.api_v2.schema.swagger.find_all_handlers', return_value=[])
    @patch('builtins.open', new_callable=MagicMock)
    def test_generates_empty_spec_no_handlers(self, mock_open, _mock_find):
        from compresso.webserver.api_v2.schema.swagger import generate_swagger_file
        errors = generate_swagger_file()
        assert isinstance(errors, list)
        assert len(errors) == 0
        # Should write both JSON and YAML files
        assert mock_open.call_count == 2


@pytest.mark.unittest
class TestSwaggerConstants:

    @pytest.mark.skipif(not apispec_available, reason="apispec not installed")
    def test_api_version_is_string_two(self):
        from compresso.webserver.api_v2.schema.swagger import API_VERSION
        assert API_VERSION == "2"

    @pytest.mark.skipif(not apispec_available, reason="apispec not installed")
    def test_security_spec_contains_basic_auth(self):
        from compresso.webserver.api_v2.schema.swagger import OPENAPI_SPEC_SECURITY
        assert 'BasicAuth' in OPENAPI_SPEC_SECURITY
