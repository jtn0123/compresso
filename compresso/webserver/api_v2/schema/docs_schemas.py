#!/usr/bin/env python3

"""
compresso.docs_schemas.py

Marshmallow schemas for documentation API endpoints.
"""

from marshmallow import fields, validate

from compresso.webserver.api_v2.schema.schemas import BaseSchema


class DocumentContentSuccessSchema(BaseSchema):
    """Schema for updating tables by ID"""

    content = fields.List(
        cls_or_instance=fields.Str,
        required=True,
        metadata={
            "description": "Document contents read line-by-line into a list",
            "example": [
                "First line\n",
                "Second line\n",
                "\n",
            ],
        },
        validate=validate.Length(min=1),
    )
