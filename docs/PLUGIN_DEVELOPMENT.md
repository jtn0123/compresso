# Plugin Development Guide

## Overview

Compresso uses a plugin system that allows developers to extend every stage of the media processing pipeline. Plugins are Python packages that implement one or more **runner functions**, each corresponding to a specific hook point in the task lifecycle. The plugin system supports:

- **Library Management** -- Deciding whether a file should be queued for processing.
- **Worker Processing** -- Executing commands (typically FFmpeg) to transcode or manipulate files.
- **Postprocessing** -- Controlling where output files are moved and reacting to task results.
- **Frontend** -- Rendering custom UI panels and exposing custom API endpoints.
- **Events** -- Reacting to lifecycle events such as scans completing, tasks being queued, and workers starting or finishing.

Plugins are installed into the Compresso plugins directory (typically `~/.compresso/plugins/<plugin_id>/`) and are managed through the Compresso Web UI or API. Each plugin can provide configurable settings that users adjust per-library through the UI.

---

## Plugin Structure

### Directory Layout

A plugin lives in its own directory named after its `plugin_id`:

```
my_awesome_plugin/
    __init__.py          # Required (can be empty)
    info.json            # Required -- plugin metadata
    plugin.py            # Required -- contains runner functions and Settings class
    requirements.txt     # Optional -- pip dependencies (installed to site-packages/)
    changelog.md         # Optional -- shown in the UI
    description.md       # Optional -- extended description shown in the UI
    site-packages/       # Auto-created -- pip install target for requirements.txt
```

### info.json Schema

Every plugin must include an `info.json` file at its root. Here is the full schema with an example:

```json
{
    "id": "my_awesome_plugin",
    "name": "My Awesome Plugin",
    "author": "Your Name",
    "version": "1.0.0",
    "description": "A short description of what this plugin does.",
    "icon": "https://example.com/icon.png",
    "compatibility": [2],
    "tags": "video,ffmpeg,encoding",
    "bundled": false
}
```

| Field           | Type       | Required | Description |
|-----------------|------------|----------|-------------|
| `id`            | `string`   | Yes      | Unique identifier. Must match the plugin directory name. Use snake_case. |
| `name`          | `string`   | Yes      | Human-readable display name. |
| `author`        | `string`   | Yes      | Author name or organization. |
| `version`       | `string`   | Yes      | Semantic version string (e.g., `"1.0.0"`). |
| `description`   | `string`   | Yes      | Short description shown in the plugin list. |
| `icon`          | `string`   | No       | URL to an icon image for the UI. |
| `compatibility` | `int[]`    | Yes      | List of plugin handler versions this plugin supports. Current version is `2`. |
| `tags`          | `string`   | No       | Comma-separated tags for search/filtering. |
| `bundled`       | `boolean`  | No       | Set to `true` only for plugins shipped with Compresso itself. |

### plugin.py Structure

The `plugin.py` file is the entry point for your plugin. It contains:

1. An optional `Settings` class (subclassing `PluginSettings`) for user-configurable options.
2. One or more **runner functions** that correspond to the hook points you want to use.

Minimal example:

```python
#!/usr/bin/env python3

from compresso.libs.unplugins.settings import PluginSettings


class Settings(PluginSettings):
    settings = {
        "my_option": "default_value",
    }
    form_settings = {
        "my_option": {
            "label":       "My Option",
            "description": "Description shown in the UI.",
            "input_type":  "text",
        },
    }


def on_worker_process(data, **kwargs):
    """Worker runner -- builds an FFmpeg command."""
    settings = Settings(library_id=data.get('library_id'))
    my_option = settings.get_setting("my_option")

    # ... build your command ...
    data["exec_command"] = ["ffmpeg", "-i", data["file_in"], data["file_out"]]
```

---

## Plugin Types and Hook Points

Plugins are executed in a defined order during the task lifecycle. Each hook point has a specific runner function name, receives a mutable `data` dictionary, and optionally accepts keyword arguments for helper objects.

**Runner function signature (recommended):**

```python
def runner_function_name(data, **kwargs):
    # kwargs may contain:
    #   task_data_store  -> TaskDataStore class
    #   file_metadata    -> CompressoFileMetadata class
    pass
```

The `**kwargs` pattern is recommended because Compresso injects `task_data_store` and `file_metadata` as keyword arguments when available. Legacy positional signatures are still supported but deprecated.

### Execution Order

The plugin types are executed in this order for each task:

