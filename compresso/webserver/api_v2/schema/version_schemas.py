#!/usr/bin/env python3

"""
compresso.version_schemas.py

Marshmallow schemas for version API endpoints.
"""

from marshmallow import fields

from compresso.webserver.api_v2.schema.schemas import BaseSchema


class VersionReadSuccessSchema(BaseSchema):
    """Schema for returning the application version"""

    version = fields.Str(
        required=True,
        metadata={"description": "Application version", "example": "1.0.0"},
    )
