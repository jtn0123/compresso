#!/usr/bin/env python3

"""
    compresso.config.py

    Written by:               Josh.5 <jsunnex@gmail.com>
    Date:                     06 Dec 2018, (7:21 AM)

    Copyright:
           Copyright (C) Josh Sunnex - All Rights Reserved

           Permission is hereby granted, free of charge, to any person obtaining a copy
           of this software and associated documentation files (the "Software"), to deal
           in the Software without restriction, including without limitation the rights
           to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
           copies of the Software, and to permit persons to whom the Software is
           furnished to do so, subject to the following conditions:

           The above copyright notice and this permission notice shall be included in all
           copies or substantial portions of the Software.

           THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
           EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
           MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
           IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
           DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
           OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
           OR OTHER DEALINGS IN THE SOFTWARE.

"""

import json
import os

from compresso import metadata
from compresso.libs import common
from compresso.libs.logs import CompressoLogging
from compresso.libs.singleton import SingletonType

try:
    from json.decoder import JSONDecodeError
except ImportError:
    JSONDecodeError = ValueError

logger = CompressoLogging.get_logger(name="Config")

# Default configuration constants
DEFAULT_UI_PORT = 8888
DEFAULT_SCAN_INTERVAL_MINUTES = 1440  # 24 hours
DEFAULT_CONCURRENT_FILE_TESTERS = 2
DEFAULT_MAX_TASK_AGE_DAYS = 91  # ~3 months
DEFAULT_READINESS_TIMEOUT_SECONDS = 30
DEFAULT_WORKER_CAP = 2


