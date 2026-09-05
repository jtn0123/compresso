"""A silent encoder must not evade the comparison deadline."""

import sys
from unittest.mock import MagicMock

import pytest

from compresso.libs.comparison import ComparisonManager


def test_silent_encoder_obeys_timeout():
    manager = object.__new__(ComparisonManager)
    manager.ENCODE_TIMEOUT = 0.1
    with pytest.raises(RuntimeError, match="timed out"):
        manager._run_encode_with_progress(
            [sys.executable, "-c", "import time; time.sleep(1)"], MagicMock(), duration=10
        )
