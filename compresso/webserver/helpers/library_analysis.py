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
from datetime import datetime

from compresso.libs.ffprobe_utils import extract_media_metadata
from compresso.libs.library import Library
from compresso.libs.logs import CompressoLogging
from compresso.libs.unmodels import CompressionStats, LibraryAnalysisCache

logger = CompressoLogging.get_logger("library_analysis")

# In-progress analyses keyed by library_id
_active_analyses: dict = {}
_analyses_lock = threading.Lock()


def start_analysis(library_id):
    """
    Start a background analysis for the given library.
    Returns immediately with status info.
    """
    with _analyses_lock:
        if library_id in _active_analyses:
            info = _active_analyses[library_id]
            if info.get("status") == "running":
                return {"status": "running", "progress": info.get("progress", {})}

    # Validate library exists
    library = Library(library_id)
    library_path = library.get_path()

    progress = {"checked": 0, "total": 0}
    info = {"status": "running", "progress": progress, "library_id": library_id}

    with _analyses_lock:
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


def _run_analysis(library_id, library_path, info):
    """
    Background thread: walk library, probe each media file, aggregate results.
    """
    try:
        # Collect all files
        media_extensions = {
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
        all_files = []
        for root, _dirs, files in os.walk(library_path):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext in media_extensions:
                    all_files.append(os.path.join(root, fname))

        info["progress"]["total"] = len(all_files)
        info["progress"]["checked"] = 0

        # Group data: key = (codec, resolution)
        groups = {}
        for filepath in all_files:
            try:
                meta = extract_media_metadata(filepath)
                codec = meta.get("codec", "unknown").lower()
                # Strip "(estimated)" suffix
                if " (estimated)" in codec:
                    codec = codec.replace(" (estimated)", "")
                resolution = meta.get("resolution", "unknown")
                file_size = os.path.getsize(filepath)

                # Calculate bitrate from file size and duration
                bitrate_mbps = 0
                try:
                    from compresso.libs.ffprobe_utils import probe_file

                    probe_data = probe_file(filepath, timeout=10)
                    if probe_data and probe_data.get("format"):
                        duration = float(probe_data["format"].get("duration", 0))
                        if duration > 0:
                            bit_rate = probe_data["format"].get("bit_rate")
                            bitrate_mbps = float(bit_rate) / 1000000 if bit_rate else file_size * 8 / duration / 1000000
                except Exception as e:
                    logger.debug("Failed to probe bitrate for %s: %s", filepath, e)

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
