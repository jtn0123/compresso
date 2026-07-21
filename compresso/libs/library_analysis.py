#!/usr/bin/env python3

"""
compresso.library_analysis.py

Background library analysis engine.
Scans library files via ffprobe, groups by (codec, resolution),
and cross-references historical CompressionStats to estimate savings.

"""

import json
import os
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import NoReturn, Protocol, TypedDict, cast

from compresso.libs import common, narrowing
from compresso.libs.ffprobe_utils import extract_media_metadata
from compresso.libs.library import Library
from compresso.libs.logs import CompressoLogging
from compresso.libs.peewee_types import execute_write, iterate_query
from compresso.libs.unmodels import CompressionStats, FileMetadata, FileMetadataPaths, LibraryAnalysisCache

logger = CompressoLogging.get_logger("library_analysis")
ANALYSIS_METADATA_KEY = "_compresso_library_analysis"

type AnalysisEntry = dict[str, object]
type FingerprintInfo = tuple[str, str]


class AnalysisProgress(TypedDict):
    checked: int
    total: int


class AnalysisInfo(TypedDict, total=False):
    status: str
    progress: AnalysisProgress
    library_id: int
    generation: str
    error: str


class AnalysisGroup(TypedDict):
    codec: str
    resolution: str
    count: int
    total_size_bytes: int
    total_bitrate: float


class HistoricalEntry(TypedDict):
    avg_savings_pct: float
    count: int


type HistoricalSavings = dict[tuple[str, str], HistoricalEntry]


class FileMetadataGetOrCreate(Protocol):
    def __call__(
        self,
        *,
        fingerprint: str,
        defaults: dict[str, object],
    ) -> tuple[FileMetadata, bool]: ...


class AnalysisCacheGetOrCreate(Protocol):
    def __call__(
        self,
        *,
        library_id: int,
        defaults: dict[str, object],
    ) -> tuple[LibraryAnalysisCache, bool]: ...


# In-progress analyses keyed by library_id
_active_analyses: dict[int, AnalysisInfo] = {}
_analyses_lock = threading.Lock()
_MEDIA_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".m4v",
    ".ts",
    ".mpg",
    ".mpeg",
    ".m2ts",
    ".mts",
    ".mxf",
    ".rmvb",
    ".vob",
    ".ogv",
    ".3gp",
}


def _raise_walk_error(error: OSError) -> NoReturn:
    raise error


def _cancelled(cancel_event: threading.Event | None) -> bool:
    return cancel_event is not None and cancel_event.is_set()


def _validate_media_directories(
    root: str,
    directories: list[str],
    cancel_event: threading.Event | None,
) -> bool:
    for directory in directories:
        if _cancelled(cancel_event):
            return False
        candidate = Path(root) / directory
        if candidate.is_symlink():
            raise ValueError(f"library analysis refuses symbolic-link directory: {candidate}")
    return True


def _iter_directory_media(
    root: str,
    files: list[str],
    cancel_event: threading.Event | None,
) -> Iterator[Path]:
    for filename in sorted(files):
        if _cancelled(cancel_event):
            return
        if os.path.splitext(filename)[1].lower() not in _MEDIA_EXTENSIONS:
            continue
        candidate = Path(root) / filename
        if candidate.is_symlink():
            raise ValueError(f"library analysis refuses symbolic-link media: {candidate}")
        yield candidate


def iter_media_files(
    library_path: str | os.PathLike[str],
    *,
    on_error: Callable[[OSError], object] | None = None,
    cancel_event: threading.Event | None = None,
) -> Iterator[Path]:
    """Yield media paths deterministically while bounding each directory batch."""
    for root, directories, files in os.walk(library_path, onerror=on_error or _raise_walk_error):
        if _cancelled(cancel_event):
            return
        if not _validate_media_directories(root, directories, cancel_event):
            return
        directories.sort()
        yield from _iter_directory_media(root, files, cancel_event)


def probe_analysis_file(filepath: str | os.PathLike[str]) -> AnalysisEntry:
    """Read media metadata without updating analysis caches or task state."""
    return _probe_analysis_file(filepath)


