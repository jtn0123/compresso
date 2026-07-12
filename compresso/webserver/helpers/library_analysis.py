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
from datetime import datetime

from compresso.libs import common
from compresso.libs.ffprobe_utils import extract_media_metadata
from compresso.libs.library import Library
from compresso.libs.logs import CompressoLogging
from compresso.libs.unmodels import CompressionStats, FileMetadata, FileMetadataPaths, LibraryAnalysisCache

logger = CompressoLogging.get_logger("library_analysis")
ANALYSIS_METADATA_KEY = "_compresso_library_analysis"

# In-progress analyses keyed by library_id
_active_analyses: dict = {}
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
    ".vob",
    ".ogv",
    ".3gp",
}


def start_analysis(library_id):
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

    progress = {"checked": 0, "total": 0}
    info = {"status": "running", "progress": progress, "library_id": library_id}

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


def get_analysis_status(library_id):
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
        results = json.loads(cache.analysis_json)
    except (json.JSONDecodeError, TypeError):
        results = {}

    return {
        "status": "complete",
        "progress": {"checked": cache.file_count, "total": cache.file_count},
        "version": cache.version,
        "results": results,
    }


def _normalise_codec(codec):
    codec = (codec or "unknown").lower()
    if " (estimated)" in codec:
        codec = codec.replace(" (estimated)", "")
    return codec


def _load_json_dict(value):
    try:
        data = json.loads(value or "{}")
        return data if isinstance(data, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _probe_analysis_file(filepath):
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
    bitrate_mbps = float(meta.get("bitrate_mbps", 0) or 0)
    duration = float(meta.get("duration", 0) or 0)
    if bitrate_mbps <= 0 and duration > 0:
        bitrate_mbps = file_size * 8 / duration / 1000000

    return {
        "codec": _normalise_codec(meta.get("codec")),
        "resolution": meta.get("resolution", "unknown"),
        "file_size": file_size,
        "bitrate_mbps": bitrate_mbps,
        **stat_identity,
        "updated_at": datetime.now().isoformat(),
    }


def _cached_analysis_file(filepath, generation=None):
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
            return cached, (path_row.file_metadata.fingerprint, path_row.file_metadata.fingerprint_algo)

        fingerprint, algo = common.get_file_fingerprint(filepath)
        return None, (fingerprint, algo)
    except Exception as e:
        logger.debug("Unable to read library analysis metadata cache for %s: %s", filepath, e)
        return None, None


def _persist_analysis_file(filepath, fingerprint_info, entry, generation=None):
    if not fingerprint_info:
        return
    try:
        fingerprint, algo = fingerprint_info
        row, _created = FileMetadata.get_or_create(
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

        FileMetadataPaths.delete().where(
            (FileMetadataPaths.path == filepath) & (FileMetadataPaths.file_metadata != row.id)
        ).execute()
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


def _analyse_file_incremental(filepath, generation=None):
    cached, fingerprint = _cached_analysis_file(filepath, generation=generation)
    if cached:
        return cached

    entry = _probe_analysis_file(filepath)
    if generation:
        _persist_analysis_file(filepath, fingerprint, entry, generation=generation)
    else:
        _persist_analysis_file(filepath, fingerprint, entry)
    return entry


def _path_is_within(path, resolved_root):
    try:
        return os.path.commonpath((os.path.realpath(path), resolved_root)) == resolved_root
    except (TypeError, ValueError):
        return False


def _cleanup_stale_analysis_paths(library_path, generation):
    """Remove prior-generation path markers without retaining every scanned path."""
    try:
        resolved_library_path = os.path.realpath(library_path)
        current_type = f"library_analysis:{generation}"
        query = FileMetadataPaths.select().where(
            FileMetadataPaths.path_type.startswith("library_analysis") & (FileMetadataPaths.path_type != current_type)
        )
        stale_ids = [path_row.id for path_row in query.iterator() if _path_is_within(path_row.path, resolved_library_path)]
        if stale_ids:
            FileMetadataPaths.delete().where(FileMetadataPaths.id.in_(stale_ids)).execute()
    except Exception as e:
        logger.debug("Unable to clean stale library analysis generations: %s", e)


def _run_analysis(library_id, library_path, info):
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
        groups = {}
        for root, _dirs, files in os.walk(library_path):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in _MEDIA_EXTENSIONS:
                    continue
                filepath = os.path.join(root, fname)
                info["progress"]["total"] += 1
                try:
                    analysis_entry = _analyse_file_incremental(filepath, generation=generation)
                    codec = analysis_entry.get("codec", "unknown")
                    resolution = analysis_entry.get("resolution", "unknown")
                    file_size = analysis_entry.get("file_size", 0)
                    bitrate_mbps = analysis_entry.get("bitrate_mbps", 0)

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
        result_groups = []
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
        result_groups.sort(key=lambda g: g["estimated_savings_bytes"], reverse=True)

        results = {
            "groups": result_groups,
            "total_files": total_files,
            "total_size_bytes": total_size,
            "already_optimal": already_optimal,
            "total_estimated_savings_bytes": total_estimated_savings,
            "last_run": datetime.now().isoformat(),
        }

        # Save to cache
        cache, created = LibraryAnalysisCache.get_or_create(
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
        def cleanup():
            time.sleep(10)
            with _analyses_lock:
                if _active_analyses.get(library_id, {}).get("status") != "running":
                    _active_analyses.pop(library_id, None)

        threading.Thread(target=cleanup, daemon=True).start()


def _get_historical_savings():
    """
    Query CompressionStats for historical savings grouped by (source_codec, source_resolution).
    Returns dict: {(codec, resolution): {'avg_savings_pct': float, 'count': int}}
    """
    from peewee import fn

    results = {}
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

        for row in query.dicts():
            codec = (row.get("source_codec") or "").lower()
            resolution = row.get("source_resolution") or ""
            avg_source = row.get("avg_source", 0)
            avg_dest = row.get("avg_dest", 0)
            count = row.get("cnt", 0)
            if avg_source > 0 and count > 0:
                savings_pct = ((avg_source - avg_dest) / avg_source) * 100
                results[(codec, resolution)] = {
                    "avg_savings_pct": savings_pct,
                    "count": count,
                }
    except Exception as e:
        logger.warning("Failed to query historical savings: %s", str(e))

    return results


def _lookup_savings(historical, codec, resolution):
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
    return 0, 0, "none"
