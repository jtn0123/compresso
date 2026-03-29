#!/usr/bin/env python3

"""
compresso.filebrowser_schemas.py

Marshmallow schemas for file browser API endpoints.
"""

from marshmallow import fields, validate

from compresso.webserver.api_v2.schema.schemas import BaseSchema


class RequestDirectoryListingDataSchema(BaseSchema):
    """Schema for requesting a directory content listing"""

    current_path = fields.Str(
        metadata={"example": "/"},
        load_default="/",
    )
    list_type = fields.Str(
        metadata={"example": "directories"},
        load_default="all",
    )


class DirectoryListingResultsSchema(BaseSchema):
    """Schema for directory listing results returned"""

    directories = fields.List(
        cls_or_instance=fields.Dict,
        required=True,
        metadata={
            "description": "A list of directories in the given path",
            "example": [
                {
                    "value": "home",
                    "label": "/home",
                },
                {
                    "value": "tmp",
                    "label": "/tmp",  # noqa: S108 — UI label for Linux default path
                },
            ],
        },
        validate=validate.Length(min=0),
    )
    files = fields.List(
        cls_or_instance=fields.Dict,
        required=True,
        metadata={
            "description": "A list of files in the given path",
            "example": [
                {
                    "value": "file1.txt",
                    "label": "/file1.txt",
                },
                {
                    "value": "file2.txt",
                    "label": "/file2.txt",
                },
            ],
        },
        validate=validate.Length(min=0),
    )
