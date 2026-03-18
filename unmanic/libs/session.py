#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    unmanic.session.py

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
import os
import time

from unmanic import config
from unmanic.libs.logs import UnmanicLogging
from unmanic.libs.singleton import SingletonType
from unmanic.libs.unmodels import Installation


class Session(object, metaclass=SingletonType):
    """
    Session

    Manages the Unmanic applications session.
    All features are unlocked — no remote API calls.

    """

    # All features unlocked
    level = 100

    # No limits on libraries or linked installations
    library_count = 999999
    link_count = 999999

    picture_uri = ''
    name = ''
    email = ''
    created = None
    last_check = None
    uuid = None
    user_access_token = None
    application_token = None

    def __init__(self, *args, **kwargs):
        self.logger = UnmanicLogging.get_logger(name=__class__.__name__)
        self.logger.info('Initialising new session object (all features unlocked)')
        self.created = time.time()
        self.last_check = time.time()

    def get_installation_uuid(self):
        """
        Returns the installation UUID as a string.
        If it does not yet exist, it will create one.

        :return:
        """
        if not self.uuid:
            self.__fetch_installation_data()
        return self.uuid

    def get_supporter_level(self):
        """
        Returns the supporter level (always 100 — all features unlocked).

        :return:
        """
        return self.level

    def register_unmanic(self, force=False):
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

    def sign_out(self, remote=True):
        """
        No-op — no remote session to sign out from.

        :return:
        """
        return True

    def auth_user_account(self, force_checkin=False):
        """No-op — always authenticated."""
        return True

    def auth_trial_account(self):
        """No-op — all features unlocked."""
        return True

    def verify_token(self):
        """No-op — no tokens needed."""
        return True

    def get_access_token(self):
        """No-op — no tokens needed."""
        return True

    def fetch_user_data(self):
        """No-op — no remote user data."""
        pass

    def init_device_auth_flow(self):
        """No-op — no device auth needed."""
        return False

    def poll_for_app_token(self, device_code, interval, expires_in):
        """No-op — no app token polling needed."""
        return True

    def get_site_url(self):
        """Return empty string — no remote API."""
        return ""

    def get_sign_out_url(self):
        """Return empty string — no sign out URL needed."""
        return ""

    def get_patreon_login_url(self):
        """Return empty string — no Patreon login needed."""
        return ""

    def get_github_login_url(self):
        """Return empty string — no GitHub login needed."""
        return ""

    def get_discord_login_url(self):
        """Return empty string — no Discord login needed."""
        return ""

    def get_patreon_sponsor_page(self):
        """No-op — no sponsor page needed."""
        return False

    def get_credit_portal_funding_proposals(self):
        """No-op — no credit portal needed."""
        return None, 500

    def __fetch_installation_data(self):
        """
        Fetch installation data from DB (UUID only).

        :return:
        """
        db_installation = Installation()
        try:
            current_installation = db_installation.select().order_by(Installation.id.asc()).limit(1).get()
        except Exception:
            self.logger.debug('Unmanic session does not yet exist... Creating.')
            db_installation.delete().execute()
            current_installation = db_installation.create()

        self.uuid = str(current_installation.uuid)
        # Always keep level at 100
        self.level = 100
        self.created = current_installation.created if current_installation.created else time.time()
        if isinstance(self.created, datetime.datetime):
            self.created = self.created.timestamp()
