#!/usr/bin/env python3

"""
tests.unit.test_openapi_validation.py

Validates that the OpenAPI schema generation produces
a structurally valid OpenAPI 3.0 spec.
Requires apispec: pip install apispec apispec-webframeworks
"""

import pytest
from marshmallow import ValidationError

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
            title="Compresso API",
            version="2.0.0",
            openapi_version="3.0.0",
        )
        d = spec.to_dict()
        assert d["info"]["title"] == "Compresso API"
        assert d["openapi"] == "3.0.0"
        assert "paths" in d
        assert "info" in d

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

        assert hasattr(schemas, "RequestTableDataSchema")

    @pytest.mark.parametrize("payload", [{"start": -1}, {"length": 0}, {"length": 1001}])
    def test_table_schema_rejects_unsafe_pagination(self, payload):
        from compresso.webserver.api_v2.schema.schemas import RequestTableDataSchema

        with pytest.raises(ValidationError):
            RequestTableDataSchema().load(payload)

    @pytest.mark.parametrize("payload", [{"start": -1}, {"length": 0}, {"length": 1001}])
    def test_approval_schema_rejects_unsafe_pagination(self, payload):
        from compresso.webserver.api_v2.schema.approval_schemas import RequestApprovalTasksSchema

        with pytest.raises(ValidationError):
            RequestApprovalTasksSchema().load(payload)

    def test_pending_create_schema_rejects_unknown_task_type(self):
        from compresso.webserver.api_v2.schema.pending_schemas import RequestPendingTaskCreateSchema

        with pytest.raises(ValidationError):
            RequestPendingTaskCreateSchema().load({"path": "/media/video.mkv", "type": "mystery"})
