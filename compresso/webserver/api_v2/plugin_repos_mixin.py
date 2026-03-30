#!/usr/bin/env python3

"""
compresso.plugin_repos_mixin.py

Mixin providing plugin repository management endpoints for ApiPluginsHandler.
"""

import json
import os
import time
from functools import partial

import tornado.log
from tornado.ioloop import IOLoop

from compresso import config as compresso_config
from compresso.webserver.api_v2.base_api_handler import LOG_UNHANDLED_ERROR, BaseApiError
from compresso.webserver.api_v2.schema.plugin_schemas import (
    PluginReposListResultsSchema,
    RequestUpdatePluginReposListSchema,
)
from compresso.webserver.helpers import plugins


class PluginReposMixin:
    """Mixin for plugin repository management endpoints."""

    @staticmethod
    def _read_json_file(path):
        with open(path) as f:
            return json.load(f)

    @staticmethod
    def _write_json_file(path, data):
        with open(path, "w") as f:
            json.dump(data, f)

    async def update_repo_list(self):
        """
        Plugins - Update the plugin repo list
        ---
        description: Updates the plugin repo list.
        requestBody:
            description: Requested an update to the plugin repo list.
            required: True
            content:
                application/json:
                    schema:
                        RequestUpdatePluginReposListSchema
        responses:
            200:
                description: 'Successful request; Returns success status'
                content:
                    application/json:
                        schema:
                            BaseSuccessSchema
            400:
                description: Bad request; Check `messages` for any validation errors
                content:
                    application/json:
                        schema:
                            BadRequestSchema
            404:
                description: Bad request; Requested endpoint not found
                content:
                    application/json:
                        schema:
                            BadEndpointSchema
            405:
                description: Bad request; Requested method is not allowed
                content:
                    application/json:
                        schema:
                            BadMethodSchema
            500:
                description: Internal error; Check `error` for exception
                content:
                    application/json:
                        schema:
                            InternalErrorSchema
        """
        try:
            json_request = self.read_json_request(RequestUpdatePluginReposListSchema())

            if not plugins.save_plugin_repos_list(json_request.get("repos_list")):
                self.set_status(self.STATUS_ERROR_INTERNAL, reason="Failed to update plugin repo list")
                self.write_error()
                return

            self.write_success()
            return
        except BaseApiError as bae:
            tornado.log.app_log.error(f"BaseApiError.{self.route.get('call_method')}: {bae!s}")
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(bae))
            self.write_error()
            return
        except Exception as e:
            tornado.log.app_log.exception(LOG_UNHANDLED_ERROR, self.__class__.__name__, self.route.get("call_method"))
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def get_repo_list(self):
        """
        Plugins - Read all configured plugin repos
        ---
        description: Returns a list of plugin repos.
        responses:
            200:
                description: 'Sample response: Returns a list of plugin repos.'
                content:
                    application/json:
                        schema:
                            PluginReposListResultsSchema
            400:
                description: Bad request; Check `messages` for any validation errors
                content:
                    application/json:
                        schema:
                            BadRequestSchema
            404:
                description: Bad request; Requested endpoint not found
                content:
                    application/json:
                        schema:
                            BadEndpointSchema
            405:
                description: Bad request; Requested method is not allowed
                content:
                    application/json:
                        schema:
                            BadMethodSchema
            500:
                description: Internal error; Check `error` for exception
                content:
                    application/json:
                        schema:
                            InternalErrorSchema
        """
        try:
            plugin_repos_list = plugins.prepare_plugin_repos_list()

            response = self.build_response(PluginReposListResultsSchema(), {"repos": plugin_repos_list})
            self.write_success(response)
            return
        except BaseApiError as bae:
            tornado.log.app_log.error(f"BaseApiError.{self.route.get('call_method')}: {bae!s}")
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(bae))
            self.write_error()
            return
        except Exception as e:
            tornado.log.app_log.exception(LOG_UNHANDLED_ERROR, self.__class__.__name__, self.route.get("call_method"))
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def reload_repo_data(self):
        """
        Plugins - Reload plugin repositories remote data
        ---
        description: Reload plugin repositories remote data.
        responses:
            200:
                description: 'Successful request; Returns success status'
                content:
                    application/json:
                        schema:
                            BaseSuccessSchema
            400:
                description: Bad request; Check `messages` for any validation errors
                content:
                    application/json:
                        schema:
                            BadRequestSchema
            404:
                description: Bad request; Requested endpoint not found
                content:
                    application/json:
                        schema:
                            BadEndpointSchema
            405:
                description: Bad request; Requested method is not allowed
                content:
                    application/json:
                        schema:
                            BadMethodSchema
            500:
                description: Internal error; Check `error` for exception
                content:
                    application/json:
                        schema:
                            InternalErrorSchema
        """
        try:
            if not plugins.reload_plugin_repos_data():
                self.set_status(self.STATUS_ERROR_INTERNAL, reason="Failed to pull latest plugin repo data")
                self.write_error()
                return

            self.write_success()
            return
        except BaseApiError as bae:
            tornado.log.app_log.error(f"BaseApiError.{self.route.get('call_method')}: {bae!s}")
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(bae))
            self.write_error()
            return
        except Exception as e:
            tornado.log.app_log.exception(LOG_UNHANDLED_ERROR, self.__class__.__name__, self.route.get("call_method"))
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def get_community_repos(self):
        """
        Plugins - Read community plugin repos from the Compresso API
        ---
        description: Returns a list of community plugin repos.
        responses:
            200:
                description: 'Success: Returns a list of community repos.'
            429:
                description: 'Rate limit exceeded.'
            401:
                description: 'Unauthorized.'
            403:
                description: 'Forbidden.'
            500:
                description: Internal error; Check `error` for exception
        """
        try:
            cache_ttl_seconds = 2 * 60 * 60
            cache_root = compresso_config.Config().get_plugins_path()
            os.makedirs(cache_root, exist_ok=True)
            cache_path = os.path.join(cache_root, "community-repos-cache.json")

            if not self.settings.get("serve_traceback") and os.path.exists(cache_path):
                try:
                    cached = await IOLoop.current().run_in_executor(None, self._read_json_file, cache_path)
                    cached_at = cached.get("cached_at", 0)
                    cached_response = cached.get("response")
                    repos = cached_response.get("repos") if cached_response else None
                    # Validate cached schema (repo_* keys) to avoid serving stale/old-format data.
                    if repos and (not isinstance(repos, list) or not repos or not repos[0].get("repo_id")):
                        repos = None
                    if cached_response and repos and (time.time() - cached_at) < cache_ttl_seconds:
                        self.write_success(cached_response)
                        return
                except Exception:
                    tornado.log.app_log.warning("Failed to read community repos cache", exc_info=True)

            uuid = self.session.get_installation_uuid()
            level = self.session.get_supporter_level()
            api_path = f"plugin_repos/community_forks/uuid/{uuid}/level/{level}"
            response, status_code = self.session.api_get("compresso-api", 2, api_path)
            if status_code != 200:
                self.set_status(status_code)
                self.finish(response)
                return
            if not self.settings.get("serve_traceback"):
                try:
                    await IOLoop.current().run_in_executor(
                        None, partial(self._write_json_file, cache_path, {"cached_at": time.time(), "response": response})
                    )
                except Exception:
                    tornado.log.app_log.warning("Failed to write community repos cache", exc_info=True)
            self.write_success(response)
            return
        except BaseApiError as bae:
            tornado.log.app_log.error(f"BaseApiError.{self.route.get('call_method')}: {bae!s}")
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(bae))
            self.write_error()
            return
        except Exception as e:
            tornado.log.app_log.exception(LOG_UNHANDLED_ERROR, self.__class__.__name__, self.route.get("call_method"))
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()
