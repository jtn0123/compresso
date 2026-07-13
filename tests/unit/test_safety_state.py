import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from compresso.libs.safety_state import SafetyState, record_safety_event


@pytest.mark.unittest
class TestSafetyState:
    def test_new_store_is_ready(self, tmp_path):
        snapshot = SafetyState(tmp_path).snapshot()

        assert snapshot["pause_required"] is False
        assert snapshot["status"] == "ready"
        assert snapshot["events"] == []

    def test_trigger_is_durable_private_and_idempotent(self, tmp_path):
        def clock():
            return datetime(2026, 7, 12, 12, tzinfo=UTC)

        store = SafetyState(tmp_path, now=clock)

        first = store.trigger("disk-reserve", "Cache reserve breached", details={"free_bytes": 10})
        second = store.trigger("disk-reserve", "Cache reserve still breached", details={"free_bytes": 5})

        assert first["id"] == second["id"]
        assert second["occurrences"] == 2
        assert store.snapshot()["pause_required"] is True
        assert SafetyState(tmp_path, now=clock).snapshot()["events"][0]["details"]["free_bytes"] == 5
        state_path = Path(tmp_path) / "safety" / "state.json"
        assert json.loads(state_path.read_text())["schema_version"] == 1
        if os.name != "nt":
            assert state_path.stat().st_mode & 0o777 == 0o600

    def test_acknowledge_then_clear_allows_release(self, tmp_path):
        store = SafetyState(tmp_path)
        event = store.trigger("manifest-corruption", "Manifest checksum mismatch")

        acknowledged = store.acknowledge(event["id"], actor="operator")
        assert acknowledged["acknowledged_by"] == "operator"
        store.clear("manifest-corruption", resolution="Manifest restored from journal")

        assert store.can_release()[0] is True
        snapshot = store.release_pause()
        assert snapshot["pause_required"] is False
        assert snapshot["status"] == "ready"

    def test_release_rejects_active_or_unacknowledged_event(self, tmp_path):
        store = SafetyState(tmp_path)
        event = store.trigger("rollback-failure", "Rollback did not complete")

        allowed, reasons = store.can_release()
        assert allowed is False
        assert "active" in reasons[0]
        store.clear("rollback-failure", resolution="Recovered manually")
        allowed, reasons = store.can_release()
        assert allowed is False
        assert "acknowledgement" in reasons[0]

        with pytest.raises(ValueError, match="cannot be released"):
            store.release_pause()
        store.acknowledge(event["id"])
        assert store.release_pause()["pause_required"] is False

    def test_unknown_event_operations_fail(self, tmp_path):
        store = SafetyState(tmp_path)

        with pytest.raises(KeyError, match="Unknown safety event"):
            store.acknowledge("missing")
        with pytest.raises(KeyError, match="Unknown active safety event"):
            store.clear("missing")

    def test_corrupt_state_fails_closed_and_preserves_evidence(self, tmp_path):
        state_dir = Path(tmp_path) / "safety"
        state_dir.mkdir()
        (state_dir / "state.json").write_text("not-json")

        snapshot = SafetyState(tmp_path).snapshot()

        assert snapshot["pause_required"] is True
        assert snapshot["status"] == "paused"
        assert snapshot["events"][0]["code"] == "safety-state-corrupt"
        assert list(state_dir.glob("state.corrupt-*.json"))

    def test_history_is_bounded(self, tmp_path):
        start = datetime(2026, 1, 1, tzinfo=UTC)
        ticks = iter(start + timedelta(seconds=index) for index in range(20))
        store = SafetyState(tmp_path, now=lambda: next(ticks), max_events=3)

        for index in range(5):
            event = store.trigger(f"event-{index}", f"Event {index}")
            store.acknowledge(event["id"])
            store.clear(f"event-{index}")

        assert len(store.snapshot()["events"]) == 3

    def test_active_events_are_never_discarded_to_meet_history_bound(self, tmp_path):
        store = SafetyState(tmp_path, max_events=2)

        for index in range(3):
            store.trigger(f"active-{index}", f"Active {index}")

        assert [event["code"] for event in store.snapshot()["events"]] == ["active-0", "active-1", "active-2"]

    def test_recorder_rejects_mock_or_missing_userdata_paths(self):
        settings = MagicMock()
        settings.get_userdata_path.return_value = MagicMock()

        with pytest.raises(ValueError, match="concrete user-data path"):
            record_safety_event(settings, None, "disk-reserve", "Low disk")
