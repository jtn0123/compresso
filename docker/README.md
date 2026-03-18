# Unmanic Docker Image


### Building the Source
Before building the image, you need to have built the unmanic python package:
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
docker build -f ./docker/Dockerfile -t josh5/unmanic:staging .
```

For the recommended production layout and a large-library checklist, see [../docs/FORK_DEPLOYMENT.md](../docs/FORK_DEPLOYMENT.md).
