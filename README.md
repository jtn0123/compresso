# COMPRESSO — Media Library Optimizer

Compresso is a media library optimizer with approval workflow, compression dashboard, A/B preview, and health checks. Originally forked from [Josh5/Unmanic](https://github.com/Unmanic/unmanic), it has diverged significantly with new features and deployment hardening.

### Key Features

- **Approval workflow** — review and approve/reject compression tasks before they modify your library
- **Compression dashboard** — track compression ratios, space savings, and processing stats
- **A/B preview** — compare source vs. encoded output before committing changes
- **Health checks** — readiness endpoint at `/compresso/api/v2/healthcheck/readiness`
- **Large-library safe defaults** — conservative worker cap, explicit cache path
- Frontend vendored in-repo (no submodule/recursive clone required)
- Node.js 24 build baseline, validated in CI
- SQLite maintenance on container startup
- Structured log markers for startup/worker/post-processing failures

### Supported Deploy Paths

- **Docker (recommended)** — see [`docker/docker-compose.yml`](docker/docker-compose.yml) and [`docs/FORK_DEPLOYMENT.md`](docs/FORK_DEPLOYMENT.md)
- **Source** — see [Install and Run](#install-and-run) below

---

### Table Of Contents

[Dependencies](#dependencies)

[Screen-shots](#screen-shots)

[Install and Run](#install-and-run)

[License and Contribution](#license-and-contribution)


## Dependencies

 - Python 3.x ([Install](https://www.python.org/downloads/))
 - To install requirements run 'python3 -m pip install -r requirements.txt' from the project root

Since Compresso can be used for running any commands, you will need to ensure that the required dependencies for those commands are also installed on your system.

## Screen-shots

#### Dashboard:
![Screen-shot - Dashboard](./docs/images/unmanic-dashboard-processing-anime.png)
#### File metrics:
![Screen-shot - Desktop](./docs/images/unmanic-file-size-data-panel-anime.png)
#### Installed plugins:
![Screen-shot - Desktop](./docs/images/unmanic-list-installed-plugins.png)

## Install and Run

To run from source:

1) Install Python 3 and Node.js 24.x.
2) Install Python build dependencies:
    ```
    python3 -m pip install -r requirements.txt -r requirements-dev.txt
    ```
3) Optionally run the frontend validation steps used in CI:
    ```bash
    cd compresso/webserver/frontend
    npm ci
    npm run lint
    npm run build:publish
    cd ../../..
    ```
4) Build and install the package:
    ```bash
    rm -rf build dist
    python3 -m build --no-isolation --skip-dependency-check --wheel
    python3 -m pip install --user "$(find dist -maxdepth 1 -type f -name '*.whl' | sort | tail -n 1)"
    ```
5) Run Compresso:
    ```bash
    compresso
    ```
6) Open your web browser and navigate to http://localhost:8888/

Node.js 24 is the supported frontend build baseline. Node 22 may still work, but CI and release validation now use Node 24.

The Python package build performs its own clean frontend install from the committed lockfile, so a pre-existing `node_modules` directory is not required.

For a production-focused source or Docker workflow, including a deployment checklist for large libraries, see [docs/FORK_DEPLOYMENT.md](./docs/FORK_DEPLOYMENT.md).

### Configuration

Compresso stores its configuration in `~/.compresso/`:
- `~/.compresso/config/` — settings.json and database
- `~/.compresso/logs/` — application logs
- `~/.compresso/plugins/` — installed plugins
- `~/.compresso/userdata/` — user data

## License and Contribution

This projected is licensed under the GPL version 3.

Copyright (C) Josh Sunnex - All Rights Reserved

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

This project contains libraries imported from external authors.
Please refer to the source of these libraries for more information on their respective licenses.

---
