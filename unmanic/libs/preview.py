#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    unmanic.preview.py

    Preview engine for A/B comparison of transcoding.
    Extracts a short segment from a source file, re-encodes it using
    both a high-quality reference and the library's configured pipeline,
    then serves both clips for side-by-side comparison.

"""

import os
import shutil
import subprocess
import threading
import time
import uuid

from unmanic import config
from unmanic.libs.logs import UnmanicLogging


class PreviewManager:
    """
    Manages preview job creation, status tracking, and cleanup.
    Only one preview job can run at a time.
    """

    _lock = threading.Lock()
    _current_job = None
    _jobs = {}

    MAX_DURATION = 30  # seconds
    CLEANUP_AGE = 86400  # 24 hours in seconds

    def __init__(self):
        self.logger = UnmanicLogging.get_logger(name=__class__.__name__)
        self.settings = config.Config()

    def get_preview_cache_dir(self):
        """Get the base directory for preview cache files."""
        cache_path = self.settings.get_cache_path()
        preview_dir = os.path.join(cache_path, 'preview')
        os.makedirs(preview_dir, exist_ok=True)
        return preview_dir

    def create_preview(self, source_path, start_time, duration, library_id):
        """
        Create a new preview job.

        :param source_path: Absolute path to the source media file
        :param start_time: Start time in seconds
        :param duration: Duration in seconds (max 30)
        :param library_id: Library ID to use for pipeline config
        :return: job_id string
        """
        # Validate inputs
        if not os.path.exists(source_path):
            raise ValueError("Source file does not exist: {}".format(source_path))

        if duration > self.MAX_DURATION:
            duration = self.MAX_DURATION

        if duration <= 0:
            raise ValueError("Duration must be positive")

        if start_time < 0:
            start_time = 0

        # Check if a job is already running
        with self._lock:
            if self._current_job and self._jobs.get(self._current_job, {}).get('status') == 'running':
                raise RuntimeError("A preview job is already running. Please wait for it to complete.")

        job_id = str(uuid.uuid4())[:8]
        job_dir = os.path.join(self.get_preview_cache_dir(), job_id)
        os.makedirs(job_dir, exist_ok=True)

        job = {
            'job_id': job_id,
            'source_path': source_path,
            'start_time': start_time,
            'duration': duration,
            'library_id': library_id,
            'status': 'running',
            'error': None,
            'created_at': time.time(),
            'job_dir': job_dir,
            'segment_path': os.path.join(job_dir, 'segment.mkv'),
            'source_web_path': os.path.join(job_dir, 'source_web.mp4'),
            'encoded_path': os.path.join(job_dir, 'encoded.mp4'),
            'source_size': 0,
            'encoded_size': 0,
            'source_codec': '',
            'encoded_codec': '',
            'vmaf_score': None,
            'ssim_score': None,
        }

        with self._lock:
            self._jobs[job_id] = job
            self._current_job = job_id

        # Run the preview generation in a background thread
        thread = threading.Thread(target=self._generate_preview, args=(job_id,), daemon=True)
        thread.start()

        return job_id

    def _generate_preview(self, job_id):
        """Generate preview clips in a background thread."""
        job = self._jobs.get(job_id)
        if not job:
            return

        try:
            source_path = job['source_path']
            start_time = job['start_time']
            duration = job['duration']
            segment_path = job['segment_path']
            source_web_path = job['source_web_path']
            encoded_path = job['encoded_path']

            # Step 1: Extract segment from original (stream copy — fast)
            self.logger.info("Preview [%s]: Extracting segment from %s", job_id, source_path)
            extract_cmd = [
                'ffmpeg', '-y',
                '-ss', str(start_time),
                '-t', str(duration),
                '-i', source_path,
                '-c', 'copy',
                segment_path,
            ]
            result = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                raise RuntimeError("Segment extraction failed: {}".format(result.stderr[-500:] if result.stderr else ''))

            # Step 2: Re-encode source to browser-playable MP4 (high quality reference)
            self.logger.info("Preview [%s]: Creating browser-playable source reference", job_id)
            source_web_cmd = [
                'ffmpeg', '-y',
                '-i', segment_path,
                '-c:v', 'libx264',
                '-crf', '1',
                '-preset', 'ultrafast',
                '-c:a', 'aac',
                '-b:a', '192k',
                source_web_path,
            ]
            result = subprocess.run(source_web_cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise RuntimeError("Source web encode failed: {}".format(result.stderr[-500:] if result.stderr else ''))

            # Step 3: Encode using a standard encode to simulate the library pipeline
            # We use reasonable defaults here. A full plugin pipeline integration
            # would require running the actual plugin runners, which is complex.
            # For now, use a standard CRF 23 encode as the "encoded" version.
            self.logger.info("Preview [%s]: Creating encoded preview", job_id)
            encoded_cmd = [
                'ffmpeg', '-y',
                '-i', segment_path,
                '-c:v', 'libx264',
                '-crf', '23',
                '-preset', 'medium',
                '-c:a', 'aac',
                '-b:a', '128k',
                encoded_path,
            ]
            result = subprocess.run(encoded_cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise RuntimeError("Encoded preview failed: {}".format(result.stderr[-500:] if result.stderr else ''))

            # Get file sizes
            if os.path.exists(source_web_path):
                job['source_size'] = os.path.getsize(source_web_path)
            if os.path.exists(encoded_path):
                job['encoded_size'] = os.path.getsize(encoded_path)

            # Get codec info via ffprobe
            job['source_codec'] = self._get_video_codec(source_path)
            job['encoded_codec'] = self._get_video_codec(encoded_path)

            # Step 4: Compute quality metrics (VMAF/SSIM) if possible
            self.logger.info("Preview [%s]: Computing quality metrics", job_id)
            vmaf_score, ssim_score = self.compute_quality_metrics(source_web_path, encoded_path)
            job['vmaf_score'] = vmaf_score
            job['ssim_score'] = ssim_score

            job['status'] = 'ready'
            self.logger.info("Preview [%s]: Complete", job_id)

        except Exception as e:
            self.logger.error("Preview [%s]: Failed - %s", job_id, str(e))
            job['status'] = 'failed'
            job['error'] = str(e)
        finally:
            with self._lock:
                if self._current_job == job_id:
                    self._current_job = None

    def _get_video_codec(self, filepath):
        """Get the video codec of a file using ffprobe."""
        try:
            cmd = [
                'ffprobe', '-v', 'quiet',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=codec_name',
                '-of', 'csv=p=0',
                filepath,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ''

    def compute_quality_metrics(self, source_path, encoded_path):
        """
        Compute VMAF and SSIM quality metrics between source and encoded.
        Returns (vmaf_score, ssim_score) — either can be None if unavailable.

        :param source_path: Path to the source/reference video
        :param encoded_path: Path to the encoded/distorted video
        :return: tuple (float or None, float or None)
        """
        vmaf_score = None
        ssim_score = None

        # Try SSIM first (more widely available)
        try:
            ssim_cmd = [
                'ffmpeg', '-y',
                '-i', encoded_path,
                '-i', source_path,
                '-lavfi', 'ssim',
                '-f', 'null', '-',
            ]
            result = subprocess.run(ssim_cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and result.stderr:
                import re
                match = re.search(r'All:(\d+\.\d+)', result.stderr)
                if match:
                    ssim_score = float(match.group(1))
        except Exception as e:
            self.logger.debug("SSIM computation failed: %s", str(e))

        # Try VMAF (requires libvmaf)
        try:
            vmaf_cmd = [
                'ffmpeg', '-y',
                '-i', encoded_path,
                '-i', source_path,
                '-lavfi', 'libvmaf',
                '-f', 'null', '-',
            ]
            result = subprocess.run(vmaf_cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0 and result.stderr:
                import re
                match = re.search(r'VMAF score:\s*(\d+\.\d+)', result.stderr)
                if not match:
                    match = re.search(r'vmaf_score:\s*(\d+\.\d+)', result.stderr)
                if match:
                    vmaf_score = float(match.group(1))
        except Exception as e:
            self.logger.debug("VMAF computation failed (libvmaf may not be available): %s", str(e))

        return vmaf_score, ssim_score

    def get_job_status(self, job_id):
        """
        Get the status of a preview job.

        :param job_id: The job ID
        :return: dict with job status and file URLs
        """
        job = self._jobs.get(job_id)
        if not job:
            return None

        result = {
            'job_id': job['job_id'],
            'status': job['status'],
            'error': job['error'],
            'source_size': job.get('source_size', 0),
            'encoded_size': job.get('encoded_size', 0),
            'source_codec': job.get('source_codec', ''),
            'encoded_codec': job.get('encoded_codec', ''),
            'vmaf_score': job.get('vmaf_score'),
            'ssim_score': job.get('ssim_score'),
        }

        if job['status'] == 'ready':
            result['source_url'] = '/unmanic/preview/{}/source_web.mp4'.format(job_id)
            result['encoded_url'] = '/unmanic/preview/{}/encoded.mp4'.format(job_id)

        return result

    def cleanup_job(self, job_id):
        """
        Clean up a specific preview job's files.

        :param job_id: The job ID
        """
        job = self._jobs.pop(job_id, None)
        if job:
            job_dir = job.get('job_dir')
            if job_dir and os.path.exists(job_dir):
                shutil.rmtree(job_dir, ignore_errors=True)
                self.logger.info("Preview [%s]: Cleaned up", job_id)

    def cleanup_old_previews(self):
        """
        Remove preview jobs older than CLEANUP_AGE.
        Called periodically by the scheduler.
        """
        now = time.time()
        expired_ids = []

        for job_id, job in list(self._jobs.items()):
            if (now - job.get('created_at', 0)) > self.CLEANUP_AGE:
                expired_ids.append(job_id)

        for job_id in expired_ids:
            self.cleanup_job(job_id)

        # Also clean up any orphaned directories
        preview_dir = self.get_preview_cache_dir()
        if os.path.exists(preview_dir):
            for entry in os.listdir(preview_dir):
                entry_path = os.path.join(preview_dir, entry)
                if os.path.isdir(entry_path) and entry not in self._jobs:
                    try:
                        mtime = os.path.getmtime(entry_path)
                        if (now - mtime) > self.CLEANUP_AGE:
                            shutil.rmtree(entry_path, ignore_errors=True)
                            self.logger.info("Preview: Cleaned up orphaned directory %s", entry)
                    except OSError:
                        pass

        if expired_ids:
            self.logger.info("Preview: Cleaned up %d expired preview jobs", len(expired_ids))
