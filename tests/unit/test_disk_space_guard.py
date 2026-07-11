#!/usr/bin/env python3

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from compresso.libs.disk_space_guard import DiskSpaceGuard


def _settings(*, reserve_gb=0, multiplier=1.25, enabled=True):
    settings = MagicMock()
    settings.get_disk_space_guard_enabled.return_value = enabled
    settings.get_minimum_free_space_gb.return_value = reserve_gb
    settings.get_disk_space_output_multiplier.return_value = multiplier
    return settings


def _guard(settings, free_bytes):
    return DiskSpaceGuard(settings, disk_usage=lambda _path: SimpleNamespace(free=free_bytes))


@pytest.mark.unittest
def test_cache_preflight_requires_headroom_for_estimated_output(tmp_path):
    source = tmp_path / "source.mkv"
    source.write_bytes(b"x" * 100)
    cache = tmp_path / "cache" / "output.mkv"
    cache.parent.mkdir()

    result = _guard(_settings(multiplier=1.25), free_bytes=124).check_cache_capacity(source, cache)

    assert result.ok is False
    assert result.required_bytes == 125
    assert result.free_bytes == 124
    assert result.phase == "encode_cache"


@pytest.mark.unittest
def test_staging_preflight_requires_room_for_encoded_copy(tmp_path):
    encoded = tmp_path / "encoded.mkv"
    encoded.write_bytes(b"x" * 80)
    staging = tmp_path / "staging" / "task_1" / "encoded.mkv"

    result = _guard(_settings(), free_bytes=79).check_staging_capacity(encoded, staging)

    assert result.ok is False
    assert result.required_bytes == 80
    assert result.phase == "approval_staging"


@pytest.mark.unittest
def test_finalization_preflight_accounts_for_original_backup_and_output(tmp_path):
    source = tmp_path / "library" / "source.mkv"
    encoded = tmp_path / "cache" / "encoded.mkv"
    destination = tmp_path / "library" / "source.mkv"
    source.parent.mkdir()
    encoded.parent.mkdir()
    source.write_bytes(b"x" * 100)
    encoded.write_bytes(b"y" * 60)

    result = _guard(_settings(), free_bytes=159).check_finalization_capacity(source, encoded, destination)

    assert result.ok is False
    assert result.required_bytes == 160
    assert result.phase == "final_replacement"


@pytest.mark.unittest
def test_configured_reserve_is_added_to_required_capacity(tmp_path):
    source = tmp_path / "source.mkv"
    source.write_bytes(b"x" * 100)
    cache = tmp_path / "cache" / "output.mkv"
    cache.parent.mkdir()

    result = _guard(_settings(reserve_gb=1, multiplier=1), free_bytes=(1024**3) + 99).check_cache_capacity(source, cache)

    assert result.required_bytes == (1024**3) + 100
    assert result.ok is False


@pytest.mark.unittest
def test_disabled_guard_allows_work_without_disk_lookup(tmp_path):
    disk_usage = MagicMock()
    guard = DiskSpaceGuard(_settings(enabled=False), disk_usage=disk_usage)

    result = guard.check_cache_capacity(tmp_path / "missing-source", tmp_path / "missing-cache")

    assert result.ok is True
    assert result.phase == "disabled"
    disk_usage.assert_not_called()


@pytest.mark.unittest
@pytest.mark.parametrize("invalid", ["nan", "inf", "-inf", float("nan"), float("inf"), 1e300])
def test_nonfinite_capacity_settings_fall_back_instead_of_crashing(tmp_path, invalid):
    source = tmp_path / "source.mkv"
    source.write_bytes(b"x" * 100)
    cache = tmp_path / "cache" / "output.mkv"
    cache.parent.mkdir()

    result = _guard(_settings(reserve_gb=invalid, multiplier=invalid), free_bytes=10**12).check_cache_capacity(source, cache)

    assert result.required_bytes == (5 * 1024**3) + 125
