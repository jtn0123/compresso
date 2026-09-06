"""A silent encoder must not evade the comparison deadline."""

import sys
from unittest.mock import MagicMock

import pytest

from compresso.libs.comparison_encoder import run_encode_with_progress


def test_silent_encoder_obeys_timeout():
    command = [sys.executable, "-c", "import time; time.sleep(1)"]
    candidate = MagicMock()
    with pytest.raises(RuntimeError, match="timed out"):
        run_encode_with_progress(command, candidate, duration=10, timeout=0.1)
