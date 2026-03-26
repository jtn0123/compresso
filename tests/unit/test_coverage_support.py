#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import importlib
import runpy
import sys
import types
import zipfile

import pytest
from tornado.web import URLSpec
from unittest.mock import MagicMock, patch


def _fresh_import(module_name):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


@pytest.fixture
def fake_apispec(monkeypatch):
    yaml_utils = types.ModuleType('apispec.yaml_utils')

    def load_yaml_from_docstring(docstring):
        if not docstring or 'description:' not in docstring:
            return None
        description = docstring.split('description:', 1)[1].splitlines()[0].strip()
        return {'description': description}

    yaml_utils.load_yaml_from_docstring = load_yaml_from_docstring

    exceptions = types.ModuleType('apispec.exceptions')

    class FakeAPISpecError(Exception):
        pass

    exceptions.APISpecError = FakeAPISpecError

    apispec = types.ModuleType('apispec')

    class FakeAPISpec:
        def __init__(self, *args, **kwargs):
            self.paths = []

        def path(self, urlspec):
            handler = urlspec[1] if isinstance(urlspec, tuple) else urlspec.handler_class
            if getattr(handler, 'raise_spec_error', False):
                raise FakeAPISpecError('bad handler')
            self.paths.append(urlspec)

        def to_dict(self):
            return {'paths': len(self.paths)}

        def to_yaml(self):
            return 'openapi: 3.0.0\n'

    apispec.APISpec = FakeAPISpec
    apispec.yaml_utils = yaml_utils

    marshmallow = types.ModuleType('apispec.ext.marshmallow')

    class MarshmallowPlugin:
        pass

    marshmallow.MarshmallowPlugin = MarshmallowPlugin

    tornado_plugin_module = types.ModuleType('apispec_webframeworks.tornado')

    class TornadoPlugin:
        def _extensions_from_handler(self, handler_class):
            return {'x-handler': handler_class.__name__}

        def tornadopath2openapi(self, urlspec, params_method):
            return urlspec.regex.pattern

    tornado_plugin_module.TornadoPlugin = TornadoPlugin

    monkeypatch.setitem(sys.modules, 'apispec', apispec)
    monkeypatch.setitem(sys.modules, 'apispec.yaml_utils', yaml_utils)
    monkeypatch.setitem(sys.modules, 'apispec.exceptions', exceptions)
    monkeypatch.setitem(sys.modules, 'apispec.ext.marshmallow', marshmallow)
    monkeypatch.setitem(sys.modules, 'apispec_webframeworks.tornado', tornado_plugin_module)

    yield FakeAPISpecError

    for module_name in (
        'compresso.webserver.api_v2.schema.compresso',
        'compresso.webserver.api_v2.schema.swagger',
    ):
        sys.modules.pop(module_name, None)


@pytest.mark.unittest
def test_main_module_invokes_service_main(monkeypatch):
    fake_service = types.ModuleType('compresso.service')
    fake_service.main = MagicMock()
    monkeypatch.setitem(sys.modules, 'compresso.service', fake_service)

    runpy.run_module('compresso.__main__', run_name='__main__')

    fake_service.main.assert_called_once_with()


@pytest.mark.unittest
def test_generate_log_files_zip_creates_archive(tmp_path):
    from compresso.webserver.helpers import documents

    cache_path = tmp_path / 'cache'
    logs_path = tmp_path / 'logs'
    nested_logs = logs_path / 'nested'
    nested_logs.mkdir(parents=True)
    (logs_path / 'compresso.log').write_text('main log', encoding='utf-8')
    (nested_logs / 'worker.log').write_text('worker log', encoding='utf-8')

    settings = MagicMock()
    settings.get_cache_path.return_value = str(cache_path)
    settings.get_log_path.return_value = str(logs_path)

    with patch.object(documents.config, 'Config', return_value=settings):
        output_path = documents.generate_log_files_zip()

    assert output_path.endswith('CompressoLogs.zip')
    with zipfile.ZipFile(output_path) as archive:
        assert sorted(archive.namelist()) == ['compresso.log', 'worker.log']


@pytest.mark.unittest
@pytest.mark.parametrize(
    ('function_name', 'method_name', 'args'),
    [
        ('pause_worker_by_id', 'pause_worker_thread', (4,)),
        ('pause_all_workers', 'pause_all_worker_threads', ()),
        ('resume_worker_by_id', 'resume_worker_thread', (5,)),
        ('resume_all_workers', 'resume_all_worker_threads', ()),
        ('terminate_worker_by_id', 'terminate_worker_thread', (6,)),
        ('terminate_all_workers', 'terminate_all_worker_threads', ()),
    ],
)
def test_worker_helper_delegates_to_foreman(function_name, method_name, args):
    from compresso.webserver.helpers import workers

    foreman = MagicMock()
    expected = {'method': method_name}
    getattr(foreman, method_name).return_value = expected
    running_threads = MagicMock()
    running_threads.get_compresso_running_thread.return_value = foreman

    with patch.object(workers, 'CompressoRunningThreads', return_value=running_threads):
        result = getattr(workers, function_name)(*args)

    running_threads.get_compresso_running_thread.assert_called_once_with('foreman')
    getattr(foreman, method_name).assert_called_once_with(*args)
    assert result == expected


@pytest.mark.unittest
def test_fetch_windows_drives_detects_existing_drive_letters(monkeypatch):
    from compresso.webserver.helpers import filebrowser

    monkeypatch.setattr(filebrowser.os.path, 'exists', lambda path: path in {'C:', 'Z:'})

    assert filebrowser.fetch_windows_drives() == ['C:', 'Z:']


