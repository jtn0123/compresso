#!/usr/bin/env python3

"""Shared guard for tests that need to create real symlinks.

Several suites prove that Compresso refuses to follow a symlink out of a
configured root. Creating one requires privileges that a stock Windows account
does not have (Developer Mode or an elevated shell), so those tests fail on a
developer machine while passing on CI, where the runner is privileged.

Probing at import time — rather than skipping on ``os.name == "nt"`` — keeps the
coverage wherever symlinks actually work, including privileged Windows, and
skips with a clear reason only where the operating system refuses.
"""

import functools
import os
import tempfile

import pytest


@functools.cache
def symlinks_available() -> bool:
    """Whether this process can create a symlink on the temp filesystem."""
    with tempfile.TemporaryDirectory(prefix="compresso-symlink-probe-") as probe_dir:
        target = os.path.join(probe_dir, "target")
        link = os.path.join(probe_dir, "link")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("probe")
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError, AttributeError):
            return False
        return os.path.islink(link)


requires_symlinks = pytest.mark.skipif(
    not symlinks_available(),
    reason=(
        "creating symlinks is not permitted for this account; enable Windows Developer Mode "
        "or run elevated to exercise the symlink-rejection guards"
    ),
)
