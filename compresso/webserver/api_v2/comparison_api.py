#!/usr/bin/env python3

"""API endpoints for persistent sample bake-off comparisons."""

from compresso.libs.comparison import ComparisonManager
from compresso.libs.preview import validate_preview_source_path
from compresso.webserver.api_v2.base_api_handler import BaseApiError, BaseApiHandler
from compresso.webserver.api_v2.schema.comparison_schemas import (
    ComparisonCreateResponseSchema,
    ComparisonProfilesResponseSchema,
    ComparisonStatusResponseSchema,
    RequestComparisonCleanupSchema,
    RequestComparisonCreateSchema,
    RequestComparisonStatusSchema,
    RequestComparisonWinnerSchema,
)


class ApiComparisonHandler(BaseApiHandler):
    routes = [
        {
            "path_pattern": r"/comparison/profiles",
            "supported_methods": ["GET"],
            "call_method": "get_profiles",
        },
        {
            "path_pattern": r"/comparison/create",
            "supported_methods": ["POST"],
            "call_method": "create_comparison",
        },
        {
            "path_pattern": r"/comparison/status",
            "supported_methods": ["POST"],
            "call_method": "get_comparison_status",
        },
        {
            "path_pattern": r"/comparison/winner",
            "supported_methods": ["POST"],
            "call_method": "select_winner",
        },
        {
            "path_pattern": r"/comparison/cleanup",
            "supported_methods": ["POST"],
            "call_method": "cleanup_comparison",
        },
    ]

    async def get_profiles(self):
        """
        Comparison - profiles
        ---
        description: List built-in sample encode profiles and local encoder availability.
        responses:
            200:
                description: Available comparison profiles.
                content:
                    application/json:
                        schema:
                            ComparisonProfilesResponseSchema
        """
        try:
            response = self.build_response(
                ComparisonProfilesResponseSchema(),
                {"success": True, "profiles": ComparisonManager.get_profiles()},
            )
            self.write_success(response)
        except Exception as exc:
            self.handle_unhandled_error(exc)

    async def create_comparison(self):
        """
        Comparison - create
        ---
        description: Create a persistent two-to-four candidate sample encode batch.
        requestBody:
            required: True
            content:
                application/json:
                    schema:
                        RequestComparisonCreateSchema
        responses:
            200:
                description: Comparison batch created.
                content:
                    application/json:
                        schema:
                            ComparisonCreateResponseSchema
        """
        try:
            request = self.read_json_request(RequestComparisonCreateSchema())
            from compresso.webserver.helpers.healthcheck import validate_library_exists

            validate_library_exists(request["library_id"])
            source_path = validate_preview_source_path(
                request["source_path"],
                library_id=request["library_id"],
                allow_cache=False,
            )
            batch_uuid = ComparisonManager().create_batch(
                source_path=source_path,
                start_time=request["start_time"],
                duration=request["duration"],
                library_id=request["library_id"],
                profile_keys=request["profile_keys"],
            )
            response = self.build_response(
                ComparisonCreateResponseSchema(),
                {"success": True, "batch_uuid": batch_uuid},
            )
            self.write_success(response)
        except (ValueError, RuntimeError) as exc:
            self.handle_base_api_error(
                BaseApiError("Comparison request could not be processed", private_detail=f"{type(exc).__name__}: {exc}")
            )
        except BaseApiError as exc:
            self.handle_base_api_error(exc)
        except Exception as exc:
            self.handle_unhandled_error(exc)

    async def get_comparison_status(self):
        """
        Comparison - status
        ---
        description: Read batch and per-candidate status, progress, paths, and metrics.
        requestBody:
            required: True
            content:
                application/json:
                    schema:
                        RequestComparisonStatusSchema
        responses:
            200:
                description: Current comparison status.
                content:
                    application/json:
                        schema:
                            ComparisonStatusResponseSchema
        """
        try:
            request = self.read_json_request(RequestComparisonStatusSchema())
            status = ComparisonManager().get_batch_status(request["batch_uuid"])
            if status is None:
                raise ValueError("Comparison batch not found")
            status["success"] = True
            response = self.build_response(ComparisonStatusResponseSchema(), status)
            self.write_success(response)
        except ValueError as exc:
            self.handle_base_api_error(BaseApiError("Comparison batch not found", private_detail=str(exc)))
        except BaseApiError as exc:
            self.handle_base_api_error(exc)
        except Exception as exc:
            self.handle_unhandled_error(exc)

    async def select_winner(self):
        """
        Comparison - winner
        ---
        description: Pick a completed candidate and optionally queue the full source with that profile.
        requestBody:
            required: True
            content:
                application/json:
                    schema:
                        RequestComparisonWinnerSchema
        responses:
            200:
                description: Updated comparison status.
                content:
                    application/json:
                        schema:
                            ComparisonStatusResponseSchema
        """
        try:
            request = self.read_json_request(RequestComparisonWinnerSchema())
            status = ComparisonManager().select_winner(
                request["batch_uuid"],
                request["candidate_uuid"],
                queue_full_encode=request["queue_full_encode"],
            )
            status["success"] = True
            response = self.build_response(ComparisonStatusResponseSchema(), status)
            self.write_success(response)
        except (ValueError, RuntimeError) as exc:
            self.handle_base_api_error(
                BaseApiError("Winner could not be applied", private_detail=f"{type(exc).__name__}: {exc}")
            )
        except BaseApiError as exc:
            self.handle_base_api_error(exc)
        except Exception as exc:
            self.handle_unhandled_error(exc)

    async def cleanup_comparison(self):
        """
        Comparison - cleanup
        ---
        description: Remove a terminal comparison batch and its cached samples.
        requestBody:
            required: True
            content:
                application/json:
                    schema:
                        RequestComparisonCleanupSchema
        responses:
            200:
                description: Comparison removed.
        """
        try:
            request = self.read_json_request(RequestComparisonCleanupSchema())
            ComparisonManager().cleanup_batch(request["batch_uuid"])
            self.write_success()
        except RuntimeError as exc:
            self.handle_base_api_error(BaseApiError("Comparison is still running", private_detail=str(exc)))
        except BaseApiError as exc:
            self.handle_base_api_error(exc)
        except Exception as exc:
            self.handle_unhandled_error(exc)
