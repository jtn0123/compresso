#!/usr/bin/env python3

"""
compresso.notification_schemas.py

Marshmallow schemas for notification API endpoints.
"""

from marshmallow import fields, validate

from compresso.webserver.api_v2.schema.schemas import BaseSchema


class NotificationDataSchema(BaseSchema):
    """Schema for notification data"""

    uuid = fields.Str(
        required=True,
        metadata={"description": "Unique ID for this notification", "example": "updateAvailable"},
    )
    type = fields.Str(
        required=True,
        metadata={"description": "The type of notification", "example": "info"},
    )
    icon = fields.Str(
        required=True,
        metadata={"description": "The icon to display with the notification", "example": "update"},
    )
    label = fields.Str(
        required=True,
        metadata={
            "description": "The label of the notification. Can be a I18n key or a string",
            "example": "updateAvailableLabel",
        },
    )
    message = fields.Str(
        required=True,
        metadata={
            "description": "The message of the notification. Can be a I18n key or a string",
            "example": "updateAvailableMessage",
        },
    )
    navigation = fields.Dict(
        required=True,
        metadata={
            "description": "The navigation links of the notification",
            "example": {"url": "https://github.com/jtn0123/compresso"},
        },
    )


class RequestNotificationsDataSchema(BaseSchema):
    """Schema for returning the current list of notifications"""

    notifications = fields.Nested(
        NotificationDataSchema,
        required=True,
        metadata={"description": "List of notifications"},
        many=True,
        validate=validate.Length(min=0),
    )
