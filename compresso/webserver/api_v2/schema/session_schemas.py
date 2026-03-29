#!/usr/bin/env python3

"""
compresso.session_schemas.py

Marshmallow schemas for session API endpoints.
"""

from marshmallow import fields

from compresso.webserver.api_v2.schema.schemas import BaseSchema


class SessionStateSuccessSchema(BaseSchema):
    """Schema for returning session data"""

    level = fields.Int(
        required=True,
        metadata={"description": "User level", "example": 0},
    )
    picture_uri = fields.Str(
        required=False,
        metadata={"description": "User picture", "example": "https://c8.patreon.com/2/200/561356054"},
    )
    name = fields.Str(
        required=False,
        metadata={"description": "User name", "example": "ExampleUsername123"},
    )
    email = fields.Str(
        required=False,
        metadata={"description": "User email", "example": "example@gmail.com"},
    )
    created = fields.Float(
        required=False,
        metadata={"description": "Session time created", "example": 1627793093.676484},
    )
    uuid = fields.Str(
        required=True,
        metadata={"description": "Installation uuid", "example": "b429fcc7-9ce1-bcb3-2b8a-b094747f226e"},
    )


class SessionAuthCodeSchema(BaseSchema):
    """Schema for returning a verification auth code request"""

    user_code = fields.Str(
        required=True,
        metadata={"description": "The user code", "example": "123456"},
    )
    device_code = fields.Str(
        required=True,
        metadata={
            "description": "A device code",
            "example": "6f6867e0006f7240c9a85703a521f1705873630355f68ebbcf251a07b080172b",
        },
    )
    verification_uri = fields.Str(
        required=True,
        metadata={"description": "The verification URI to submit the code manually", "example": "/support-auth-api/link"},
    )
    verification_uri_complete = fields.Str(
        required=True,
        metadata={"description": "User email", "example": "/support-auth-api/v2/app_auth/link_with_user_code/123456"},
    )
    expires_in = fields.Int(
        required=True,
        metadata={"description": "The time until the user_code expires", "example": 120},
    )