1. `library_management.file_test` -- Should this file be processed?
2. `events.file_queued` -- File was marked for processing.
3. `events.task_queued` -- Task was created in the queue.
4. `events.scan_complete` -- Library scan finished.
5. `events.task_scheduled` -- Task was scheduled on a worker.
6. `events.worker_process_started` -- Worker picked up the task.
7. `worker.process` -- Execute processing commands (run for each plugin in the flow).
8. `events.worker_process_complete` -- All worker plugins finished.
9. `events.postprocessor_started` -- Postprocessor picked up the task.
10. `postprocessor.file_move` -- Control file copy/move operations.
11. `postprocessor.task_result` -- React to final task success/failure.
12. `events.postprocessor_complete` -- Task fully complete and recorded.

Plugin types with `has_flow: True` (file_test, worker.process, file_move, task_result) can have multiple plugins ordered in a user-defined flow per library. Event types run for all enabled plugins without a specific order.

---

### Library Management: File Test

**Runner function:** `on_library_management_file_test`

**When it runs:** During library scans, for every file found. Determines whether a file should be added to the pending task queue.

**Data dictionary:**

| Key                          | Type   | Required | Description |
|------------------------------|--------|----------|-------------|
| `library_id`                 | `int`  | Yes      | The library being scanned. |
| `path`                       | `str`  | Yes      | Full path to the file being tested. |
| `issues`                     | `list` | Yes      | List of issue dicts (each with `id` and `message`). |
| `add_file_to_pending_tasks`  | `bool` | Yes      | Set to `True` to queue the file, `False` to skip it. |
| `priority_score`             | `int`  | Yes      | Additional priority offset for queue ordering. |
| `shared_info`                | `dict` | No       | Shared data between file test plugins in the same flow. |

**Example:**

```python
def on_library_management_file_test(data, **kwargs):
    """Only process .mkv files larger than 1 GB."""
    import os

    path = data.get("path", "")

    if not path.lower().endswith(".mkv"):
        data["add_file_to_pending_tasks"] = False
        data["issues"].append({
            "id":      "not_mkv",
            "message": "File is not an MKV -- skipping."
        })
        return

    file_size = os.path.getsize(path)
    if file_size < 1_073_741_824:  # 1 GB
        data["add_file_to_pending_tasks"] = False
        data["issues"].append({
            "id":      "too_small",
            "message": "File is smaller than 1 GB -- skipping."
        })
```

---

### Worker: Process

**Runner function:** `on_worker_process`

**When it runs:** When a worker picks up a task and processes it through the plugin flow. Each worker plugin in the flow runs in sequence.

**Data dictionary:**

| Key                        | Type                   | Required | Description |
|----------------------------|------------------------|----------|-------------|
| `library_id`               | `int`                  | Yes      | The library for this task. |
| `task_id`                  | `int`                  | No       | Unique task identifier. |
| `worker_log`               | `list`                 | Yes      | Append log strings here for the UI tail display. |
| `exec_command`             | `list` or `str`        | Yes      | The subprocess command for Compresso to execute. Set to `[]` to skip. |
| `current_command`          | `list`                 | Yes      | List whose last entry is shown as "current command" in the UI. |
| `command_progress_parser`  | `callable` or `None`   | Yes      | Function to parse STDOUT for progress reporting. `None` to skip. |
| `file_in`                  | `str`                  | Yes      | Source file path. |
| `file_out`                 | `str`                  | Yes      | Destination file path (in the cache directory). |
| `original_file_path`       | `str`                  | No       | Absolute path to the original source file. |
| `repeat`                   | `bool`                 | No       | Set to `True` to re-run this same plugin after it completes. |

**Building FFmpeg commands:**

The most common pattern is to construct an FFmpeg command list and assign it to `data["exec_command"]`. Compresso will execute this command as a subprocess and capture output.

```python
def on_worker_process(data, **kwargs):
    file_in = data["file_in"]
    file_out = data["file_out"]

    cmd = [
        "ffmpeg", "-y",
        "-i", file_in,
        "-c:v", "libx265",
        "-crf", "23",
        "-preset", "medium",
        "-c:a", "copy",
        file_out
    ]

    data["exec_command"] = cmd
    data["worker_log"].append("Running: {}\n".format(" ".join(cmd)))

    # Update the UI's current command display
    if isinstance(data.get("current_command"), list):
        data["current_command"].clear()
        data["current_command"].append(" ".join(cmd))
```

**Progress parser:**

To report progress to the UI, provide a `command_progress_parser` function:

