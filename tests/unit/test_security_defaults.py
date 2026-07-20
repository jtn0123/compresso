"""Tests for secure-by-default auth enforcement and file browser containment."""

import os

import pytest

from compresso import config
from compresso.libs.singleton import SingletonType
from compresso.webserver.helpers import filebrowser


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


@pytest.fixture
def settings(tmp_path):
    return config.Config(config_path=str(tmp_path / "config"))


@pytest.mark.unittest
class TestAuthEnforcementDefaults:
    def test_loopback_defaults_do_not_enforce_auth(self, settings):
        settings.ui_address = "127.0.0.1"
        assert settings.get_api_auth_enforced() is False
        assert settings.get_csrf_protection_enforced() is False

    def test_network_exposure_enforces_auth_and_csrf(self, settings):
        settings.ui_address = "0.0.0.0"
        assert settings.get_api_auth_enforced() is True
        assert settings.get_csrf_protection_enforced() is True

    def test_explicit_opt_out_disables_network_enforcement(self, settings):
        settings.ui_address = "0.0.0.0"
        settings.allow_unauthenticated_network_access = True
        assert settings.get_api_auth_enforced() is False
        assert settings.get_csrf_protection_enforced() is False

    def test_explicit_enable_still_enforced_on_loopback(self, settings):
        settings.ui_address = "127.0.0.1"
        settings.api_auth_enabled = True
        settings.csrf_protection_enabled = True
        assert settings.get_api_auth_enforced() is True
        assert settings.get_csrf_protection_enforced() is True

    def test_token_generated_when_network_enforced(self, tmp_path):
        os.environ["ui_address"] = "0.0.0.0"
        try:
            SingletonType._instances = {}
            enforced_settings = config.Config(config_path=str(tmp_path / "config-net"))
            assert enforced_settings.get_api_auth_enforced() is True
            assert enforced_settings.get_api_auth_token() != ""
        finally:
            del os.environ["ui_address"]

    def test_browse_root_paths_parses_string_and_list(self, settings):
        settings.browse_root_paths = "/media/a, /media/b"
        assert settings.get_browse_root_paths() == ["/media/a", "/media/b"]
        settings.browse_root_paths = ["/media/c"]
        assert settings.get_browse_root_paths() == ["/media/c"]
        settings.browse_root_paths = []
        assert settings.get_browse_root_paths() == []


@pytest.mark.unittest
class TestFileBrowserContainment:
    def test_unrestricted_without_browse_roots(self, settings, tmp_path):
        target = tmp_path / "anywhere"
        target.mkdir()
        assert filebrowser._validate_browsable_path(str(target)) == os.path.realpath(str(target))

    def test_path_outside_roots_is_clamped(self, settings, tmp_path):
        root = tmp_path / "media"
        root.mkdir()
        settings.browse_root_paths = [str(root)]
        assert filebrowser._validate_browsable_path("/etc") == os.path.realpath(str(root))

    def test_path_inside_roots_is_allowed(self, settings, tmp_path):
        root = tmp_path / "media"
        sub = root / "movies"
        sub.mkdir(parents=True)
        settings.browse_root_paths = [str(root)]
        assert filebrowser._validate_browsable_path(str(sub)) == os.path.realpath(str(sub))

    def test_traversal_out_of_root_is_clamped(self, settings, tmp_path):
        root = tmp_path / "media"
        root.mkdir()
        settings.browse_root_paths = [str(root)]
        sneaky = str(root / ".." / "..")
        assert filebrowser._validate_browsable_path(sneaky) == os.path.realpath(str(root))

    def test_sibling_prefix_directory_is_not_treated_as_inside(self, settings, tmp_path):
        root = tmp_path / "media"
        root.mkdir()
        sibling = tmp_path / "media-other"
        sibling.mkdir()
        settings.browse_root_paths = [str(root)]
        assert filebrowser._validate_browsable_path(str(sibling)) == os.path.realpath(str(root))
