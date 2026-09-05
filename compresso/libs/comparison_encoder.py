"""Bounded execution and progress reporting for sample encoders."""

import subprocess
import threading
import time
from contextlib import suppress

from compresso.libs.unmodels.comparisoncandidates import ComparisonCandidates


def run_encode_with_progress(command: list[str], candidate: ComparisonCandidates, duration: float, timeout: float) -> None:
    started = time.monotonic()
    process = subprocess.Popen(  # noqa: S603 - command is assembled only from the static profile catalog
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output_lines = []
    timed_out = threading.Event()

    def terminate_on_deadline() -> None:
        if process.poll() is None:
            timed_out.set()
            with suppress(ProcessLookupError):
                process.kill()

    watchdog = threading.Timer(timeout, terminate_on_deadline)
    watchdog.daemon = True
    watchdog.start()
    try:
        if process.stdout is None:
            raise RuntimeError("Sample encoder did not expose stdout")
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
            if (time.monotonic() - started) > timeout:
                process.kill()
                raise RuntimeError("Sample encode timed out")
        return_code = process.wait(timeout=10)
        if timed_out.is_set():
            raise RuntimeError("Sample encode timed out")
    finally:
        watchdog.cancel()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        if process.stdout:
            process.stdout.close()
    if return_code != 0:
        raise RuntimeError(f"Sample encode failed: {' '.join(output_lines[-10:])[-500:]}")
