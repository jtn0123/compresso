# Configuration Reference

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PUID` | `1000` | User ID for the runtime process |
| `PGID` | `1000` | Group ID for the runtime process |
| `TZ` | System default | Container timezone (e.g. `America/New_York`) |
| `DEBUGGING` | unset | Set to `true` to enable dev mode (`--dev` flag) |
| `UNMANIC_SQLITE_MAINTENANCE` | `basic` | SQLite maintenance mode: `basic`, `full`, or `off` |
| `UNMANIC_DB_PATH` | `/config/.compresso/config/compresso.db` | Path to the SQLite database |
| `UNMANIC_RUN_COMMAND` | unset | Custom run command template (use `{cmd}` as placeholder) |
| `USE_CUSTOM_SUPPORT_API` | unset | `test` or `dev` to override the support API URL |

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
      - "8888:8888"
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/New_York
    volumes:
      - ./config:/config
      - /path/to/media:/library
      - /tmp/compresso:/tmp/compresso
    # For VAAPI hardware acceleration, uncomment:
    # devices:
    #   - /dev/dri:/dev/dri
```
