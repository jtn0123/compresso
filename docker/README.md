# Compresso Docker Image


### Building the Source
Before building the image, you need to have built the compresso python package:
```bash
rm -rf ./build ./dist
python3 -m pip install -r requirements.txt -r requirements-dev.txt
python3 -m build --no-isolation --skip-dependency-check --wheel
python3 -m build --no-isolation --skip-dependency-check --sdist
```

This fork vendors the frontend directly in the main repository. A recursive clone is no longer required.

Node.js 24 is the supported frontend build baseline for this fork.
The Python build performs a clean frontend install from the committed lockfile as part of package creation.


### Building the image
Simply run this command from the root of the project:
```bash
docker build -f ./docker/Dockerfile -t jtn0123/compresso:staging .
```

A canonical production [`docker-compose.yml`](docker-compose.yml) is included in this directory as a starting point.

For the recommended production layout and a large-library checklist, see [../docs/FORK_DEPLOYMENT.md](../docs/FORK_DEPLOYMENT.md).

### Build Architecture

The Docker image uses a two-layer strategy for faster iteration:

1. **Base image** (`Dockerfile.base` → `ghcr.io/jtn0123/compresso-base:latest`):
   Contains the OS (Ubuntu 24.04), FFmpeg, Python 3.13, Node.js 24, VAAPI/Vulkan
   drivers, and Python pip dependencies. Rebuilt automatically on changes to
   `Dockerfile.base` or `requirements.txt`, and weekly via CI.

2. **Application image** (`Dockerfile` → `jtn0123/compresso:latest`):
   Installs the pre-built Compresso wheel and entrypoint scripts on top of the
   base image. Built on every push to master, staging, or dev branches.

This separation means most CI builds only rebuild the lightweight application
layer (~1–2 minutes instead of ~10–15 minutes). To override the base image locally:

```bash
docker build -f docker/Dockerfile --build-arg BASE_IMAGE=my-custom-base:latest -t compresso:local .
```

Images are published to both Docker Hub (`jtn0123/compresso`) and GHCR (`ghcr.io/jtn0123/compresso`).
