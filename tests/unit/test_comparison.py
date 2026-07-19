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
def test_profile_detection_reports_only_installed_encoders(comparison_db):
    ComparisonManager._encoder_cache = None
    result = MagicMock(stdout="V..... libx265\nV..... libx264", stderr="")

    with patch("compresso.libs.comparison.subprocess.run", return_value=result) as run:
        profiles = ComparisonManager.get_profiles()

    availability = {profile["key"]: profile["available"] for profile in profiles}
    assert availability["x265_crf_22"] is True
    assert availability["x264_crf_23"] is True
    assert availability["svt_av1_crf_30"] is False
    run.assert_called_once_with(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.unittest
def test_profile_detection_handles_missing_ffmpeg(comparison_db):
    ComparisonManager._encoder_cache = None

    with patch("compresso.libs.comparison.subprocess.run", side_effect=OSError("missing")):
        assert ComparisonManager._detect_encoders() == set()


@pytest.mark.unittest
def test_recovery_marks_interrupted_batches_and_candidates_failed(comparison_db, tmp_path):
    batch = ComparisonBatches.create(
        batch_uuid="interrupted-batch",
        source_path=str(tmp_path / "movie.mkv"),
        status="running",
    )
    candidate = ComparisonCandidates.create(
        batch=batch,
        candidate_uuid="interrupted-candidate",
        profile_key="x264_crf_23",
        profile_label="x264 CRF 23",
        encoder="libx264",
        codec="h264",
        status="queued",
    )
    ComparisonManager._recovered = False

    ComparisonManager._recover_interrupted_batches_once()
    ComparisonManager._recover_interrupted_batches_once()

    batch = ComparisonBatches.get_by_id(batch.id)
    candidate = ComparisonCandidates.get_by_id(candidate.id)
    assert batch.status == "failed"
    assert "restarted" in batch.error
    assert candidate.status == "failed"
    assert "restarted" in candidate.error


@pytest.mark.unittest
def test_prepare_reference_persists_browser_source_details(comparison_db, tmp_path):
    batch = ComparisonBatches.create(
        batch_uuid="reference-batch",
        source_path=str(tmp_path / "movie.mkv"),
        start_time=3,
        duration=8,
        status="running",
    )
    batch_dir = tmp_path / "bakeoff" / batch.batch_uuid
    batch_dir.mkdir(parents=True)
    (batch_dir / "source_segment.mkv").write_bytes(b"reference-segment")
    manager = build_manager(tmp_path)
    success = MagicMock(returncode=0, stderr="")

    with patch.object(manager, "_run_command", return_value=success) as run:
        segment_path, source_web_path = manager._prepare_reference(batch, str(batch_dir))

    batch = ComparisonBatches.get_by_id(batch.id)
    assert segment_path == str(batch_dir / "source_segment.mkv")
    assert source_web_path == str(batch_dir / "source_reference.mp4")
    assert batch.source_size == len(b"reference-segment")
    assert batch.source_url.endswith("/reference-batch/source_reference.mp4")
    assert batch.progress == 5
    assert run.call_count == 2


@pytest.mark.unittest
def test_run_batch_completes_after_two_successful_candidates(comparison_db, tmp_path):
    batch = ComparisonBatches.create(
        batch_uuid="completed-batch",
        source_path=str(tmp_path / "movie.mkv"),
        status="queued",
    )
    for index, profile_key in enumerate(("x265_crf_22", "x264_crf_23"), start=1):
        profile = PROFILE_CATALOG[profile_key]
        ComparisonCandidates.create(
            batch=batch,
            candidate_uuid=f"completed-candidate-{index}",
            profile_key=profile_key,
            profile_label=profile["label"],
            encoder=profile["encoder"],
            codec=profile["codec"],
            status="queued",
        )
    manager = build_manager(tmp_path)

    def complete_candidate(_batch, candidate, *_args):
        candidate.status = "completed"
        candidate.progress = 100
        candidate.save()

    with (
        patch.object(manager, "_prepare_reference", return_value=("segment.mkv", "reference.mp4")),
        patch.object(manager, "_run_candidate", side_effect=complete_candidate) as run_candidate,
    ):
        manager._run_batch(batch.batch_uuid)

    batch = ComparisonBatches.get_by_id(batch.id)
    assert batch.status == "completed"
    assert batch.progress == 100
    assert run_candidate.call_count == 2


@pytest.mark.unittest
def test_run_batch_marks_queued_candidates_failed_after_reference_error(comparison_db, tmp_path):
    manager = build_manager(tmp_path)
    batch = ComparisonBatches.create(
        batch_uuid="failed-batch",
        source_path=str(tmp_path / "movie.mkv"),
        status="queued",
    )
    candidate = ComparisonCandidates.create(
        batch=batch,
        candidate_uuid="never-started",
        profile_key="x264_crf_23",
        profile_label="x264 CRF 23",
        encoder="libx264",
        codec="h264",
        status="queued",
    )

    with patch.object(manager, "_prepare_reference", side_effect=RuntimeError("reference failed")):
        manager._run_batch(batch.batch_uuid)

    batch = ComparisonBatches.get_by_id(batch.id)
    candidate = ComparisonCandidates.get_by_id(candidate.id)
    assert batch.status == "failed"
    assert batch.error == "reference failed"
    assert candidate.status == "failed"
    assert "before this candidate ran" in candidate.error


@pytest.mark.unittest
def test_candidate_success_persists_size_and_quality_metrics(comparison_db, tmp_path):
    batch = ComparisonBatches.create(
        batch_uuid="metrics-batch",
        source_path=str(tmp_path / "movie.mkv"),
        source_size=1000,
        duration=10,
        status="running",
    )
    candidate = ComparisonCandidates.create(
        batch=batch,
        candidate_uuid="metrics-candidate",
        profile_key="x264_crf_23",
        profile_label="x264 CRF 23",
        encoder="libx264",
        codec="h264",
        status="queued",
    )
    batch_dir = tmp_path / "bakeoff" / batch.batch_uuid
    batch_dir.mkdir(parents=True)
    (batch_dir / "metrics-candidate.mp4").write_bytes(b"x" * 600)
    manager = build_manager(tmp_path)
    manager.preview_manager.compute_quality_metrics.return_value = (95.4, 0.98)
    success = MagicMock(returncode=0, stderr="")

    with (
        patch.object(manager, "_run_encode_with_progress") as encode,
        patch.object(manager, "_run_command", return_value=success),
    ):
        manager._run_candidate(batch, candidate, "segment.mkv", "reference.mp4", str(batch_dir))

    candidate = ComparisonCandidates.get_by_id(candidate.id)
    assert candidate.status == "completed"
    assert candidate.output_size == 600
    assert candidate.size_saved_bytes == 400
    assert candidate.size_saved_percent == 40
    assert candidate.vmaf_score == 95.4
    assert candidate.ssim_score == 0.98
    assert candidate.output_url.endswith("/metrics-candidate-preview.mp4")
    encode.assert_called_once()


@pytest.mark.unittest
def test_candidate_failure_is_persisted_without_stopping_batch(comparison_db, tmp_path):
    batch = ComparisonBatches.create(
        batch_uuid="candidate-failure-batch",
        source_path=str(tmp_path / "movie.mkv"),
        source_size=1000,
        duration=10,
        status="running",
    )
    candidate = ComparisonCandidates.create(
        batch=batch,
        candidate_uuid="failed-candidate",
        profile_key="x264_crf_23",
        profile_label="x264 CRF 23",
        encoder="libx264",
        codec="h264",
        status="queued",
    )
    manager = build_manager(tmp_path)

    with patch.object(manager, "_run_encode_with_progress", side_effect=RuntimeError("encoder failed")):
        manager._run_candidate(batch, candidate, "segment.mkv", "reference.mp4", str(tmp_path))

    candidate = ComparisonCandidates.get_by_id(candidate.id)
    assert candidate.status == "failed"
    assert candidate.error == "encoder failed"


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


@pytest.mark.unittest
def test_cleanup_removes_terminal_batch_and_cached_files(comparison_db, tmp_path):
    manager = build_manager(tmp_path)
    batch = ComparisonBatches.create(
        batch_uuid="cleanup-batch",
        source_path="/media/a.mkv",
        status="completed",
    )
    ComparisonCandidates.create(
        batch=batch,
        candidate_uuid="cleanup-candidate",
        profile_key="x264_crf_23",
        profile_label="x264 CRF 23",
        encoder="libx264",
        codec="h264",
        status="completed",
    )
    batch_dir = tmp_path / "cache" / "preview" / "bakeoff" / batch.batch_uuid
    batch_dir.mkdir(parents=True)
    (batch_dir / "sample.mp4").write_bytes(b"sample")

    assert manager.cleanup_batch(batch.batch_uuid) is True
    assert manager.cleanup_batch("missing-batch") is False
    assert not batch_dir.exists()
    assert ComparisonBatches.get_or_none(ComparisonBatches.id == batch.id) is None
    assert ComparisonCandidates.select().count() == 0
