import versioninfo


def test_source_version_reads_package_metadata(monkeypatch, tmp_path):
    package_info = tmp_path / "PKG-INFO"
    package_info.write_text(
        "Metadata-Version: 2.4\nName: compresso\nVersion: 9.8.7\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(versioninfo, "is_git_vcs", lambda: False)
    monkeypatch.setattr(versioninfo, "get_base_dir", lambda: str(tmp_path))

    assert versioninfo.version() == "9.8.7"
    assert versioninfo.full_version() == "9.8.7"
