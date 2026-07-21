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

        def test_data_type(provided_data: object, expected_data_type: object) -> bool:
            # Test for NoneType
            # Callable functions are best tested with the callable function
            # Everything else should be tested with the isinstance function
            if provided_data is None and expected_data_type is None:
                return True
            elif expected_data_type == "callable":
                if callable(provided_data):
                    return True
            elif isinstance(expected_data_type, type) and isinstance(provided_data, expected_data_type):
                return True
            return False

        errors: list[str] = []
        if not isinstance(result_data, dict):
            # This runner function is not returning anything
            error = f"Plugin '{plugin_id} - {plugin_runner}()' has failed to return any output data."
            errors.append(error)
            return errors
        for key in data_schema:
            schema_meta_value = data_schema.get(key)
            if not isinstance(schema_meta_value, dict):
                errors.append(f"Plugin schema for '{data_tree}{key}' must be an object.")
                continue
            schema_meta = cast("dict[str, object]", schema_meta_value)
            if schema_meta.get("required") and key not in result_data:
                error = (
                    f"Plugin '{plugin_id} - {plugin_runner}()' is missing required key '{data_tree}{key}' in the output data."
                )
                errors.append(error)

            # Ensure that data present is of the correct type
            # Recursively check for children elements
            data_type = schema_meta.get("type")
            if key in result_data:
                child_data = result_data.get(key)

                # Test that the data is of the correct type
                # Types can be multiple things for some plugin runners. If type is a list of types,
                #   iterate over that list and test all types.
                correct_type = False
                if isinstance(data_type, list):
                    for dt in cast("list[object]", data_type):
                        if test_data_type(child_data, dt):
                            correct_type = True
                            break
                else:
                    correct_type = test_data_type(child_data, data_type)

                # If data is not of the correct type, then append the error message
                if not correct_type:
                    error = (
                        f"Plugin '{plugin_id} - {plugin_runner}()' output data returned"
                        f" incorrect data type in key '{data_tree}{key}'."
                        f" Expected '{data_type}', but received"
                        f" '{type(result_data.get(key))}'."
                    )
                    errors.append(error)
                # Check if data_schema has children
                children_data_schema = schema_meta.get("children")
                if isinstance(children_data_schema, dict):
                    child_data_tree = f"{data_tree}{key}>"
                    errors += self.__data_schema_test_data(
                        plugin_id, plugin_runner, child_data, children_data_schema, data_tree=child_data_tree
                    )

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

        def supports_kwarg(name: str) -> bool:
            if name in params:
                return True
            return any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values())

        # Execute plugin function
        run_count = 0
        while run_count < 2:
            # if we have a task_id, bind context for store-based calls
            task_id = test_data_copy.get("task_id")
            typed_task_id = task_id if isinstance(task_id, int) and not isinstance(task_id, bool) else None
            if typed_task_id is not None:
                TaskDataStore.bind_runner_context(
                    task_id=typed_task_id,
                    plugin_id=plugin_id,
                    runner=plugin_runner,
                )

            metadata_path = test_data_copy.get("path") or test_data_copy.get("file_path")
            CompressoFileMetadata.bind_runner_context(
                plugin_id=plugin_id,
                task_id=typed_task_id,
                path=metadata_path if isinstance(metadata_path, str) else None,
            )

            # v2.0: kwargs-only plugin runner contract (matches executor.py).
            # Legacy positional fallback removed; non-conforming plugins
            # will raise TypeError, surfaced as a clean test-data error.
            kwargs: dict[str, object] = {}
            if supports_kwarg("task_data_store"):
                kwargs["task_data_store"] = TaskDataStore
            if supports_kwarg("file_metadata"):
                kwargs["file_metadata"] = CompressoFileMetadata
            plugin_runner_function(test_data_copy, **kwargs)
            # break loop if the plugin did not request to be run again
            if not test_data_copy.get("repeat", False):
                break
            run_count += 1

        # Ensure the modified test data is valid according to the schema
        errors = self.__data_schema_test_data(plugin_id, plugin_runner, test_data_copy, data_schema)

        return errors