```python
def my_progress_parser(line_text, pid=None, proc_start_time=None, unset=False):
    """Parse FFmpeg output to extract progress percentage."""
    if unset:
        return {}
    import re
    match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', str(line_text))
    if match:
        h, m, s = float(match.group(1)), float(match.group(2)), float(match.group(3))
        current = h * 3600 + m * 60 + s
        percent = min(100, int(current / total_duration * 100))
        return {"percent": str(percent)}
    return {}

data["command_progress_parser"] = my_progress_parser
```

**Spawning a child process (advanced):**

For complex Python-only work (not a simple CLI command), use `PluginChildProcess`:

```python
from compresso.libs.unplugins.child_process import PluginChildProcess

def on_worker_process(data, **kwargs):
    proc = PluginChildProcess(plugin_id="my_plugin", data=data)

    def child_work(log_queue, prog_queue):
        import time
        for i in range(10):
            log_queue.put("Step {}/10 completed".format(i + 1))
            prog_queue.put((i + 1) * 10)  # percent 0-100
            time.sleep(1)

    success = proc.run(child_work)

    if not success:
        data["worker_log"].append("Child process failed!\n")

    # Set exec_command to empty so Compresso does not run another subprocess
    data["exec_command"] = []
```

The `PluginChildProcess` helper:
1. Spawns `target` in a `multiprocessing.Process`.
2. Registers the child PID for CPU/memory monitoring in the UI.
3. Drains `log_queue` into `data["worker_log"]`.
4. Drains `prog_queue` into the progress parser.
5. Cleans up the PID on exit.

---

### Postprocessor: File Move

**Runner function:** `on_postprocessor_file_movement`

**When it runs:** After all worker plugins complete, during the postprocessor stage. Controls how and where the output file is copied or moved.

**Data dictionary:**

| Key                      | Type   | Required | Description |
|--------------------------|--------|----------|-------------|
| `library_id`             | `int`  | Yes      | The library for this task. |
| `task_id`                | `int`  | No       | Unique task identifier. |
| `source_data`            | `dict` | Yes      | `{"abspath": "...", "basename": "..."}` for the original source. |
| `remove_source_file`     | `bool` | Yes      | Whether to delete the original after copy. Default: `True` if name changed. |
| `copy_file`              | `bool` | Yes      | Whether Compresso should perform a copy with the returned paths. Default: `False`. |
| `file_in`                | `str`  | Yes      | The converted cache file to copy from. |
| `file_out`               | `str`  | Yes      | The destination path to copy to. |
| `run_default_file_copy`  | `bool` | Yes      | Whether Compresso should also run its default file movement. Default: `True`. |

**Example -- copy output to a secondary location:**

```python
import os
import shutil

def on_postprocessor_file_movement(data, **kwargs):
    """Copy finished file to a backup directory."""
    backup_dir = "/mnt/backup/transcoded"
    os.makedirs(backup_dir, exist_ok=True)

    source_basename = data["source_data"]["basename"]
    backup_path = os.path.join(backup_dir, source_basename)

    # Tell Compresso to do an additional copy
    data["copy_file"] = True
    data["file_in"] = data["file_in"]  # the cache file
    data["file_out"] = backup_path

    # Still run the default file movement too
    data["run_default_file_copy"] = True
```

---

### Postprocessor: Task Result

**Runner function:** `on_postprocessor_task_results`

**When it runs:** After all file movements are complete. Provides final task outcome data for logging, notifications, or cleanup.

**Data dictionary:**

| Key                            | Type    | Required | Description |
|--------------------------------|---------|----------|-------------|
| `library_id`                   | `int`   | No       | The library for this task. |
| `task_id`                      | `int`   | No       | Unique task identifier. |
| `task_type`                    | `str`   | No       | `"local"` or `"remote"`. |
| `final_cache_path`             | `str`   | No       | Path to the final cache file used for destination copies. |
| `task_processing_success`      | `bool`  | No       | Did all worker processes succeed? |
| `file_move_processes_success`  | `bool`  | No       | Did all file movements succeed? |
| `destination_files`            | `list`  | No       | List of all file paths created by postprocessor movements. |
| `source_data`                  | `dict`  | No       | `{"abspath": "...", "basename": "..."}` for the original source. |
| `start_time`                   | `float` | No       | UNIX timestamp when the task began. |
| `finish_time`                  | `float` | No       | UNIX timestamp when the task completed. |

**Example -- send a notification on failure:**

```python
def on_postprocessor_task_results(data, **kwargs):
    if not data.get("task_processing_success"):
        source = data.get("source_data", {}).get("basename", "unknown")
        send_notification("Task failed for: {}".format(source))
```

