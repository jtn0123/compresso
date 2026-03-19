#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    compresso.approval_api.py

    API handler for the approval workflow.
    Provides endpoints to list, approve, reject, and inspect tasks
    that are awaiting user approval before file replacement.
"""

import tornado.log

from compresso.webserver.api_v2.base_api_handler import BaseApiError, BaseApiHandler
from compresso.webserver.api_v2.schema.approval_schemas import (
    RequestApprovalTasksSchema,
    ApprovalTasksResponseSchema,
    RequestApprovalActionSchema,
    RequestRejectActionSchema,
    RequestApprovalDetailSchema,
    ApprovalDetailResponseSchema,
    ApprovalCountResponseSchema,
)


class ApiApprovalHandler(BaseApiHandler):
    routes = [
        {
            "path_pattern":      r"/approval/tasks",
            "supported_methods": ["POST"],
            "call_method":       "get_approval_tasks",
        },
        {
            "path_pattern":      r"/approval/approve",
            "supported_methods": ["POST"],
            "call_method":       "approve_tasks",
        },
        {
            "path_pattern":      r"/approval/reject",
            "supported_methods": ["POST"],
            "call_method":       "reject_tasks",
        },
        {
            "path_pattern":      r"/approval/detail",
            "supported_methods": ["POST"],
            "call_method":       "get_task_detail",
        },
        {
            "path_pattern":      r"/approval/count",
            "supported_methods": ["GET"],
            "call_method":       "get_approval_count",
        },
    ]

    async def get_approval_tasks(self):
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
                    'start':        json_request.get('start', 0),
                    'length':       json_request.get('length', 10),
                    'search_value': json_request.get('search_value', ''),
                    'library_ids':  json_request.get('library_ids', []),
                },
                include_library=json_request.get('include_library', False),
            )

            result['success'] = True
            response = self.build_response(ApprovalTasksResponseSchema(), result)
            self.write_success(response)
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def approve_tasks(self):
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
            approval.approve_tasks(json_request.get('id_list', []))

            self.write_success()
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def reject_tasks(self):
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
            approval.reject_tasks(
                task_ids=json_request.get('id_list', []),
                requeue=json_request.get('requeue', False),
            )

            self.write_success()
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def get_task_detail(self):
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
            detail = approval.get_approval_task_detail(json_request.get('id'))

            if detail is None:
                self.set_status(self.STATUS_ERROR_EXTERNAL, reason="Task not found or not awaiting approval")
                self.write_error()
                return

            detail['success'] = True
            response = self.build_response(ApprovalDetailResponseSchema(), detail)
            self.write_success(response)
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def get_approval_count(self):
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

            response = self.build_response(
                ApprovalCountResponseSchema(),
                {"success": True, "count": count}
            )
            self.write_success(response)
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()
