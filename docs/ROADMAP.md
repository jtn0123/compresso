# Compresso Roadmap

Last updated: 2026-03-25

This document tracks planned work for Compresso, organized by priority. Each item includes
what exists today, what's missing, and why it matters.

---

## P1 -- Multi-Platform Support

Compresso currently runs on Linux (native + Docker). The goal is full support for
**macOS** (primary encoding platform), **Windows** (secondary encoding platform),
and **Linux** (server/Docker), with CI coverage across all three.

### Current State

| Platform | Status |
|---|---|
| Linux (native) | Fully supported |
| Linux (Docker, amd64) | Fully supported |
| Linux (Docker, arm64) | Builds in CI, not smoke-tested |
| macOS | Partially works -- GPU monitoring and default paths are Linux-only |
| Windows | Partially works -- process priority and GPU monitoring are Linux-only |

CI today runs **Ubuntu-only** for all unit tests, integration tests, and linting.

### What Needs to Change

#### GPU Monitoring (`compresso/libs/gpu_monitor.py`)

The biggest blocker. Intel and AMD GPU detection are hardcoded to Linux sysfs paths.

| GPU Vendor | Linux (today) | macOS (needed) | Windows (needed) |
|---|---|---|---|
| NVIDIA | `nvidia-smi` (works everywhere) | `nvidia-smi` (works if installed) | `nvidia-smi` (works if installed) |
| Intel | `/sys/class/drm` sysfs | `system_profiler SPDisplaysDataType` or `ioreg` | WMI or DirectX query |
| AMD | `/sys/class/drm` sysfs | `system_profiler SPDisplaysDataType` | WMI or `rocm-smi` |

- NVIDIA path already works cross-platform (uses `nvidia-smi` CLI)
- Intel/AMD need platform-specific backends with a shared interface
- Graceful degradation already exists (if detection fails, GPU section just hides) -- this is fine for initial support

#### Default Paths (`compresso/libs/common.py`)

Currently hardcodes `/library` and `/tmp/compresso` on all POSIX systems.

| Setting | Linux (today) | macOS (needed) | Windows (needed) |
|---|---|---|---|
| Library path | `/library` | `~/Movies` or user-configured | `%USERPROFILE%\Videos` or user-configured |
| Cache path | `/tmp/compresso` | `~/Library/Caches/compresso` | `%LOCALAPPDATA%\compresso\cache` |
| Config path | `~/.compresso` | `~/Library/Application Support/compresso` | `%APPDATA%\compresso` |

#### Process Priority (`compresso/libs/workers.py`)

Line 657 only sets process priority on POSIX via `os.nice()`. Windows needs
`psutil.Process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)` or similar.

#### Setup Metadata (`setup.py`)

OS classifiers only list Linux. Add macOS and Windows classifiers.

#### FFmpeg/FFprobe Availability

Currently assumes `ffmpeg` and `ffprobe` are on PATH. Should add startup validation
with clear error messages pointing to installation instructions per platform:
- macOS: `brew install ffmpeg`
- Windows: download from ffmpeg.org or `winget install ffmpeg`
- Linux: package manager

### CI Changes Required

The current CI runs everything on `ubuntu-latest`. Adding platform coverage:

#### Unit Tests (`python_lint_and_run_unit_tests.yml`)

Add a platform matrix to the existing sharded test job:

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
    shard: [1, 2, 3]
```

Key considerations:
- macOS and Windows runners are more expensive (3x and 2x respectively) --
  consider running the full matrix only on PRs to master/staging, and a
  single shard on feature branches
- FFmpeg needs to be installed on macOS (`brew install ffmpeg`) and
  Windows (`choco install ffmpeg` or download)
- Some tests may need `pytest.mark.skipif` for platform-specific features
  (e.g., sysfs GPU detection tests should only run on Linux)

#### Integration Tests (`integration_test_and_build_all_packages_ci.yml`)

- Currently uses `apt-get install ffmpeg` -- needs platform-specific FFmpeg install
- Test video cache key uses `runner.os` so caches will be per-platform automatically
- Consider running integration tests on macOS + Windows only on staging/master
  merges (not every push) to manage runner costs

#### Platform-Specific Test Markers

Add pytest markers for platform-specific tests:

```python
@pytest.mark.skipif(sys.platform == "win32", reason="sysfs not available on Windows")
def test_amd_gpu_sysfs_detection():
    ...

