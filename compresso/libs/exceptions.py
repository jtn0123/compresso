#!/usr/bin/env python3

"""
compresso.libs.exceptions.py

Custom exception hierarchy for the post-processing pipeline.
Replaces bare ``except Exception`` blocks in postprocessor.py with
specific, identifiable exception types.
"""


class PostProcessingError(Exception):
    """Base for all post-processing errors."""


class FileOperationError(PostProcessingError):
    """File copy/move/delete failures (OSError, PermissionError, shutil.Error)."""


class GuardrailRejectionError(PostProcessingError):
    """Task rejected by size/quality guardrails."""


class PolicyResolutionError(PostProcessingError):
    """Could not determine replacement policy from library config."""


class TaskStagingError(PostProcessingError):
    """Failed to stage file for approval or finalization."""


class QualityMetricsError(PostProcessingError):
    """Quality score computation (ffprobe/VMAF/SSIM) failed."""


class TaskMetadataError(PostProcessingError):
    """Failed to write/commit task metadata or history log."""
