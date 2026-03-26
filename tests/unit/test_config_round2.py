#!/usr/bin/env python3

"""
tests.unit.test_config_round2.py

Unit tests for Config getters/setters added in Round 2:
- get_default_max_retries()
- get_staging_expiry_days()
- get_onboarding_completed() / set_onboarding_completed()
"""

import json
import os
from unittest.mock import patch

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_config(tmp_path, settings_data=None):
    """Create a Config with controlled paths and optional settings."""
    config_path = str(tmp_path / "config")
    os.makedirs(config_path, exist_ok=True)

    if settings_data is not None:
        with open(os.path.join(config_path, "settings.json"), "w") as f:
            json.dump(settings_data, f)

    with patch.dict(os.environ, {}, clear=True), patch("compresso.config.common") as mock_common:
        mock_common.get_home_dir.return_value = str(tmp_path)
        mock_common.get_default_library_path.return_value = str(tmp_path / "library")
        mock_common.get_default_cache_path.return_value = str(tmp_path / "cache")
        mock_common.json_dump_to_file.return_value = {"success": True, "errors": []}
        with patch("compresso.config.CompressoLogging"), patch("compresso.config.metadata") as mock_meta:
            mock_meta.read_version_string.return_value = "1.0.0-test"
            from compresso.config import Config

            c = Config(config_path=config_path)
    return c


# ------------------------------------------------------------------
# TestGetDefaultMaxRetries
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestGetDefaultMaxRetries:
    def test_returns_default_value(self, tmp_path):
        c = _make_config(tmp_path)
        assert c.get_default_max_retries() == 3

    def test_returns_configured_value(self, tmp_path):
        c = _make_config(tmp_path, settings_data={"default_max_retries": 5})
        assert c.get_default_max_retries() == 5

    def test_returns_zero_for_zero(self, tmp_path):
        c = _make_config(tmp_path, settings_data={"default_max_retries": 0})
        assert c.get_default_max_retries() == 0

    def test_clamps_negative_to_zero(self, tmp_path):
        c = _make_config(tmp_path, settings_data={"default_max_retries": -5})
        assert c.get_default_max_retries() == 0

    def test_handles_string_value(self, tmp_path):
        c = _make_config(tmp_path, settings_data={"default_max_retries": "7"})
        assert c.get_default_max_retries() == 7

    def test_returns_fallback_for_invalid_string(self, tmp_path):
        c = _make_config(tmp_path)
        c.default_max_retries = "not_a_number"
        assert c.get_default_max_retries() == 3

    def test_returns_fallback_for_none(self, tmp_path):
        c = _make_config(tmp_path)
        c.default_max_retries = None
        assert c.get_default_max_retries() == 3


# ------------------------------------------------------------------
# TestGetStagingExpiryDays
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestGetStagingExpiryDays:
    def test_returns_default_value(self, tmp_path):
        c = _make_config(tmp_path)
        assert c.get_staging_expiry_days() == 7

    def test_returns_configured_value(self, tmp_path):
        c = _make_config(tmp_path, settings_data={"staging_expiry_days": 14})
        assert c.get_staging_expiry_days() == 14

    def test_returns_zero_for_disabled(self, tmp_path):
        c = _make_config(tmp_path, settings_data={"staging_expiry_days": 0})
        assert c.get_staging_expiry_days() == 0

    def test_clamps_negative_to_zero(self, tmp_path):
        c = _make_config(tmp_path, settings_data={"staging_expiry_days": -3})
        assert c.get_staging_expiry_days() == 0

    def test_handles_string_value(self, tmp_path):
        c = _make_config(tmp_path, settings_data={"staging_expiry_days": "30"})
        assert c.get_staging_expiry_days() == 30

    def test_returns_fallback_for_invalid_string(self, tmp_path):
        c = _make_config(tmp_path)
        c.staging_expiry_days = "garbage"
        assert c.get_staging_expiry_days() == 7

    def test_returns_fallback_for_none(self, tmp_path):
        c = _make_config(tmp_path)
        c.staging_expiry_days = None
        assert c.get_staging_expiry_days() == 7


# ------------------------------------------------------------------
# TestOnboardingCompleted
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestOnboardingCompleted:
    def test_default_is_false(self, tmp_path):
        c = _make_config(tmp_path)
        assert c.get_onboarding_completed() is False

    def test_returns_true_when_set(self, tmp_path):
        c = _make_config(tmp_path, settings_data={"onboarding_completed": True})
        assert c.get_onboarding_completed() is True

    def test_handles_string_true(self, tmp_path):
        c = _make_config(tmp_path)
        c.onboarding_completed = "true"
        assert c.get_onboarding_completed() is True

    def test_handles_string_1(self, tmp_path):
        c = _make_config(tmp_path)
        c.onboarding_completed = "1"
        assert c.get_onboarding_completed() is True

    def test_handles_string_yes(self, tmp_path):
        c = _make_config(tmp_path)
        c.onboarding_completed = "yes"
        assert c.get_onboarding_completed() is True

    def test_handles_string_on(self, tmp_path):
        c = _make_config(tmp_path)
        c.onboarding_completed = "on"
        assert c.get_onboarding_completed() is True

    def test_handles_string_TRUE_case_insensitive(self, tmp_path):
        c = _make_config(tmp_path)
        c.onboarding_completed = "TRUE"
        assert c.get_onboarding_completed() is True

    def test_handles_string_false(self, tmp_path):
        c = _make_config(tmp_path)
        c.onboarding_completed = "false"
        assert c.get_onboarding_completed() is False

    def test_handles_string_no(self, tmp_path):
        c = _make_config(tmp_path)
        c.onboarding_completed = "no"
        assert c.get_onboarding_completed() is False

    def test_handles_string_random(self, tmp_path):
        c = _make_config(tmp_path)
        c.onboarding_completed = "maybe"
        assert c.get_onboarding_completed() is False

    def test_handles_int_1(self, tmp_path):
        c = _make_config(tmp_path)
        c.onboarding_completed = 1
        assert c.get_onboarding_completed() is True

    def test_handles_int_0(self, tmp_path):
        c = _make_config(tmp_path)
        c.onboarding_completed = 0
        assert c.get_onboarding_completed() is False


@pytest.mark.unittest
class TestSetOnboardingCompleted:
    def test_set_true(self, tmp_path):
        c = _make_config(tmp_path)
        c.set_onboarding_completed(True)
        assert c.onboarding_completed is True

    def test_set_false(self, tmp_path):
        c = _make_config(tmp_path)
        c.set_onboarding_completed(True)
        c.set_onboarding_completed(False)
        assert c.onboarding_completed is False

    def test_set_string_true(self, tmp_path):
        c = _make_config(tmp_path)
        c.set_onboarding_completed("true")
        assert c.onboarding_completed is True

    def test_set_string_1(self, tmp_path):
        c = _make_config(tmp_path)
        c.set_onboarding_completed("1")
        assert c.onboarding_completed is True

    def test_set_string_false(self, tmp_path):
        c = _make_config(tmp_path)
        c.set_onboarding_completed("false")
        assert c.onboarding_completed is False

    def test_set_string_random(self, tmp_path):
        c = _make_config(tmp_path)
        c.set_onboarding_completed("maybe")
        assert c.onboarding_completed is False

    def test_roundtrip_through_getter(self, tmp_path):
        c = _make_config(tmp_path)
        c.set_onboarding_completed(True)
        assert c.get_onboarding_completed() is True
        c.set_onboarding_completed(False)
        assert c.get_onboarding_completed() is False
