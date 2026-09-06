"""Regression coverage for comparison handoff and response contracts."""

from unittest.mock import MagicMock, patch

import pytest

from compresso.bundled_plugins.encoding_presets import plugin
from compresso.libs.exceptions import TaskError
from compresso.libs.task import load_task_metadata
from compresso.webserver.api_v2.schema.comparison_schemas import (
    ComparisonCandidateSchema,
    ComparisonStatusResponseSchema,
)


@pytest.mark.parametrize("payload", ["broken", "[]", "null"])
def test_worker_metadata_read_rejects_corrupt_rows(payload):
    with (
        patch("compresso.libs.unmodels.TaskMetadata.get_or_none", return_value=MagicMock(json_blob=payload)),
        pytest.raises(TaskError, match="metadata"),
    ):
        load_task_metadata(42, strict=True)


def test_worker_metadata_read_rejects_database_failure():
    with patch("compresso.libs.unmodels.TaskMetadata.get_or_none", side_effect=RuntimeError("table unavailable")):
        with pytest.raises(TaskError, match="metadata"):
            load_task_metadata(42, strict=True)
        assert load_task_metadata(42) == {}


def test_task_profile_does_not_silently_ignore_a_read_failure():
    with (
        patch("compresso.libs.unmodels.TaskMetadata.get_or_none", side_effect=RuntimeError("table unavailable")),
        pytest.raises(TaskError, match="metadata"),
    ):
        plugin._load_task_profile_override(42)


@pytest.mark.parametrize(
    "preset,expected", [("medium", "balanced"), ("fast", "speed"), ("slow", "quality"), ("quality", "quality")]
)
def test_generic_amf_presets_use_native_quality_tokens(preset, expected):
    command = []
    plugin._append_video_settings(command, {"video_encoder": "hevc_amf", "encoder_preset": preset})
    assert command[command.index("-quality") + 1] == expected


def test_response_schemas_emit_defaults_when_optional_fields_are_missing():
    for schema in [ComparisonCandidateSchema(), ComparisonStatusResponseSchema()]:
        result = schema.dump({})
        assert result["source_size"] == 0
        assert result["error"] is None
    candidate = ComparisonCandidateSchema().dump({})
    assert candidate["output_url"] == ""
    assert candidate["vmaf_score"] is None
    batch = ComparisonStatusResponseSchema().dump({})
    assert batch["source_url"] == ""
    assert batch["winner_candidate_id"] is None
    assert batch["full_encode_task_id"] is None
