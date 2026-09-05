#!/usr/bin/env python3

"""
compresso.plugin_repos_mixin.py

Mixin providing plugin repository management endpoints for ApiPluginsHandler.
"""

import json
import os
import time
from collections.abc import Mapping
from functools import partial

import tornado.log
from tornado.ioloop import IOLoop

from compresso import config as compresso_config
from compresso.libs.json_state import atomic_json_write
from compresso.libs.session import Session
from compresso.webserver.api_v2.base_api_handler import BaseApiError, BaseApiHandler
from compresso.webserver.api_v2.schema.plugin_schemas import (
    PluginReposListResultsSchema,
    RequestUpdatePluginReposListSchema,
)
from compresso.webserver.helpers import plugins


def _read_json_file(path: str | os.PathLike[str]) -> dict[str, object]:
    with open(path) as f:
        value = json.load(f)
    if not isinstance(value, Mapping):
        raise ValueError("Community repository cache must contain an object")
    return {str(key): item for key, item in value.items()}


def _write_json_file(path: str | os.PathLike[str], data: object) -> None:
    atomic_json_write(path, data, mode=0o600)


class PluginReposMixin(BaseApiHandler):
    """Mixin for plugin repository management endpoints."""

    session: Session | None

    async def update_repo_list(self) -> None:
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

            repos_value = json_request.get("repos_list")
            repos_list = [item for item in repos_value if isinstance(item, str)] if isinstance(repos_value, list) else []
            if not plugins.save_plugin_repos_list(repos_list):
                self.set_status(self.STATUS_ERROR_INTERNAL, reason="Failed to update plugin repo list")
                self.write_error()
                return

            self.write_success()
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def get_repo_list(self) -> None:
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
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def reload_repo_data(self) -> None:
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
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def get_community_repos(self) -> None:
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

            if await self._serve_community_repos_cache(cache_path, cache_ttl_seconds):
                return

            active_session = self.session
            if active_session is None:
                raise RuntimeError("Session is unavailable")
            uuid = active_session.get_installation_uuid()
            level = active_session.get_supporter_level()
            api_path = f"plugin_repos/community_forks/uuid/{uuid}/level/{level}"
            response, status_code = active_session.api_get("compresso-api", 2, api_path)
            if status_code != 200:
                self.set_status(status_code)
                self.finish(response)
                return
            if not self.settings.get("serve_traceback"):
                try:
                    await IOLoop.current().run_in_executor(
                        None, partial(_write_json_file, cache_path, {"cached_at": time.time(), "response": response})
                    )
                except Exception:
                    tornado.log.app_log.warning("Failed to write community repos cache", exc_info=True)
            self.write_success(response)
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def _serve_community_repos_cache(self, cache_path: str, cache_ttl_seconds: int) -> bool:
        if self.settings.get("serve_traceback") or not os.path.exists(cache_path):
            return False
        try:
            cached = await IOLoop.current().run_in_executor(None, _read_json_file, cache_path)
            cached_at_value = cached.get("cached_at", 0)
            cached_at = float(cached_at_value) if isinstance(cached_at_value, (int, float)) else 0.0
            raw_response = cached.get("response")
            response = {str(key): value for key, value in raw_response.items()} if isinstance(raw_response, Mapping) else None
            repos = response.get("repos") if response is not None else None
            first_repo = repos[0] if isinstance(repos, list) and repos else None
            valid = isinstance(first_repo, Mapping) and bool(first_repo.get("repo_id"))
            if response and valid and (time.time() - cached_at) < cache_ttl_seconds:
                self.write_success(response)
                return True
        except Exception:
            tornado.log.app_log.warning("Failed to read community repos cache", exc_info=True)
        return False
