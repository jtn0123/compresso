#!/usr/bin/env python3

"""
compresso.approval_api.py

API handler for the approval workflow.
Provides endpoints to list, approve, reject, and inspect tasks
that are awaiting user approval before file replacement.
"""

from compresso.webserver.api_v2.base_api_handler import (
    BaseApiError,
    BaseApiHandler,
    boolean_value,
    float_value,
    integer_list_value,
    integer_value,
    string_value,
)
from compresso.webserver.api_v2.schema.approval_schemas import (
    ApprovalCountResponseSchema,
    ApprovalDetailResponseSchema,
    ApprovalSummaryResponseSchema,
    ApprovalTasksResponseSchema,
    RequestApprovalActionSchema,
    RequestApprovalDetailSchema,
    RequestApprovalTasksSchema,
    RequestRejectActionSchema,
)


class ApiApprovalHandler(BaseApiHandler):
    routes = [
        {
            "path_pattern": r"/approval/tasks",
            "supported_methods": ["POST"],
            "call_method": "get_approval_tasks",
        },
        {
            "path_pattern": r"/approval/summary",
            "supported_methods": ["POST"],
            "call_method": "get_approval_summary",
        },
        {
            "path_pattern": r"/approval/approve",
            "supported_methods": ["POST"],
            "call_method": "approve_tasks",
        },
        {
            "path_pattern": r"/approval/reject",
            "supported_methods": ["POST"],
            "call_method": "reject_tasks",
        },
        {
            "path_pattern": r"/approval/detail",
            "supported_methods": ["POST"],
            "call_method": "get_task_detail",
        },
        {
            "path_pattern": r"/approval/count",
            "supported_methods": ["GET"],
            "call_method": "get_approval_count",
        },
    ]

    async def get_approval_tasks(self) -> None:
        """
        Approval - list tasks
        ---
        description: List tasks awaiting approval with pagination and filtering.
        requestBody:
            description: Pagination and filter parameters.
            required: True
            content:
                application/json:
                    schema:
                        RequestApprovalTasksSchema
        responses:
            200:
                description: 'Paginated list of tasks awaiting approval.'
                content:
                    application/json:
                        schema:
                            ApprovalTasksResponseSchema
        """
        try:
            json_request = self.read_json_request(RequestApprovalTasksSchema())

            from compresso.webserver.helpers import approval

            result = approval.prepare_filtered_approval_tasks(
                params={
                    "start": json_request.get("start", 0),
                    "length": json_request.get("length", 10),
                    "search_value": json_request.get("search_value", ""),
                    "library_ids": json_request.get("library_ids", []),
                    "order_by": json_request.get("order_by", "finish_time"),
                    "order_direction": json_request.get("order_direction", "desc"),
                    "codec": json_request.get("codec", ""),
                    "quality_min": json_request.get("quality_min", 0),
                },
                include_library=boolean_value(json_request.get("include_library")),
            )

            result["success"] = True
            response = self.build_response(ApprovalTasksResponseSchema(), result)
            self.write_success(response)
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def get_approval_summary(self) -> None:
        """
        Approval - summary
        ---
        description: Aggregate tasks awaiting approval with optional filters.
        requestBody:
            description: Filter parameters.
            required: True
            content:
                application/json:
                    schema:
                        RequestApprovalTasksSchema
        responses:
            200:
                description: 'Aggregate summary for tasks awaiting approval.'
                content:
                    application/json:
                        schema:
                            ApprovalSummaryResponseSchema
        """
        try:
            json_request = self.read_json_request(RequestApprovalTasksSchema())

            from compresso.webserver.helpers import approval

            result = approval.prepare_approval_summary(
                params={
                    "search_value": json_request.get("search_value", ""),
                    "library_ids": json_request.get("library_ids", []),
                    "order_by": json_request.get("order_by", "finish_time"),
                    "order_direction": json_request.get("order_direction", "desc"),
                    "codec": json_request.get("codec", ""),
                    "quality_min": json_request.get("quality_min", 0),
                }
            )

            result["success"] = True
            response = self.build_response(ApprovalSummaryResponseSchema(), result)
            self.write_success(response)
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def approve_tasks(self) -> None:
        """
        Approval - approve tasks
        ---
        description: Approve one or more tasks. Approved tasks will have their
                     transcoded files replace the originals.
        requestBody:
            description: List of task IDs to approve.
            required: True
            content:
                application/json:
                    schema:
                        RequestApprovalActionSchema
        responses:
            200:
                description: 'Success response.'
                content:
                    application/json:
                        schema:
                            BaseSuccessSchema
        """
        try:
            json_request = self.read_json_request(RequestApprovalActionSchema())

            from compresso.webserver.helpers import approval

            if boolean_value(json_request.get("all_matching")):
                ids = approval.get_all_matching_task_ids(
                    search_value=string_value(json_request.get("search_value")),
                    library_ids=integer_list_value(json_request.get("library_ids")),
                    codec=string_value(json_request.get("codec")),
                    quality_min=float_value(json_request.get("quality_min")),
                )
            else:
                ids = integer_list_value(json_request.get("id_list"))
            approval.approve_tasks(ids)

            self.write_success()
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def reject_tasks(self) -> None:
        """
        Approval - reject tasks
        ---
        description: Reject one or more tasks. Staged and cache files are cleaned up.
                     Optionally requeue the tasks instead of deleting them.
        requestBody:
            description: List of task IDs to reject, with optional requeue flag.
            required: True
            content:
                application/json:
                    schema:
                        RequestRejectActionSchema
        responses:
            200:
                description: 'Success response.'
                content:
                    application/json:
                        schema:
                            BaseSuccessSchema
        """
        try:
            json_request = self.read_json_request(RequestRejectActionSchema())

            from compresso.webserver.helpers import approval

            if boolean_value(json_request.get("all_matching")):
                ids = approval.get_all_matching_task_ids(
                    search_value=string_value(json_request.get("search_value")),
                    library_ids=integer_list_value(json_request.get("library_ids")),
                    codec=string_value(json_request.get("codec")),
                    quality_min=float_value(json_request.get("quality_min")),
                )
            else:
                ids = integer_list_value(json_request.get("id_list"))
            approval.reject_tasks(
                task_ids=ids,
                requeue=boolean_value(json_request.get("requeue")),
            )

            self.write_success()
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def get_task_detail(self) -> None:
        """
        Approval - task detail
        ---
        description: Get detailed comparison data for a single task awaiting approval.
        requestBody:
            description: Task ID to inspect.
            required: True
            content:
                application/json:
                    schema:
                        RequestApprovalDetailSchema
        responses:
            200:
                description: 'Detailed task data including source/staged file comparison.'
                content:
                    application/json:
                        schema:
                            ApprovalDetailResponseSchema
        """
        try:
            json_request = self.read_json_request(RequestApprovalDetailSchema())

            from compresso.webserver.helpers import approval

            detail = approval.get_approval_task_detail(integer_value(json_request.get("id")))

            if detail is None:
                self.set_status(self.STATUS_ERROR_EXTERNAL, reason="Task not found or not awaiting approval")
                self.write_error()
                return

            detail["success"] = True
            response = self.build_response(ApprovalDetailResponseSchema(), detail)
            self.write_success(response)
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def get_approval_count(self) -> None:
        """
        Approval - count
        ---
        description: Get the count of tasks awaiting approval.
        responses:
            200:
                description: 'Count of tasks awaiting approval.'
                content:
                    application/json:
                        schema:
                            ApprovalCountResponseSchema
        """
        try:
            from compresso.webserver.helpers import approval

            count = approval.get_approval_count()

            response = self.build_response(ApprovalCountResponseSchema(), {"success": True, "count": count})
            self.write_success(response)
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)
