#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_openapi_validation.py

    Validates that the OpenAPI schema generation produces
    a structurally valid OpenAPI 3.0 spec.
    Requires apispec: pip install apispec apispec-webframeworks
"""

import pytest

try:
    from apispec import APISpec
    from apispec.ext.marshmallow import MarshmallowPlugin
    HAS_APISPEC = True
except ImportError:
    HAS_APISPEC = False


@pytest.mark.unittest
class TestSwaggerSpecGeneration:

    @pytest.mark.skipif(not HAS_APISPEC, reason="apispec not installed")
    def test_apispec_produces_valid_spec(self):
        """Verify apispec produces a valid OpenAPI 3.0 structure."""
        spec = APISpec(
            title="Unmanic API",
            version="2.0.0",
            openapi_version="3.0.0",
        )
        d = spec.to_dict()
        assert d['info']['title'] == "Unmanic API"
        assert d['openapi'] == "3.0.0"
        assert 'paths' in d
        assert 'info' in d

    @pytest.mark.skipif(not HAS_APISPEC, reason="apispec not installed")
    def test_marshmallow_plugin_loadable(self):
        """Verify MarshmallowPlugin integrates with APISpec."""
        spec = APISpec(
            title="Test",
            version="1.0.0",
            openapi_version="3.0.0",
            plugins=[MarshmallowPlugin()],
        )
        assert spec.to_dict() is not None

    def test_schema_modules_importable(self):
        """Verify our schema modules can be imported."""
        from compresso.webserver.api_v2.schema import schemas
        assert hasattr(schemas, 'RequestTableDataSchema')