---

### Frontend: Panel

**Runner function:** `render_frontend_panel`

**When it runs:** When the Compresso frontend requests a panel page from this plugin (via `/compresso/panel/<plugin_id>/...`).

**Data dictionary:**

| Key            | Type   | Required | Description |
|----------------|--------|----------|-------------|
| `content_type` | `str`  | Yes      | Response content type (e.g., `"text/html"`). |
| `content`      | `str`  | Yes      | The HTML or text content to return. |
| `path`         | `str`  | No       | The sub-path after `/compresso/panel`. |
| `arguments`    | `dict` | No       | Dictionary of GET query parameters. |

**Example:**

```python
def render_frontend_panel(data, **kwargs):
    data["content_type"] = "text/html"
    data["content"] = """
    <!doctype html>
    <html>
    <head><title>My Plugin Panel</title></head>
    <body>
        <h1>Hello from My Plugin</h1>
        <p>Path: {}</p>
    </body>
    </html>
    """.format(data.get("path", "/"))
```

---

### Frontend: Plugin API

**Runner function:** `render_plugin_api`

**When it runs:** When the Compresso frontend receives a request to `/compresso/plugin_api/<plugin_id>/...`. Allows plugins to expose custom REST-like endpoints.

**Data dictionary:**

| Key            | Type    | Required | Description |
|----------------|---------|----------|-------------|
| `content_type` | `str`   | Yes      | Response content type (e.g., `"application/json"`). |
| `content`      | `dict`  | Yes      | The response body (will be JSON-serialized). |
| `status`       | `int`   | Yes      | HTTP status code. |
| `method`       | `str`   | No       | HTTP method (`"GET"`, `"POST"`, etc.). |
| `path`         | `str`   | No       | The sub-path after the plugin API prefix. |
| `uri`          | `str`   | No       | The full request URI. |
| `query`        | `str`   | No       | The raw query string. |
| `arguments`    | `dict`  | No       | Parsed GET query parameters. |
| `body`         | `bytes` | No       | Raw request body. |

**Example -- a webhook endpoint:**

```python
import json

def render_plugin_api(data, **kwargs):
    if data.get("path") == "/webhook" and data.get("method") == "POST":
        body = json.loads(data.get("body", b"{}"))
        # Process webhook payload...
        data["content"] = {"status": "received", "payload": body}
        data["status"] = 200
    else:
        data["content"] = {"error": "Not found"}
        data["status"] = 404
```

---

### Events

Event runners are fired at specific points in the task lifecycle. They do not participate in the plugin flow ordering -- all enabled event plugins run for every event. Event runners receive data but their modifications to that data are typically not used by subsequent processing stages.

#### `events.file_queued` -- `emit_file_queued`

Fires when a file has been tested and is about to be added to the pending queue.

| Key              | Type   | Description |
|------------------|--------|-------------|
| `library_id`     | `int`  | Library ID. |
| `file_path`      | `str`  | Full path to the file. |
| `priority_score` | `int`  | Assigned priority. |
| `issues`         | `list` | File issues raised during testing. |

#### `events.task_queued` -- `emit_task_queued`

Fires when a new task is created in the execution queue.

| Key           | Type   | Description |
|---------------|--------|-------------|
| `library_id`  | `int`  | Library ID. |
| `task_id`     | `int`  | Unique task identifier. |
| `task_type`   | `str`  | `"local"` or `"remote"`. |
| `source_data` | `dict` | `{"abspath": "...", "basename": "..."}`. |

#### `events.scan_complete` -- `emit_scan_complete`

Fires after a library scan completes.

| Key                   | Type    | Description |
|-----------------------|---------|-------------|
| `library_id`          | `int`   | Library ID. |
| `library_name`        | `str`   | Human-readable library name. |
| `library_path`        | `str`   | Filesystem path to the library. |
| `scan_start_time`     | `float` | UNIX timestamp when scan started. |
| `scan_end_time`       | `float` | UNIX timestamp when scan ended. |
| `scan_duration`       | `float` | Duration in seconds. |
| `files_scanned_count` | `int`   | Total files scanned. |

#### `events.task_scheduled` -- `emit_task_scheduled`

Fires when a task is scheduled for execution on a worker.

| Key                        | Type   | Description |
|----------------------------|--------|-------------|
| `library_id`               | `int`  | Library ID. |
| `task_id`                  | `int`  | Unique task identifier. |
| `task_type`                | `str`  | `"local"` or `"remote"`. |
| `task_schedule_type`       | `str`  | Where the task is being scheduled. |
| `remote_installation_info` | `dict` | For remote tasks: `{"uuid": "...", "address": "..."}`. Empty for local. |
| `source_data`              | `dict` | `{"abspath": "...", "basename": "..."}`. |

