#!/usr/bin/env python3

"""
compresso.preview.py

Preview engine for A/B comparison of transcoding.
Extracts a short segment from a source file, re-encodes it using
both a high-quality reference and the library's configured pipeline,
then serves both clips for side-by-side comparison.

"""

import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from collections.abc import Mapping, Sequence
from typing import Protocol, TypedDict

from compresso import config
from compresso.libs import narrowing
from compresso.libs.logs import CompressoLogging


class PreviewJob(TypedDict):
    job_id: str
    source_path: str
    start_time: float
    duration: float
    library_id: int
    status: str
    error: str | None
    created_at: float
    job_dir: str
    segment_path: str
    source_web_path: str
    encoded_path: str
    source_size: int
    encoded_size: int
    source_codec: str
    encoded_codec: str
    vmaf_score: float | None
    ssim_score: float | None
    encoded_by_pipeline: bool


class PreviewPluginHandler(Protocol):
    def exec_plugin_runner(self, data: dict[str, object], plugin_id: str, plugin_type: str) -> bool: ...


def _command(value: object) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return []
    return value


class PreviewManager:
    """
    Manages preview job creation, status tracking, and cleanup.
    Only one preview job can run at a time.
    """

    _lock = threading.Lock()
    _current_job: str | None = None
    _jobs: dict[str, PreviewJob] = {}

    MAX_DURATION = 30  # seconds
    MAX_JOB_TIMEOUT = 600  # 10 minutes max per preview job
    CLEANUP_AGE = 86400  # 24 hours in seconds

    def __init__(self) -> None:
        self.logger = CompressoLogging.get_logger(name=type(self).__name__)
        self.settings = config.Config()

    def _run_plugin_pipeline(self, segment_path: str, encoded_path: str, library_id: int) -> bool:
        """
        Run the library's plugin pipeline on a segment to produce an encoded file.

        This is a simplified version of the worker plugin execution loop.

        :param segment_path: Path to the source segment
        :param encoded_path: Desired output path for the encoded file
        :param library_id: Library ID whose plugins to use
        :return: True if pipeline ran successfully, False otherwise
        """
        try:
            from compresso.libs.plugins import PluginsHandler
        except ImportError:
            self.logger.warning("PluginsHandler not available, cannot run plugin pipeline")
            return False

        try:
            plugin_handler = PluginsHandler()
            plugin_modules = plugin_handler.get_enabled_plugin_modules_by_type("worker.process", library_id=library_id)
        except Exception as e:
            self.logger.warning("Failed to load plugins: %s", str(e))
            return False

        if not plugin_modules:
            return False

        return self._execute_preview_pipeline(plugin_handler, plugin_modules, segment_path, encoded_path, library_id)

    def _execute_preview_pipeline(
        self,
        plugin_handler: PreviewPluginHandler,
        plugin_modules: Sequence[Mapping[str, object]],
        segment_path: str,
        encoded_path: str,
        library_id: int,
    ) -> bool:

        data: dict[str, object] = {
            "worker_log": [],
            "library_id": library_id,
            "exec_command": [],
            "current_command": [],
            "command_progress_parser": None,
            "file_in": segment_path,
            "file_out": None,
            "original_file_path": segment_path,
            "repeat": False,
        }

        job_dir = os.path.dirname(encoded_path)
        intermediate_files: list[str] = []
        current_input = segment_path

        try:
            for i, plugin_module in enumerate(plugin_modules):
                _, ext = os.path.splitext(current_input)
                plugin_out = os.path.join(job_dir, f"plugin_{i}{ext}")
                if not self._run_preview_plugin(plugin_handler, plugin_module, data, current_input, plugin_out):
                    return False

                plugin_output = narrowing.strict_str_or_none(data.get("file_out")) or plugin_out
                if os.path.exists(plugin_output):
                    if current_input != segment_path:
                        intermediate_files.append(current_input)
                    current_input = plugin_output

            # Determine the final pipeline output
            pipeline_output = current_input

            ensured_output = self._ensure_preview_mp4(pipeline_output, job_dir)
            if ensured_output is None:
                return False

            # Copy final output to encoded_path
            shutil.copy2(ensured_output, encoded_path)
            return True

        finally:
            # Clean up intermediate files
            for f in intermediate_files:
                try:
                    if os.path.exists(f):
                        os.remove(f)
                except OSError:
                    pass

    def _run_preview_plugin(
        self,
        plugin_handler: PreviewPluginHandler,
        plugin_module: Mapping[str, object],
        data: dict[str, object],
        current_input: str,
        plugin_out: str,
    ) -> bool:
        plugin_id = plugin_module.get("plugin_id")
        if not isinstance(plugin_id, str):
            self.logger.warning("Skipping preview plugin with an invalid plugin ID")
            return False
        data.update({"file_in": current_input, "file_out": plugin_out, "exec_command": [], "repeat": False})
        try:
            plugin_handler.exec_plugin_runner(data, plugin_id, "worker.process")
        except Exception as error:
            self.logger.warning("Plugin %s runner failed: %s", plugin_id, error)
            return False
        command = _command(data.get("exec_command"))
        if not command:
            return True
        try:
            result = subprocess.run(  # noqa: S603 - trusted plugin exec_command from internal pipeline
                command, capture_output=True, text=True, timeout=300
            )
        except subprocess.TimeoutExpired:
            self.logger.warning("Plugin %s command timed out", plugin_id)
            return False
        if result.returncode != 0:
            self.logger.warning("Plugin %s command failed: %s", plugin_id, result.stderr[-500:] if result.stderr else "")
            return False
        return True

    def _ensure_preview_mp4(self, pipeline_output: str, job_dir: str) -> str | None:
        if os.path.splitext(pipeline_output)[1].lower() == ".mp4":
            return pipeline_output
        remux_path = os.path.join(job_dir, "remuxed.mp4")
        remux = ["ffmpeg", "-y", "-i", pipeline_output, "-c:v", "copy", "-c:a", "aac", remux_path]
        result = subprocess.run(  # noqa: S603 - trusted ffmpeg remux command
            remux, capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            return remux_path
        reencode = [
            "ffmpeg",
            "-y",
            "-i",
            pipeline_output,
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            remux_path,
        ]
        result = subprocess.run(  # noqa: S603 - trusted ffmpeg re-encode command
            reencode, capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            return remux_path
        self.logger.warning("Remux/re-encode to MP4 failed: %s", result.stderr[-500:] if result.stderr else "")
        return None

    def get_preview_cache_dir(self) -> str:
        """Get the base directory for preview cache files."""
        cache_path = self.settings.get_cache_path()
        preview_dir = os.path.join(cache_path, "preview")
        os.makedirs(preview_dir, exist_ok=True)
        return preview_dir

    def create_preview(
        self,
        source_path: str,
        start_time: float,
        duration: float,
        library_id: int,
    ) -> str:
        """
        Create a new preview job.

        :param source_path: Absolute path to the source media file
        :param start_time: Start time in seconds
        :param duration: Duration in seconds (max 30)
        :param library_id: Library ID to use for pipeline config
        :return: job_id string
        """
        # Validate inputs
        if not os.path.isfile(source_path):
            raise ValueError(f"Source file does not exist or is not a file: {source_path}")

        if duration > self.MAX_DURATION:
            duration = self.MAX_DURATION

        if duration <= 0:
            raise ValueError("Duration must be positive")

        if start_time < 0:
            start_time = 0

        # Check if a job is already running
        with self._lock:
            current_job = self._jobs.get(self._current_job) if self._current_job else None
            if current_job is not None and current_job["status"] == "running":
                raise RuntimeError("A preview job is already running. Please wait for it to complete.")

        job_id = str(uuid.uuid4())[:8]
        job_dir = os.path.join(self.get_preview_cache_dir(), job_id)
        os.makedirs(job_dir, exist_ok=True)

        job: PreviewJob = {
            "job_id": job_id,
            "source_path": source_path,
            "start_time": start_time,
            "duration": duration,
            "library_id": library_id,
            "status": "running",
            "error": None,
            "created_at": time.time(),
            "job_dir": job_dir,
            "segment_path": os.path.join(job_dir, "segment.mkv"),
            "source_web_path": os.path.join(job_dir, "source_web.mp4"),
            "encoded_path": os.path.join(job_dir, "encoded.mp4"),
            "source_size": 0,
            "encoded_size": 0,
            "source_codec": "",
            "encoded_codec": "",
            "vmaf_score": None,
            "ssim_score": None,
            "encoded_by_pipeline": False,
        }

        with self._lock:
            self._jobs[job_id] = job
            self._current_job = job_id

        # Run the preview generation in a background thread
        thread = threading.Thread(target=self._generate_preview, args=(job_id,), daemon=True)
        thread.start()

        return job_id

    def _check_timeout(self, job_id: str) -> None:
        """Check if a preview job has exceeded MAX_JOB_TIMEOUT and raise if so."""
        job = self._jobs.get(job_id)
        if not job:
            raise RuntimeError(f"Job {job_id} not found")
        elapsed = time.time() - job["created_at"]
        if elapsed > self.MAX_JOB_TIMEOUT:
            raise RuntimeError(f"Preview job {job_id} timed out after {elapsed:.0f}s (limit {self.MAX_JOB_TIMEOUT}s)")

    def _generate_preview(self, job_id: str) -> None:
        """Generate preview clips in a background thread."""
        job = self._jobs.get(job_id)
        if not job:
            return

        try:
            self._generate_preview_files(job_id, job)
            self._update_preview_metrics(job_id, job)
            job["status"] = "ready"
            self.logger.info("Preview [%s]: Complete", job_id)

        except Exception as e:
            self.logger.error("Preview [%s]: Failed - %s", job_id, str(e))
            job["status"] = "failed"
            job["error"] = str(e)
        finally:
            with self._lock:
                if self._current_job == job_id:
                    self._current_job = None

    def _generate_preview_files(self, job_id: str, job: PreviewJob) -> None:
        self._check_timeout(job_id)
        self.logger.info("Preview [%s]: Extracting segment from %s", job_id, job["source_path"])
        self._run_preview_command(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(job["start_time"]),
                "-t",
                str(job["duration"]),
                "-i",
                job["source_path"],
                "-c",
                "copy",
                job["segment_path"],
            ],
            120,
            "Segment extraction failed",
        )
        self._check_timeout(job_id)
        self.logger.info("Preview [%s]: Creating browser-playable source reference", job_id)
        self._run_preview_command(
            [
                "ffmpeg",
                "-y",
                "-i",
                job["segment_path"],
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
                job["source_web_path"],
            ],
            300,
            "Source web encode failed",
        )
        job["encoded_by_pipeline"] = self._encode_preview_comparison(job_id, job)

    def _encode_preview_comparison(self, job_id: str, job: PreviewJob) -> bool:
        self._check_timeout(job_id)
        try:
            if self._run_plugin_pipeline(job["segment_path"], job["encoded_path"], job["library_id"]):
                return True
        except Exception as error:
            self.logger.warning("Preview [%s]: Plugin pipeline failed: %s", job_id, error)
        self.logger.info("Preview [%s]: Falling back to default encode", job_id)
        self._run_preview_command(
            [
                "ffmpeg",
                "-y",
                "-i",
                job["segment_path"],
                "-c:v",
                "libx264",
                "-crf",
                "23",
                "-preset",
                "medium",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                job["encoded_path"],
            ],
            300,
            "Encoded preview failed",
        )
        return False

    @staticmethod
    def _run_preview_command(command: list[str], timeout: int, failure_message: str) -> None:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)  # noqa: S603
        if result.returncode != 0:
            raise RuntimeError(f"{failure_message}: {result.stderr[-500:] if result.stderr else ''}")

    def _update_preview_metrics(self, job_id: str, job: PreviewJob) -> None:
        if os.path.exists(job["source_web_path"]):
            job["source_size"] = os.path.getsize(job["source_web_path"])
        if os.path.exists(job["encoded_path"]):
            job["encoded_size"] = os.path.getsize(job["encoded_path"])
        job["source_codec"] = self._get_video_codec(job["source_path"])
        job["encoded_codec"] = self._get_video_codec(job["encoded_path"])
        self._check_timeout(job_id)
        self.logger.info("Preview [%s]: Computing quality metrics", job_id)
        job["vmaf_score"], job["ssim_score"] = self.compute_quality_metrics(job["source_web_path"], job["encoded_path"])

    def _get_video_codec(self, filepath: str) -> str:
        """Get the video codec of a file using ffprobe."""
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "csv=p=0",
                filepath,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)  # noqa: S603 - trusted ffprobe command built internally
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            self.logger.debug("Codec detection failed for %s: %s", filepath, str(e))
        return ""

    def compute_quality_metrics(self, source_path: str, encoded_path: str) -> tuple[float | None, float | None]:
        """
        Compute VMAF and SSIM quality metrics between source and encoded.
        Returns (vmaf_score, ssim_score) — either can be None if unavailable.

        :param source_path: Path to the source/reference video
        :param encoded_path: Path to the encoded/distorted video
        :return: tuple (float or None, float or None)
        """
        vmaf_score: float | None = None
        ssim_score: float | None = None

        # Try SSIM first (more widely available)
        try:
            ssim_cmd = [
                "ffmpeg",
                "-y",
                "-i",
                encoded_path,
                "-i",
                source_path,
                "-lavfi",
                "[0:v][1:v]ssim",
                "-f",
                "null",
                "-",
            ]
            result = subprocess.run(ssim_cmd, capture_output=True, text=True, timeout=120)  # noqa: S603 - trusted ffmpeg SSIM computation command
            if result.returncode == 0 and result.stderr:
                match = re.search(r"All:(\d+(?:\.\d+)?)", result.stderr)
                if match:
                    ssim_score = float(match.group(1))
        except Exception as e:
            self.logger.debug("SSIM computation failed: %s", str(e))

        # Try VMAF (requires libvmaf)
        try:
            vmaf_cmd = [
                "ffmpeg",
                "-y",
                "-i",
                encoded_path,
                "-i",
                source_path,
                "-lavfi",
                "[0:v][1:v]libvmaf",
                "-f",
                "null",
                "-",
            ]
            result = subprocess.run(vmaf_cmd, capture_output=True, text=True, timeout=300)  # noqa: S603 - trusted ffmpeg VMAF computation command
            if result.returncode == 0 and result.stderr:
                match = re.search(r"VMAF score:\s*(\d+(?:\.\d+)?)", result.stderr)
                if not match:
                    match = re.search(r"vmaf_score:\s*(\d+(?:\.\d+)?)", result.stderr)
                if match:
                    vmaf_score = float(match.group(1))
        except Exception as e:
            self.logger.debug("VMAF computation failed (libvmaf may not be available): %s", str(e))

        return vmaf_score, ssim_score

    def get_job_status(self, job_id: str) -> dict[str, object] | None:
        """
        Get the status of a preview job.

        :param job_id: The job ID
        :return: dict with job status and file URLs
        """
        job = self._jobs.get(job_id)
        if not job:
            return None

        result: dict[str, object] = {
            "job_id": job["job_id"],
            "status": job["status"],
            "error": job["error"],
            "source_size": job.get("source_size", 0),
            "encoded_size": job.get("encoded_size", 0),
            "source_codec": job.get("source_codec", ""),
            "encoded_codec": job.get("encoded_codec", ""),
            "vmaf_score": job.get("vmaf_score"),
            "ssim_score": job.get("ssim_score"),
            "encoded_by_pipeline": job.get("encoded_by_pipeline", False),
        }

        if job["status"] == "ready":
            result["source_url"] = f"/compresso/preview/{job_id}/source_web.mp4"
            result["encoded_url"] = f"/compresso/preview/{job_id}/encoded.mp4"

        return result

    def cleanup_job(self, job_id: str) -> None:
        """
        Clean up a specific preview job's files.

        :param job_id: The job ID
        """
        job = self._jobs.pop(job_id, None)
        if job:
            job_dir = job.get("job_dir")
            if isinstance(job_dir, str) and job_dir and os.path.exists(job_dir):
                shutil.rmtree(job_dir, ignore_errors=True)
                self.logger.info("Preview [%s]: Cleaned up", job_id)

    def cleanup_old_previews(self) -> None:
        """
        Remove preview jobs older than CLEANUP_AGE.
        Called periodically by the scheduler.
        """
        now = time.time()
        expired_ids: list[str] = []

        for job_id, job in list(self._jobs.items()):
            if (now - job.get("created_at", 0)) > self.CLEANUP_AGE:
                expired_ids.append(job_id)

        for job_id in expired_ids:
            self.cleanup_job(job_id)

        # Also clean up any orphaned directories
        preview_dir = self.get_preview_cache_dir()
        if os.path.exists(preview_dir):
            for entry in os.listdir(preview_dir):
                self._cleanup_orphaned_preview(preview_dir, entry, now)

        if expired_ids:
            self.logger.info("Preview: Cleaned up %d expired preview jobs", len(expired_ids))

    def _cleanup_orphaned_preview(self, preview_dir: str, entry: str, now: float) -> None:
        entry_path = os.path.join(preview_dir, entry)
        if not os.path.isdir(entry_path) or entry in self._jobs:
            return
        try:
            if (now - os.path.getmtime(entry_path)) > self.CLEANUP_AGE:
                shutil.rmtree(entry_path, ignore_errors=True)
                self.logger.info("Preview: Cleaned up orphaned directory %s", entry)
        except OSError as e:
            self.logger.debug("Failed to clean up preview directory %s: %s", entry, e)