def lookup_savings(
    historical: HistoricalSavings,
    codec: str,
    resolution: str,
) -> tuple[float, int, str]:
    """Expose the analysis engine's evidence lookup for read-only planning."""
    return _lookup_savings(historical, codec, resolution)


def start_analysis(library_id: int) -> dict[str, object]:
    """
    Start a background analysis for the given library.
    Returns immediately with status info.
    """
    with _analyses_lock:
        existing = _active_analyses.get(library_id)
        if existing and existing.get("status") == "running":
            return {"status": "running", "progress": existing.get("progress", {})}

    # Validate library exists
    library = Library(library_id)
    library_path = library.get_path()

    progress: AnalysisProgress = {"checked": 0, "total": 0}
    info: AnalysisInfo = {"status": "running", "progress": progress, "library_id": library_id}

    with _analyses_lock:
        existing = _active_analyses.get(library_id)
        if existing and existing.get("status") == "running":
            return {"status": "running", "progress": existing.get("progress", {})}
        _active_analyses[library_id] = info

    thread = threading.Thread(
        target=_run_analysis,
        args=(library_id, library_path, info),
        name=f"LibraryAnalysis-{library_id}",
        daemon=True,
    )
    thread.start()

    return {"status": "running", "progress": progress}


def get_analysis_status(library_id: int) -> dict[str, object]:
    """
    Get current analysis status and cached results for a library.
    """
    with _analyses_lock:
        active = _active_analyses.get(library_id)

    # If analysis is running, return progress
    if active and active.get("status") == "running":
        return {
            "status": "running",
            "progress": active.get("progress", {}),
            "version": 0,
            "results": None,
        }

    # Otherwise return cached results
    cache = LibraryAnalysisCache.get_or_none(LibraryAnalysisCache.library_id == library_id)
    if not cache:
        return {
            "status": "none",
            "progress": {"checked": 0, "total": 0},
            "version": 0,
            "results": None,
        }

    try:
        raw_results: object = json.loads(cache.analysis_json)
        results = narrowing.string_keyed_dict(raw_results)
    except (json.JSONDecodeError, TypeError):
        results = {}

    return {
        "status": "complete",
        "progress": {"checked": cache.file_count, "total": cache.file_count},
        "version": cache.version,
        "results": results,
    }


def _normalise_codec(codec: object) -> str:
    codec = codec.lower() if isinstance(codec, str) and codec else "unknown"
    if " (estimated)" in codec:
        codec = codec.replace(" (estimated)", "")
    return codec


def _load_json_dict(value: object) -> dict[str, object]:
    try:
        raw_data: object = json.loads(value if isinstance(value, str) and value else "{}")
        return narrowing.string_keyed_dict(raw_data)
    except (TypeError, json.JSONDecodeError):
        return {}


def _probe_analysis_file(filepath: str | os.PathLike[str]) -> AnalysisEntry:
    meta = extract_media_metadata(filepath)
    file_size = os.path.getsize(filepath)
    try:
        stat = os.stat(filepath)
        stat_identity = {
            "stat_size": stat.st_size,
            "stat_mtime_ns": stat.st_mtime_ns,
            "stat_device": stat.st_dev,
            "stat_inode": stat.st_ino,
        }
    except OSError:
        stat_identity = {}
    bitrate_mbps = narrowing.coerce_float(meta.get("bitrate_mbps"))
    duration = narrowing.coerce_float(meta.get("duration"))
    if bitrate_mbps <= 0 and duration > 0:
        bitrate_mbps = file_size * 8 / duration / 1000000

    resolution = meta.get("resolution")
    return {
        "codec": _normalise_codec(meta.get("codec")),
        "resolution": resolution if isinstance(resolution, str) and resolution else "unknown",
        "file_size": file_size,
        "bitrate_mbps": bitrate_mbps,
        **stat_identity,
        "updated_at": datetime.now().isoformat(),
    }


