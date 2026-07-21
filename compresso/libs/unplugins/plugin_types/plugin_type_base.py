#!/usr/bin/env python3

"""
compresso.plugin_type_base.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     05 Mar 2021, (8:09 PM)

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

import inspect
import json
from collections.abc import Callable, Mapping
from copy import deepcopy
from types import ModuleType
from typing import cast

from compresso.libs.metadata import CompressoFileMetadata
from compresso.libs.task import TaskDataStore


class PluginType:
    """
    PluginType

    Generic configuration and methods used across all plugin types
    """

    name = ""
    runner = ""
    runner_docstring = ""
    data_schema: dict[str, dict[str, object]] = {}
    test_data: dict[str, object] = {}

    def plugin_type_name(self) -> str:
        """
        Return the plugin runner string

        :return:
        """
        return self.name

    def plugin_runner(self) -> str:
        """
        Return the plugin runner string

        :return:
        """
        return self.runner

    def plugin_runner_docstring(self) -> str:
        """
        Return the plugin runner docstring

        :return:
        """
        return self.runner_docstring

    def get_plugin_runner_function(self, plugin_module: ModuleType) -> Callable[..., object] | None:
        plugin_runner = self.plugin_runner()
        # Check if this module contains the given plugin type runner function
        if hasattr(plugin_module, plugin_runner):
            # If it does, add it to the plugin_modules list
            return cast("Callable[..., object]", getattr(plugin_module, plugin_runner))
        return None

    def get_data_schema(self) -> dict[str, dict[str, object]]:
        """
        Return the plugin data schema dictionary

        :return:
        """
        return self.data_schema

    def get_test_data(self) -> dict[str, object]:
        """
        Return the plugin test data dictionary

        :return:
        """
        return self.test_data

    @staticmethod
    def modify_test_data(d: Mapping[str, object], v: Mapping[str, str]) -> dict[str, object]:
        dict_str = json.dumps(d)
        for a, b in v.items():
            dict_str = dict_str.replace(a, b)
        result = json.loads(dict_str)
        if not isinstance(result, dict) or not all(isinstance(key, str) for key in result):
            return {}
        return cast("dict[str, object]", result)

    def __data_schema_test_data(
        self,
        plugin_id: str,
        plugin_runner: str,
        result_data: object,
        data_schema: Mapping[str, object],
        data_tree: str = "/",
    ) -> list[str]:
        """
        Ensure the test data returned is valid according to the schema

        :param plugin_id:
        :param plugin_runner:
        :param result_data:
        :param data_schema:
        :param data_tree:
        :return:
        """

        errors: list[str] = []
        if not isinstance(result_data, dict):
            # This runner function is not returning anything
            error = f"Plugin '{plugin_id} - {plugin_runner}()' has failed to return any output data."
            errors.append(error)
            return errors
        for key in data_schema:
            errors.extend(self._validate_schema_key(plugin_id, plugin_runner, result_data, data_schema, data_tree, key))

        return errors

    @staticmethod
    def _test_data_type(provided_data: object, expected_type: object) -> bool:
        if provided_data is None and expected_type is None:
            return True
        if expected_type == "callable":
            return callable(provided_data)
        return isinstance(expected_type, type) and isinstance(provided_data, expected_type)

    def _validate_schema_key(
        self,
        plugin_id: str,
        plugin_runner: str,
        result_data: dict[object, object],
        data_schema: Mapping[str, object],
        data_tree: str,
        key: str,
    ) -> list[str]:
        schema_meta = data_schema.get(key)
        if not isinstance(schema_meta, dict):
            return [f"Plugin schema for '{data_tree}{key}' must be an object."]
        errors: list[str] = []
        if schema_meta.get("required") and key not in result_data:
            errors.append(f"Plugin '{plugin_id} - {plugin_runner}()' is missing required key '{data_tree}{key}'.")
        if key not in result_data:
            return errors
        child_data = result_data.get(key)
        data_type = schema_meta.get("type")
        expected_types = data_type if isinstance(data_type, list) else [data_type]
        if not any(self._test_data_type(child_data, expected) for expected in expected_types):
            errors.append(
                f"Plugin '{plugin_id} - {plugin_runner}()' returned incorrect type for '{data_tree}{key}': "
                f"expected '{data_type}', received '{type(child_data)}'."
            )
        children = schema_meta.get("children")
        if isinstance(children, dict):
            errors.extend(self.__data_schema_test_data(plugin_id, plugin_runner, child_data, children, f"{data_tree}{key}>"))
        return errors

    def run_data_schema_tests(self, plugin_id: str, plugin_module: ModuleType, test_data: Mapping[str, object]) -> list[str]:
        """
        With a given set of test data, this method tests the provided
        plugin module's data output against the schema dictionary.

        :param plugin_id:
        :param plugin_module:
        :param test_data:
        :return:
        """
        plugin_runner = self.plugin_runner()
        plugin_runner_function = self.get_plugin_runner_function(plugin_module)
        if plugin_runner_function is None:
            return [f"Plugin '{plugin_id}' does not provide runner '{plugin_runner}'."]
        plugin_runner_sig = inspect.signature(plugin_runner_function)

        # Get test data
        if not test_data:
            test_data = self.get_test_data()
        test_data_copy: dict[str, object] = deepcopy(dict(test_data))

        # Get data schema
        data_schema = self.get_data_schema()

        params = plugin_runner_sig.parameters

        # Execute plugin function
        run_count = 0
        while run_count < 2:
            self._execute_test_runner(plugin_id, plugin_runner, plugin_runner_function, params, test_data_copy)
            # break loop if the plugin did not request to be run again
            if not test_data_copy.get("repeat", False):
                break
            run_count += 1

        # Ensure the modified test data is valid according to the schema
        errors = self.__data_schema_test_data(plugin_id, plugin_runner, test_data_copy, data_schema)

        return errors

    @staticmethod
    def _supports_kwarg(params: Mapping[str, inspect.Parameter], name: str) -> bool:
        return name in params or any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values())

    @classmethod
    def _execute_test_runner(
        cls,
        plugin_id: str,
        plugin_runner: str,
        plugin_runner_function: Callable[..., object],
        params: Mapping[str, inspect.Parameter],
        test_data: dict[str, object],
    ) -> None:
        task_id = test_data.get("task_id")
        typed_task_id = task_id if isinstance(task_id, int) and not isinstance(task_id, bool) else None
        if typed_task_id is not None:
            TaskDataStore.bind_runner_context(task_id=typed_task_id, plugin_id=plugin_id, runner=plugin_runner)
        metadata_path = test_data.get("path") or test_data.get("file_path")
        CompressoFileMetadata.bind_runner_context(
            plugin_id=plugin_id,
            task_id=typed_task_id,
            path=metadata_path if isinstance(metadata_path, str) else None,
        )
        kwargs: dict[str, object] = {}
        if cls._supports_kwarg(params, "task_data_store"):
            kwargs["task_data_store"] = TaskDataStore
        if cls._supports_kwarg(params, "file_metadata"):
            kwargs["file_metadata"] = CompressoFileMetadata
        plugin_runner_function(test_data, **kwargs)
