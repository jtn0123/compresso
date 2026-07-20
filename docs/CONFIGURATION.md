# Configuration Reference

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PUID` | `1000` | User ID for the runtime process |
| `PGID` | `1000` | Group ID for the runtime process |
| `TZ` | System default | Container timezone (e.g. `America/New_York`) |
| `DEBUGGING` | unset | Set to `true` to enable dev mode (`--dev` flag) |
| `COMPRESSO_SQLITE_MAINTENANCE` | `basic` | SQLite maintenance mode: `basic`, `full`, or `off` |
| `COMPRESSO_DB_PATH` | `/config/.compresso/config/compresso.db` | Path to the SQLite database |
| `COMPRESSO_RUN_COMMAND` | unset | Custom run command template (use `{cmd}` as placeholder) |
| `USE_CUSTOM_SUPPORT_API` | unset | `test` or `dev` to override the support API URL |
| `PORT` | `8888` | Override the web UI / API port (forwarded to `--port` CLI arg) |
| `HOME_DIR` | `~` (source), `/config` (Docker) | Override the home directory used to resolve `~/.compresso/` paths |
| `ui_address` | `127.0.0.1` | Listen address. Container deployments must set `0.0.0.0`; source installs default to loopback for safety. |

## Volume Mounts

| Path | Purpose |
|------|---------|
| `/config` | Persistent configuration and database storage |
| `/library` | Media library root — source files to process |
| `/tmp/compresso` | Temporary working directory for in-progress tasks |

## Port Mapping

| Port | Protocol | Description |
|------|----------|-------------|
| `8888` | TCP | Web UI and API |

## Health Check

The container includes a built-in `HEALTHCHECK` that polls the readiness endpoint:

```
GET http://127.0.0.1:8888/compresso/api/v2/healthcheck/readiness
```

- Interval: 30s
- Timeout: 10s
- Start period: 60s
- Retries: 3

## Hardware Acceleration

> **Hardware encoding is a last resort.** If your goal is smaller files, use the default software encoders (`libx265` / `libsvtav1`) — they produce meaningfully smaller files at the same visual quality and run on any CPU (Intel, AMD, Apple Silicon). Hardware acceleration below is worthwhile for quality-neutral *decoding*, or when encode speed genuinely matters more than storage savings. See the [Encoding Guide](ENCODING_GUIDE.md).

### VAAPI (Intel / AMD)

Pass the render device into the container:

```yaml
devices:
  - /dev/dri:/dev/dri
```

The image includes `va-driver-all`, Intel media drivers, and `vainfo`.

### NVIDIA

Requires the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/overview.html).

```yaml
runtime: nvidia
environment:
  - NVIDIA_VISIBLE_DEVICES=all
  - NVIDIA_DRIVER_CAPABILITIES=compute,video,utility
```

## Minimal Docker Compose Example

```yaml
services:
  compresso:
    image: ghcr.io/jtn0123/compresso:latest
    container_name: compresso
    restart: unless-stopped
    ports:
      - "127.0.0.1:8888:8888"
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/New_York
      - ui_address=0.0.0.0
    volumes:
      - ./config:/config
      - /path/to/media:/library
      - /tmp/compresso:/tmp/compresso
    # For VAAPI hardware acceleration, uncomment:
    # devices:
    #   - /dev/dri:/dev/dri
```

The loopback host binding is the safe default. A master that must accept LAN workers can use `8888:8888` after enabling API authentication and restricting access with the host firewall. Configure a unique destination `api_token` on each remote link; it is masked on read and is not returned by the general settings endpoint. Basic authentication remains supported independently. API v1 is authenticated and rate-limited but deprecated for removal in the next major release.

## Transfer safety

Media sent between the master and a worker uses only the resumable transfer API.
The retired `/compresso/api/v2/upload/pending/file` route returns HTTP 410.
Every distributed media job must include a stable job ID, and every 8 MiB chunk
plus the completed file is SHA-256 checked.

| Setting | Default | Description |
|---|---:|---|
| `maximum_transfer_file_size_gb` | `1024` | Maximum declared size of one incoming media file (1 TiB by default). |
| `minimum_free_space_gb` | `5` | Cache space that incoming chunks must leave unused. |
| `transfer_partial_retention_hours` | `48` | Resume window before an interrupted session and all owned artifacts are removed. |

Session creation reserves the remaining bytes for every active transfer so
concurrent workers cannot collectively overcommit the cache. Free space is
rechecked before every chunk. A reserve failure returns HTTP 507, persists the
disk-reserve safety latch, pauses local workers, and leaves the partial transfer
available to resume after operator acknowledgement and a successful capacity
recheck. Operators can intentionally abandon an incomplete session with
`DELETE /compresso/api/v2/transfer/session/{transfer_id}`.

Plugin ZIP uploads remain separate from media ingress. They use the framework's
ordinary multipart parser and are limited to 64 MiB compressed.

## Crash-safe JSON state

Installation-owned JSON state is written through one same-directory atomic
writer. It flushes and `fsync`s the temporary file, replaces the prior document
atomically, and `fsync`s the parent directory where the platform supports it.
This covers `settings.json`, resumable-transfer manifests, the durable safety
latch, recovery journals, scan checkpoints, log-forwarding offsets, media
manifests, plugin settings, and operational reports.

The root of `settings.json` must be a JSON object. A syntactically valid list,
string, number, boolean, or null value is logged and ignored without rewriting
the file. Startup then retains conservative defaults: loopback UI binding,
library scanning disabled, and the safe worker cap. Remote task `data.json`
files and sensitive configuration/state files are created owner-readable only.