def _cached_analysis_file(
    filepath: str,
    generation: str | None = None,
) -> tuple[AnalysisEntry | None, FingerprintInfo | None]:
    try:
        path_row = FileMetadataPaths.get_or_none(FileMetadataPaths.path == filepath)
        if not path_row:
            return None, common.get_file_fingerprint(filepath)

        metadata = _load_json_dict(path_row.file_metadata.metadata_json)
        cached = metadata.get(ANALYSIS_METADATA_KEY)
        if not isinstance(cached, dict):
            return None, common.get_file_fingerprint(filepath)
        required = {"codec", "resolution", "file_size", "bitrate_mbps"}
        if not required.issubset(cached):
            return None, common.get_file_fingerprint(filepath)

        stat = os.stat(filepath)
        stat_matches = (
            cached.get("stat_size") == stat.st_size
            and cached.get("stat_mtime_ns") == stat.st_mtime_ns
            and cached.get("stat_device") == stat.st_dev
            and cached.get("stat_inode") == stat.st_ino
        )
        if stat_matches:
            if generation:
                current_type = f"library_analysis:{generation}"
                if path_row.path_type != current_type:
                    path_row.path_type = current_type
                    path_row.updated_at = datetime.now()
                    path_row.save()
            return narrowing.string_keyed_dict(cached), (
                path_row.file_metadata.fingerprint,
                path_row.file_metadata.fingerprint_algo,
            )

        fingerprint, algo = common.get_file_fingerprint(filepath)
        return None, (fingerprint, algo)
    except Exception as e:
        logger.debug("Unable to read library analysis metadata cache for %s: %s", filepath, e)
        return None, None


def _persist_analysis_file(
    filepath: str,
    fingerprint_info: FingerprintInfo | None,
    entry: AnalysisEntry,
    generation: str | None = None,
) -> None:
    if not fingerprint_info:
        return
    try:
        fingerprint, algo = fingerprint_info
        get_or_create = cast("FileMetadataGetOrCreate", FileMetadata.get_or_create)
        row, _created = get_or_create(
            fingerprint=fingerprint,
            defaults={
                "fingerprint_algo": algo,
                "metadata_json": "{}",
                "updated_at": datetime.now(),
            },
        )
        row.fingerprint_algo = algo
        metadata = _load_json_dict(row.metadata_json)
        metadata[ANALYSIS_METADATA_KEY] = entry
        row.metadata_json = json.dumps(metadata, sort_keys=True)
        row.updated_at = datetime.now()
        row.save()

        execute_write(
            FileMetadataPaths.delete().where(
                (FileMetadataPaths.path == filepath) & (FileMetadataPaths.file_metadata != row.id)
            )
        )
        path_row = FileMetadataPaths.get_or_none(
            (FileMetadataPaths.file_metadata == row.id) & (FileMetadataPaths.path == filepath)
        )
        if path_row:
            path_row.updated_at = datetime.now()
            path_row.path_type = f"library_analysis:{generation}" if generation else "library_analysis"
            path_row.save()
        else:
            path_type = f"library_analysis:{generation}" if generation else "library_analysis"
            FileMetadataPaths.create(file_metadata=row.id, path=filepath, path_type=path_type)
    except Exception as e:
        logger.debug("Unable to persist library analysis metadata cache for %s: %s", filepath, e)


def _analyse_file_incremental(filepath: str, generation: str | None = None) -> AnalysisEntry:
    cached, fingerprint = _cached_analysis_file(filepath, generation=generation)
    if cached:
        return cached

    entry = _probe_analysis_file(filepath)
    if generation:
        _persist_analysis_file(filepath, fingerprint, entry, generation=generation)
    else:
        _persist_analysis_file(filepath, fingerprint, entry)
    return entry


def _path_is_within(path: str, resolved_root: str) -> bool:
    try:
        return os.path.commonpath((os.path.realpath(path), resolved_root)) == resolved_root
    except (TypeError, ValueError):
        return False


def _cleanup_stale_analysis_paths(library_path: str, generation: str) -> None:
    """Remove prior-generation path markers without retaining every scanned path."""
    try:
        resolved_library_path = os.path.realpath(library_path)
        current_type = f"library_analysis:{generation}"
        query = FileMetadataPaths.select().where(
            FileMetadataPaths.path_type.startswith("library_analysis") & (FileMetadataPaths.path_type != current_type)
        )
        stale_ids = [
            path_row.id
            for path_row in iterate_query(query, FileMetadataPaths)
            if _path_is_within(path_row.path, resolved_library_path)
        ]
        if stale_ids:
            execute_write(FileMetadataPaths.delete().where(FileMetadataPaths.id.in_(stale_ids)))
    except Exception as e:
        logger.debug("Unable to clean stale library analysis generations: %s", e)


