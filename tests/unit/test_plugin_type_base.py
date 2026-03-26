#!/usr/bin/env python3

"""
    tests.unit.test_plugin_type_base.py

    Tests for the PluginType base class.
    Covers: accessors, get_plugin_runner_function, modify_test_data,
    __data_schema_test_data, run_data_schema_tests.
"""


from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType
from compresso.libs.unplugins.plugin_types.plugin_type_base import PluginType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


@pytest.mark.unittest
class TestPluginTypeAccessors:

    def test_plugin_type_name(self):
        pt = PluginType()
        pt.name = 'test_type'
        assert pt.plugin_type_name() == 'test_type'

    def test_plugin_runner(self):
        pt = PluginType()
        pt.runner = 'on_library_management_file_test'
        assert pt.plugin_runner() == 'on_library_management_file_test'

    def test_plugin_runner_docstring(self):
        pt = PluginType()
        pt.runner_docstring = 'Runs file tests'
        assert pt.plugin_runner_docstring() == 'Runs file tests'

    def test_get_data_schema(self):
        pt = PluginType()
        pt.data_schema = {'key': {'type': str, 'required': True}}
        assert pt.get_data_schema() == {'key': {'type': str, 'required': True}}

    def test_get_test_data(self):
        pt = PluginType()
        pt.test_data = {'path': '/test.mp4'}
        assert pt.get_test_data() == {'path': '/test.mp4'}


@pytest.mark.unittest
class TestPluginTypeGetRunnerFunction:

    def test_returns_function_when_exists(self):
        pt = PluginType()
        pt.runner = 'on_test'
        module = MagicMock()
        module.on_test = lambda data: data
        result = pt.get_plugin_runner_function(module)
        assert result is not None

    def test_returns_none_when_missing(self):
        pt = PluginType()
        pt.runner = 'on_test'
        module = MagicMock(spec=[])
        result = pt.get_plugin_runner_function(module)
        assert result is None


@pytest.mark.unittest
class TestPluginTypeModifyTestData:

    def test_basic_replacement(self):
        d = {'name': 'PLACEHOLDER', 'value': 'keep'}
        v = {'PLACEHOLDER': 'replaced'}
        result = PluginType.modify_test_data(d, v)
        assert result['name'] == 'replaced'
        assert result['value'] == 'keep'

    def test_no_replacement(self):
        d = {'name': 'test'}
        v = {'OTHER': 'replaced'}
        result = PluginType.modify_test_data(d, v)
        assert result == d

    def test_multiple_replacements(self):
        d = {'a': 'X', 'b': 'Y'}
        v = {'X': 'one', 'Y': 'two'}
        result = PluginType.modify_test_data(d, v)
        assert result['a'] == 'one'
        assert result['b'] == 'two'


@pytest.mark.unittest
class TestPluginTypeDataSchemaValidation:

    def _make_plugin_type(self):
        pt = PluginType()
        pt.name = 'test'
        pt.runner = 'on_test'
        pt.data_schema = {
            'output': {
                'type': str,
                'required': True,
            },
            'count': {
                'type': int,
                'required': False,
            },
        }
        pt.test_data = {'path': '/test.mp4'}
        return pt

    def test_data_schema_test_valid_data(self):
        pt = self._make_plugin_type()
        result_data = {'output': 'success', 'count': 1}
        errors = pt._PluginType__data_schema_test_data(
            'test.plugin', 'on_test', result_data, pt.data_schema
        )
        assert errors == []

    def test_data_schema_test_missing_required(self):
        pt = self._make_plugin_type()
        result_data = {'count': 1}
        errors = pt._PluginType__data_schema_test_data(
            'test.plugin', 'on_test', result_data, pt.data_schema
        )
        assert any('missing required' in e.lower() for e in errors)

    def test_data_schema_test_wrong_type(self):
        pt = self._make_plugin_type()
        result_data = {'output': 123, 'count': 'not_int'}
        errors = pt._PluginType__data_schema_test_data(
            'test.plugin', 'on_test', result_data, pt.data_schema
        )
        assert len(errors) == 2

    def test_data_schema_test_none_return(self):
        pt = self._make_plugin_type()
        errors = pt._PluginType__data_schema_test_data(
            'test.plugin', 'on_test', None, pt.data_schema
        )
        assert any('failed to return' in e.lower() for e in errors)

    def test_data_schema_test_callable_type(self):
        pt = PluginType()
        pt.data_schema = {
            'func': {
                'type': 'callable',
                'required': True,
            },
        }
        result_data = {'func': lambda: None}
        errors = pt._PluginType__data_schema_test_data(
            'test.plugin', 'on_test', result_data, pt.data_schema
        )
        assert errors == []

    def test_data_schema_test_multiple_types(self):
        pt = PluginType()
        pt.data_schema = {
            'value': {
                'type': [str, int],
                'required': True,
            },
        }
        # str should pass
        errors1 = pt._PluginType__data_schema_test_data(
            'test.plugin', 'on_test', {'value': 'hello'}, pt.data_schema
        )
        assert errors1 == []

        # int should also pass
        errors2 = pt._PluginType__data_schema_test_data(
            'test.plugin', 'on_test', {'value': 42}, pt.data_schema
        )
        assert errors2 == []

        # float should fail
        errors3 = pt._PluginType__data_schema_test_data(
            'test.plugin', 'on_test', {'value': 3.14}, pt.data_schema
        )
        assert len(errors3) == 1

    def test_data_schema_test_children(self):
        pt = PluginType()
        pt.data_schema = {
            'nested': {
                'type': dict,
                'required': True,
                'children': {
                    'child_key': {
                        'type': str,
                        'required': True,
                    },
                },
            },
        }
        result_data = {'nested': {'child_key': 'val'}}
        errors = pt._PluginType__data_schema_test_data(
            'test.plugin', 'on_test', result_data, pt.data_schema
        )
        assert errors == []

        # Missing child key
        result_data_bad = {'nested': {}}
        errors_bad = pt._PluginType__data_schema_test_data(
            'test.plugin', 'on_test', result_data_bad, pt.data_schema
        )
        assert any('missing required' in e.lower() for e in errors_bad)

    def test_data_schema_none_type(self):
        pt = PluginType()
        pt.data_schema = {
            'value': {
                'type': None,
                'required': False,
            },
        }
        result_data = {'value': None}
        errors = pt._PluginType__data_schema_test_data(
            'test.plugin', 'on_test', result_data, pt.data_schema
        )
        assert errors == []


