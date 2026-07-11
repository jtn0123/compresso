import importlib.util
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "verify-release-integrity.py"
SPEC = importlib.util.spec_from_file_location("verify_release_integrity", MODULE_PATH)
release_integrity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_integrity)
read_sdist_version = release_integrity.read_sdist_version
read_wheel_version = release_integrity.read_wheel_version
verify_release = release_integrity.verify_release


def _write_wheel(path, version):
    with zipfile.ZipFile(path, "w") as wheel:
        wheel.writestr("compresso-1.0.dist-info/METADATA", f"Metadata-Version: 2.4\nName: compresso\nVersion: {version}\n")


def _write_sdist(path, version):
    payload = f"Metadata-Version: 2.4\nName: compresso\nVersion: {version}\n".encode()
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo("compresso-1.0/PKG-INFO")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))


def test_reads_versions_from_built_artifact_metadata(tmp_path):
    wheel = tmp_path / "compresso.whl"
    sdist = tmp_path / "compresso.tar.gz"
    _write_wheel(wheel, "1.14.0")
    _write_sdist(sdist, "1.14.0")

    assert read_wheel_version(wheel) == "1.14.0"
    assert read_sdist_version(sdist) == "1.14.0"


def test_verify_release_rejects_source_version_mismatch(tmp_path):
    (tmp_path / "VERSION").write_text("1.13.0\n")

    with pytest.raises(ValueError, match="VERSION mismatch"):
        verify_release(tmp_path, "1.14.0", "abc123", "abc123")


def test_verify_release_rejects_artifact_version_mismatch(tmp_path):
    (tmp_path / "VERSION").write_text("1.14.0\n")
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    _write_wheel(dist_dir / "compresso.whl", "1.13.0")
    _write_sdist(dist_dir / "compresso.tar.gz", "1.14.0")

    with pytest.raises(ValueError, match="Artifact version mismatch"):
        verify_release(tmp_path, "1.14.0", "abc123", "abc123", dist_dir=dist_dir)
