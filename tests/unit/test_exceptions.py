#!/usr/bin/env python3

"""
tests.unit.test_exceptions.py

Tests for the custom exception hierarchy in compresso.libs.exceptions.
"""

import pytest

from compresso.libs.exceptions import (
    FileOperationError,
    GuardrailRejectionError,
    PolicyResolutionError,
    PostProcessingError,
    QualityMetricsError,
    TaskMetadataError,
    TaskStagingError,
)


@pytest.mark.unittest
class TestExceptionHierarchy:
    """Verify all custom exceptions descend from PostProcessingError."""

    def test_file_operation_error_is_post_processing(self):
        assert issubclass(FileOperationError, PostProcessingError)

    def test_guardrail_rejection_is_post_processing(self):
        assert issubclass(GuardrailRejectionError, PostProcessingError)

    def test_policy_resolution_is_post_processing(self):
        assert issubclass(PolicyResolutionError, PostProcessingError)

    def test_quality_metrics_is_post_processing(self):
        assert issubclass(QualityMetricsError, PostProcessingError)

    def test_task_metadata_is_post_processing(self):
        assert issubclass(TaskMetadataError, PostProcessingError)

    def test_task_staging_is_post_processing(self):
        assert issubclass(TaskStagingError, PostProcessingError)

    def test_post_processing_error_is_exception(self):
        assert issubclass(PostProcessingError, Exception)

    def test_catch_all_custom_exceptions_with_base(self):
        """A single except PostProcessingError catches all subtypes."""
        for exc_cls in (
            FileOperationError,
            GuardrailRejectionError,
            PolicyResolutionError,
            QualityMetricsError,
            TaskMetadataError,
            TaskStagingError,
        ):
            with pytest.raises(PostProcessingError):
                raise exc_cls("test")

    def test_exception_preserves_message(self):
        err = FileOperationError("copy failed: /src -> /dst")
        assert "copy failed" in str(err)

    def test_exception_chaining(self):
        """Verify from-clause chaining works correctly."""
        original = OSError("disk full")
        try:
            raise FileOperationError("copy failed") from original
        except FileOperationError as chained:
            assert chained.__cause__ is original
