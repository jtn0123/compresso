#!/usr/bin/env python3

"""
compresso.system_schemas.py

Marshmallow schemas for system status API endpoints.
"""

from marshmallow import fields

from compresso.webserver.api_v2.schema.schemas import BaseSchema


class SystemStatusCpuSchema(BaseSchema):
    """Schema for CPU info within system status"""

    count = fields.Int(required=True, metadata={"description": "Number of CPU cores", "example": 8})
    percent = fields.Float(required=True, metadata={"description": "Current CPU usage percentage", "example": 42.5})
    brand = fields.Str(required=True, metadata={"description": "CPU brand string", "example": "Apple M2 Pro"})


class SystemStatusMemorySchema(BaseSchema):
    """Schema for memory info within system status"""

    total_gb = fields.Float(required=True, metadata={"description": "Total RAM in GB", "example": 32.0})
    used_gb = fields.Float(required=True, metadata={"description": "Used RAM in GB", "example": 18.4})
    percent = fields.Float(required=True, metadata={"description": "RAM usage percentage", "example": 57.5})


class SystemStatusDiskSchema(BaseSchema):
    """Schema for disk info within system status"""

    total_gb = fields.Float(required=True, metadata={"description": "Total disk in GB", "example": 1000.0})
    used_gb = fields.Float(required=True, metadata={"description": "Used disk in GB", "example": 650.0})
    percent = fields.Float(required=True, metadata={"description": "Disk usage percentage", "example": 65.0})
    path = fields.Str(required=True, metadata={"description": "Disk mount path", "example": "/"})


class SystemStatusGpuSchema(BaseSchema):
    """Schema for GPU info within system status"""

    type = fields.Str(required=True, metadata={"description": "GPU type", "example": "nvidia"})
    name = fields.Str(required=True, metadata={"description": "GPU name", "example": "RTX 3080"})
    memory_total_mb = fields.Int(required=True, metadata={"description": "GPU memory in MB", "example": 10240})
    driver_version = fields.Str(required=True, metadata={"description": "GPU driver version", "example": "535.129.03"})


class SystemStatusPlatformSchema(BaseSchema):
    """Schema for platform info within system status"""

    system = fields.Str(required=True, metadata={"description": "Operating system", "example": "Linux"})
    node = fields.Str(required=True, metadata={"description": "Hostname", "example": "media-server"})
    release = fields.Str(required=True, metadata={"description": "Kernel release", "example": "6.1.0"})


class SystemStatusSuccessSchema(BaseSchema):
    """Schema for returning system status metrics"""

    cpu = fields.Nested(SystemStatusCpuSchema, required=True)
    memory = fields.Nested(SystemStatusMemorySchema, required=True)
    disk = fields.Nested(SystemStatusDiskSchema, required=True)
    gpus = fields.List(fields.Nested(SystemStatusGpuSchema), required=True)
    platform = fields.Nested(SystemStatusPlatformSchema, required=True)
    uptime_seconds = fields.Int(required=True, metadata={"description": "System uptime in seconds", "example": 86400})
