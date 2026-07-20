#!/usr/bin/env python3

"""Persistent 2-4 way sample encode comparisons."""

import datetime
import json
import logging
import os
import shutil
import subprocess
import threading
import time
import uuid

from compresso import config
from compresso.libs.logs import CompressoLogging
from compresso.libs.preview import PreviewManager
from compresso.libs.unmodels import ComparisonBatches, ComparisonCandidates

VIDEO_STREAM_MAP = "0:v:0"
MOVFLAGS_FASTSTART = "+faststart"

PROFILE_CATALOG = {
    "x265_crf_22": {
        "label": "x265 CRF 22",
        "description": "High-quality HEVC software encode",
        "encoder": "libx265",
        "codec": "hevc",
        "crf": 22,
        "preset": "medium",
        "hardware": False,
        "ffmpeg_args": ["-c:v", "libx265", "-crf", "22", "-preset", "medium"],
    },
    "x265_crf_26": {
        "label": "x265 CRF 26",
        "description": "Smaller HEVC software encode",
        "encoder": "libx265",
        "codec": "hevc",
        "crf": 26,
        "preset": "slow",
        "hardware": False,
        "ffmpeg_args": ["-c:v", "libx265", "-crf", "26", "-preset", "slow"],
    },
    "svt_av1_crf_30": {
        "label": "SVT-AV1 CRF 30",
        "description": "Efficient AV1 software encode",
        "encoder": "libsvtav1",
        "codec": "av1",
        "crf": 30,
        "preset": "8",
        "hardware": False,
        "ffmpeg_args": ["-c:v", "libsvtav1", "-crf", "30", "-preset", "8"],
    },
    "amd_amf_hevc_quality": {
        "label": "AMD AMF HEVC Quality",
        "description": "Fast HEVC encode on supported AMD GPUs",
        "encoder": "hevc_amf",
        "codec": "hevc",
        "crf": 24,
        "preset": "quality",
        "hardware": True,
        "ffmpeg_args": ["-c:v", "hevc_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "24", "-qp_p", "24"],
    },
    "x264_crf_23": {
        "label": "x264 CRF 23",
        "description": "Compatible H.264 software baseline",
        "encoder": "libx264",
        "codec": "h264",
        "crf": 23,
        "preset": "medium",
        "hardware": False,
        "ffmpeg_args": ["-c:v", "libx264", "-crf", "23", "-preset", "medium"],
    },
}


class ComparisonManager:
    """Create, execute, inspect, and finalize comparison batches."""

    MAX_DURATION = 30
    MAX_CANDIDATES = 4
    MIN_CANDIDATES = 2
    ENCODE_TIMEOUT = 600
    _encoder_cache = None
    _encoder_lock = threading.Lock()
    _batch_semaphore = threading.Semaphore(1)
    _recovery_lock = threading.Lock()
    _recovered = False

    def __init__(self):
        self.logger = CompressoLogging.get_logger(name=__class__.__name__)
        self.settings = config.Config()
        self.preview_manager = PreviewManager()
        self._recover_interrupted_batches_once()

    @classmethod
    def _detect_encoders(cls):
        with cls._encoder_lock:
            if cls._encoder_cache is not None:
                return cls._encoder_cache
            try:
                result = subprocess.run(
                    ["ffmpeg", "-hide_banner", "-encoders"],  # noqa: S607 - configured media runtime dependency
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                output = f"{result.stdout}\n{result.stderr}"
                cls._encoder_cache = {
                    profile["encoder"] for profile in PROFILE_CATALOG.values() if profile["encoder"] in output
                }
            except (OSError, subprocess.SubprocessError):
                cls._encoder_cache = set()
            return cls._encoder_cache

    @classmethod
    def get_profiles(cls):
        available_encoders = cls._detect_encoders()
        return [
            {
                "key": key,
                "label": profile["label"],
                "description": profile["description"],
                "encoder": profile["encoder"],
                "codec": profile["codec"],
                "crf": profile["crf"],
                "preset": profile["preset"],
                "hardware": profile["hardware"],
                "available": profile["encoder"] in available_encoders,
            }
            for key, profile in PROFILE_CATALOG.items()
        ]

    @classmethod
    def _recover_interrupted_batches_once(cls):
        with cls._recovery_lock:
            if cls._recovered:
                return
            now = datetime.datetime.now()
            try:
                ComparisonCandidates.update(
                    status="failed",
                    error="Compresso restarted before this sample encode completed",
                    completed_at=now,
                ).where(ComparisonCandidates.status.in_(["queued", "running"])).execute()
                ComparisonBatches.update(
                    status="failed",
                    error="Compresso restarted before this comparison completed",
                    updated_at=now,
                ).where(ComparisonBatches.status.in_(["queued", "running"])).execute()
            except Exception:
                # Startup migrations may not have created the tables yet in import-only contexts.
                logging.getLogger(__name__).debug("Comparison recovery deferred until tables exist", exc_info=True)
                return
            cls._recovered = True

    def get_comparison_cache_dir(self):
        comparison_dir = os.path.join(self.settings.get_cache_path(), "preview", "bakeoff")
        os.makedirs(comparison_dir, exist_ok=True)
        return comparison_dir

    def create_batch(self, source_path, start_time, duration, library_id, profile_keys):
        source_path = os.path.realpath(source_path)
        if not os.path.isfile(source_path):
            raise ValueError("Source file does not exist or is not a file")
        if len(profile_keys) < self.MIN_CANDIDATES or len(profile_keys) > self.MAX_CANDIDATES:
            raise ValueError("Select between two and four comparison profiles")
        if len(set(profile_keys)) != len(profile_keys):
            raise ValueError("Comparison profiles must be unique")

        available = {profile["key"] for profile in self.get_profiles() if profile["available"]}
        for profile_key in profile_keys:
            if profile_key not in PROFILE_CATALOG:
                raise ValueError(f"Unknown comparison profile: {profile_key}")
            if profile_key not in available:
                raise ValueError(f"Encoder is not available for profile: {profile_key}")

        duration = min(float(duration), self.MAX_DURATION)
        if duration <= 0:
            raise ValueError("Duration must be positive")
        start_time = max(0, float(start_time))

        batch_uuid = str(uuid.uuid4())
        batch = ComparisonBatches.create(
            batch_uuid=batch_uuid,
            source_path=source_path,
            library_id=library_id,
            start_time=start_time,
            duration=duration,
            status="queued",
        )
        for profile_key in profile_keys:
            profile = PROFILE_CATALOG[profile_key]
            ComparisonCandidates.create(
                batch=batch,
                candidate_uuid=str(uuid.uuid4()),
                profile_key=profile_key,
                profile_label=profile["label"],
                encoder=profile["encoder"],
                codec=profile["codec"],
                options_json=json.dumps(self._task_profile(profile)),
                status="queued",
            )

        thread = threading.Thread(
            target=self._run_batch_guarded,
            args=(batch_uuid,),
            daemon=True,
            name=f"Bakeoff-{batch_uuid[:8]}",
        )
        thread.start()
        return batch_uuid

    def _run_batch_guarded(self, batch_uuid):
        """Keep comparison workloads queued so only one batch encodes at a time."""
        with self._batch_semaphore:
            self._run_batch(batch_uuid)

    @staticmethod
    def _task_profile(profile):
        return {
            "video_codec": profile["codec"],
            "video_encoder": profile["encoder"],
            "crf": profile["crf"],
            "encoder_preset": profile["preset"],
        }

    @staticmethod
    def _run_command(command, timeout):
        return subprocess.run(  # noqa: S603 - commands use validated paths and the static profile catalog
            command, capture_output=True, text=True, timeout=timeout
        )

    def _prepare_reference(self, batch, batch_dir):
        segment_path = os.path.join(batch_dir, "source_segment.mkv")
        source_web_path = os.path.join(batch_dir, "source_reference.mp4")
        extract = self._run_command(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(batch.start_time),
                "-t",
                str(batch.duration),
                "-i",
                batch.source_path,
                "-map",
                VIDEO_STREAM_MAP,
                "-map",
                "0:a?",
                "-c",
                "copy",
                segment_path,
            ],
            120,
        )
        if extract.returncode != 0:
            raise RuntimeError(f"Sample extraction failed: {(extract.stderr or '')[-500:]}")

        reference = self._run_command(
            [
                "ffmpeg",
                "-y",
                "-i",
                segment_path,
                "-map",
                VIDEO_STREAM_MAP,
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-crf",
                "1",
                "-preset",
                "ultrafast",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                MOVFLAGS_FASTSTART,
                source_web_path,
            ],
            300,
        )
        if reference.returncode != 0:
            raise RuntimeError(f"Reference encode failed: {(reference.stderr or '')[-500:]}")

        batch.source_size = os.path.getsize(segment_path)
        batch.source_url = f"/compresso/preview/bakeoff/{batch.batch_uuid}/source_reference.mp4"
        batch.progress = 5
        batch.updated_at = datetime.datetime.now()
        batch.save()
        return segment_path, source_web_path

    def _run_batch(self, batch_uuid):
        batch = ComparisonBatches.get_or_none(ComparisonBatches.batch_uuid == batch_uuid)
        if batch is None:
            return
        batch_dir = os.path.join(self.get_comparison_cache_dir(), batch_uuid)
        os.makedirs(batch_dir, exist_ok=True)
        batch.status = "running"
        batch.updated_at = datetime.datetime.now()
        batch.save()
        try:
            segment_path, source_web_path = self._prepare_reference(batch, batch_dir)
            candidates = list(
                ComparisonCandidates.select().where(ComparisonCandidates.batch == batch.id).order_by(ComparisonCandidates.id)
            )
            for candidate in candidates:
                self._run_candidate(batch, candidate, segment_path, source_web_path, batch_dir)
                self._update_batch_progress(batch)

            completed = (
                ComparisonCandidates.select()
                .where((ComparisonCandidates.batch == batch.id) & (ComparisonCandidates.status == "completed"))
                .count()
            )
            batch.status = "completed" if completed >= self.MIN_CANDIDATES else "failed"
            if batch.status == "failed":
                batch.error = "Fewer than two sample encodes completed successfully"
            batch.progress = 100
            batch.updated_at = datetime.datetime.now()
            batch.save()
        except Exception as exc:
            self.logger.exception("Comparison [%s] failed", batch_uuid)
            ComparisonCandidates.update(
                status="failed",
                error="Comparison stopped before this candidate ran",
                completed_at=datetime.datetime.now(),
            ).where((ComparisonCandidates.batch == batch.id) & (ComparisonCandidates.status == "queued")).execute()
            batch.status = "failed"
            batch.error = str(exc)
            batch.updated_at = datetime.datetime.now()
            batch.save()

    def _run_candidate(self, batch, candidate, segment_path, source_web_path, batch_dir):
        profile = PROFILE_CATALOG[candidate.profile_key]
        output_path = os.path.join(batch_dir, f"{candidate.candidate_uuid}.mp4")
        preview_path = os.path.join(batch_dir, f"{candidate.candidate_uuid}-preview.mp4")
        candidate.status = "running"
        candidate.progress = 1
        candidate.started_at = datetime.datetime.now()
        candidate.output_path = output_path
        candidate.preview_path = preview_path
        candidate.source_size = batch.source_size
        candidate.save()
        try:
            encode_command = [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                segment_path,
                "-map",
                VIDEO_STREAM_MAP,
                "-map",
                "0:a?",
                *profile["ffmpeg_args"],
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                MOVFLAGS_FASTSTART,
                "-progress",
                "pipe:1",
                "-nostats",
                output_path,
            ]
            self._run_encode_with_progress(encode_command, candidate, batch.duration)

            candidate.progress = 78
            candidate.save()
            preview_result = self._run_command(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    output_path,
                    "-map",
                    VIDEO_STREAM_MAP,
                    "-map",
                    "0:a?",
                    "-c:v",
                    "libx264",
                    "-crf",
                    "1",
                    "-preset",
                    "ultrafast",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-movflags",
                    MOVFLAGS_FASTSTART,
                    preview_path,
                ],
                300,
            )
            if preview_result.returncode != 0:
                raise RuntimeError(f"Browser preview failed: {(preview_result.stderr or '')[-500:]}")

            candidate.progress = 88
            candidate.save()
            vmaf_score, ssim_score = self.preview_manager.compute_quality_metrics(source_web_path, output_path)
            output_size = os.path.getsize(output_path)
            saved_bytes = batch.source_size - output_size
            saved_percent = (saved_bytes / batch.source_size * 100) if batch.source_size else 0
            candidate.output_url = f"/compresso/preview/bakeoff/{batch.batch_uuid}/{candidate.candidate_uuid}-preview.mp4"
            candidate.output_size = output_size
            candidate.size_saved_bytes = saved_bytes
            candidate.size_saved_percent = round(saved_percent, 2)
            candidate.vmaf_score = vmaf_score
            candidate.ssim_score = ssim_score
            candidate.progress = 100
            candidate.status = "completed"
            candidate.completed_at = datetime.datetime.now()
            candidate.save()
        except Exception as exc:
            self.logger.error("Comparison candidate [%s] failed: %s", candidate.candidate_uuid, exc)
            candidate.status = "failed"
            candidate.error = str(exc)
            candidate.completed_at = datetime.datetime.now()
            candidate.save()

    def _run_encode_with_progress(self, command, candidate, duration):
        started = time.monotonic()
        process = subprocess.Popen(  # noqa: S603 - command is assembled only from the static profile catalog
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        output_lines = []
        try:
            for raw_line in iter(process.stdout.readline, ""):
                line = raw_line.strip()
                output_lines.append(line)
                if line.startswith("out_time_ms="):
                    try:
                        encoded_seconds = int(line.split("=", 1)[1]) / 1_000_000
                        progress = min(75, max(1, int((encoded_seconds / duration) * 75)))
                        if progress > candidate.progress:
                            candidate.progress = progress
                            candidate.save()
                    except (TypeError, ValueError, ZeroDivisionError):
                        pass
                if (time.monotonic() - started) > self.ENCODE_TIMEOUT:
                    process.kill()
                    raise RuntimeError("Sample encode timed out")
            return_code = process.wait(timeout=10)
        finally:
            if process.stdout:
                process.stdout.close()
        if return_code != 0:
            raise RuntimeError(f"Sample encode failed: {' '.join(output_lines[-10:])[-500:]}")

    @staticmethod
    def _update_batch_progress(batch):
        candidates = ComparisonCandidates.select(ComparisonCandidates.progress).where(ComparisonCandidates.batch == batch.id)
        progress_values = [row.progress for row in candidates]
        batch.progress = round(sum(progress_values) / len(progress_values), 2) if progress_values else 0
        batch.updated_at = datetime.datetime.now()
        batch.save()

    def get_batch_status(self, batch_uuid):
        batch = ComparisonBatches.get_or_none(ComparisonBatches.batch_uuid == batch_uuid)
        if batch is None:
            return None
        candidates = (
            ComparisonCandidates.select().where(ComparisonCandidates.batch == batch.id).order_by(ComparisonCandidates.id)
        )
        return {
            "batch_uuid": batch.batch_uuid,
            "source_path": batch.source_path,
            "source_size": batch.source_size,
            "source_url": batch.source_url,
            "library_id": batch.library_id,
            "start_time": batch.start_time,
            "duration": batch.duration,
            "status": batch.status,
            "progress": batch.progress,
            "winner_candidate_id": batch.winner_candidate_id,
            "full_encode_task_id": batch.full_encode_task_id,
            "error": batch.error,
            "candidates": [self._serialize_candidate(candidate) for candidate in candidates],
        }

    @staticmethod
    def _serialize_candidate(candidate):
        return {
            "id": candidate.id,
            "candidate_uuid": candidate.candidate_uuid,
            "profile_key": candidate.profile_key,
            "profile_label": candidate.profile_label,
            "encoder": candidate.encoder,
            "codec": candidate.codec,
            "status": candidate.status,
            "progress": candidate.progress,
            "output_path": candidate.output_path,
            "output_url": candidate.output_url,
            "output_size": candidate.output_size,
            "source_size": candidate.source_size,
            "size_saved_bytes": candidate.size_saved_bytes,
            "size_saved_percent": candidate.size_saved_percent,
            "vmaf_score": candidate.vmaf_score,
            "ssim_score": candidate.ssim_score,
            "error": candidate.error,
        }

    def select_winner(self, batch_uuid, candidate_uuid, queue_full_encode=False):
        batch = ComparisonBatches.get_or_none(ComparisonBatches.batch_uuid == batch_uuid)
        if batch is None:
            raise ValueError("Comparison batch not found")
        if batch.status != "completed":
            raise ValueError("A winner can only be selected from a completed comparison")
        candidate = ComparisonCandidates.get_or_none(
            (ComparisonCandidates.batch == batch.id) & (ComparisonCandidates.candidate_uuid == candidate_uuid)
        )
        if candidate is None or candidate.status != "completed":
            raise ValueError("Only a completed candidate can be selected")

        batch.winner_candidate_id = candidate.id
        batch.updated_at = datetime.datetime.now()
        if queue_full_encode and batch.full_encode_task_id is None:
            from compresso.webserver.helpers import pending_tasks

            task_metadata = {
                "__meta__": {
                    "comparison_profile": json.loads(candidate.options_json),
                    "comparison_batch_uuid": batch.batch_uuid,
                    "comparison_candidate_uuid": candidate.candidate_uuid,
                }
            }
            task_info = pending_tasks.create_task(
                batch.source_path,
                library_id=batch.library_id,
                task_metadata=task_metadata,
                force_local=True,
            )
            if not task_info:
                raise RuntimeError("This source file is already queued or being processed")
            batch.full_encode_task_id = task_info["id"]
        batch.save()
        return self.get_batch_status(batch_uuid)

    def cleanup_batch(self, batch_uuid):
        batch = ComparisonBatches.get_or_none(ComparisonBatches.batch_uuid == batch_uuid)
        if batch is None:
            return False
        if batch.status in {"queued", "running"}:
            raise RuntimeError("A running comparison cannot be cleaned up")
        batch_dir = os.path.join(self.get_comparison_cache_dir(), batch_uuid)
        shutil.rmtree(batch_dir, ignore_errors=True)
        batch.delete_instance(recursive=True)
        return True