def _run_analysis(library_id: int, library_path: str, info: AnalysisInfo) -> None:
    """
    Background thread: walk library, probe each media file, aggregate results.
    """
    try:
        generation = uuid.uuid4().hex
        info["generation"] = generation
        info["progress"]["total"] = 0
        info["progress"]["checked"] = 0

        # Group data: key = (codec, resolution). Files are consumed directly
        # from os.walk so memory does not grow with library size.
        groups: dict[tuple[str, str], AnalysisGroup] = {}
        for filepath in iter_media_files(library_path):
            info["progress"]["total"] += 1
            try:
                analysis_entry = _analyse_file_incremental(str(filepath), generation=generation)
                codec_value = analysis_entry.get("codec")
                resolution_value = analysis_entry.get("resolution")
                codec = codec_value if isinstance(codec_value, str) and codec_value else "unknown"
                resolution = resolution_value if isinstance(resolution_value, str) and resolution_value else "unknown"
                file_size = narrowing.coerce_int(analysis_entry.get("file_size"))
                bitrate_mbps = narrowing.coerce_float(analysis_entry.get("bitrate_mbps"))

                key = (codec, resolution)
                if key not in groups:
                    groups[key] = {
                        "codec": codec,
                        "resolution": resolution,
                        "count": 0,
                        "total_size_bytes": 0,
                        "total_bitrate": 0,
                    }
                groups[key]["count"] += 1
                groups[key]["total_size_bytes"] += file_size
                groups[key]["total_bitrate"] += bitrate_mbps

            except Exception as e:
                logger.debug("Analysis skipped file %s: %s", filepath, str(e))

            info["progress"]["checked"] += 1

        _cleanup_stale_analysis_paths(library_path, generation)

        # Cross-reference with historical CompressionStats for savings estimates
        historical = _get_historical_savings()

        # Build final results
        result_groups: list[dict[str, object]] = []
        total_files = 0
        total_size = 0
        total_estimated_savings = 0
        already_optimal = 0

        # Get skip codecs for this library
        try:
            library = Library(library_id)
            skip_codecs = [c.lower() for c in library.get_skip_codecs()]
        except Exception:
            skip_codecs = []

        for key, group in groups.items():
            codec, resolution = key
            count = group["count"]
            size = group["total_size_bytes"]
            avg_bitrate = group["total_bitrate"] / count if count > 0 else 0

            total_files += count
            total_size += size

            # Check if already optimal (in skip list)
            if codec in skip_codecs:
                already_optimal += count
                result_groups.append(
                    {
                        "codec": codec,
                        "resolution": resolution,
                        "count": count,
                        "total_size_bytes": size,
                        "avg_bitrate_mbps": round(avg_bitrate, 1),
                        "estimated_savings_pct": 0,
                        "estimated_savings_bytes": 0,
                        "confidence": "optimal",
                        "historical_sample_count": 0,
                    }
                )
                continue

            # Look up historical savings
            savings_pct, sample_count, confidence = _lookup_savings(historical, codec, resolution)

            est_savings_bytes = int(size * savings_pct / 100) if savings_pct > 0 else 0
            total_estimated_savings += est_savings_bytes

            result_groups.append(
                {
                    "codec": codec,
                    "resolution": resolution,
                    "count": count,
                    "total_size_bytes": size,
                    "avg_bitrate_mbps": round(avg_bitrate, 1),
                    "estimated_savings_pct": round(savings_pct, 1),
                    "estimated_savings_bytes": est_savings_bytes,
                    "confidence": confidence,
                    "historical_sample_count": sample_count,
                }
            )

        # Sort by estimated savings descending
        result_groups.sort(key=lambda group: narrowing.coerce_int(group.get("estimated_savings_bytes")), reverse=True)

        results: dict[str, object] = {
            "groups": result_groups,
            "total_files": total_files,
            "total_size_bytes": total_size,
            "already_optimal": already_optimal,
            "total_estimated_savings_bytes": total_estimated_savings,
            "last_run": datetime.now().isoformat(),
        }

        # Save to cache
        get_or_create_cache = cast("AnalysisCacheGetOrCreate", LibraryAnalysisCache.get_or_create)
        cache, created = get_or_create_cache(
            library_id=library_id,
            defaults={
                "analysis_json": json.dumps(results),
                "file_count": total_files,
                "last_run": datetime.now(),
                "version": 1,
            },
        )
        if not created:
            cache.analysis_json = json.dumps(results)
            cache.file_count = total_files
            cache.last_run = datetime.now()
            cache.version += 1
            cache.save()

        info["status"] = "complete"
        logger.info("Library analysis complete for library %s: %d files", library_id, total_files)

    except Exception as e:
        logger.exception("Library analysis failed for library %s: %s", library_id, str(e))
        info["status"] = "error"
        info["error"] = str(e)
    finally:
        # Clean up after a delay so status can be polled
        def cleanup() -> None:
            time.sleep(10)
            with _analyses_lock:
                active = _active_analyses.get(library_id)
                if active is None or active.get("status") != "running":
                    _active_analyses.pop(library_id, None)

        threading.Thread(target=cleanup, daemon=True).start()


