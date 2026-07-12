"""Seed two tiny approval tasks through the installed Compresso package."""

import json
import os
import time
from pathlib import Path

from compresso import config
from compresso.libs.unmodels.tasks import Tasks
from compresso.service import init_db


def main():
    home = Path(os.environ["HOME_DIR"])
    settings = config.Config()
    database = init_db(settings.get_config_path())
    fixtures = {}

    for action in ("approve", "reject"):
        source = home / "library" / f"{action}.mkv"
        cache_dir = home / "cache" / f"compresso_file_conversion-e2e-{action}"
        cache = cache_dir / f"{action}.mkv"
        source.parent.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        source.write_bytes(f"original-{action}".encode())
        cache.write_bytes(f"encoded-{action}".encode())

        task = Tasks.create(
            abspath=str(source),
            cache_path=str(cache),
            priority=100,
            type="local",
            library_id=1,
            status="awaiting_approval",
            success=True,
            processed_by_worker="packaged-e2e",
            source_size=source.stat().st_size,
            staged_size=cache.stat().st_size,
        )
        staged_dir = home / "staging" / f"task_{task.id}"
        staged_dir.mkdir(parents=True)
        staged = staged_dir / cache.name
        staged.write_bytes(cache.read_bytes())
        fixtures[action] = {
            "id": task.id,
            "source": str(source),
            "cache": str(cache),
            "staged_dir": str(staged_dir),
        }

    (home / "e2e-fixture.json").write_text(json.dumps(fixtures))
    database.stop()
    while not database.is_stopped():
        time.sleep(0.05)


if __name__ == "__main__":
    main()