class Config(metaclass=SingletonType):
    app_version = ''

    test = ''

    def __init__(self, config_path=None, **kwargs):
        # Set the default UI Port
        self.ui_port = DEFAULT_UI_PORT
        self.ui_address = ''

        # SSL/TLS settings
        self.ssl_enabled = False
        self.ssl_certfilepath = None
        self.ssl_keyfilepath = None

        # Set default directories
        home_directory = common.get_home_dir()
        self.config_path = os.path.join(home_directory, '.compresso', 'config')
        self.log_path = os.path.join(home_directory, '.compresso', 'logs')
        self.plugins_path = os.path.join(home_directory, '.compresso', 'plugins')
        self.userdata_path = os.path.join(home_directory, '.compresso', 'userdata')

        # Configure debugging
        self.debugging = False

        # Configure log buffer retention (in days)
        self.log_buffer_retention = 0

        # Configure first run (future feature)
        self.first_run = False
        self.release_notes_viewed = None
        self.trial_welcome_viewed = None

        # Library Settings:
        self.library_path = common.get_default_library_path()
        self.enable_library_scanner = False
        self.schedule_full_scan_minutes = DEFAULT_SCAN_INTERVAL_MINUTES
        self.follow_symlinks = True
        self.concurrent_file_testers = DEFAULT_CONCURRENT_FILE_TESTERS
        self.run_full_scan_on_start = False
        self.clear_pending_tasks_on_restart = True
        self.auto_manage_completed_tasks = False
        self.compress_completed_tasks_logs = False
        self.max_age_of_completed_tasks = DEFAULT_MAX_TASK_AGE_DAYS
        self.always_keep_failed_tasks = True

        # Worker settings
        self.cache_path = common.get_default_cache_path()

        # Link settings
        self.installation_name = ''
        self.installation_public_address = ''
        self.remote_installations = []
        self.distributed_worker_count_target = 0

        # Legacy config
        # TODO(v2.0): Remove legacy number_of_workers and worker_event_schedules fields
        self.number_of_workers = None
        self.worker_event_schedules = None

        # Approval workflow settings
        self.approval_required = False
        self.staging_path = os.path.join(home_directory, '.compresso', 'staging')

        # Task retry settings
        self.default_max_retries = 3

        # Staging auto-cleanup settings
        self.staging_expiry_days = 7  # 0 = disabled

        # External notification channels (Discord, Slack, Webhook)
        self.notification_channels = []

        # Onboarding wizard
        self.onboarding_completed = False

        # Fork-specific deployment hardening defaults
        self.large_library_safe_defaults = True
        self.startup_readiness_timeout_seconds = DEFAULT_READINESS_TIMEOUT_SECONDS
        self.default_worker_cap = DEFAULT_WORKER_CAP

        # Import env variables and override all previous settings.
        self.__import_settings_from_env()

        # Import Compresso path settings from command params
        if kwargs.get('compresso_path'):
            self.set_config_item('config_path', os.path.join(kwargs.get('compresso_path'), 'config'), save_settings=False)
            self.set_config_item('plugins_path', os.path.join(kwargs.get('compresso_path'), 'plugins'), save_settings=False)
            self.set_config_item('userdata_path', os.path.join(kwargs.get('compresso_path'), 'userdata'), save_settings=False)

        # Finally, re-read config from file and override all previous settings.
        self.__import_settings_from_file(config_path)

        # Overwrite current settings with given args
        if config_path:
            self.set_config_item('config_path', config_path, save_settings=False)

        # Overwrite all other settings passed from command params
        if kwargs.get('port'):
            self.set_config_item('ui_port', kwargs.get('port'), save_settings=False)
        if kwargs.get('address'):
            self.set_config_item('ui_address', kwargs.get('address'), save_settings=False)

        # Apply fork-safe defaults after all explicit config has loaded.
        # Effective precedence for this fork is:
        # defaults -> environment -> settings.json -> explicit constructor args -> safe default fill-ins
        # The final safe-default layer only fills unset values and should not override explicit operator choices.
        self.__apply_large_library_safe_defaults()

        # Apply settings to the compresso logger
        self.__setup_compresso_logger()

    def __apply_large_library_safe_defaults(self):
        if not self.get_large_library_safe_defaults():
            return

        # Keep the deployment defaults conservative without overriding explicitly stored values.
        self.enable_library_scanner = False if self.enable_library_scanner is None else self.enable_library_scanner
        self.run_full_scan_on_start = False if self.run_full_scan_on_start is None else self.run_full_scan_on_start
        self.concurrent_file_testers = int(self.concurrent_file_testers or 2)
        if self.number_of_workers is None:
            self.number_of_workers = self.get_default_worker_cap()

    def get_config_as_dict(self):
        """
        Return a dictionary of configuration fields and their current values

        :return:
        """
        return self.__dict__

    def get_config_keys(self):
        """
        Return a list of configuration fields

        :return:
        """
        return self.get_config_as_dict().keys()

    def __setup_compresso_logger(self):
        """
        Pass configuration to the global logger

        :return:
        """
        CompressoLogging.get_logger(settings=self)

    def __import_settings_from_env(self):
        """
        Read configuration from environment variables.
        This is useful for running in a docker container or for unit testing.

        :return:
        """
        for setting in self.get_config_keys():
            if setting in os.environ:
                self.set_config_item(setting, os.environ.get(setting), save_settings=False)

    def __import_settings_from_file(self, config_path=None):
        """
        Read configuration from the settings JSON file.

        :return:
        """
        # If config path was not passed as variable, use the default one
        if not config_path:
            config_path = self.get_config_path()
        # Ensure the config path exists
        if not os.path.exists(config_path):
            os.makedirs(config_path)
        settings_file = os.path.join(config_path, 'settings.json')
        if os.path.exists(settings_file):
            data = {}
            try:
                with open(settings_file) as infile:
                    data = json.load(infile)
            except Exception as e:
                logger.exception("Exception in reading saved settings from file: %s", e)
            # Set data to Config class
            self.set_bulk_config_items(data, save_settings=False)

    def reload(self):
        """
        Reload configuration from file
        :return:
        """
        self.__import_settings_from_file()

    def __write_settings_to_file(self):
        """
        Dump current settings to the settings JSON file.

        :return:
        """
        if not os.path.exists(self.get_config_path()):
            os.makedirs(self.get_config_path())
        settings_file = os.path.join(self.get_config_path(), 'settings.json')
        data = self.get_config_as_dict()
        result = common.json_dump_to_file(data, settings_file)
        if not result['success']:
            for message in result['errors']:
                logger.error(message)
            raise Exception("Exception in writing settings to file")

    def get_config_item(self, key):
        """
        Get setting from either this class or the Settings model

        :param key:
        :return:
        """
        # First attempt to fetch it from this class' get functions
        if hasattr(self, f"get_{key}"):
            getter = getattr(self, f"get_{key}")
            if callable(getter):
                return getter()

    def set_config_item(self, key, value, save_settings=True):
        """
        Assigns a value to a given configuration field.
        This is applied to both this class.

        If 'save_settings' is set to False, then settings are only
        assigned and not saved to file.

        :param key:
        :param value:
        :param save_settings:
        :return:
        """
        # Get lowercase value of key
        field_id = key.lower()
        # Check if key is a valid setting
        if field_id not in self.get_config_keys():
            logger.warning("Attempting to save unknown key: %s", key)
            # Do not proceed if this is any key other than the database
            return

        # If in a special config list, execute that command
        if hasattr(self, f"set_{key}"):
            setter = getattr(self, f"set_{key}")
            if callable(setter):
                setter(value)
        else:
            # Assign value directly to class attribute
            setattr(self, key, value)

        # Save settings (if requested)
        if save_settings:
            try:
                self.__write_settings_to_file()
            except Exception:
                logger.exception("Failed to write settings to file: %s", str(self.get_config_as_dict()))

    def set_bulk_config_items(self, items, save_settings=True):
        """
        Write bulk config items to this class.

        :param items:
        :param save_settings:
        :return:
        """
        # Set values that match the settings model attributes
        config_keys = self.get_config_keys()
        for config_key in config_keys:
            # Only import the item if it exists (Running a get here would default a missing var to None)
            if config_key in items:
                self.set_config_item(config_key, items[config_key], save_settings=save_settings)

    @staticmethod
    def read_version():
        """
        Return the application's version number as a string

        :return:
        """
        return metadata.read_version_string('long')

    def read_system_logs(self, lines=None):
        """
        Return an array of system log lines

        :param lines:
        :return:
        """
        log_file = os.path.join(self.log_path, 'compresso.log')
        with open(log_file) as f:
            all_lines = f.readlines()
        if lines is not None:
            all_lines = all_lines[-lines:]
        return [line.rstrip() for line in all_lines]

    def get_ui_port(self):
        """
        Get setting - ui_port

        :return:
        """
        return self.ui_port

    def get_ui_address(self):
        """
        Get setting - ui_address

        :return:
        """
        return self.ui_address

    def get_cache_path(self):
        """
        Get setting - cache_path

        :return:
        """
        return self.cache_path

    def set_cache_path(self, cache_path):
        """
        Get setting - cache_path

        :return:
        """
        if cache_path == "":
            logger.warning("Cache path cannot be empty. Resetting it to default.")
            cache_path = common.get_default_cache_path()
        self.cache_path = cache_path

    def get_config_path(self):
        """
        Get setting - config_path

        :return:
        """
        return self.config_path

    def get_debugging(self):
        """
        Get setting - debugging

        :return:
        """
        return self.debugging

    def set_debugging(self, value):
        """
        Set setting - debugging

        This requires an update to the logger object

        :return:
        """
        if value:
            CompressoLogging.enable_debugging()
        else:
            CompressoLogging.disable_debugging()
        self.debugging = value

    def get_log_buffer_retention(self):
        """
        Get setting - log_buffer_retention

        :return:
        """
        return self.log_buffer_retention

    def set_log_buffer_retention(self, value):
        """
        Set setting - log_buffer_retention

        This requires an update to the logger object

        :return:
        """
        try:
            retention_days = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"log_buffer_retention must be an integer, got {value!r}") from None
        try:
            # On Compresso startup, it may not have yet initialised the logger when this is first run.
            CompressoLogging.set_remote_logging_retention(retention_days)
        except (AttributeError):
            pass
        self.log_buffer_retention = retention_days

    def get_first_run(self):
        """
        Get setting - first_run

        :return:
        """
        return self.first_run

    def get_release_notes_viewed(self):
        """
        Get setting - release_notes_viewed

        :return:
        """
        return self.release_notes_viewed

    def get_trial_welcome_viewed(self):
        """
        Get setting - trial_welcome_viewed

        :return:
        """
        return self.trial_welcome_viewed

    def get_library_path(self):
        """
        Get setting - library_path

        :return:
        """
        return self.library_path

    def get_clear_pending_tasks_on_restart(self):
        """
        Get setting - clear_pending_tasks_on_restart

        :return:
        """
        return self.clear_pending_tasks_on_restart

    def get_auto_manage_completed_tasks(self):
        """
        Get setting - auto_manage_completed_tasks

        :return:
        """
        return self.auto_manage_completed_tasks

    def get_max_age_of_completed_tasks(self):
        """
        Get setting - max_age_of_completed_tasks

        :return:
        """
        return self.max_age_of_completed_tasks

    def get_compress_completed_tasks_logs(self):
        """
        Get setting - compress_completed_tasks_logs

        :return:
        """
        return self.compress_completed_tasks_logs

    def get_always_keep_failed_tasks(self):
        """
        Get setting - always_keep_failed_tasks

        :return:
        """
        return self.always_keep_failed_tasks

    def get_log_path(self):
        """
        Get setting - log_path

        :return:
        """
        return self.log_path

    def get_number_of_workers(self):
        """
        Get setting - number_of_workers

        :return:
        """
        return self.number_of_workers

    def get_worker_event_schedules(self):
        """
        Get setting - worker_event_schedules

        :return:
        """
        return self.worker_event_schedules

    def get_enable_library_scanner(self):
        """
        Get setting - enable_library_scanner

        :return:
        """
        return self.enable_library_scanner

    def get_run_full_scan_on_start(self):
        """
        Get setting - run_full_scan_on_start

        :return:
        """
        return self.run_full_scan_on_start

    def get_schedule_full_scan_minutes(self):
        """
        Get setting - schedule_full_scan_minutes

        :return:
        """
        return self.schedule_full_scan_minutes

    def get_follow_symlinks(self):
        """
        Get setting - follow_symlinks

        :return:
        """
        return self.follow_symlinks

    def get_concurrent_file_testers(self):
        """
        Get setting - concurrent_file_testers

        :return:
        """
        return self.concurrent_file_testers

    def get_plugins_path(self):
        """
        Get setting - config_path

        :return:
        """
        return self.plugins_path

    def get_userdata_path(self):
        """
        Get setting - userdata_path

        :return:
        """
        return self.userdata_path

    def get_installation_name(self):
        """
        Get setting - installation_name

        :return:
        """
        return self.installation_name

    def get_installation_public_address(self):
        """
        Get setting - installation_public_address

        :return:
        """
        return self.installation_public_address

    def get_large_library_safe_defaults(self):
        """
        Get setting - large_library_safe_defaults

        :return:
        """
        if isinstance(self.large_library_safe_defaults, str):
            return self.large_library_safe_defaults.lower() in ('true', '1', 'yes', 'on')
        return bool(self.large_library_safe_defaults)

    def get_startup_readiness_timeout_seconds(self):
        """
        Get setting - startup_readiness_timeout_seconds

        :return:
        """
        return max(1, int(self.startup_readiness_timeout_seconds))

    def get_default_worker_cap(self):
        """
        Get setting - default_worker_cap

        :return:
        """
        return max(1, int(self.default_worker_cap))

    def get_approval_required(self):
        if isinstance(self.approval_required, str):
            return self.approval_required.lower() in ('true', '1', 'yes', 'on')
        return bool(self.approval_required)

    def get_staging_path(self):
        return self.staging_path

    def set_staging_path(self, staging_path):
        if staging_path == "":
            staging_path = os.path.join(common.get_home_dir(), '.compresso', 'staging')
        self.staging_path = staging_path

    def get_remote_installations(self):
        """
        Get setting - remote_installations

        :return:
        """
        remote_installations = []
        for ri in self.remote_installations:
            ri['distributed_worker_count_target'] = self.distributed_worker_count_target
            remote_installations.append(ri)
        return remote_installations

    def get_distributed_worker_count_target(self):
        """
        Get setting - distributed_worker_count_target

        :return:
        """
        return self.distributed_worker_count_target

    def get_ssl_enabled(self):
        """
        Get setting - ssl_enabled

        :return:
        """
        # Convert string to boolean if necessary (for environment variables)
        if isinstance(self.ssl_enabled, str):
            return self.ssl_enabled.lower() in ('true', '1', 'yes', 'on')
        return bool(self.ssl_enabled)

    def get_ssl_certfilepath(self):
        """
        Get setting - ssl_certfilepath

        :return:
        """
        return self.ssl_certfilepath

    def get_ssl_keyfilepath(self):
        """
        Get setting - ssl_keyfilepath

        :return:
        """
        return self.ssl_keyfilepath

    def get_default_max_retries(self):
        """
        Get setting - default_max_retries

        :return:
        """
        try:
            return max(0, int(self.default_max_retries))
        except (TypeError, ValueError):
            return 3

    def get_staging_expiry_days(self):
        """
        Get setting - staging_expiry_days
        Returns 0 if disabled.

        :return:
        """
        try:
            return max(0, int(self.staging_expiry_days))
        except (TypeError, ValueError):
            return 7

    def get_onboarding_completed(self):
        """
        Get setting - onboarding_completed

        :return:
        """
        if isinstance(self.onboarding_completed, str):
            return self.onboarding_completed.lower() in ('true', '1', 'yes', 'on')
        return bool(self.onboarding_completed)

    def set_onboarding_completed(self, value):
        """
        Set setting - onboarding_completed

        :return:
        """
        if isinstance(value, str):
            self.onboarding_completed = value.lower() in ('true', '1', 'yes', 'on')
        else:
            self.onboarding_completed = bool(value)

    def get_notification_channels(self):
        """
        Get setting - notification_channels

        :return:
        """
        if not isinstance(self.notification_channels, list):
            return []
        return list(self.notification_channels)

    def set_notification_channels(self, value):
        """
        Set setting - notification_channels

        :return:
        """
        if isinstance(value, list):
            self.notification_channels = value
        else:
            logger.warning("notification_channels must be a list, got %s; resetting to []", type(value).__name__)
            self.notification_channels = []