@pytest.mark.unittest
class TestPluginTypeRunDataSchemaTests:

    @patch('compresso.libs.unplugins.plugin_types.plugin_type_base.CompressoFileMetadata')
    @patch('compresso.libs.unplugins.plugin_types.plugin_type_base.TaskDataStore')
    def test_run_data_schema_tests_success(self, mock_tds, mock_meta):
        pt = PluginType()
        pt.name = 'test'
        pt.runner = 'on_test'
        pt.logger = MagicMock()
        pt.data_schema = {
            'output': {'type': str, 'required': True},
        }
        pt.test_data = {'path': '/test.mp4'}

        def on_test(data, **kwargs):
            data['output'] = 'done'

        module = MagicMock()
        module.on_test = on_test

        errors = pt.run_data_schema_tests('test.plugin', module, None)
        assert errors == []

    @patch('compresso.libs.unplugins.plugin_types.plugin_type_base.CompressoFileMetadata')
    @patch('compresso.libs.unplugins.plugin_types.plugin_type_base.TaskDataStore')
    def test_run_data_schema_tests_with_repeat(self, mock_tds, mock_meta):
        pt = PluginType()
        pt.name = 'test'
        pt.runner = 'on_test'
        pt.logger = MagicMock()
        pt.data_schema = {
            'output': {'type': str, 'required': True},
        }
        pt.test_data = {'path': '/test.mp4'}

        call_count = [0]

        def on_test(data, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                data['repeat'] = True
            else:
                data['repeat'] = False
            data['output'] = 'done'

        module = MagicMock()
        module.on_test = on_test

        errors = pt.run_data_schema_tests('test.plugin', module, None)
        assert errors == []
        assert call_count[0] == 2

    @patch('compresso.libs.unplugins.plugin_types.plugin_type_base.CompressoFileMetadata')
    @patch('compresso.libs.unplugins.plugin_types.plugin_type_base.TaskDataStore')
    def test_run_data_schema_tests_with_custom_test_data(self, mock_tds, mock_meta):
        pt = PluginType()
        pt.name = 'test'
        pt.runner = 'on_test'
        pt.logger = MagicMock()
        pt.data_schema = {
            'output': {'type': str, 'required': True},
        }
        pt.test_data = {'path': '/default.mp4'}

        def on_test(data, **kwargs):
            data['output'] = data.get('path', '')

        module = MagicMock()
        module.on_test = on_test

        custom_data = {'path': '/custom.mp4'}
        errors = pt.run_data_schema_tests('test.plugin', module, custom_data)
        assert errors == []

    @patch('compresso.libs.unplugins.plugin_types.plugin_type_base.CompressoFileMetadata')
    @patch('compresso.libs.unplugins.plugin_types.plugin_type_base.TaskDataStore')
    def test_run_data_schema_tests_legacy_positional(self, mock_tds, mock_meta):
        """Test legacy plugin that accepts positional args."""
        pt = PluginType()
        pt.name = 'test'
        pt.runner = 'on_test'
        pt.logger = MagicMock()
        pt.data_schema = {
            'output': {'type': str, 'required': True},
        }
        pt.test_data = {'path': '/test.mp4'}

        # Legacy plugin function with only positional params (no **kwargs)
        def on_test(data):
            data['output'] = 'legacy'

        module = MagicMock()
        module.on_test = on_test

        errors = pt.run_data_schema_tests('test.plugin', module, None)
        assert errors == []
