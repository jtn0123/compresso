#!/usr/bin/env python3

"""
tests.unit.test_config_clamped_settings.py

Covers the shared clamp-and-default helpers behind the numeric Config getters.
Every numeric setting arrives from settings.json or the settings API, so the
getters must clamp to their floor, accept numeric strings, and fall back to the
packaged default instead of raising during startup.
"""

import pytest

from compresso.config import (
    DEFAULT_DISK_SPACE_RETRY_SECONDS,
    DEFAULT_LIBRARY_SCAN_QUEUE_LIMIT,
    DEFAULT_MINIMUM_FREE_SPACE_GB,
    DEFAULT_READINESS_TIMEOUT_SECONDS,
    DEFAULT_WORKER_CAP,
    _clamped_float,
    _clamped_int,
)


class TestClampedInt:
    def test_returns_value_above_the_floor(self):
        assert _clamped_int(42, minimum=1, default=7) == 42

    def test_raises_a_value_below_the_floor_to_the_floor(self):
        assert _clamped_int(0, minimum=5, default=7) == 5
        assert _clamped_int(-100, minimum=1, default=7) == 1

    def test_accepts_numeric_strings_from_settings_json(self):
        assert _clamped_int("42", minimum=1, default=7) == 42

    def test_truncates_floats_the_way_int_does(self):
        assert _clamped_int(9.9, minimum=1, default=7) == 9

    @pytest.mark.parametrize("value", [True, False])
    def test_rejects_booleans_rather_than_counting_them_as_zero_or_one(self, value):
        assert _clamped_int(value, minimum=1, default=7) == 7

    @pytest.mark.parametrize("value", ["", "abc", "1.5", None, [], {}, object()])
    def test_falls_back_to_the_default_for_unusable_values(self, value):
        assert _clamped_int(value, minimum=1, default=7) == 7

    def test_never_raises_for_hostile_input(self):
        assert _clamped_int(float("nan"), minimum=1, default=7) == 7
        assert _clamped_int(float("inf"), minimum=1, default=7) == 7


class TestClampedFloat:
    def test_returns_value_above_the_floor(self):
        assert _clamped_float(2.5, minimum=1.0, default=9.0) == 2.5

    def test_raises_a_value_below_the_floor_to_the_floor(self):
        assert _clamped_float(0.5, minimum=1.0, default=9.0) == 1.0

    def test_accepts_numeric_strings_including_fractions(self):
        assert _clamped_float("2.5", minimum=0.0, default=9.0) == 2.5

    @pytest.mark.parametrize("value", [True, False])
    def test_rejects_booleans(self, value):
        assert _clamped_float(value, minimum=0.0, default=9.0) == 9.0

    @pytest.mark.parametrize("value", ["", "abc", None, [], {}, object()])
    def test_falls_back_to_the_default_for_unusable_values(self, value):
        assert _clamped_float(value, minimum=0.0, default=9.0) == 9.0


class TestConfigGettersUseTheHelpers:
    """The getters must not raise, whatever ends up on the instance."""

    @pytest.fixture
    def config(self, monkeypatch, tmp_path):
        from compresso import config as config_module
        from compresso.libs.singleton import SingletonType

        SingletonType._instances = {}
        monkeypatch.setattr(config_module.common, "get_home_dir", lambda: str(tmp_path))
        monkeypatch.setattr(config_module.common, "get_default_library_path", lambda: str(tmp_path / "library"))
        monkeypatch.setattr(config_module.common, "get_default_cache_path", lambda: str(tmp_path / "cache"))
        instance = config_module.Config(config_path=str(tmp_path / "config"))
        yield instance
        SingletonType._instances = {}

    @pytest.mark.parametrize(
        ("attribute", "getter", "default"),
        [
            ("library_scan_queue_limit", "get_library_scan_queue_limit", DEFAULT_LIBRARY_SCAN_QUEUE_LIMIT),
            ("disk_space_retry_seconds", "get_disk_space_retry_seconds", DEFAULT_DISK_SPACE_RETRY_SECONDS),
            # These two previously called int() unguarded and raised on bad input.
            (
                "startup_readiness_timeout_seconds",
                "get_startup_readiness_timeout_seconds",
                DEFAULT_READINESS_TIMEOUT_SECONDS,
            ),
            ("default_worker_cap", "get_default_worker_cap", DEFAULT_WORKER_CAP),
        ],
    )
    def test_int_getters_fall_back_instead_of_raising(self, config, attribute, getter, default):
        setattr(config, attribute, "not-a-number")
        assert getattr(config, getter)() == default

    def test_float_getter_falls_back_instead_of_raising(self, config):
        config.minimum_free_space_gb = "not-a-number"
        assert config.get_minimum_free_space_gb() == DEFAULT_MINIMUM_FREE_SPACE_GB

    def test_worker_cap_still_clamps_to_at_least_one(self, config):
        config.default_worker_cap = 0
        assert config.get_default_worker_cap() == 1

    def test_readiness_timeout_still_clamps_to_at_least_one(self, config):
        config.startup_readiness_timeout_seconds = -5
        assert config.get_startup_readiness_timeout_seconds() == 1
