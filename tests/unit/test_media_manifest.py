#!/usr/bin/env python3

import json
from unittest.mock import patch

import pytest

from compresso.libs.media_manifest import compare_media_summaries, create_manifest, verify_manifest


@pytest.mark.unittest
def test_probe_passes_media_path_as_explicit_input_operand():
    with patch("compresso.libs.media_manifest.subprocess.run") as run:
        run.return_value.stdout = json.dumps({"streams": [], "chapters": [], "format": {}})

        from compresso.libs.media_manifest import probe_media

        probe_media("-untrusted-name.mkv")

    command = run.call_args.args[0]
    assert command[-2:] == ["-i", "-untrusted-name.mkv"]


@pytest.mark.unittest
def test_compare_detects_stream_chapter_and_hdr_loss():
    before = {
        "streams": {"video": 1, "audio": 2, "subtitle": 3, "data": 0, "attachment": 1},
        "chapters": 4,
        "duration_seconds": 120.0,
        "video": {"color_primaries": "bt2020", "color_transfer": "smpte2084", "color_space": "bt2020nc"},
    }
    after = {
        "streams": {"video": 1, "audio": 1, "subtitle": 2, "data": 0, "attachment": 0},
        "chapters": 0,
        "duration_seconds": 115.0,
        "video": {"color_primaries": "bt709", "color_transfer": "bt709", "color_space": "bt709"},
    }

    issues = compare_media_summaries(before, after)

    assert any("audio" in issue for issue in issues)
    assert any("subtitle" in issue for issue in issues)
    assert any("attachment" in issue for issue in issues)
    assert any("chapters" in issue for issue in issues)
    assert any("color_transfer" in issue for issue in issues)
    assert any("duration" in issue for issue in issues)


@pytest.mark.unittest
def test_manifest_create_and_verify_accounts_for_every_file(tmp_path, monkeypatch):
    root = tmp_path / "media"
    root.mkdir()
    (root / "a.mkv").write_bytes(b"aaaa")
    (root / "b.mp4").write_bytes(b"bbbbbb")
    manifest_path = tmp_path / "before.json"
    summary = {
        "streams": {"video": 1, "audio": 1, "subtitle": 0, "data": 0, "attachment": 0},
        "chapters": 0,
        "duration_seconds": 60.0,
        "video": {"color_primaries": "bt709", "color_transfer": "bt709", "color_space": "bt709"},
    }
    monkeypatch.setattr("compresso.libs.media_manifest.probe_media", lambda _path: summary)

    manifest = create_manifest(str(root), str(manifest_path))
    report = verify_manifest(str(manifest_path), str(root))

    assert len(manifest["files"]) == 2
    assert report["total"] == 2
    assert report["passed"] == 2
    assert report["failed"] == 0
    assert json.loads(manifest_path.read_text())["root"] == str(root)


@pytest.mark.unittest
def test_verify_reports_missing_file(tmp_path, monkeypatch):
    root = tmp_path / "media"
    root.mkdir()
    (root / "a.mkv").write_bytes(b"aaaa")
    manifest_path = tmp_path / "before.json"
    summary = {
        "streams": {"video": 1, "audio": 1, "subtitle": 0, "data": 0, "attachment": 0},
        "chapters": 0,
        "duration_seconds": 60.0,
        "video": {},
    }
    monkeypatch.setattr("compresso.libs.media_manifest.probe_media", lambda _path: summary)
    create_manifest(str(root), str(manifest_path))
    (root / "a.mkv").unlink()

    report = verify_manifest(str(manifest_path), str(root))

    assert report["failed"] == 1
    assert report["files"][0]["issues"] == ["output file is missing"]


@pytest.mark.unittest
def test_verify_rejects_manifest_path_that_escapes_root(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    outside = tmp_path / "outside.mkv"
    outside.write_bytes(b"outside")
    manifest_path = tmp_path / "before.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "root": str(root),
                "files": [{"relative_path": "../outside.mkv", "size_bytes": 7, "media": {}}],
            }
        )
    )

    report = verify_manifest(str(manifest_path), str(root))

    assert report["failed"] == 1
    assert report["files"][0]["issues"] == ["manifest path escapes verification root"]


@pytest.mark.unittest
def test_create_rejects_non_positive_sample_size(tmp_path):
    root = tmp_path / "media"
    root.mkdir()

    with pytest.raises(ValueError, match="sample size"):
        create_manifest(str(root), str(tmp_path / "manifest.json"), sample_size=0)