@pytest.mark.unittest
def test_directory_listing_fetches_files_and_directories(tmp_path):
    from compresso.webserver.helpers.filebrowser import DirectoryListing

    (tmp_path / 'alpha').mkdir()
    (tmp_path / 'bravo.txt').write_text('data', encoding='utf-8')

    listing = DirectoryListing()
    data = listing.fetch_path_data(str(tmp_path))

    assert any(item['name'] == 'alpha' for item in data['directories'])
    assert any(item['name'] == 'bravo.txt' for item in data['files'])


@pytest.mark.unittest
def test_fetch_directories_ignores_permission_errors(tmp_path):
    from compresso.webserver.helpers import filebrowser

    with patch.object(filebrowser.os.path, 'exists', return_value=True), \
         patch.object(filebrowser.os.path, 'abspath', side_effect=lambda path: str(tmp_path)), \
         patch.object(filebrowser.os, 'listdir', side_effect=PermissionError):
        results = filebrowser.DirectoryListing.fetch_directories(str(tmp_path))

    # No directory entries from listdir — only possible ".." parent entry
    assert all(item['name'] == '..' for item in results)


@pytest.mark.unittest
def test_fetch_directories_returns_drives_for_missing_windows_path(monkeypatch):
    from compresso.webserver.helpers import filebrowser

    monkeypatch.setattr(filebrowser.os.path, 'exists', lambda _path: False)
    monkeypatch.setattr(filebrowser.os, 'name', 'nt')
    monkeypatch.setattr(filebrowser, 'fetch_windows_drives', lambda: ['C:'])

    results = filebrowser.DirectoryListing.fetch_directories('missing')

    assert results[0]['name'] == 'C:'


@pytest.mark.unittest
def test_fetch_directories_returns_default_root_for_missing_posix_path(monkeypatch):
    from compresso.webserver.helpers import filebrowser

    monkeypatch.setattr(filebrowser.os.path, 'exists', lambda _path: False)
    monkeypatch.setattr(filebrowser.os, 'name', 'posix')
    monkeypatch.setattr(filebrowser.common, 'get_default_root_path', lambda: '/')

    results = filebrowser.DirectoryListing.fetch_directories('missing')

    assert results == [{'name': '/', 'full_path': '/'}]


@pytest.mark.unittest
def test_compresso_spec_plugin_reads_operations(fake_apispec):
    compresso_schema = _fresh_import('compresso.webserver.api_v2.schema.compresso')

    def get_handler(self):
        """
        Example endpoint
        ---
        description: returns test data
        """

    handler_class = type(
        'SchemaHandler',
        (),
        {
            'routes': [{'path_pattern': r'/schema/test', 'supported_methods': ['GET'], 'call_method': 'get_handler'}],
            'get_handler': get_handler,
            'get': get_handler,
        },
    )
    plugin = compresso_schema.CompressoSpecPlugin()
    urlspec = URLSpec(r'/schema/test', handler_class)

    operations = list(plugin._operations_from_urlspec(urlspec))
    openapi_path = plugin.path_helper({}, urlspec=urlspec)

    assert operations == [{'get': {'description': 'returns test data'}}]
    assert '/schema/test' in openapi_path


@pytest.mark.unittest
def test_compresso_spec_plugin_raises_for_missing_operations(fake_apispec):
    FakeAPISpecError = fake_apispec
    compresso_schema = _fresh_import('compresso.webserver.api_v2.schema.compresso')

    handler_class = type('SchemaHandler', (), {'routes': [], 'get': lambda self: None})
    plugin = compresso_schema.CompressoSpecPlugin()
    urlspec = URLSpec(r'/schema/test', handler_class)

    with pytest.raises(FakeAPISpecError):
        plugin.path_helper({}, urlspec=urlspec)


@pytest.mark.unittest
def test_swagger_helpers_find_handlers_and_generate_files(fake_apispec, tmp_path):
    swagger = _fresh_import('compresso.webserver.api_v2.schema.swagger')

    handler_class = type(
        'SwaggerHandler',
        (),
        {
            'routes': [{'path_pattern': r'/swagger/test', 'supported_methods': ['GET'], 'call_method': 'get'}],
            'get': lambda self: None,
        },
    )
    bad_handler = type('BadSwaggerHandler', (), {'routes': [{'path_pattern': r'/bad', 'supported_methods': ['GET'], 'call_method': 'get'}]})
    bad_handler.raise_spec_error = True
    bad_handler.get = lambda self: None

    fake_module = types.SimpleNamespace(SwaggerHandler=handler_class, BadSwaggerHandler=bad_handler)

    with patch.object(swagger, 'list_all_handlers', return_value=['SwaggerHandler']), \
         patch.object(swagger.importlib, 'import_module', return_value=fake_module):
        assert swagger.find_all_handlers() == [(r'/swagger/test', handler_class)]

    fake_module_dir = tmp_path / 'api_v2' / 'schema'
    fake_module_dir.mkdir(parents=True)
    fake_module_path = fake_module_dir / 'swagger.py'
    fake_module_path.write_text('# fake', encoding='utf-8')
    swagger.__file__ = str(fake_module_path)
    (tmp_path / 'docs').mkdir()

    with patch.object(swagger, 'find_all_handlers', return_value=[(r'/swagger/test', handler_class), (r'/bad', bad_handler)]):
        errors = swagger.generate_swagger_file()

    assert len(errors) == 1
    assert 'Failed to append spec path' in errors[0]
    output_base = tmp_path / 'docs' / 'api_schema_v2'
    assert (output_base.with_suffix('.json')).exists()
    assert (output_base.with_suffix('.yaml')).exists()
