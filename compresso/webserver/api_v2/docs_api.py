#!/usr/bin/env python3

"""
    compresso.docs_api.py

    Written by:               Josh.5 <jsunnex@gmail.com>
    Date:                     29 Jul 2021, (11:31 AM)

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
import os
import subprocess

import tornado.log

from compresso.libs import session
from compresso.libs.uiserver import CompressoDataQueues
from compresso.webserver.api_v2.base_api_handler import BaseApiError, BaseApiHandler
from compresso.webserver.api_v2.schema.schemas import DocumentContentSuccessSchema
from compresso.webserver.helpers import documents

GITHUB_RELEASES_URL = "https://github.com/jtn0123/compresso/releases"


def _generate_changelog_from_git():
    """
    Generate a changelog from git tags and commit messages.
    Returns a list of markdown lines, or None if git is unavailable.

    Groups commits by tag (version). Each tag links to GitHub releases.
    Untagged commits at HEAD appear under "Unreleased".
    """
    try:
        # Find the repo root (walk up from this file)
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

        # Check if this is a git repo
        result = subprocess.run(
            ['git', 'rev-parse', '--git-dir'],  # noqa: S607 - git resolved from PATH intentionally
            capture_output=True, text=True, cwd=repo_root, timeout=5
        )
        if result.returncode != 0:
            return None

        # Get all tags sorted by date (newest first)
        tags_result = subprocess.run(
            ['git', 'tag', '--sort=-creatordate', '--format=%(refname:short)|%(creatordate:short)'],  # noqa: S607 - git resolved from PATH intentionally
            capture_output=True, text=True, cwd=repo_root, timeout=10
        )
        tags = []
        for line in tags_result.stdout.strip().split('\n'):
            if '|' in line:
                name, date = line.split('|', 1)
                tags.append((name.strip(), date.strip()))

        lines = ["# Changelog\n", "\n"]
        lines.append("All notable changes to this project are documented here. ")
        lines.append(f"See [GitHub Releases]({GITHUB_RELEASES_URL}) for downloads.\n\n")

        # Get commits from HEAD to the first tag (unreleased)
        if tags:
            unreleased_result = subprocess.run(  # noqa: S603 - trusted git command with internal tag data
                ['git', 'log', f'{tags[0][0]}..HEAD', '--pretty=format:- %s (%h)', '--no-merges'],  # noqa: S607 - git resolved from PATH intentionally
                capture_output=True, text=True, cwd=repo_root, timeout=10
            )
            unreleased = unreleased_result.stdout.strip()
            if unreleased:
                lines.append("## Unreleased\n\n")
                lines.append(unreleased + "\n\n")

        # For each tag, get commits between it and the previous tag
        for i, (tag, date) in enumerate(tags):
            tag_url = f"{GITHUB_RELEASES_URL}/tag/{tag}"
            lines.append(f"## [{tag}]({tag_url}) — {date}\n\n")

            if i + 1 < len(tags):
                prev_tag = tags[i + 1][0]
                log_range = f'{prev_tag}..{tag}'
            else:
                log_range = tag

            commits_result = subprocess.run(  # noqa: S603 - trusted git command with internal tag data
                ['git', 'log', log_range, '--pretty=format:- %s (%h)', '--no-merges'],  # noqa: S607 - git resolved from PATH intentionally
                capture_output=True, text=True, cwd=repo_root, timeout=10
            )
            commits = commits_result.stdout.strip()
            if commits:
                lines.append(commits + "\n\n")
            else:
                lines.append("- Initial release\n\n")

        # If no tags at all, just show recent commits
        if not tags:
            lines.append("## Recent Changes\n\n")
            all_result = subprocess.run(
                ['git', 'log', '--pretty=format:- %s (%h)', '--no-merges', '-50'],  # noqa: S607 - git resolved from PATH intentionally
                capture_output=True, text=True, cwd=repo_root, timeout=10
            )
            if all_result.stdout.strip():
                lines.append(all_result.stdout.strip() + "\n\n")

        return lines

    except (subprocess.SubprocessError, OSError):
        return None


class ApiDocsHandler(BaseApiHandler):
    session = None
    config = None
    params = None
    compresso_data_queues = None

    routes = [
        {
            "path_pattern":      r"/docs/privacypolicy",
            "supported_methods": ["GET"],
            "call_method":       "get_privacy_policy",
        },
        {
            "path_pattern":      r"/docs/logs/zip",
            "supported_methods": ["GET"],
            "call_method":       "get_logs_as_zip",
        },
    ]

    def initialize(self, **kwargs):
        self.session = session.Session()
        self.params = kwargs.get("params")
        udq = CompressoDataQueues()
        self.compresso_data_queues = udq.get_compresso_data_queues()

    async def get_privacy_policy(self):
        """
        Docs - read privacy policy
        ---
        description: Returns the privacy policy.
        responses:
            200:
                description: 'Sample response: Returns the privacy policy.'
                content:
                    application/json:
                        schema:
                            DocumentContentSuccessSchema
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
            # Try to generate changelog from git history
            changelog_content = _generate_changelog_from_git()

            # Fallback to static file if git is unavailable
            if not changelog_content:
                privacy_policy_file = os.path.join(os.path.dirname(__file__), '..', 'docs', 'privacy_policy.md')
                if os.path.exists(privacy_policy_file):
                    with open(privacy_policy_file) as f:
                        changelog_content = f.readlines()

            if not changelog_content:
                self.set_status(self.STATUS_ERROR_INTERNAL, reason="Unable to generate changelog.")
                self.write_error()
                return

            response = self.build_response(
                DocumentContentSuccessSchema(),
                {
                    "content": changelog_content,
                }
            )
            self.write_success(response)
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(bae))
            self.write_error()
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def get_logs_as_zip(self):
        """
        Docs - get log files as zip
        ---
        description: Returns the all log files as zip.
        responses:
            200:
                description: 'Sample response: Returns the all log files as zip.'
                content:
                    application/octet-stream:
                        schema:
                            type: string
                            format: binary
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
            log_files_zip_path = documents.generate_log_files_zip()

            with open(log_files_zip_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    self.write(chunk)

            self.set_header('Content-Type', 'application/octet-stream')
            self.set_header('Content-Disposition', 'attachment; filename=CompressoLogs.zip')
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(bae))
            self.write_error()
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()