@pytest.mark.unittest
@pytest.mark.parametrize("relative_path", [None, "", "/absolute/movie.mkv", r"C:\absolute\movie.mkv", 42])
def test_verify_reports_malformed_manifest_paths_instead_of_crashing(tmp_path, relative_path):
    root = tmp_path / "media"
    root.mkdir()
    manifest_path = tmp_path / "before.json"
    manifest_path.write_text(
        json.dumps(
            {"version": 1, "root": str(root), "files": [{"relative_path": relative_path, "size_bytes": 1, "media": {}}]}
        )
    )

    report = verify_manifest(str(manifest_path), str(root))

    assert report["failed"] == 1
    assert report["files"][0]["issues"] == ["manifest relative_path is invalid"]


@pytest.mark.unittest
def test_verify_empty_manifest_fails_closed(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    manifest_path = tmp_path / "before.json"
    manifest_path.write_text(json.dumps({"version": 1, "root": str(root), "files": []}))

    report = verify_manifest(str(manifest_path), str(root))

    assert report["failed"] == 1
    assert report["files"][0]["issues"] == ["manifest contains no files"]


@pytest.mark.unittest
def test_create_manifest_rejects_empty_media_root(tmp_path):
    root = tmp_path / "media"
    root.mkdir()

    with pytest.raises(ValueError, match="no supported media"):
        create_manifest(str(root), str(tmp_path / "manifest.json"))


@pytest.mark.unittest
def test_create_manifest_rejects_symlinked_media(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    outside = tmp_path / "outside.mkv"
    outside.write_bytes(b"outside")
    (root / "linked.mkv").symlink_to(outside)

    with pytest.raises(ValueError, match="symbolic-link"):
        create_manifest(str(root), str(tmp_path / "manifest.json"))


@pytest.mark.unittest
def test_create_manifest_rejects_symlinked_directory(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "movie.mkv").write_bytes(b"outside")
    (root / "linked").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic-link directory"):
        create_manifest(str(root), str(tmp_path / "manifest.json"))


@pytest.mark.unittest
def test_create_manifest_surfaces_directory_walk_errors(tmp_path, monkeypatch):
    root = tmp_path / "media"
    root.mkdir()

    def unreadable_walk(_root, *, onerror):
        onerror(PermissionError("denied"))
        return iter(())

    monkeypatch.setattr("compresso.libs.media_manifest.os.walk", unreadable_walk)

    with pytest.raises(OSError, match="could not read"):
        create_manifest(str(root), str(tmp_path / "manifest.json"))


@pytest.mark.unittest
def test_verify_rejects_duplicate_entries_and_unexpected_outputs(tmp_path, monkeypatch):
    root = tmp_path / "media"
    root.mkdir()
    (root / "a.mkv").write_bytes(b"aaaa")
    (root / "unexpected.mkv").write_bytes(b"extra")
    summary = {"streams": {}, "chapters": 0, "duration_seconds": 1.0, "video": {}}
    monkeypatch.setattr("compresso.libs.media_manifest.probe_media", lambda _path: summary)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "root": str(root),
                "files": [
                    {"relative_path": "a.mkv", "size_bytes": 4, "checksum": "unused", "media": summary},
                    {"relative_path": "a.mkv", "size_bytes": 4, "checksum": "unused", "media": summary},
                ],
            }
        )
    )

    report = verify_manifest(str(manifest_path), str(root))

    assert report["failed"] == 2
    assert any(result["issues"] == ["manifest relative_path is duplicated"] for result in report["files"])
    assert any(result["issues"] == ["unexpected output file is not present in the manifest"] for result in report["files"])


@pytest.mark.unittest
def test_verify_rejects_unknown_version_and_nonfinite_duration(tmp_path, monkeypatch):
    root = tmp_path / "media"
    root.mkdir()
    (root / "a.mkv").write_bytes(b"aaaa")
    monkeypatch.setattr(
        "compresso.libs.media_manifest.probe_media",
        lambda _path: {"streams": {}, "chapters": 0, "duration_seconds": 1.0, "video": {}},
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 999,
                "root": str(root),
                "files": [
                    {
                        "relative_path": "a.mkv",
                        "size_bytes": 4,
                        "checksum": "unused",
                        "media": {"streams": {}, "chapters": 0, "duration_seconds": float("nan"), "video": {}},
                    }
                ],
            }
        )
    )

    report = verify_manifest(str(manifest_path), str(root))

    assert report["failed"] == 2
    assert any("manifest version is unsupported" in result["issues"] for result in report["files"])
    assert any("duration is not finite" in result["issues"] for result in report["files"])