#### `events.worker_process_started` -- `emit_worker_process_started`

Fires at the very start of a worker processing a task.

| Key                    | Type   | Description |
|------------------------|--------|-------------|
| `library_id`           | `int`  | Library ID. |
| `task_id`              | `int`  | Unique task identifier. |
| `task_type`            | `str`  | `"local"` or `"remote"`. |
| `original_file_path`   | `str`  | Absolute path to the original source file. |
| `task_cache_path`      | `str`  | Target cache path for this task. |
| `worker_runners_info`  | `dict` | Per-runner metadata with initial status (`"pending"`) and success (`False`). |

#### `events.worker_process_complete` -- `emit_worker_process_complete`

Fires when a worker finishes processing all plugins for a task.

| Key                    | Type   | Description |
|------------------------|--------|-------------|
| `library_id`           | `int`  | Library ID. |
| `task_id`              | `int`  | Unique task identifier. |
| `task_type`            | `str`  | `"local"` or `"remote"`. |
| `original_file_path`   | `str`  | Absolute path to the original source file. |
| `final_cache_path`     | `str`  | Path to the final cache file. |
| `overall_success`      | `bool` | `True` if all processing completed successfully. |
| `worker_runners_info`  | `dict` | Per-runner metadata including status and success. |
| `worker_log`           | `list` | Accumulated log lines. |

#### `events.postprocessor_started` -- `emit_postprocessor_started`

Fires when the postprocessor picks up a task.

| Key           | Type   | Description |
|---------------|--------|-------------|
| `library_id`  | `int`  | Library ID. |
| `task_id`     | `int`  | Unique task identifier. |
| `task_type`   | `str`  | `"local"` or `"remote"`. |
| `cache_path`  | `str`  | Path to the task's cache file. |
| `source_data` | `dict` | `{"abspath": "...", "basename": "..."}`. |

#### `events.postprocessor_complete` -- `emit_postprocessor_complete`

Fires when a task has been fully post-processed and recorded in history.

| Key                    | Type    | Description |
|------------------------|---------|-------------|
| `library_id`           | `int`   | Library ID. |
| `task_id`              | `int`   | Unique task identifier. |
| `task_type`            | `str`   | `"local"` or `"remote"`. |
| `source_data`          | `dict`  | `{"abspath": "...", "basename": "..."}`. |
| `destination_data`     | `dict`  | `{"abspath": "...", "basename": "..."}`. |
| `task_success`         | `bool`  | Whether the task succeeded. |
| `start_time`           | `float` | UNIX timestamp when the task began. |
| `finish_time`          | `float` | UNIX timestamp when the task completed. |
| `processed_by_worker`  | `str`   | Identifier of the worker that processed it. |
| `log`                  | `str`   | Full text of the task log. |

**Example -- log all completed tasks:**

```python
def emit_postprocessor_complete(data, **kwargs):
    import logging
    logger = logging.getLogger("my_plugin")
    source = data.get("source_data", {}).get("basename", "?")
    success = data.get("task_success", False)
    duration = (data.get("finish_time", 0) - data.get("start_time", 0))
    logger.info("Task %s: %s (%.1fs) -- %s",
                data.get("task_id"), source, duration,
                "OK" if success else "FAILED")
```

---

## Plugin Settings

### Defining Settings

Settings are defined in a `Settings` class inside `plugin.py` that subclasses `PluginSettings`:

```python
from compresso.libs.unplugins.settings import PluginSettings

class Settings(PluginSettings):
    settings = {
        "quality":     23,
        "preset":      "medium",
        "output_dir":  "",
        "enabled":     True,
    }
```

The `settings` dict defines the default values for each setting key. These defaults are used until a user configures different values through the UI.

### Settings Schema (form_settings)

The `form_settings` dict controls how each setting is rendered in the Compresso Web UI:

```python
    form_settings = {
        "quality": {
            "label":       "Quality (CRF)",
            "description": "Lower values = better quality, larger files.",
            "input_type":  "slider",
            "slider_min":  0,
            "slider_max":  63,
            "slider_step": 1,
        },
        "preset": {
            "label":       "Encoder Preset",
            "description": "Speed/quality tradeoff.",
            "input_type":  "select",
            "select_options": [
                {"value": "fast",   "label": "Fast"},
                {"value": "medium", "label": "Medium"},
                {"value": "slow",   "label": "Slow"},
            ],
        },
        "output_dir": {
            "label":       "Output Directory",
            "description": "Custom output path. Leave empty for default.",
            "input_type":  "text",
            "placeholder": "/path/to/output",
        },
        "enabled": {
            "label":       "Enable Processing",
            "description": "Toggle this plugin on or off.",
            "input_type":  "boolean",
        },
    }
```

