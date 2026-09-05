#!/usr/bin/env python3

"""
compresso.session.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     10 Mar 2021, (5:20 PM)

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

import datetime
import time
from asyncio import Future
from collections.abc import Mapping

import requests

from compresso.libs.logs import CompressoLogging
from compresso.libs.peewee_types import execute_write
from compresso.libs.singleton import SingletonType
from compresso.libs.unmodels.installation import Installation


class Session(metaclass=SingletonType):
    """
    Session

    Manages the Compresso applications session.
    All features are unlocked — no remote API calls.

    """

    # All features unlocked
    level: int = 100

    # No limits on libraries or linked installations
    library_count: int = 999999
    link_count: int = 999999

    picture_uri: str = ""
    name: str = ""
    email: str = ""
    created: float | None = None
    last_check: float | None = None
    uuid: str | None = None
    user_access_token: str | None = None
    application_token: str | None = None
    token_poll_task: Future[bool] | None = None

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.logger = CompressoLogging.get_logger(name=type(self).__name__)
        self.requests_session = requests.Session()
        self.logger.info("Initialising new session object (all features unlocked)")
        self.created = time.time()
        self.last_check = time.time()

    def get_installation_uuid(self) -> str:
        """
        Returns the installation UUID as a string.
        If it does not yet exist, it will create one.

        :return:
        """
        if not self.uuid:
            self.__fetch_installation_data()
        if self.uuid is None:
            raise RuntimeError("Installation UUID could not be created")
        return self.uuid

    def get_supporter_level(self) -> int:
        """
        Returns the supporter level (always 100 — all features unlocked).

        :return:
        """
        return self.level

    def register_compresso(self, force: bool = False) -> bool:
        """
        No-op. All features are unlocked without registration.

        :param force:
        :return:
        """
        if not self.uuid:
            self.__fetch_installation_data()
        self.last_check = time.time()
        if not self.created:
            self.created = time.time()
        return True

    def sign_out(self, remote: bool = True) -> bool:
        """
        No-op — no remote session to sign out from.

        :return:
        """
        return True

    def auth_user_account(self, force_checkin: bool = False) -> bool:
        """No-op — always authenticated."""
        return True

    def auth_trial_account(self) -> bool:
        """No-op — all features unlocked."""
        return True

    def verify_token(self) -> bool:
        """No-op — no tokens needed."""
        return True

    def get_access_token(self) -> bool:
        """No-op — no tokens needed."""
        return True

    def fetch_user_data(self) -> None:
        """No-op — no remote user data."""

    def init_device_auth_flow(self) -> dict[str, object] | bool:
        """No-op — no device auth needed."""
        return False

    def poll_for_app_token(self, device_code: str, interval: int, expires_in: int) -> bool:
        """No-op — no app token polling needed."""
        return True

    def get_site_url(self) -> str:
        """Return empty string — no remote API."""
        return ""

    def get_sign_out_url(self) -> str:
        """Return empty string — no sign out URL needed."""
        return ""

    def get_patreon_login_url(self) -> str:
        """Return empty string — no Patreon login needed."""
        return ""

    def get_github_login_url(self) -> str:
        """Return empty string — no GitHub login needed."""
        return ""

    def get_discord_login_url(self) -> str:
        """Return empty string — no Discord login needed."""
        return ""

    def get_patreon_sponsor_page(self) -> bool:
        """No-op — no sponsor page needed."""
        return False

    def get_credit_portal_funding_proposals(self) -> tuple[None, int]:
        """No-op — no credit portal needed."""
        return None, 500

    def api_get(self, service: str, version: int, path: str) -> tuple[dict[str, object], int]:
        """Return a typed unavailable response for retired hosted-service APIs."""
        self.logger.debug("Hosted API GET is unavailable: %s v%s %s", service, version, path)
        return {}, 503

    def api_post(self, service: str, version: int, path: str, data: Mapping[str, object]) -> tuple[dict[str, object], int]:
        """Return a typed unavailable response for retired hosted-service APIs."""
        self.logger.debug("Hosted API POST is unavailable: %s v%s %s", service, version, path)
        return {}, 503

    def __fetch_installation_data(self) -> None:
        """
        Fetch installation data from DB (UUID only).

        :return:
        """
        db_installation = Installation()
        try:
            current_installation = db_installation.select().order_by(Installation.id.asc()).limit(1).get()
        except Exception:
            self.logger.debug("Compresso session does not yet exist... Creating.")
            execute_write(db_installation.delete())
            current_installation = db_installation.create()

        self.uuid = str(current_installation.uuid)
        # Always keep level at 100
        self.level = 100
        created = current_installation.created
        self.created = created.timestamp() if isinstance(created, datetime.datetime) else time.time()
