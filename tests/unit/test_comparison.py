#!/usr/bin/env python3

import json
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.comparison import PROFILE_CATALOG, ComparisonManager
from compresso.libs.unmodels import (
    ComparisonBatches,
    ComparisonCandidates,
    Libraries,
    Tags,
    TaskMetadata,
    Tasks,
)
from compresso.libs.unmodels.lib import Database


@pytest.fixture
def comparison_db(tmp_path):
    previous_recovered = ComparisonManager._recovered
    previous_encoder_cache = ComparisonManager._encoder_cache
    database = Database.select_database(
        {
            "TYPE": "SQLITE",
            "FILE": str(tmp_path / "comparison.db"),
            "MIGRATIONS_DIR": str(tmp_path / "migrations"),
        }
    )
    database.create_tables(
        [
            Tags,
            Libraries,
            Tasks,
            TaskMetadata,
            ComparisonBatches,
            ComparisonCandidates,
        ]
    )
    Libraries.create(name="Media", path=str(tmp_path), priority_score=0)
    ComparisonManager._recovered = False
    ComparisonManager._encoder_cache = {profile["encoder"] for profile in PROFILE_CATALOG.values()}
    yield database
    database.close()
    ComparisonManager._recovered = previous_recovered
    ComparisonManager._encoder_cache = previous_encoder_cache


def build_manager(tmp_path):
    settings = MagicMock()
    settings.get_cache_path.return_value = str(tmp_path / "cache")
    with patch("compresso.libs.comparison.config.Config", return_value=settings):
        manager = ComparisonManager()
    manager.settings = settings
    manager.preview_manager = MagicMock()
    return manager


@pytest.mark.unittest
def test_create_batch_persists_two_to_four_candidate_jobs(comparison_db, tmp_path):
    source = tmp_path / "movie.mkv"
    source.write_bytes(b"source")
    manager = build_manager(tmp_path)

    with patch("compresso.libs.comparison.threading.Thread") as thread_class:
        batch_uuid = manager.create_batch(
            str(source),
            start_time=4,
            duration=12,
            library_id=1,
            profile_keys=["x265_crf_22", "svt_av1_crf_30", "x264_crf_23"],
        )

    batch = ComparisonBatches.get(ComparisonBatches.batch_uuid == batch_uuid)
    candidates = list(ComparisonCandidates.select().where(ComparisonCandidates.batch == batch.id))
    assert batch.status == "queued"
    assert [candidate.status for candidate in candidates] == ["queued", "queued", "queued"]
    assert {candidate.profile_key for candidate in candidates} == {
        "x265_crf_22",
        "svt_av1_crf_30",
        "x264_crf_23",
    }
    assert json.loads(candidates[0].options_json)["video_encoder"] == "libx265"
    assert "output_format" not in json.loads(candidates[0].options_json)
    thread_class.return_value.start.assert_called_once_with()


@pytest.mark.unittest
@pytest.mark.parametrize(
    "profile_keys",
    [
        ["x265_crf_22"],
        ["x265_crf_22"] * 2,
        ["x265_crf_22", "unknown_profile"],
    ],
)
def test_create_batch_rejects_invalid_candidate_selection(comparison_db, tmp_path, profile_keys):
    source = tmp_path / "movie.mkv"
    source.write_bytes(b"source")
    manager = build_manager(tmp_path)

    with pytest.raises(ValueError):
        manager.create_batch(str(source), 0, 10, 1, profile_keys)


@pytest.mark.unittest
def test_status_includes_paths_progress_and_quality_metrics(comparison_db, tmp_path):
    batch = ComparisonBatches.create(
        batch_uuid="batch-1",
        source_path=str(tmp_path / "movie.mkv"),
        source_size=1000,
        source_url="/compresso/preview/bakeoff/batch-1/source_reference.mp4",
        status="running",
        progress=50,
    )
    ComparisonCandidates.create(
        batch=batch,
        candidate_uuid="candidate-1",
        profile_key="x265_crf_22",
        profile_label="x265 CRF 22",
        encoder="libx265",
        codec="hevc",
        status="completed",
        progress=100,
        output_path="/cache/sample.mp4",
        output_url="/compresso/preview/bakeoff/batch-1/sample.mp4",
        output_size=600,
        source_size=1000,
        size_saved_bytes=400,
        size_saved_percent=40,
        vmaf_score=95.2,
        ssim_score=0.98,
    )

    status = build_manager(tmp_path).get_batch_status("batch-1")

    assert status["progress"] == 50
    assert status["candidates"][0]["output_path"] == "/cache/sample.mp4"
    assert status["candidates"][0]["size_saved_percent"] == 40
    assert status["candidates"][0]["vmaf_score"] == 95.2


@pytest.mark.unittest
def test_winner_handoff_queues_task_with_scoped_profile_metadata(comparison_db, tmp_path):
    source = tmp_path / "winner.mkv"
    source.write_bytes(b"source")
    batch = ComparisonBatches.create(
        batch_uuid="winner-batch",
        source_path=str(source),
        library_id=1,
        status="completed",
    )
    candidate = ComparisonCandidates.create(
        batch=batch,
        candidate_uuid="winner-candidate",
        profile_key="x265_crf_22",
        profile_label="x265 CRF 22",
        encoder="libx265",
        codec="hevc",
        options_json=json.dumps({"video_encoder": "libx265", "crf": 22}),
        status="completed",
        progress=100,
    )
    manager = build_manager(tmp_path)

    with patch("compresso.libs.task.config.Config", return_value=manager.settings):
        status = manager.select_winner("winner-batch", candidate.candidate_uuid, queue_full_encode=True)

    task = Tasks.get_by_id(status["full_encode_task_id"])
    metadata = TaskMetadata.get(TaskMetadata.task == task.id)
    payload = json.loads(metadata.json_blob)
    assert task.status == "pending"
    assert task.force_local is True
    assert payload["__meta__"]["comparison_profile"]["video_encoder"] == "libx265"
    assert payload["__meta__"]["comparison_batch_uuid"] == "winner-batch"


@pytest.mark.unittest
def test_winner_rejects_an_incomplete_comparison(comparison_db, tmp_path):
    batch = ComparisonBatches.create(
        batch_uuid="running-winner-batch",
        source_path=str(tmp_path / "source.mkv"),
        library_id=1,
        status="running",
    )
    candidate = ComparisonCandidates.create(
        batch=batch,
        candidate_uuid="early-candidate",
        profile_key="x264_crf_23",
        profile_label="x264 CRF 23",
        encoder="libx264",
        codec="h264",
        status="completed",
        progress=100,
    )

    with pytest.raises(ValueError, match="completed comparison"):
        build_manager(tmp_path).select_winner(batch.batch_uuid, candidate.candidate_uuid)


@pytest.mark.unittest
def test_encode_progress_updates_candidate(comparison_db, tmp_path):
    manager = build_manager(tmp_path)
    candidate = MagicMock(progress=1)
    stdout = StringIO("out_time_ms=5000000\nprogress=end\n")
    process = MagicMock(stdout=stdout)
    process.wait.return_value = 0

    with patch("compresso.libs.comparison.subprocess.Popen", return_value=process):
        manager._run_encode_with_progress(["ffmpeg"], candidate, duration=10)

    assert candidate.progress == 37
    assert candidate.save.called


@pytest.mark.unittest
def test_cleanup_refuses_running_batch(comparison_db, tmp_path):
    manager = build_manager(tmp_path)
    ComparisonBatches.create(batch_uuid="running-batch", source_path="/media/a.mkv", status="running")

    with pytest.raises(RuntimeError):
        manager.cleanup_batch("running-batch")