### Input Types

| Input Type | Properties | Description |
|------------|-----------|-------------|
| `text`     | `placeholder` (optional) | Free-form text input. |
| `select`   | `select_options` (required) | Dropdown. Each option is `{"value": "...", "label": "..."}`. |
| `slider`   | `slider_min`, `slider_max`, `slider_step` | Numeric slider. |
| `boolean`  | (none)    | Toggle switch (True/False). |

Each form setting entry supports these common fields:

| Field         | Type   | Description |
|---------------|--------|-------------|
| `label`       | `str`  | Display label in the UI. |
| `description` | `str`  | Help text shown below the input. |
| `input_type`  | `str`  | One of `text`, `select`, `slider`, `boolean`. |

### Accessing Settings at Runtime

Inside a runner function, instantiate the `Settings` class with the current `library_id` to load per-library configuration:

```python
def on_worker_process(data, **kwargs):
    settings = Settings(library_id=data.get("library_id"))

    # Get a single setting
    quality = settings.get_setting("quality")       # Returns 23 (or user-configured value)

    # Get all settings as a dict
    all_settings = settings.get_setting()            # Returns {"quality": 23, "preset": "medium", ...}

    # Get the default value (ignoring user config)
    default_quality = settings.get_default_setting("quality")  # Always returns 23
```

Settings are stored on disk as JSON files in the plugin's profile directory:
- `settings.json` -- global defaults
- `settings.<library_id>.json` -- per-library overrides

---

## Helper Objects

### TaskDataStore

`TaskDataStore` is a thread-safe, in-memory store for sharing data across plugins within a single task's lifecycle. It is available as a keyword argument (`task_data_store`) or can be imported directly.

```python
from compresso.libs.task import TaskDataStore
```

It provides two separate stores:

**1. Runner State (immutable)** -- Data scoped to a specific `(task_id, plugin_id, runner)`. Once a key is set, it cannot be overwritten.

```python
# Store data (returns True if stored, False if key already exists)
TaskDataStore.set_runner_value("ffprobe_info", {"streams": [...], "format": {...}})

# Retrieve data
info = TaskDataStore.get_runner_value("ffprobe_info")

# Read data from a different plugin's runner
info = TaskDataStore.get_runner_value(
    "ffprobe_info",
    plugin_id="other_plugin",
    runner="on_worker_process"
)
```

**2. Task State (mutable)** -- Arbitrary key-value pairs for a task, freely updated by any plugin.

```python
# Store or overwrite a value
TaskDataStore.set_task_state("source_file_size", 1_500_000_000)

# Read it back (same or different plugin)
size = TaskDataStore.get_task_state("source_file_size")

# Delete a key
TaskDataStore.delete_task_state("source_file_size")

# Export entire task state as a dict or JSON
state_dict = TaskDataStore.export_task_state(task_id)
state_json = TaskDataStore.export_task_state_json(task_id, indent=2)

# Import/merge state from a dict or JSON string
TaskDataStore.import_task_state(task_id, {"key": "value"})
TaskDataStore.import_task_state_json(task_id, '{"key": "value"}')
```

Task state is automatically cleared when a task reaches `"complete"` status.

### CompressoFileMetadata

`CompressoFileMetadata` provides persistent, fingerprint-based metadata storage tied to files. It survives across tasks -- if a file is re-processed, plugins can read metadata set by previous runs. Available as a keyword argument (`file_metadata`) or imported directly.

```python
from compresso.libs.metadata import CompressoFileMetadata
```

**Reading metadata:**

```python
def on_library_management_file_test(data, **kwargs):
    file_metadata = kwargs.get("file_metadata")
    # Get metadata stored by this plugin for the current file
    my_data = file_metadata.get()

    # Get metadata stored by a different plugin
    other_data = file_metadata.get(plugin_id_override="other_plugin")
```

**Writing metadata (requires task context):**

```python
def on_worker_process(data, **kwargs):
    file_metadata = kwargs.get("file_metadata")
    # Store metadata for the current file under this plugin's namespace
    file_metadata.set({
        "video_codec": "hevc",
        "original_bitrate": 15000000,
    })

    # Store in the source scope (persists with the source file's fingerprint)
    file_metadata.set({"analysis_done": True}, use_source_scope=True)
```

