#!/usr/bin/env python3

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from compresso import config
from compresso.libs.singleton import SingletonType
from compresso.libs.startup import StartupState, _sum_worker_groups_count, build_startup_summary, validate_startup_environment


def reset_singletons():
    SingletonType._instances.pop(config.Config, None)
    SingletonType._instances.pop(StartupState, None)


@pytest.mark.unittest
def test_safe_defaults_enabled_by_default():
    reset_singletons()
    config_path = tempfile.mkdtemp(prefix="compresso_tests_config_")

    settings = config.Config(config_path=config_path)

    # v2.0: number_of_workers is no longer a top-level setting; the only
    # top-level worker-related default that remains is default_worker_cap.
    assert settings.get_large_library_safe_defaults() is True
    assert settings.get_default_worker_cap() == 2


@pytest.mark.unittest
def test_safe_defaults_can_be_disabled_from_config_file():
    reset_singletons()
    config_path = tempfile.mkdtemp(prefix="compresso_tests_config_")
    with open(os.path.join(config_path, "settings.json"), "w") as infile:
        json.dump(
            {
                "large_library_safe_defaults": False,
            },
            infile,
        )

    settings = config.Config(config_path=config_path)

    assert settings.get_large_library_safe_defaults() is False


@pytest.mark.unittest
def test_settings_file_overrides_environment_but_constructor_args_override_both(monkeypatch):
    reset_singletons()
    config_path = tempfile.mkdtemp(prefix="compresso_tests_config_")
    with open(os.path.join(config_path, "settings.json"), "w") as infile:
        json.dump(
            {
                "ui_port": 9001,
                "enable_library_scanner": True,
            },
            infile,
        )

    monkeypatch.setenv("ui_port", "9000")

    settings = config.Config(config_path=config_path, port=9002)

    assert settings.get_ui_port() == 9002
    assert settings.get_enable_library_scanner() is True


@pytest.mark.unittest
def test_safe_defaults_only_fill_unset_values():
    """Verify that values explicitly set in settings.json are not
    overwritten by `__apply_large_library_safe_defaults`."""
    reset_singletons()
    config_path = tempfile.mkdtemp(prefix="compresso_tests_config_")
    with open(os.path.join(config_path, "settings.json"), "w") as infile:
        json.dump(
            {
                "concurrent_file_testers": 4,
            },
            infile,
        )

    settings = config.Config(config_path=config_path)

    assert settings.get_concurrent_file_testers() == 4


@pytest.mark.unittest
def test_sum_worker_groups_count_sums_across_all_groups():
    """v2.0: build_startup_summary's worker_count now comes from the
    sum of number_of_workers across all configured worker groups (the
    legacy top-level Config.number_of_workers was removed). Pin that
    behavior so a future regression that re-introduces a top-level
    field — or stops summing — fails here."""
    with patch("compresso.libs.worker_group.WorkerGroup.get_all_worker_groups") as mock_get:
        mock_get.return_value = [
            {"id": 1, "number_of_workers": 3},
            {"id": 2, "number_of_workers": 5},
            {"id": 3, "number_of_workers": 0},
        ]
        assert _sum_worker_groups_count() == 8


@pytest.mark.unittest
def test_sum_worker_groups_count_handles_none_and_missing_keys():
    """Worker-group dicts in older DB rows may have None or a missing
    number_of_workers field. The helper must coerce both to 0 rather
    than raising TypeError."""
    with patch("compresso.libs.worker_group.WorkerGroup.get_all_worker_groups") as mock_get:
        mock_get.return_value = [
            {"id": 1, "number_of_workers": None},
            {"id": 2},  # missing key
            {"id": 3, "number_of_workers": 2},
        ]
        assert _sum_worker_groups_count() == 2


@pytest.mark.unittest
def test_sum_worker_groups_count_returns_zero_on_db_error():
    """If the worker-group DB raises (e.g. mid-migration, transient
    lock), the helper must fail closed to 0 rather than propagate, so
    the startup summary still renders without workers."""
    with patch("compresso.libs.worker_group.WorkerGroup.get_all_worker_groups", side_effect=RuntimeError("db down")):
        assert _sum_worker_groups_count() == 0


@pytest.mark.unittest
def test_build_startup_summary_uses_worker_group_sum(monkeypatch, tmp_path):
    """End-to-end: build_startup_summary should plumb the
    worker-group total into its `worker_count` field."""
    reset_singletons()
    config_path = tempfile.mkdtemp(prefix="compresso_tests_summary_")
    settings = config.Config(config_path=config_path)

    with (
        patch("compresso.libs.worker_group.WorkerGroup.get_all_worker_groups") as mock_get,
        patch("compresso.libs.startup._validate_ffmpeg", return_value={"version": "x"}),
    ):
        mock_get.return_value = [
            {"id": 1, "number_of_workers": 4},
            {"id": 2, "number_of_workers": 2},
        ]
        summary = build_startup_summary(settings, event_monitor_module=None)
    assert summary["worker_count"] == 6
    assert summary["event_monitor_active"] is False
    assert summary["ffmpeg_version"] == "x"


@pytest.mark.unittest
def test_validate_startup_environment_rejects_missing_library():
    reset_singletons()
    base_dir = tempfile.mkdtemp(prefix="compresso_tests_startup_")
    config_dir = os.path.join(base_dir, "config")
    cache_dir = os.path.join(base_dir, "cache")
    missing_library = os.path.join(base_dir, "library")

    settings = config.Config(config_path=config_dir)
    settings.set_config_item("cache_path", cache_dir, save_settings=False)
    settings.set_config_item("library_path", missing_library, save_settings=False)

    with pytest.raises(RuntimeError, match="library path"):
        validate_startup_environment(settings)


@pytest.mark.unittest
def test_validate_startup_environment_rejects_invalid_cache_path():
    reset_singletons()
    base_dir = tempfile.mkdtemp(prefix="compresso_tests_startup_")
    config_dir = os.path.join(base_dir, "config")
    library_dir = os.path.join(base_dir, "library")
    os.makedirs(library_dir, exist_ok=True)

    settings = config.Config(config_path=config_dir)
    settings.set_config_item("library_path", library_dir, save_settings=False)
    settings.set_config_item("cache_path", os.path.abspath(os.sep), save_settings=False)

    with pytest.raises(RuntimeError, match="cache path"):
        validate_startup_environment(settings)


@pytest.mark.unittest
def test_startup_readiness_requires_all_stages():
    reset_singletons()
    startup_state = StartupState()
    startup_state.reset()

    for stage in StartupState.REQUIRED_STAGES:
        startup_state.mark_ready(stage, detail=stage)

    snapshot = startup_state.snapshot()

    assert snapshot["ready"] is True
    assert all(snapshot["stages"].values())


@pytest.mark.unittest
def test_startup_readiness_reports_errors():
    reset_singletons()
    startup_state = StartupState()
    startup_state.reset()
    startup_state.mark_ready("config_loaded", detail="ok")
    startup_state.mark_error("ui_server_ready", "bind failed")

    snapshot = startup_state.snapshot()

    assert snapshot["ready"] is False
    assert snapshot["stages"]["ui_server_ready"] is False
    assert snapshot["errors"][0]["stage"] == "ui_server_ready"