@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only GPU detection")
def test_macos_gpu_detection():
    ...
```

#### Frontend Tests

Frontend tests (Vitest) are platform-independent and don't need a matrix -- they
can stay Ubuntu-only.

### Acceptance Criteria

- [ ] Unit tests pass on macOS, Windows, and Linux in CI
- [ ] Integration tests pass on macOS and Linux in CI (Windows stretch goal)
- [ ] GPU monitoring works or gracefully degrades on all platforms
- [ ] Default paths are sensible on all platforms
- [ ] Process priority is set correctly on all platforms
- [ ] FFmpeg availability is validated at startup with helpful error messages
- [ ] No Linux-only assumptions remain in core code paths

---

## P2 -- Encoding Intelligence

Features that make Compresso smarter about what and how it encodes.

### Smart Skip Rules

**What exists:** Files are queued for processing and go through the plugin pipeline.
There's no built-in way to say "skip files already in HEVC" or "skip files under 500MB."

**What's needed:** Simple, configurable rules evaluated before a task enters the queue:

- Skip by codec (e.g., "don't re-encode files already in hevc/av1")
- Skip by file size (e.g., "ignore files under 200MB")
- Skip by resolution (e.g., "only process files 1080p or higher")
- Skip by age (e.g., "only process files added in the last 30 days")
- Skip by container (e.g., "only process MKV files")

These should be per-library settings, not global, since different libraries have
different needs.

**Why it matters:** Without skip rules, Compresso will re-scan and attempt to
re-process files that are already optimized, wasting time and CPU/GPU cycles.
Tdarr has this via plugin filters -- Compresso should have it as a first-class
feature with a clean UI, not requiring plugins.

### Per-Library Encoding Profiles

**What exists:** One encoding preset plugin that applies globally. Libraries exist
as organizational units with their own scan settings, but encoding settings aren't
tied to libraries.

**What's needed:**

- Named encoding profiles (e.g., "4K HEVC High Quality", "720p Web Quick", "Audio FLAC")
- Assign profiles to libraries (movies get profile A, security cameras get profile B)
- Profile management UI in settings

**Why it matters:** A movie library and a security camera archive have very different
encoding needs. Currently you'd need to change settings between processing runs.

### Two-Pass Encoding

**What exists:** Single-pass CRF encoding only.

**What's needed:** Option for two-pass encoding in the encoding presets plugin.
Two-pass gives better quality at a target bitrate because the encoder can analyze
the full file before encoding.

- Add two-pass toggle to encoding preset settings
- Handle the two-pass FFmpeg command generation (pass 1 with `-pass 1 -f null /dev/null`,
  pass 2 with `-pass 2`)
- Temp file management for the pass 1 stats file

### HDR Tone Mapping

**What exists:** Nothing -- HDR content is either passed through or potentially
mangled during transcoding.

**What's needed:** Detection and handling of HDR content:

- Detect HDR metadata (BT.2020 color space, PQ/HLG transfer, HDR10/HDR10+/Dolby Vision)
- Option to preserve HDR during re-encoding (pass through metadata)
- Option to tone-map HDR to SDR for compatibility (using FFmpeg's `tonemap` filter)
- Display HDR status in file info and compression dashboard

**Why it matters:** 4K Blu-ray rips and modern streaming downloads are increasingly
HDR. Re-encoding without handling HDR metadata produces washed-out or incorrect colors.

---

## P3 -- Quality of Life

Improvements that make daily use more pleasant.

### Notification Improvements

**What exists:** Discord, Slack, and generic webhook notifications for 5 event types.
No retry on failure, no batching, `health_check_failed` is defined but never dispatched.

**What's needed:**

1. **Notification batching/digest** -- Instead of 50 individual Discord messages
   when a batch completes, send one summary: "Batch complete: 15 files processed,
   8.3 GB saved, avg VMAF 94.2." Add a configurable digest window (e.g., 5 minutes).

2. **Wire up `health_check_failed`** -- The event type exists in
   `external_notifications.py` but is never dispatched. Add a dispatch call in
   `healthcheck.py` when a thorough scan finds corruption.

3. **Retry with backoff** -- Currently a failed notification is silently dropped.
   Add 3 retries with exponential backoff (1s, 5s, 15s) before giving up.

4. **Delivery log** -- Store dispatch attempts (success/failure) in SQLite.
   Add an API endpoint and UI panel to view notification history.

### WebSocket Disconnect Indicator

**What exists:** WebSocket connection for real-time dashboard updates. No UI
feedback when the connection drops.

**What's needed:** A small connection status indicator (dot or icon) in the header
bar. Green when connected, yellow when reconnecting, red when disconnected. The
main dashboard already shows a "stale data" banner after 10 seconds, but it's
not visible from other pages.

### Encoding Comparison Tool

**What exists:** A/B preview system that generates a segment and compares original
vs. one encoding. VMAF/SSIM scoring.

**What's needed:** Extend the preview system to compare multiple encoding settings
side-by-side:

- Pick a sample file
- Choose 2-4 encoding presets (e.g., CRF 18 vs 22 vs 26, or HEVC vs AV1)
- Generate all variants
- Show a comparison table: file size, VMAF score, SSIM score, encoding time
- Help the user pick the best quality/size tradeoff before committing to a
  library-wide encode

### Storage Space Projection

**What exists:** Compression dashboard shows space saved for completed tasks,
codec distribution, and per-file statistics.

**What's needed:** A "what if" projection for unprocessed files:

- "If you encode your remaining X files to HEVC CRF 22, estimated savings: ~Y TB"
- Based on average compression ratios from completed tasks in the same library
- Show projected savings per library
- Factor in current codec distribution (H.264 files compress more than HEVC files)

---

## P4 -- GPU-Aware Worker Scheduling

### Current State

GPU monitoring is fully implemented and displayed on the dashboard:
- NVIDIA: utilization, memory, temperature via `nvidia-smi`
- Intel: frequency and temperature via sysfs
- AMD: busy percent, VRAM, temperature via sysfs

**The problem:** GPU monitoring is completely disconnected from worker scheduling.
The `worker_type` field in worker groups is documented as "an organizational/display
label only." Task assignment uses string tags only -- zero GPU awareness.

### What's Needed

For a single-machine setup with one GPU, this is lower priority since the GPU
worker will always use the available GPU. It becomes important with multiple GPUs
or multiple machines.

When prioritized, the work involves:

1. **Worker-GPU binding** -- Workers created with a `gpu_index` so each worker
   is pinned to a specific GPU. Foreman assigns GPU index at worker creation time.

2. **Task GPU requirements** -- Tasks tagged with whether they need GPU based on
   the encoding preset (e.g., `h264_nvenc` requires GPU, `libx264` does not).

3. **GPU utilization check** -- Before assigning a task to a GPU worker, check
   that the assigned GPU isn't already at 100% utilization.

4. **GPU-aware ETA** -- The ETA calculator (`queue_eta.py`) currently divides
   pending tasks equally across all workers. GPU workers are typically 3-5x faster
   than CPU workers -- factor this into the ETA calculation.

5. **Worker status enrichment** -- Include GPU utilization in worker status API
   responses so the dashboard can show which GPU each worker is using.

---

## P5 -- Distributed Worker Hardening

### Current State

Multi-machine encoding works for 2-3 nodes via HTTP-based remote task management.
Remote nodes are manually configured, tasks are routed to the first available
remote, and files are transferred with optional checksum validation.

### Known Issues

These are documented issues found in code review. They don't block small
deployments but would cause problems at scale:

| Issue | Location | Impact |
|---|---|---|
| No load balancing -- first available remote gets the task | `foreman.py:313` | Uneven distribution |
| Task state desync if both sides crash mid-task | `remote_task_manager.py:155,499` | Lost work |
| Orphaned files on remote after download failure | `remote_task_manager.py:489` | Disk waste |
| Network lock can spin indefinitely | `remote_task_manager.py:298-308` | Worker stall |
| No distributed tracing (can't correlate local/remote logs) | Throughout | Hard to debug |
| Queue dequeue race between put and manager spawn | `foreman.py:745` | Orphaned task |

### What's Needed (When Prioritized)

1. **Simple load balancing** -- Prefer the remote node with the fewest active tasks
   instead of first-available.

2. **Remote node status panel** -- The backend tracks link status (connected,
   reconnecting, disconnected) but it's not surfaced well in the UI. A dedicated
   panel showing each node's connection state, active tasks, and transfer progress.

3. **Orphaned file cleanup** -- Periodic background job that checks remote nodes
   for cached files from completed/failed tasks and removes them.

4. **Task correlation IDs** -- Assign a trace ID when a task is created and include
   it in all log messages on both local and remote sides.

---

## P6 -- Future Ideas

Longer-term features worth considering but not currently planned.

### DTS Audio Codec Support

The audio codec list doesn't include DTS, which is common in Blu-ray rips. Adding
DTS decode support (FFmpeg handles it) and possibly DTS encode (requires `libdca`).

### Lossless Encoding Mode

Some codecs support lossless encoding (`-lossless 1` for some H.265 encoders,
`-crf 0` for x264/x265). Not currently exposed in the encoding presets UI. Could
be useful for archival workflows.

### Per-Stream Video Codec Selection

Currently the video codec is global per task. Some advanced workflows need different
codecs for different video streams in the same file (rare but possible with
multi-angle content).

### Advanced Encoder Parameters UI

The "extra FFmpeg flags" field works for power users but isn't discoverable. A
more guided UI for common advanced parameters would help:

- B-frame count
- Reference frames
- Lookahead depth
- Rate control mode (CRF vs CBR vs VBR)
- Grain synthesis (for film content)

### Encoding Profile Import/Export

Allow exporting encoding profiles as JSON files and importing them. Useful for
sharing configurations between instances or backing up settings.

### MQTT Integration

For home automation setups, publishing events to an MQTT broker would allow
integration with Home Assistant, Node-RED, etc. Events like task completion,
queue empty, and health check failures could trigger automations.

---

## Reference: Compresso vs Tdarr

For context, here's where Compresso stands relative to Tdarr (the main comparable
tool in this space) as of this writing.

### Where Compresso is Ahead

| Feature | Compresso | Tdarr |
|---|---|---|
| VMAF/SSIM quality scoring | Built-in, shown in approval and notifications | Not available |
| A/B side-by-side preview | Full preview with quality metrics | Not available |
| Approval workflow | Rich -- search, sort, bulk ops, reject options | Basic staging with global toggle |
| Task retry | Automatic with configurable count | Failed = stuck |
| File safety/rollback | Backup before replace, full rollback on failure | No rollback |
| Analytics dashboard | Codec distribution, timelines, encoding speed, ETA | Basic counts only |
| Task history | Search, filter, sort, CSV export, reprocess | Basic job reports |
| Open source | GPL-3.0 | Proprietary EULA |

### Where Tdarr is Ahead

| Feature | Tdarr | Compresso |
|---|---|---|
| Distributed architecture | Purpose-built server/node, tested at 1M files | Basic HTTP, works for 2-3 nodes |
| GPU worker scheduling | GPU-aware worker types, encoder selection per worker | Monitor only, not used for scheduling |
| Visual flow editor | Node-based workflow builder with templates | Plugin stacks only |
| Plugin ecosystem | 89 contributors, 1,700+ commits in community repo | 1 bundled plugin |
| HandBrake support | Dual engine (FFmpeg + HandBrake) | FFmpeg only |
| Library scheduling | 7-day/24-hour per-library schedule grid | Basic scan intervals |
| Platform support | Windows, Linux, macOS, Docker (amd64 + ARM) | Linux + Docker only |

### Roughly Equal

- Plugin system architecture (both have version-2 APIs)
- Docker deployment (both production-ready)
- Web dashboard (both Vue.js-based)
- FFmpeg codec/container support
- Worker management (both have configurable pools)