Metadata is committed to the persistent database when `CompressoFileMetadata.commit_task()` is called at the end of the task lifecycle. Per-plugin metadata is limited to 32 KB of JSON.

### FFmpeg Utilities

While Compresso does not provide a dedicated FFmpeg wrapper library, the standard pattern for worker plugins is:

1. Build a command list: `["ffmpeg", "-y", "-i", file_in, ..., file_out]`
2. Assign it to `data["exec_command"]`
3. Optionally probe the file with `ffprobe` for duration/stream info
4. Provide a `command_progress_parser` to parse FFmpeg's stderr for `time=HH:MM:SS.ss`

See the [Complete Example](#complete-example) below for a full implementation.

---

## Complete Example

This section walks through the bundled **Encoding Presets** plugin (`encoding_presets`) step by step.

### info.json

```json
{
    "id": "encoding_presets",
    "name": "Encoding Presets",
    "author": "Compresso",
    "version": "1.0.0",
    "description": "Configure encoding quality settings: CRF/quality level, encoder preset speed, maximum bitrate cap, resolution scaling, and audio bitrate. Builds FFmpeg commands with your chosen parameters.",
    "icon": "",
    "compatibility": [2],
    "tags": "encoding,ffmpeg,quality,presets,video,audio",
    "bundled": true
}
```

Key points:
- `"compatibility": [2]` declares compatibility with plugin handler version 2 (current).
- `"bundled": true` marks it as a built-in plugin.

### Settings Class

```python
from compresso.libs.unplugins.settings import PluginSettings

class Settings(PluginSettings):
    settings = {
        "video_codec":       "",
        "video_encoder":     "",
        "crf":               23,
        "encoder_preset":    "medium",
        "max_bitrate":       "",
        "scale_height":      0,
        "audio_codec":       "",
        "audio_bitrate":     "",
        "output_format":     "",
        "extra_flags":       "",
    }

    form_settings = {
        "video_codec": {
            "label":       "Video Codec",
            "description": "Target video codec. Leave empty to keep source codec.",
            "input_type":  "select",
            "select_options": [
                {"value": "",     "label": "Same as source"},
                {"value": "h264", "label": "H.264 (AVC)"},
                {"value": "hevc", "label": "H.265 (HEVC)"},
                {"value": "av1",  "label": "AV1"},
                {"value": "vp9",  "label": "VP9"},
            ],
        },
        "crf": {
            "label":       "Quality (CRF)",
            "description": "Constant Rate Factor. Lower = better quality, larger files. Typical: 18-28.",
            "input_type":  "slider",
            "slider_min":  0,
            "slider_max":  63,
            "slider_step": 1,
        },
        "encoder_preset": {
            "label":       "Encoder Preset",
            "description": "Speed/quality tradeoff. Slower = better compression at same quality.",
            "input_type":  "select",
            "select_options": [
                {"value": "ultrafast", "label": "Ultrafast"},
                {"value": "fast",      "label": "Fast"},
                {"value": "medium",    "label": "Medium (default)"},
                {"value": "slow",      "label": "Slow"},
                {"value": "veryslow",  "label": "Very Slow"},
            ],
        },
        # ... additional form_settings for max_bitrate, scale_height, audio_codec, etc.
    }
```

Each key in `settings` must have a matching entry in `form_settings` if you want it configurable from the UI.

### Runner Function

The plugin implements `on_worker_process` to build an FFmpeg command:

```python
def on_worker_process(data, **kwargs):
    # 1. Load settings for the current library
    settings = Settings(library_id=data.get('library_id'))
    settings.get_setting()
    s = settings.settings_configured

    file_in = data.get("file_in")
    if not file_in:
        data["worker_log"].append("[Encoding Presets] No input file -- skipping.\n")
        return

    # 2. Determine output format and path
    source_ext = os.path.splitext(file_in)[1].lstrip('.').lower()
    output_format = s.get("output_format", "").strip() or source_ext or "mkv"
    file_in_basename = os.path.splitext(os.path.basename(file_in))[0]
    cache_dir = os.path.dirname(data.get("file_out") or file_in)
    file_out = os.path.join(cache_dir, "{}.{}".format(file_in_basename, output_format))
    data["file_out"] = file_out

    # 3. Build the FFmpeg command
    cmd = ["ffmpeg", "-y", "-i", file_in]

    video_codec = s.get("video_codec", "").strip()
    video_encoder = s.get("video_encoder", "").strip()
    if video_codec and not video_encoder:
        video_encoder = CODEC_ENCODER_MAP.get(video_codec, video_codec)

    if video_encoder:
        cmd.extend(["-c:v", video_encoder])
        cmd.extend(["-crf", str(int(s.get("crf", 23)))])
        preset = s.get("encoder_preset", "medium").strip()
        if preset:
            cmd.extend(["-preset", preset])
        max_bitrate = s.get("max_bitrate", "").strip()
        if max_bitrate:
            cmd.extend(["-maxrate", max_bitrate, "-bufsize", max_bitrate])
    else:
        cmd.extend(["-c:v", "copy"])

    # Scale if requested
    scale_height = int(s.get("scale_height", 0) or 0)
    if scale_height > 0 and video_encoder:
        cmd.extend(["-vf", "scale=-2:{}".format(scale_height)])

    # Audio
    audio_codec = s.get("audio_codec", "").strip()
    if audio_codec:
        cmd.extend(["-c:a", audio_codec])
        audio_bitrate = s.get("audio_bitrate", "").strip()
        if audio_bitrate:
            cmd.extend(["-b:a", audio_bitrate])
    else:
        cmd.extend(["-c:a", "copy"])

    cmd.append(file_out)

    # 4. Assign to data
    data["exec_command"] = cmd
    data["command_progress_parser"] = _build_ffmpeg_progress_parser(data)
    data["worker_log"].append("[Encoding Presets] Command: {}\n".format(" ".join(cmd)))
```

Key patterns demonstrated:
- Load library-specific settings via `Settings(library_id=...)`.
- Modify `data["file_out"]` to change the output file extension.
- Build a command list and assign to `data["exec_command"]`.
- Provide a progress parser for the UI.
- Append informational messages to `data["worker_log"]`.

---

## Testing Your Plugin

### Local Development Setup

1. **Create your plugin directory** inside the Compresso plugins path:
   ```bash
   mkdir -p ~/.compresso/plugins/my_plugin
   ```

2. **Create the required files**: `__init__.py`, `info.json`, `plugin.py`.

3. **Install/reload**: Compresso detects plugins in the plugins directory. After creating or modifying files, restart the Compresso service or use the plugin management UI to reload.

### Schema Validation

Compresso includes built-in schema validation for plugin runners. When you install a plugin, the system can test its runner functions against the expected data schema. The `PluginExecutor.test_plugin_runner()` method:

1. Creates test data matching the runner's schema.
2. Calls your runner function with that test data.
3. Validates that the returned/modified data still conforms to the schema.

Ensure your runner functions:
- Do not remove required keys from the `data` dictionary.
- Return the correct data types for all required fields.
- Handle missing optional fields gracefully.

### Development Tips

- **Use a git repo**: Compresso will not overwrite a plugin directory that contains a `.git` directory when installing from a repo. This protects your development copy.
- **Check logs**: Compresso logs plugin errors to its standard logging output. Look for messages prefixed with the plugin executor class name.
- **Test settings**: Verify your `Settings` class loads correctly by calling `get_setting()` and checking that defaults are returned.
- **Dependencies**: If your plugin needs third-party Python packages, list them in `requirements.txt`. They will be installed to a `site-packages/` directory inside your plugin folder. You can also use `requirements.post-install.txt` for dependencies needed only after extraction.

---

## Publishing

### Community Plugin Repos

Compresso supports multiple plugin repositories. To share your plugin:

1. **Package your plugin** as a ZIP file named `<plugin_id>-<version>.zip` containing all plugin files at the root level (not nested in a subdirectory).

2. **Host the ZIP file** at a publicly accessible URL.

3. **Create a repo manifest** -- a JSON file listing available plugins with download URLs:
   ```json
   {
       "repo": {
           "name": "My Plugin Repo",
           "repo_data_directory": "https://example.com/plugins"
       },
       "plugins": [
           {
               "id": "my_plugin",
               "name": "My Plugin",
               "author": "Your Name",
               "version": "1.0.0",
               "description": "Does awesome things.",
               "compatibility": [2],
               "tags": "video,awesome"
           }
       ]
   }
   ```
   When `repo_data_directory` is set, Compresso constructs the download URL as: `<repo_data_directory>/<plugin_id>/<plugin_id>-<version>.zip`.

4. **Add your repo** in the Compresso settings UI under Plugin Repos, or users can add it manually.

### Direct Installation

Users can also install plugins directly from a ZIP file on disk through the Compresso UI or API, without needing a repository.
