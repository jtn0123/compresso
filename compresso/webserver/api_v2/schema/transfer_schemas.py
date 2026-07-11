#!/usr/bin/env python3

from marshmallow import fields, validate

from compresso.webserver.api_v2.schema.schemas import BaseSchema


class RequestTransferSessionSchema(BaseSchema):
    job_id = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    filename = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    total_size = fields.Int(required=True, validate=validate.Range(min=0))
    expected_checksum = fields.Str(required=True, validate=validate.Regexp(r"^sha256:[0-9a-f]{64}$"))
    lease_token = fields.Str(required=False, allow_none=True, validate=validate.Length(min=1, max=128))
    origin_installation_uuid = fields.Str(required=False, allow_none=True, validate=validate.Length(min=1, max=128))
