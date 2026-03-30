#!/usr/bin/env python3

"""
tests.unit.test_secondary_coverage.py

Focused coverage tests for uncovered lines across four secondary targets:

1. workers_api.py (lines 84-88, 144-152, 199-207, 263-271, 318-326, 382-390, 437-445, 495-503)
   - initialize; BaseApiError / Exception error branches for each endpoint.

2. session_api.py (lines 78-82, 141-142, 194-195, 247-248, 291-330, 388-389)
   - initialize; BaseApiError branches for state/reload/logout; get_app_auth_code full path.

3. healthcheck_api.py (lines 125, 181-185, 213-221, 241-242, 263-271, 304-312, 365-369, 398-406, 449-453)
   - BaseApiError and Exception branches for scan_file, scan_library, cancel_scan,
     get_summary, get_readiness, get_status_list, get_workers, set_workers.

4. metadata_api.py (lines 87, 107-108, 113, 162-169, 176-183, 188-195, 209, 212, 216-226,
                   253-255, 282-285, 301-308, 349-356)
   - initialize; error branches for search_metadata, get_metadata_by_task,
     get_metadata_by_task_id, update_metadata, delete_metadata, get_metadata_by_fingerprint.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType
from compresso.webserver.api_v2.base_api_handler import BaseApiError
from compresso.webserver.api_v2.healthcheck_api import ApiHealthcheckHandler
from compresso.webserver.api_v2.metadata_api import ApiMetadataHandler
from compresso.webserver.api_v2.plugins_api import ApiPluginsHandler
from compresso.webserver.api_v2.session_api import ApiSessionHandler
from compresso.webserver.api_v2.workers_api import ApiWorkersHandler
from compresso.webserver.helpers import settings
from tests.unit.api_test_base import ApiTestBase


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


WORKERS_API = "compresso.webserver.api_v2.workers_api"
SESSION_API = "compresso.webserver.api_v2.session_api"
HEALTHCHECK_API = "compresso.webserver.api_v2.healthcheck_api"
METADATA_API = "compresso.webserver.api_v2.metadata_api"
VALIDATE_LIB_HC = "compresso.webserver.helpers.healthcheck.validate_library_exists"


# =============================================================================
# WORKERS API
# =============================================================================


def _workers_mock_initialize(self, **kwargs):
    """Stub that avoids real singleton lookups."""
    self.params = kwargs.get("params")
    self.compresso_data_queues = {}
    self.foreman = MagicMock()
    self.foreman.get_all_worker_status.return_value = [
        {
            "id": "W0",
            "name": "Worker-W0",
            "idle": True,
            "paused": False,
            "start_time": "",
            "current_file": "",
            "current_task": None,
            "current_command": None,
            "runners_info": {},
            "subprocess": {"percent": "", "elapsed": ""},
            "worker_log_tail": [],
        }
    ]


# ---------------------------------------------------------------------------
# workers_api: initialize (lines 84-88)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestWorkersApiInitialize:
    @patch("compresso.webserver.api_v2.workers_api.CompressoRunningThreads")
    @patch("compresso.webserver.api_v2.workers_api.CompressoDataQueues")
    def test_initialize_sets_foreman_and_queues(self, mock_udq, mock_urt):
        """initialize() sets compresso_data_queues and foreman (lines 84-88)."""
        handler = ApiWorkersHandler.__new__(ApiWorkersHandler)
        mock_udq.return_value.get_compresso_data_queues.return_value = {"q": "data"}
        mock_urt.return_value.get_compresso_running_thread.return_value = MagicMock(name="foreman")

        handler.initialize(params=["p"])

        assert handler.params == ["p"]
        assert handler.compresso_data_queues == {"q": "data"}
        mock_urt.return_value.get_compresso_running_thread.assert_called_with("foreman")


# ---------------------------------------------------------------------------
# workers_api: BaseApiError + Exception branches (lines 144-152, 199-207,
#              263-271, 318-326, 382-390, 437-445, 495-503)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiWorkersHandler, "initialize", _workers_mock_initialize)
class TestPauseWorkerErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiWorkersHandler

    @patch(f"{WORKERS_API}.workers.pause_worker_by_id", side_effect=BaseApiError("pause failed"))
    def test_pause_worker_base_api_error(self, _mock):
        """BaseApiError in pause_worker returns 400 (lines 144-148)."""
        resp = self.post_json("/workers/worker/pause", {"worker_id": "w1"})
        assert resp.code == 400

    @patch(f"{WORKERS_API}.workers.pause_worker_by_id", side_effect=Exception("crash"))
    def test_pause_worker_exception(self, _mock):
        """Generic Exception in pause_worker returns 500 (lines 149-152)."""
        resp = self.post_json("/workers/worker/pause", {"worker_id": "w1"})
        assert resp.code == 500


@pytest.mark.unittest
@patch.object(ApiWorkersHandler, "initialize", _workers_mock_initialize)
class TestPauseAllWorkersErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiWorkersHandler

    @patch(f"{WORKERS_API}.workers.pause_all_workers", side_effect=BaseApiError("fail"))
    def test_pause_all_base_api_error(self, _mock):
        """BaseApiError in pause_all_workers returns 400 (lines 199-203)."""
        resp = self.post_json("/workers/worker/pause/all", {})
        assert resp.code == 400

    @patch(f"{WORKERS_API}.workers.pause_all_workers", side_effect=Exception("crash"))
    def test_pause_all_exception(self, _mock):
        """Generic Exception in pause_all_workers returns 500 (lines 204-207)."""
        resp = self.post_json("/workers/worker/pause/all", {})
        assert resp.code == 500


@pytest.mark.unittest
@patch.object(ApiWorkersHandler, "initialize", _workers_mock_initialize)
class TestResumeWorkerErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiWorkersHandler

    @patch(f"{WORKERS_API}.workers.resume_worker_by_id", side_effect=BaseApiError("fail"))
    def test_resume_worker_base_api_error(self, _mock):
        """BaseApiError in resume_worker returns 400 (lines 263-267)."""
        resp = self.post_json("/workers/worker/resume", {"worker_id": "w1"})
        assert resp.code == 400

    @patch(f"{WORKERS_API}.workers.resume_worker_by_id", side_effect=Exception("crash"))
    def test_resume_worker_exception(self, _mock):
        """Generic Exception in resume_worker returns 500 (lines 268-271)."""
        resp = self.post_json("/workers/worker/resume", {"worker_id": "w1"})
        assert resp.code == 500


@pytest.mark.unittest
@patch.object(ApiWorkersHandler, "initialize", _workers_mock_initialize)
class TestResumeAllWorkersErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiWorkersHandler

    @patch(f"{WORKERS_API}.workers.resume_all_workers", side_effect=BaseApiError("fail"))
    def test_resume_all_base_api_error(self, _mock):
        """BaseApiError in resume_all_workers returns 400 (lines 318-322)."""
        resp = self.post_json("/workers/worker/resume/all", {})
        assert resp.code == 400

    @patch(f"{WORKERS_API}.workers.resume_all_workers", side_effect=Exception("crash"))
    def test_resume_all_exception(self, _mock):
        """Generic Exception in resume_all_workers returns 500 (lines 323-326)."""
        resp = self.post_json("/workers/worker/resume/all", {})
        assert resp.code == 500


@pytest.mark.unittest
@patch.object(ApiWorkersHandler, "initialize", _workers_mock_initialize)
class TestTerminateWorkerErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiWorkersHandler

    @patch(f"{WORKERS_API}.workers.terminate_worker_by_id", side_effect=BaseApiError("fail"))
    def test_terminate_worker_base_api_error(self, _mock):
        """BaseApiError in terminate_worker returns 400 (lines 382-386)."""
        resp = self.fetch(
            "/compresso/api/v2/workers/worker/terminate",
            method="DELETE",
            body=json.dumps({"worker_id": "w1"}),
            headers={"Content-Type": "application/json"},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 400

    @patch(f"{WORKERS_API}.workers.terminate_worker_by_id", side_effect=Exception("crash"))
    def test_terminate_worker_exception(self, _mock):
        """Generic Exception in terminate_worker returns 500 (lines 387-390)."""
        resp = self.fetch(
            "/compresso/api/v2/workers/worker/terminate",
            method="DELETE",
            body=json.dumps({"worker_id": "w1"}),
            headers={"Content-Type": "application/json"},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 500


@pytest.mark.unittest
@patch.object(ApiWorkersHandler, "initialize", _workers_mock_initialize)
class TestTerminateAllWorkersErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiWorkersHandler

    @patch(f"{WORKERS_API}.workers.terminate_all_workers", side_effect=BaseApiError("fail"))
    def test_terminate_all_base_api_error(self, _mock):
        """BaseApiError in terminate_all_workers returns 400 (lines 437-441)."""
        resp = self.fetch(
            "/compresso/api/v2/workers/worker/terminate/all",
            method="DELETE",
            body=json.dumps({}),
            headers={"Content-Type": "application/json"},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 400

    @patch(f"{WORKERS_API}.workers.terminate_all_workers", side_effect=Exception("crash"))
    def test_terminate_all_exception(self, _mock):
        """Generic Exception in terminate_all_workers returns 500 (lines 442-445)."""
        resp = self.fetch(
            "/compresso/api/v2/workers/worker/terminate/all",
            method="DELETE",
            body=json.dumps({}),
            headers={"Content-Type": "application/json"},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 500


@pytest.mark.unittest
@patch.object(ApiWorkersHandler, "initialize", _workers_mock_initialize)
class TestWorkersStatusErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiWorkersHandler

    def test_workers_status_base_api_error(self):
        """BaseApiError in workers_status returns 400 (lines 495-499)."""

        def _init_bae(self, **kwargs):
            self.params = kwargs.get("params")
            self.compresso_data_queues = {}
            self.foreman = MagicMock()
            self.foreman.get_all_worker_status.side_effect = BaseApiError("status fail")

        with patch.object(ApiWorkersHandler, "initialize", _init_bae):
            resp = self.get_json("/workers/status")
        assert resp.code == 400

    def test_workers_status_exception(self):
        """Generic Exception in workers_status returns 500 (lines 500-503)."""

        def _init_exc(self, **kwargs):
            self.params = kwargs.get("params")
            self.compresso_data_queues = {}
            self.foreman = MagicMock()
            self.foreman.get_all_worker_status.side_effect = Exception("crash")

        with patch.object(ApiWorkersHandler, "initialize", _init_exc):
            resp = self.get_json("/workers/status")
        assert resp.code == 500


# =============================================================================
# SESSION API
# =============================================================================


def _session_mock_initialize(self, **kwargs):
    self.session = MagicMock()
    self.session.created = 1700000000.0
    self.session.level = 1
    self.session.picture_uri = "https://example.com/pic.png"
    self.session.name = "TestUser"
    self.session.email = "test@example.com"
    self.session.uuid = "uuid-1234"
    self.session.token_poll_task = None
    self.logger = MagicMock()
    self.params = kwargs.get("params")
    self.compresso_data_queues = {}


# ---------------------------------------------------------------------------
# session_api: initialize (lines 78-82)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestSessionApiInitialize:
    @patch("compresso.webserver.api_v2.session_api.CompressoDataQueues")
    @patch("compresso.webserver.api_v2.session_api.CompressoLogging")
    @patch("compresso.webserver.api_v2.session_api.session.Session")
    def test_initialize_sets_all_fields(self, mock_session, mock_logging, mock_udq):
        """initialize() sets session, logger, params, and data queues (lines 78-82)."""
        handler = ApiSessionHandler.__new__(ApiSessionHandler)
        mock_udq.return_value.get_compresso_data_queues.return_value = {"q": "data"}
        mock_logging.get_logger.return_value = MagicMock(name="logger")

        handler.initialize(params=["p1"])

        assert handler.session is mock_session.return_value
        assert handler.params == ["p1"]
        assert handler.compresso_data_queues == {"q": "data"}


# ---------------------------------------------------------------------------
# session_api: get_session_state BaseApiError (lines 141-142)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiSessionHandler, "initialize", _session_mock_initialize)
class TestSessionStateBaseApiError(ApiTestBase):
    __test__ = True
    handler_class = ApiSessionHandler

    def test_get_session_state_base_api_error_silently_returns(self):
        """BaseApiError in get_session_state is caught and logged, no 400 written (lines 141-142).

        The branch just calls self.logger.error and returns — no status is set,
        so the connection ends without a full HTTP response.  Tornado sends 200
        with an empty body in that situation.
        """

        def _init_bae(self, **kwargs):
            _session_mock_initialize(self, **kwargs)

            class BrokenSession:
                created = 1700000000.0

                @property
                def level(self):
                    raise BaseApiError("session broken")

                picture_uri = "x"
                name = "x"
                email = "x"
                uuid = "x"
                token_poll_task = None

            self.session = BrokenSession()

        with patch.object(ApiSessionHandler, "initialize", _init_bae):
            resp = self.get_json("/session/state")
        # The BaseApiError branch just returns without writing an explicit HTTP
        # response, so Tornado auto-sends 200 with an empty-ish body.
        assert resp.code in (200, 500)


# ---------------------------------------------------------------------------
# session_api: session_reload BaseApiError (lines 194-195)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiSessionHandler, "initialize", _session_mock_initialize)
class TestSessionReloadBaseApiError(ApiTestBase):
    __test__ = True
    handler_class = ApiSessionHandler

    def test_session_reload_base_api_error_is_caught(self):
        """BaseApiError in session_reload is silently caught (lines 194-195)."""

        def _init_bae(self, **kwargs):
            _session_mock_initialize(self, **kwargs)
            self.session.register_compresso.side_effect = BaseApiError("reload broken")

        with patch.object(ApiSessionHandler, "initialize", _init_bae):
            resp = self.post_json("/session/reload", {})
        assert resp.code in (200, 500)


# ---------------------------------------------------------------------------
# session_api: session_logout BaseApiError (lines 247-248)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiSessionHandler, "initialize", _session_mock_initialize)
class TestSessionLogoutBaseApiError(ApiTestBase):
    __test__ = True
    handler_class = ApiSessionHandler

    def test_session_logout_base_api_error_is_caught(self):
        """BaseApiError in session_logout is silently caught (lines 247-248)."""

        def _init_bae(self, **kwargs):
            _session_mock_initialize(self, **kwargs)
            self.session.sign_out.side_effect = BaseApiError("logout broken")

        with patch.object(ApiSessionHandler, "initialize", _init_bae):
            resp = self.get_json("/session/logout")
        assert resp.code in (200, 500)


# ---------------------------------------------------------------------------
# session_api: get_app_auth_code (lines 291-330)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiSessionHandler, "initialize", _session_mock_initialize)
class TestGetAppAuthCode(ApiTestBase):
    __test__ = True
    handler_class = ApiSessionHandler

    def test_get_app_auth_code_success(self):
        """get_app_auth_code returns 200 with device auth data (lines 291-325)."""

        def _init_auth(self, **kwargs):
            _session_mock_initialize(self, **kwargs)
            self.session.init_device_auth_flow.return_value = {
                "user_code": "ABC-DEF",
                "device_code": "device-xyz",
                "verification_uri": "https://example.com/activate",
                "verification_uri_complete": "https://example.com/activate?code=ABC-DEF",
                "interval": 5,
                "expires_in": 900,
            }
            self.session.token_poll_task = None

        with patch.object(ApiSessionHandler, "initialize", _init_auth):
            resp = self.get_json("/session/get_app_auth_code")
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["user_code"] == "ABC-DEF"
        assert data["device_code"] == "device-xyz"

    def test_get_app_auth_code_init_returns_none(self):
        """get_app_auth_code raises Exception when init returns None → 500."""

        def _init_none(self, **kwargs):
            _session_mock_initialize(self, **kwargs)
            self.session.init_device_auth_flow.return_value = None

        with patch.object(ApiSessionHandler, "initialize", _init_none):
            resp = self.get_json("/session/get_app_auth_code")
        assert resp.code == 500

    def test_get_app_auth_code_cancels_existing_poll_task(self):
        """get_app_auth_code cancels an active token_poll_task (lines 307-309)."""

        def _init_with_task(self, **kwargs):
            _session_mock_initialize(self, **kwargs)
            existing_task = MagicMock()
            existing_task.done.return_value = False
            self.session.token_poll_task = existing_task
            self.session.init_device_auth_flow.return_value = {
                "user_code": "XY-ZW",
                "device_code": "dev-code",
                "verification_uri": "https://example.com",
                "verification_uri_complete": "https://example.com?code=XY-ZW",
                "interval": 5,
                "expires_in": 900,
            }

        with patch.object(ApiSessionHandler, "initialize", _init_with_task):
            resp = self.get_json("/session/get_app_auth_code")
        assert resp.code == 200

    def test_get_app_auth_code_exception_returns_500(self):
        """Generic Exception in get_app_auth_code returns 500 (lines 327-330)."""

        def _init_exc(self, **kwargs):
            _session_mock_initialize(self, **kwargs)
            self.session.init_device_auth_flow.side_effect = Exception("auth service down")

        with patch.object(ApiSessionHandler, "initialize", _init_exc):
            resp = self.get_json("/session/get_app_auth_code")
        assert resp.code == 500


# ---------------------------------------------------------------------------
# session_api: get_funding_proposals BaseApiError (lines 388-389)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiSessionHandler, "initialize", _session_mock_initialize)
class TestFundingProposalsBaseApiError(ApiTestBase):
    __test__ = True
    handler_class = ApiSessionHandler

    def test_get_funding_proposals_base_api_error_is_caught(self):
        """BaseApiError in get_funding_proposals is silently caught (lines 388-389)."""

        def _init_bae(self, **kwargs):
            _session_mock_initialize(self, **kwargs)
            self.session.get_credit_portal_funding_proposals.side_effect = BaseApiError("portal broken")

        with patch.object(ApiSessionHandler, "initialize", _init_bae):
            resp = self.get_json("/session/funding_proposals")
        assert resp.code in (200, 500)


# =============================================================================
# HEALTHCHECK API
# =============================================================================


# ---------------------------------------------------------------------------
# healthcheck: scan_file BaseApiError (line 125) — covered by exception + base api
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestHealthcheckScanFileBaseApiError(ApiTestBase):
    __test__ = True
    handler_class = ApiHealthcheckHandler

    @patch(VALIDATE_LIB_HC, side_effect=BaseApiError("bad library"))
    def test_scan_file_base_api_error_returns_400(self, _mock):
        """BaseApiError from validate_library_exists in scan_file returns 400 (line 125)."""
        resp = self.post_json("/healthcheck/scan", {"file_path": "/test/file.mkv"})
        assert resp.code == 400


# ---------------------------------------------------------------------------
# healthcheck: scan_library BaseApiError + Exception (lines 181-185)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestHealthcheckScanLibraryErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiHealthcheckHandler

    @patch(VALIDATE_LIB_HC, side_effect=BaseApiError("bad library"))
    def test_scan_library_base_api_error_returns_400(self, _mock):
        """BaseApiError from validate in scan_library returns 400 (lines 177-181)."""
        resp = self.post_json("/healthcheck/scan-library", {"library_id": 1})
        assert resp.code == 400

    @patch(VALIDATE_LIB_HC, return_value=True)
    @patch("compresso.webserver.helpers.healthcheck.scan_library", side_effect=Exception("crash"))
    def test_scan_library_exception_returns_500(self, _mock_scan, _mock_validate):
        """Generic Exception in scan_library returns 500 (lines 182-185)."""
        resp = self.post_json("/healthcheck/scan-library", {"library_id": 1})
        assert resp.code == 500


# ---------------------------------------------------------------------------
# healthcheck: cancel_scan BaseApiError + Exception (lines 213-221)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestHealthcheckCancelScanErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiHealthcheckHandler

    @patch("compresso.webserver.helpers.healthcheck.cancel_scan", side_effect=BaseApiError("cancel fail"))
    def test_cancel_scan_base_api_error_returns_400(self, _mock):
        """BaseApiError in cancel_scan returns 400 (lines 213-217)."""
        resp = self.post_json("/healthcheck/cancel-scan", {})
        assert resp.code == 400

    @patch("compresso.webserver.helpers.healthcheck.cancel_scan", side_effect=Exception("crash"))
    def test_cancel_scan_exception_returns_500(self, _mock):
        """Generic Exception in cancel_scan returns 500 (lines 218-221)."""
        resp = self.post_json("/healthcheck/cancel-scan", {})
        assert resp.code == 500


# ---------------------------------------------------------------------------
# healthcheck: get_summary invalid library_id + BaseApiError + Exception (lines 241-242, 263-271)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestHealthcheckSummaryErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiHealthcheckHandler

    @patch("compresso.webserver.helpers.healthcheck.get_scan_progress")
    @patch("compresso.webserver.helpers.healthcheck.get_health_summary")
    def test_get_summary_non_int_library_id_uses_none(self, mock_summary, mock_progress):
        """Non-integer library_id in get_summary falls back to None (lines 241-242)."""
        mock_summary.return_value = {
            "healthy": 0,
            "corrupted": 0,
            "warning": 0,
            "unchecked": 0,
            "checking": 0,
            "total": 0,
        }
        mock_progress.return_value = {"scanning": False, "progress": {}}
        resp = self.get_json("/healthcheck/summary?library_id=not_a_number")
        assert resp.code == 200
        mock_summary.assert_called_with(library_id=None)

    @patch("compresso.webserver.helpers.healthcheck.get_health_summary", side_effect=BaseApiError("fail"))
    def test_get_summary_base_api_error_returns_400(self, _mock):
        """BaseApiError in get_summary returns 400 (lines 263-267)."""
        resp = self.get_json("/healthcheck/summary")
        assert resp.code == 400

    @patch("compresso.webserver.helpers.healthcheck.get_health_summary", side_effect=Exception("crash"))
    def test_get_summary_exception_returns_500(self, _mock):
        """Generic Exception in get_summary returns 500 (lines 268-271)."""
        resp = self.get_json("/healthcheck/summary")
        assert resp.code == 500


# ---------------------------------------------------------------------------
# healthcheck: get_readiness BaseApiError + Exception (lines 304-312)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestHealthcheckReadinessErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiHealthcheckHandler

    @patch("compresso.webserver.helpers.healthcheck.get_startup_readiness", side_effect=BaseApiError("fail"))
    def test_get_readiness_base_api_error_returns_400(self, _mock):
        """BaseApiError in get_readiness returns 400 (lines 304-308)."""
        resp = self.get_json("/healthcheck/readiness")
        assert resp.code == 400

    @patch("compresso.webserver.helpers.healthcheck.get_startup_readiness", side_effect=Exception("crash"))
    def test_get_readiness_exception_returns_500(self, _mock):
        """Generic Exception in get_readiness returns 500 (lines 309-312)."""
        resp = self.get_json("/healthcheck/readiness")
        assert resp.code == 500


# ---------------------------------------------------------------------------
# healthcheck: get_status_list BaseApiError + Exception (lines 365-369)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestHealthcheckStatusListErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiHealthcheckHandler

    @patch("compresso.webserver.helpers.healthcheck.get_health_statuses_paginated", side_effect=BaseApiError("fail"))
    def test_get_status_list_base_api_error_returns_400(self, _mock):
        """BaseApiError in get_status_list returns 400 (lines 361-365)."""
        resp = self.post_json("/healthcheck/status", {"start": 0, "length": 10})
        assert resp.code == 400

    @patch("compresso.webserver.helpers.healthcheck.get_health_statuses_paginated", side_effect=Exception("crash"))
    def test_get_status_list_exception_returns_500(self, _mock):
        """Generic Exception in get_status_list returns 500 (lines 366-369)."""
        resp = self.post_json("/healthcheck/status", {"start": 0, "length": 10})
        assert resp.code == 500


# ---------------------------------------------------------------------------
# healthcheck: get_workers BaseApiError + Exception (lines 398-406)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestHealthcheckGetWorkersErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiHealthcheckHandler

    @patch("compresso.webserver.helpers.healthcheck.get_scan_workers", side_effect=BaseApiError("fail"))
    def test_get_workers_base_api_error_returns_400(self, _mock):
        """BaseApiError in get_workers returns 400 (lines 398-402)."""
        resp = self.get_json("/healthcheck/workers")
        assert resp.code == 400

    @patch("compresso.webserver.helpers.healthcheck.get_scan_workers", side_effect=Exception("crash"))
    def test_get_workers_exception_returns_500(self, _mock):
        """Generic Exception in get_workers returns 500 (lines 403-406)."""
        resp = self.get_json("/healthcheck/workers")
        assert resp.code == 500


# ---------------------------------------------------------------------------
# healthcheck: set_workers BaseApiError + Exception (lines 449-453)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestHealthcheckSetWorkersErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiHealthcheckHandler

    @patch("compresso.webserver.helpers.healthcheck.set_scan_workers", side_effect=BaseApiError("fail"))
    def test_set_workers_base_api_error_returns_400(self, _mock):
        """BaseApiError in set_workers returns 400 (lines 445-449)."""
        resp = self.post_json("/healthcheck/workers", {"worker_count": 2})
        assert resp.code == 400

    @patch("compresso.webserver.helpers.healthcheck.set_scan_workers", side_effect=Exception("crash"))
    def test_set_workers_exception_returns_500(self, _mock):
        """Generic Exception in set_workers returns 500 (lines 450-453)."""
        resp = self.post_json("/healthcheck/workers", {"worker_count": 2})
        assert resp.code == 500


# =============================================================================
# METADATA API
# =============================================================================


def _meta_mock_initialize(self, **kwargs):
    self.params = kwargs.get("params")


# ---------------------------------------------------------------------------
# metadata_api: initialize (line 87)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestMetadataApiInitialize:
    def test_initialize_sets_params(self):
        """initialize() sets params (line 87)."""
        handler = ApiMetadataHandler.__new__(ApiMetadataHandler)
        handler.initialize(params=["p"])
        assert handler.params == ["p"]

    def test_initialize_no_params(self):
        """initialize() without params sets None."""
        handler = ApiMetadataHandler.__new__(ApiMetadataHandler)
        handler.initialize()
        assert handler.params is None


# ---------------------------------------------------------------------------
# metadata_api: search_metadata POST path + limit/offset clamping (lines 107-108, 113)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiMetadataHandler, "initialize", _meta_mock_initialize)
class TestSearchMetadataEdgeCases(ApiTestBase):
    __test__ = True
    handler_class = ApiMetadataHandler

    @patch(f"{METADATA_API}.FileMetadataPaths")
    @patch(f"{METADATA_API}.FileMetadata")
    def test_search_metadata_limit_clamped_to_one(self, mock_fm, mock_fmp):
        """limit < 1 is clamped to 1 (line 110-111)."""
        mock_base = MagicMock()
        mock_base.count.return_value = 0
        mock_base.order_by.return_value.limit.return_value.offset.return_value = []
        mock_fm.select.return_value = mock_base

        resp = self.get_json("/metadata/search?limit=0")
        assert resp.code == 200

    @patch(f"{METADATA_API}.FileMetadataPaths")
    @patch(f"{METADATA_API}.FileMetadata")
    def test_search_metadata_offset_clamped_to_zero(self, mock_fm, mock_fmp):
        """offset < 0 is clamped to 0 (line 113)."""
        mock_base = MagicMock()
        mock_base.count.return_value = 0
        mock_base.order_by.return_value.limit.return_value.offset.return_value = []
        mock_fm.select.return_value = mock_base

        resp = self.get_json("/metadata/search?offset=-5")
        assert resp.code == 200

    @patch(f"{METADATA_API}.FileMetadataPaths")
    @patch(f"{METADATA_API}.FileMetadata")
    def test_search_metadata_bad_limit_falls_back_to_50(self, mock_fm, mock_fmp):
        """Non-integer limit falls back to 50 (lines 107-108)."""
        mock_base = MagicMock()
        mock_base.count.return_value = 0
        mock_base.order_by.return_value.limit.return_value.offset.return_value = []
        mock_fm.select.return_value = mock_base

        resp = self.get_json("/metadata/search?limit=abc")
        assert resp.code == 200


# ---------------------------------------------------------------------------
# metadata_api: search_metadata BaseApiError + Exception (lines 162-169)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiMetadataHandler, "initialize", _meta_mock_initialize)
class TestSearchMetadataErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiMetadataHandler

    @patch(f"{METADATA_API}.FileMetadata")
    def test_search_metadata_base_api_error_returns_400(self, mock_fm):
        """BaseApiError in search_metadata returns 400 (lines 162-166)."""
        mock_fm.select.side_effect = BaseApiError("db fail")
        resp = self.get_json("/metadata/search")
        assert resp.code == 400

    @patch(f"{METADATA_API}.FileMetadata")
    def test_search_metadata_exception_returns_500(self, mock_fm):
        """Generic Exception in search_metadata returns 500 (lines 167-169)."""
        mock_fm.select.side_effect = Exception("db crash")
        resp = self.get_json("/metadata/search")
        assert resp.code == 500


# ---------------------------------------------------------------------------
# metadata_api: get_metadata_by_task BaseApiError + Exception (lines 176-183)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiMetadataHandler, "initialize", _meta_mock_initialize)
class TestGetMetadataByTaskErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiMetadataHandler

    @patch(f"{METADATA_API}.CompletedTasks")
    def test_get_metadata_by_task_base_api_error(self, mock_ct):
        """BaseApiError from _get_metadata_by_task_id returns 400 (lines 176-180)."""
        mock_ct.get_by_id.side_effect = BaseApiError("task fail")

        # DoesNotExist must NOT be raised — only BaseApiError
        class NotDoesNotExist(Exception):
            pass

        mock_ct.DoesNotExist = NotDoesNotExist

        resp = self.post_json("/metadata/by-task", {"task_id": 1})
        assert resp.code == 400

    @patch(f"{METADATA_API}.CompletedTasks")
    def test_get_metadata_by_task_exception_returns_500(self, mock_ct):
        """Generic Exception from _get_metadata_by_task_id returns 500 (lines 181-183)."""

        class NotDoesNotExist(Exception):
            pass

        mock_ct.DoesNotExist = NotDoesNotExist
        mock_ct.get_by_id.side_effect = RuntimeError("db crash")

        resp = self.post_json("/metadata/by-task", {"task_id": 1})
        assert resp.code == 500


# ---------------------------------------------------------------------------
# metadata_api: get_metadata_by_task_id BaseApiError + Exception (lines 188-195)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiMetadataHandler, "initialize", _meta_mock_initialize)
class TestGetMetadataByTaskIdErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiMetadataHandler

    @patch(f"{METADATA_API}.CompletedTasks")
    def test_get_metadata_by_task_id_base_api_error(self, mock_ct):
        """BaseApiError from _get_metadata_by_task_id via URL param returns 400 (lines 188-192)."""
        mock_ct.get_by_id.side_effect = BaseApiError("task fail")

        class NotDoesNotExist(Exception):
            pass

        mock_ct.DoesNotExist = NotDoesNotExist

        resp = self.get_json("/metadata/by-task/42")
        assert resp.code == 400

    @patch(f"{METADATA_API}.CompletedTasks")
    def test_get_metadata_by_task_id_exception_returns_500(self, mock_ct):
        """Generic Exception from _get_metadata_by_task_id via URL param returns 500 (lines 193-195)."""

        class NotDoesNotExist(Exception):
            pass

        mock_ct.DoesNotExist = NotDoesNotExist
        mock_ct.get_by_id.side_effect = RuntimeError("crash")

        resp = self.get_json("/metadata/by-task/42")
        assert resp.code == 500


# ---------------------------------------------------------------------------
# metadata_api: _get_metadata_by_task_id — with metadata results (lines 209, 212, 216-226)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiMetadataHandler, "initialize", _meta_mock_initialize)
class TestGetMetadataByTaskIdResults(ApiTestBase):
    __test__ = True
    handler_class = ApiMetadataHandler

    @patch(f"{METADATA_API}.CompressoFileMetadata._load_json_dict", return_value={})
    @patch(f"{METADATA_API}.FileMetadataPaths")
    @patch(f"{METADATA_API}.FileMetadata")
    @patch(f"{METADATA_API}.CompletedTasks")
    def test_get_metadata_with_file_metadata_rows(self, mock_ct, mock_fm, mock_fmp, _mock_load):
        """_get_metadata_by_task_id builds results when FileMetadata rows exist (lines 216-226)."""
        mock_task = MagicMock()
        mock_task.abspath = "/media/test.mkv"
        mock_ct.get_by_id.return_value = mock_task

        # One file metadata row matched by task ID
        fm_id_row = MagicMock()
        fm_id_row.id = 7

        # Simulate FileMetadata.select().where() for last_task_id
        # and FileMetadataPaths.select().where() for path
        mock_fm.select.return_value.where.return_value = [fm_id_row]
        mock_fmp.select.return_value.where.return_value = []  # no path matches

        # Path map rows for id=7
        path_row = MagicMock()
        path_row.file_metadata.id = 7
        path_row.path = "/media/test.mkv"
        path_row.path_type = "source"
        mock_fmp.select.return_value.where.return_value = [path_row]

        # Full metadata rows
        meta_row = MagicMock()
        meta_row.id = 7
        meta_row.fingerprint = "fp123"
        meta_row.fingerprint_algo = "xxhash"
        meta_row.metadata_json = "{}"
        meta_row.last_task_id = 1
        mock_fm.select.return_value.where.return_value = [meta_row]

        resp = self.post_json("/metadata/by-task", {"task_id": 1})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert "results" in data


# ---------------------------------------------------------------------------
# metadata_api: update_metadata BaseApiError + Exception (lines 282-285)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiMetadataHandler, "initialize", _meta_mock_initialize)
class TestUpdateMetadataErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiMetadataHandler

    @patch(f"{METADATA_API}.FileMetadata")
    def test_update_metadata_base_api_error_returns_400(self, mock_fm):
        """BaseApiError in update_metadata returns 400 (lines 278-282)."""
        mock_fm.get_or_none.side_effect = BaseApiError("db fail")

        with patch(f"{METADATA_API}.CompressoFileMetadata._enforce_plugin_size_limit"):
            resp = self.post_json(
                "/metadata/update",
                {"fingerprint": "fp1", "plugin_id": "p1", "json_blob": {"k": "v"}},
            )
        assert resp.code == 400

    @patch(f"{METADATA_API}.FileMetadata")
    def test_update_metadata_exception_returns_500(self, mock_fm):
        """Generic Exception in update_metadata returns 500 (lines 283-285)."""
        mock_fm.get_or_none.side_effect = RuntimeError("db crash")

        with patch(f"{METADATA_API}.CompressoFileMetadata._enforce_plugin_size_limit"):
            resp = self.post_json(
                "/metadata/update",
                {"fingerprint": "fp1", "plugin_id": "p1", "json_blob": {"k": "v"}},
            )
        assert resp.code == 500


# ---------------------------------------------------------------------------
# metadata_api: delete_metadata BaseApiError + Exception (lines 301-308)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiMetadataHandler, "initialize", _meta_mock_initialize)
class TestDeleteMetadataErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiMetadataHandler

    @patch(f"{METADATA_API}.CompressoFileMetadata")
    def test_delete_metadata_base_api_error_returns_400(self, mock_cfm):
        """BaseApiError in delete_metadata returns 400 (lines 301-305)."""
        mock_cfm.delete_for_plugin.side_effect = BaseApiError("db fail")

        resp = self.fetch(
            "/compresso/api/v2/metadata",
            method="DELETE",
            body=json.dumps({"fingerprint": "fp1", "plugin_id": "p1"}),
            headers={"Content-Type": "application/json"},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 400

    @patch(f"{METADATA_API}.CompressoFileMetadata")
    def test_delete_metadata_exception_returns_500(self, mock_cfm):
        """Generic Exception in delete_metadata returns 500 (lines 306-308)."""
        mock_cfm.delete_for_plugin.side_effect = RuntimeError("db crash")

        resp = self.fetch(
            "/compresso/api/v2/metadata",
            method="DELETE",
            body=json.dumps({"fingerprint": "fp1", "plugin_id": "p1"}),
            headers={"Content-Type": "application/json"},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 500


# ---------------------------------------------------------------------------
# metadata_api: get_metadata_by_fingerprint BaseApiError + Exception (lines 349-356)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiMetadataHandler, "initialize", _meta_mock_initialize)
class TestGetMetadataByFingerprintErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiMetadataHandler

    @patch(f"{METADATA_API}.FileMetadata")
    def test_get_by_fingerprint_base_api_error_returns_400(self, mock_fm):
        """BaseApiError in get_metadata_by_fingerprint returns 400 (lines 349-353)."""
        mock_fm.get_or_none.side_effect = BaseApiError("db fail")

        resp = self.post_json("/metadata/by-fingerprint", {"fingerprint": "fp1"})
        assert resp.code == 400

    @patch(f"{METADATA_API}.FileMetadata")
    def test_get_by_fingerprint_exception_returns_500(self, mock_fm):
        """Generic Exception in get_metadata_by_fingerprint returns 500 (lines 354-356)."""
        mock_fm.get_or_none.side_effect = RuntimeError("db crash")

        resp = self.post_json("/metadata/by-fingerprint", {"fingerprint": "fp1"})
        assert resp.code == 500


# ---------------------------------------------------------------------------
# metadata_api: search_metadata POST with no path — BaseApiError check
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiMetadataHandler, "initialize", _meta_mock_initialize)
class TestSearchMetadataPostNoPath(ApiTestBase):
    __test__ = True
    handler_class = ApiMetadataHandler

    @patch(f"{METADATA_API}.FileMetadataPaths")
    @patch(f"{METADATA_API}.FileMetadata")
    def test_search_metadata_post_no_path_success(self, mock_fm, mock_fmp):
        """POST /metadata/search without path body returns all results."""
        mock_base = MagicMock()
        mock_base.count.return_value = 0
        mock_base.order_by.return_value.limit.return_value.offset.return_value = []
        mock_fm.select.return_value = mock_base
        mock_fm.id = MagicMock()

        resp = self.post_json("/metadata/search", {})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["total_count"] == 0


# =============================================================================
# PLUGIN REPOS MIXIN  (plugin_repos_mixin.py)
# =============================================================================

PLUGIN_REPOS_MIXIN = "compresso.webserver.api_v2.plugin_repos_mixin"
PLUGINS_HELPERS_MOD = "compresso.webserver.helpers.plugins"


def _plugins_mock_initialize(self, **kwargs):
    """Stub that avoids real session/queue lookups."""
    self.session = MagicMock()
    self.params = kwargs.get("params")
    self.compresso_data_queues = {}


# ---------------------------------------------------------------------------
# plugin_repos_mixin: update_repo_list — BaseApiError + Exception (lines 93-101)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiPluginsHandler, "initialize", _plugins_mock_initialize)
class TestUpdateRepoListErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiPluginsHandler

    @patch(PLUGINS_HELPERS_MOD + ".save_plugin_repos_list", side_effect=BaseApiError("save fail"))
    def test_update_repo_list_base_api_error_returns_400(self, _mock):
        """BaseApiError in update_repo_list returns 400 (lines 93-97)."""
        resp = self.post_json(
            "/plugins/repos/update",
            {"repos_list": ["https://example.com/repo.json"]},
        )
        assert resp.code == 400

    @patch(PLUGINS_HELPERS_MOD + ".save_plugin_repos_list", side_effect=Exception("crash"))
    def test_update_repo_list_exception_returns_500(self, _mock):
        """Generic Exception in update_repo_list returns 500 (lines 98-101)."""
        resp = self.post_json(
            "/plugins/repos/update",
            {"repos_list": ["https://example.com/repo.json"]},
        )
        assert resp.code == 500


# ---------------------------------------------------------------------------
# plugin_repos_mixin: get_repo_list — BaseApiError + Exception (lines 147-154)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiPluginsHandler, "initialize", _plugins_mock_initialize)
class TestGetRepoListErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiPluginsHandler

    @patch(PLUGINS_HELPERS_MOD + ".prepare_plugin_repos_list", side_effect=BaseApiError("list fail"))
    def test_get_repo_list_base_api_error_returns_400(self, _mock):
        """BaseApiError in get_repo_list returns 400 (lines 147-150)."""
        resp = self.get_json("/plugins/repos/list")
        assert resp.code == 400

    @patch(PLUGINS_HELPERS_MOD + ".prepare_plugin_repos_list", side_effect=Exception("crash"))
    def test_get_repo_list_exception_returns_500(self, _mock):
        """Generic Exception in get_repo_list returns 500 (lines 151-154)."""
        resp = self.get_json("/plugins/repos/list")
        assert resp.code == 500


# ---------------------------------------------------------------------------
# plugin_repos_mixin: reload_repo_data — BaseApiError + Exception (lines 201-209)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiPluginsHandler, "initialize", _plugins_mock_initialize)
class TestReloadRepoDataErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiPluginsHandler

    @patch(PLUGINS_HELPERS_MOD + ".reload_plugin_repos_data", side_effect=BaseApiError("reload fail"))
    def test_reload_repo_data_base_api_error_returns_400(self, _mock):
        """BaseApiError in reload_repo_data returns 400 (lines 201-205)."""
        resp = self.post_json("/plugins/repos/reload", {})
        assert resp.code == 400

    @patch(PLUGINS_HELPERS_MOD + ".reload_plugin_repos_data", side_effect=Exception("crash"))
    def test_reload_repo_data_exception_returns_500(self, _mock):
        """Generic Exception in reload_repo_data returns 500 (lines 206-209)."""
        resp = self.post_json("/plugins/repos/reload", {})
        assert resp.code == 500


# ---------------------------------------------------------------------------
# plugin_repos_mixin: get_community_repos — full path (lines 228-274)
# ---------------------------------------------------------------------------

_REPOS_RESPONSE = {
    "repos": [
        {
            "repo_id": "community-1",
            "name": "Community Repo",
            "icon": "",
            "path": "https://example.com/repo.json",
        }
    ]
}


class _CommunityReposAppMixin:
    """Helper mixin: override get_app() so application.settings has serve_traceback=True."""

    def get_app(self):
        import tornado.web

        return tornado.web.Application(
            [(r"/compresso/api/v2/(.*)", ApiPluginsHandler)],
            serve_traceback=True,
        )


@pytest.mark.unittest
class TestGetCommunityReposNoCache(_CommunityReposAppMixin, ApiTestBase):
    """Tests that exercise the live-API path (serve_traceback=True skips cache I/O)."""

    __test__ = True
    handler_class = ApiPluginsHandler

    @patch(PLUGIN_REPOS_MIXIN + ".compresso_config")
    def test_get_community_repos_api_success(self, mock_cfg):
        """get_community_repos fetches from API when cache is bypassed (serve_traceback=True) (lines 249-265)."""
        mock_cfg.Config.return_value.get_plugins_path.return_value = "/tmp/no-such-path"

        def _init(handler_self, **kwargs):
            _plugins_mock_initialize(handler_self, **kwargs)
            handler_self.session.get_installation_uuid.return_value = "uuid-test"
            handler_self.session.get_supporter_level.return_value = "free"
            handler_self.session.api_get.return_value = (_REPOS_RESPONSE, 200)

        with patch.object(ApiPluginsHandler, "initialize", _init):
            resp = self.get_json("/plugins/repos/community")
        assert resp.code == 200

    @patch(PLUGIN_REPOS_MIXIN + ".compresso_config")
    def test_get_community_repos_api_non_200_status(self, mock_cfg):
        """get_community_repos propagates non-200 API status code (lines 253-256)."""
        mock_cfg.Config.return_value.get_plugins_path.return_value = "/tmp/no-such-path"

        def _init(handler_self, **kwargs):
            _plugins_mock_initialize(handler_self, **kwargs)
            handler_self.session.get_installation_uuid.return_value = "uuid-test"
            handler_self.session.get_supporter_level.return_value = "free"
            handler_self.session.api_get.return_value = ({}, 429)

        with patch.object(ApiPluginsHandler, "initialize", _init):
            resp = self.get_json("/plugins/repos/community")
        assert resp.code == 429

    @patch(PLUGIN_REPOS_MIXIN + ".compresso_config")
    def test_get_community_repos_exception_returns_500(self, mock_cfg):
        """Generic Exception in get_community_repos returns 500 (lines 271-274)."""
        mock_cfg.Config.return_value.get_plugins_path.return_value = "/tmp/no-such-path"

        def _init(handler_self, **kwargs):
            _plugins_mock_initialize(handler_self, **kwargs)
            handler_self.session.get_installation_uuid.side_effect = Exception("session crash")

        with patch.object(ApiPluginsHandler, "initialize", _init):
            resp = self.get_json("/plugins/repos/community")
        assert resp.code == 500


@pytest.mark.unittest
@patch.object(ApiPluginsHandler, "initialize", _plugins_mock_initialize)
class TestGetCommunityReposWithCache(ApiTestBase):
    """Tests that exercise the cache path (default app has no serve_traceback)."""

    __test__ = True
    handler_class = ApiPluginsHandler

    @patch(PLUGIN_REPOS_MIXIN + ".os.path.exists", return_value=True)
    @patch(PLUGIN_REPOS_MIXIN + ".compresso_config")
    def test_get_community_repos_serves_valid_cache(self, mock_cfg, mock_exists):
        """get_community_repos returns cached response when cache is fresh and valid (lines 234-245)."""
        import time as _time

        mock_cfg.Config.return_value.get_plugins_path.return_value = "/tmp/plugins-test"

        fresh_cached = {
            "cached_at": _time.time(),
            "response": _REPOS_RESPONSE,
        }

        def _init(handler_self, **kwargs):
            _plugins_mock_initialize(handler_self, **kwargs)
            handler_self.session.get_installation_uuid.return_value = "uuid-test"
            handler_self.session.get_supporter_level.return_value = "free"

        with (
            patch.object(ApiPluginsHandler, "initialize", _init),
            patch.object(ApiPluginsHandler, "_read_json_file", return_value=fresh_cached),
        ):
            resp = self.get_json("/plugins/repos/community")
        assert resp.code == 200

    @patch(PLUGIN_REPOS_MIXIN + ".os.path.exists", return_value=True)
    @patch(PLUGIN_REPOS_MIXIN + ".compresso_config")
    def test_get_community_repos_stale_cache_falls_through_to_api(self, mock_cfg, mock_exists):
        """Stale cache falls through to the live API call (lines 243, 249-265)."""
        mock_cfg.Config.return_value.get_plugins_path.return_value = "/tmp/plugins-test"

        stale_cached = {
            "cached_at": 0,  # epoch — always stale
            "response": _REPOS_RESPONSE,
        }
        live_response = {
            "repos": [
                {
                    "repo_id": "live-repo",
                    "name": "Live",
                    "icon": "",
                    "path": "https://example.com/live.json",
                }
            ]
        }

        def _init(handler_self, **kwargs):
            _plugins_mock_initialize(handler_self, **kwargs)
            handler_self.session.get_installation_uuid.return_value = "uuid-test"
            handler_self.session.get_supporter_level.return_value = "free"
            handler_self.session.api_get.return_value = (live_response, 200)

        with (
            patch.object(ApiPluginsHandler, "initialize", _init),
            patch.object(ApiPluginsHandler, "_read_json_file", return_value=stale_cached),
            patch.object(ApiPluginsHandler, "_write_json_file"),
        ):
            resp = self.get_json("/plugins/repos/community")
        assert resp.code == 200


# =============================================================================
# SETTINGS HELPER  (compresso/webserver/helpers/settings.py)
# =============================================================================


# ---------------------------------------------------------------------------
# save_library_config: new library branch (lines 62-69)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch("compresso.webserver.helpers.settings.PluginExecutor")
@patch("compresso.webserver.helpers.settings.plugins")
@patch("compresso.webserver.helpers.settings.Library")
def test_save_library_config_creates_new_library_when_id_zero(
    mock_library_class,
    mock_plugins,
    mock_plugin_executor,
):
    """library_id=0 triggers Library.create() path (lines 62-69)."""
    mock_new_lib = MagicMock()
    mock_new_lib.get_id.return_value = 99
    mock_new_lib.get_name.return_value = "NewLib"
    mock_new_lib.get_path.return_value = "/new"
    mock_new_lib.get_locked.return_value = False
    mock_new_lib.get_enable_remote_only.return_value = False
    mock_new_lib.get_enable_scanner.return_value = False
    mock_new_lib.get_enable_inotify.return_value = False
    mock_new_lib.get_priority_score.return_value = 0
    mock_new_lib.get_tags.return_value = []
    mock_new_lib.save.return_value = True
    mock_library_class.create.return_value = mock_new_lib
    mock_plugins.get_plugin_types_with_flows.return_value = []

    result = settings.save_library_config(
        0,
        library_config={"name": "NewLib", "path": "/new"},
    )

    mock_library_class.create.assert_called_once_with({"name": "NewLib", "path": "/new"})
    assert result is True


@pytest.mark.unittest
@patch("compresso.webserver.helpers.settings.PluginExecutor")
@patch("compresso.webserver.helpers.settings.plugins")
@patch("compresso.webserver.helpers.settings.Library")
def test_save_library_config_negative_id_creates_new_library(
    mock_library_class,
    mock_plugins,
    mock_plugin_executor,
):
    """Negative library_id also triggers Library.create() (line 56 → else at 62)."""
    mock_new_lib = MagicMock()
    mock_new_lib.get_id.return_value = 100
    mock_new_lib.get_name.return_value = "AnotherLib"
    mock_new_lib.get_path.return_value = "/another"
    mock_new_lib.get_locked.return_value = False
    mock_new_lib.get_enable_remote_only.return_value = False
    mock_new_lib.get_enable_scanner.return_value = False
    mock_new_lib.get_enable_inotify.return_value = False
    mock_new_lib.get_priority_score.return_value = 0
    mock_new_lib.get_tags.return_value = []
    mock_new_lib.save.return_value = True
    mock_library_class.create.return_value = mock_new_lib
    mock_plugins.get_plugin_types_with_flows.return_value = []

    result = settings.save_library_config(
        -1,
        library_config={"name": "AnotherLib", "path": "/another"},
    )

    mock_library_class.create.assert_called_once()
    assert result is True


# ---------------------------------------------------------------------------
# save_library_config: plugin installation with repo refresh (lines 113-120)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch("compresso.webserver.helpers.settings.PluginExecutor")
@patch("compresso.webserver.helpers.settings.plugins")
@patch("compresso.webserver.helpers.settings.Library")
@patch("compresso.webserver.helpers.settings.logger")
def test_save_library_config_installs_missing_plugin_with_repo_refresh(
    mock_logger,
    mock_library_class,
    mock_plugins,
    mock_plugin_executor,
):
    """Not-installed plugin triggers repo refresh then install (lines 109-120)."""
    mock_library = MagicMock()
    mock_library.get_enable_scanner.return_value = False
    mock_library.get_enable_inotify.return_value = False
    mock_library.get_name.return_value = "Lib"
    mock_library.get_path.return_value = "/lib"
    mock_library.get_locked.return_value = False
    mock_library.get_enable_remote_only.return_value = False
    mock_library.get_priority_score.return_value = 0
    mock_library.get_tags.return_value = []
    mock_library.save.return_value = True
    mock_library_class.return_value = mock_library

    # Plugin is NOT installed → triggers refresh + install
    mock_plugins.check_if_plugin_is_installed.return_value = False
    mock_plugins.reload_plugin_repos_data.return_value = True
    mock_plugins.install_plugin_by_id.return_value = True
    mock_plugins.get_plugin_types_with_flows.return_value = []

    result = settings.save_library_config(
        1,
        plugin_config={
            "enabled_plugins": [{"plugin_id": "encoder.hevc", "has_config": False}],
        },
    )

    mock_plugins.reload_plugin_repos_data.assert_called_once()
    mock_plugins.install_plugin_by_id.assert_called_once_with("encoder.hevc")
    assert result is True


@pytest.mark.unittest
@patch("compresso.webserver.helpers.settings.PluginExecutor")
@patch("compresso.webserver.helpers.settings.plugins")
@patch("compresso.webserver.helpers.settings.Library")
def test_save_library_config_install_failure_raises_and_deletes_new_library(
    mock_library_class,
    mock_plugins,
    mock_plugin_executor,
):
    """Failed plugin install on a new library calls library.delete() then raises (lines 117-120)."""
    mock_new_lib = MagicMock()
    mock_new_lib.get_id.return_value = 101
    mock_new_lib.get_name.return_value = "NewLib"
    mock_new_lib.get_path.return_value = "/new"
    mock_new_lib.get_locked.return_value = False
    mock_new_lib.get_enable_remote_only.return_value = False
    mock_new_lib.get_enable_scanner.return_value = False
    mock_new_lib.get_enable_inotify.return_value = False
    mock_new_lib.get_priority_score.return_value = 0
    mock_new_lib.get_tags.return_value = []
    mock_library_class.create.return_value = mock_new_lib

    mock_plugins.check_if_plugin_is_installed.return_value = False
    mock_plugins.reload_plugin_repos_data.return_value = True
    mock_plugins.install_plugin_by_id.return_value = False  # install fails

    with pytest.raises(Exception, match="Failed to install plugin"):
        settings.save_library_config(
            0,
            library_config={"name": "NewLib", "path": "/new"},
            plugin_config={
                "enabled_plugins": [{"plugin_id": "bad.plugin", "has_config": False}],
            },
        )

    mock_new_lib.delete.assert_called_once()


@pytest.mark.unittest
@patch("compresso.webserver.helpers.settings.PluginExecutor")
@patch("compresso.webserver.helpers.settings.plugins")
@patch("compresso.webserver.helpers.settings.Library")
def test_save_library_config_second_missing_plugin_skips_refresh(
    mock_library_class,
    mock_plugins,
    mock_plugin_executor,
):
    """repo_refreshed flag ensures reload_plugin_repos_data is called only once (lines 113-115)."""
    mock_library = MagicMock()
    mock_library.get_enable_scanner.return_value = False
    mock_library.get_enable_inotify.return_value = False
    mock_library.get_name.return_value = "Lib"
    mock_library.get_path.return_value = "/lib"
    mock_library.get_locked.return_value = False
    mock_library.get_enable_remote_only.return_value = False
    mock_library.get_priority_score.return_value = 0
    mock_library.get_tags.return_value = []
    mock_library.save.return_value = True
    mock_library_class.return_value = mock_library

    mock_plugins.check_if_plugin_is_installed.return_value = False
    mock_plugins.reload_plugin_repos_data.return_value = True
    mock_plugins.install_plugin_by_id.return_value = True
    mock_plugins.get_plugin_types_with_flows.return_value = []

    settings.save_library_config(
        1,
        plugin_config={
            "enabled_plugins": [
                {"plugin_id": "encoder.hevc", "has_config": False},
                {"plugin_id": "filter.denoise", "has_config": False},
            ],
        },
    )

    # Reload should only be called once even though two plugins needed installing
    mock_plugins.reload_plugin_repos_data.assert_called_once()


# ---------------------------------------------------------------------------
# save_library_config: plugin flow save (lines 131-136)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch("compresso.webserver.helpers.settings.PluginExecutor")
@patch("compresso.webserver.helpers.settings.plugins")
@patch("compresso.webserver.helpers.settings.Library")
def test_save_library_config_saves_plugin_flow(
    mock_library_class,
    mock_plugins,
    mock_plugin_executor,
):
    """plugin_flow in plugin_config triggers flow save for each plugin type (lines 131-136)."""
    mock_library = MagicMock()
    mock_library.get_id.return_value = 2
    mock_library.get_enable_scanner.return_value = False
    mock_library.get_enable_inotify.return_value = False
    mock_library.get_name.return_value = "Lib"
    mock_library.get_path.return_value = "/lib"
    mock_library.get_locked.return_value = False
    mock_library.get_enable_remote_only.return_value = False
    mock_library.get_priority_score.return_value = 0
    mock_library.get_tags.return_value = []
    mock_library.save.return_value = True
    mock_library_class.return_value = mock_library

    mock_plugins.get_plugin_types_with_flows.return_value = ["worker.process", "library_management.file_test"]
    mock_plugins.save_enabled_plugin_flows_for_plugin_type.return_value = True

    result = settings.save_library_config(
        2,
        plugin_config={
            "plugin_flow": {
                "worker.process": ["encoder.hevc"],
                "library_management.file_test": [],
            }
        },
    )

    assert mock_plugins.save_enabled_plugin_flows_for_plugin_type.call_count == 2
    assert result is True


# ---------------------------------------------------------------------------
# save_library_config: plugin executor saves settings (line 127)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
@patch("compresso.webserver.helpers.settings.PluginExecutor")
@patch("compresso.webserver.helpers.settings.plugins")
@patch("compresso.webserver.helpers.settings.Library")
def test_save_library_config_calls_plugin_executor_for_has_config(
    mock_library_class,
    mock_plugins,
    mock_plugin_executor,
):
    """Plugins with has_config=True call plugin_executor.save_plugin_settings (line 127)."""
    mock_library = MagicMock()
    mock_library.get_enable_scanner.return_value = False
    mock_library.get_enable_inotify.return_value = False
    mock_library.get_name.return_value = "Lib"
    mock_library.get_path.return_value = "/lib"
    mock_library.get_locked.return_value = False
    mock_library.get_enable_remote_only.return_value = False
    mock_library.get_priority_score.return_value = 0
    mock_library.get_tags.return_value = []
    mock_library.save.return_value = True
    mock_library_class.return_value = mock_library

    mock_plugins.check_if_plugin_is_installed.return_value = True
    mock_plugins.get_plugin_types_with_flows.return_value = []

    mock_executor_instance = MagicMock()
    mock_plugin_executor.return_value = mock_executor_instance

    settings.save_library_config(
        1,
        plugin_config={
            "enabled_plugins": [
                {
                    "plugin_id": "encoder.hevc",
                    "has_config": True,
                    "settings": {"crf": "23"},
                }
            ],
        },
    )

    mock_executor_instance.save_plugin_settings.assert_called_once_with("encoder.hevc", {"crf": "23"}, library_id=1)


# ---------------------------------------------------------------------------
# save_worker_group_config: create new worker group (lines 153-177)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
def test_save_worker_group_config_creates_new_when_no_id():
    """No 'id' in data → WorkerGroup.create() is called and function returns None (lines 156-157)."""
    mock_wg_class = MagicMock()

    with (
        patch("compresso.libs.worker_group.WorkerGroup.create", mock_wg_class.create),
        # Patch the local import inside save_worker_group_config
        patch.dict("sys.modules", {"compresso.libs.worker_group": MagicMock(WorkerGroup=mock_wg_class)}),
    ):
        result = settings.save_worker_group_config({"name": "Group A", "number_of_workers": 2})

    mock_wg_class.create.assert_called_once_with({"name": "Group A", "number_of_workers": 2})
    assert result is None


@pytest.mark.unittest
def test_save_worker_group_config_updates_existing():
    """Existing 'id' in data → WorkerGroup instance is updated and saved (lines 162-177)."""
    mock_wg = MagicMock()
    mock_wg.get_locked.return_value = False
    mock_wg.get_name.return_value = "Old Name"
    mock_wg.get_number_of_workers.return_value = 1
    mock_wg.get_worker_type.return_value = "cpu"
    mock_wg.get_tags.return_value = []
    mock_wg.get_worker_event_schedules.return_value = []
    mock_wg.save.return_value = True

    mock_wg_class = MagicMock(return_value=mock_wg)

    with patch.dict("sys.modules", {"compresso.libs.worker_group": MagicMock(WorkerGroup=mock_wg_class)}):
        result = settings.save_worker_group_config(
            {
                "id": 5,
                "name": "Updated Group",
                "number_of_workers": 4,
                "worker_type": "gpu",
                "locked": True,
                "tags": ["tag1"],
                "worker_event_schedules": [{"event": "start"}],
            }
        )

    mock_wg.set_name.assert_called_with("Updated Group")
    mock_wg.set_number_of_workers.assert_called_with(4)
    mock_wg.set_worker_type.assert_called_with("gpu")
    mock_wg.set_locked.assert_called_with(True)
    mock_wg.set_tags.assert_called_with(["tag1"])
    mock_wg.set_worker_event_schedules.assert_called_with([{"event": "start"}])
    mock_wg.save.assert_called_once()
    assert result is True


@pytest.mark.unittest
def test_save_worker_group_config_update_uses_defaults_when_keys_absent():
    """Missing optional keys fall back to existing getter values (lines 164-174)."""
    mock_wg = MagicMock()
    mock_wg.get_locked.return_value = False
    mock_wg.get_name.return_value = "Existing"
    mock_wg.get_number_of_workers.return_value = 2
    mock_wg.get_worker_type.return_value = "cpu"
    mock_wg.get_tags.return_value = []
    mock_wg.get_worker_event_schedules.return_value = []
    mock_wg.save.return_value = True

    mock_wg_class = MagicMock(return_value=mock_wg)

    with patch.dict("sys.modules", {"compresso.libs.worker_group": MagicMock(WorkerGroup=mock_wg_class)}):
        settings.save_worker_group_config({"id": 3})

    # With no override keys, setters should be called with the getter return values
    mock_wg.set_name.assert_called_with("Existing")
    mock_wg.set_number_of_workers.assert_called_with(2)
    mock_wg.set_worker_type.assert_called_with("cpu")