def _get_historical_savings() -> HistoricalSavings:
    """
    Query CompressionStats for historical savings grouped by (source_codec, source_resolution).
    Returns dict: {(codec, resolution): {'avg_savings_pct': float, 'count': int}}
    """
    from peewee import fn

    results: HistoricalSavings = {}
    try:
        query = (
            CompressionStats.select(
                CompressionStats.source_codec,
                CompressionStats.source_resolution,
                fn.AVG(CompressionStats.source_size).alias("avg_source"),
                fn.AVG(CompressionStats.destination_size).alias("avg_dest"),
                fn.COUNT(CompressionStats.id).alias("cnt"),
            )
            .where(
                CompressionStats.source_size > 0,
                CompressionStats.destination_size > 0,
                CompressionStats.destination_size < CompressionStats.source_size,
            )
            .group_by(CompressionStats.source_codec, CompressionStats.source_resolution)
        )

        rows = cast("Iterable[dict[str, object]]", query.dicts())
        for row in rows:
            codec_value = row.get("source_codec")
            resolution_value = row.get("source_resolution")
            codec = codec_value.lower() if isinstance(codec_value, str) else ""
            resolution = resolution_value if isinstance(resolution_value, str) else ""
            avg_source = narrowing.coerce_float(row.get("avg_source"))
            avg_dest = narrowing.coerce_float(row.get("avg_dest"))
            count = narrowing.coerce_int(row.get("cnt"))
            if avg_source > 0 and count > 0:
                savings_pct = ((avg_source - avg_dest) / avg_source) * 100
                results[(codec, resolution)] = {
                    "avg_savings_pct": savings_pct,
                    "count": count,
                }
    except Exception as e:
        logger.warning("Failed to query historical savings: %s", str(e))

    return results


def _lookup_savings(
    historical: HistoricalSavings,
    codec: str,
    resolution: str,
) -> tuple[float, int, str]:
    """
    Look up estimated savings for a (codec, resolution) pair.
    Falls back to codec-only average if no exact match.
    Returns (savings_pct, sample_count, confidence_level).
    """
    # Exact match
    key = (codec, resolution)
    if key in historical:
        entry = historical[key]
        count = entry["count"]
        confidence = "high" if count >= 20 else ("medium" if count >= 5 else "low")
        return entry["avg_savings_pct"], count, confidence

    # Fallback: codec-only average
    codec_entries = [(k, v) for k, v in historical.items() if k[0] == codec]
    if codec_entries:
        total_savings = sum(v["avg_savings_pct"] * v["count"] for _, v in codec_entries)
        total_count = sum(v["count"] for _, v in codec_entries)
        if total_count > 0:
            avg_savings = total_savings / total_count
            confidence = "medium" if total_count >= 5 else "low"
            return avg_savings, total_count, confidence

    # No data at all
    return 0.0, 0, "none"
