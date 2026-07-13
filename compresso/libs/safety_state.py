"""Durable, fail-closed operational safety latch.

The latch is intentionally independent from the worker threads.  A hard safety
event is written to disk before callers pause work, so a process restart cannot
silently resume a deployment that still needs operator attention.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections.abc import Callable
from contextlib import suppress
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


class SafetyState:
    """Persist and manage hard-stop safety events for one installation."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        userdata_path: str | os.PathLike[str],
        *,
        now: Callable[[], datetime] | None = None,
        max_events: int = 200,
    ) -> None:
        self.root = Path(userdata_path).expanduser().resolve() / "safety"
        self.path = self.root / "state.json"
        self._now = now or (lambda: datetime.now(UTC))
        self.max_events = max(1, int(max_events))
        self._lock = _lock_for(self.path)

    def _timestamp(self) -> str:
        return self._now().astimezone(UTC).isoformat().replace("+00:00", "Z")

    @classmethod
    def _empty(cls) -> dict[str, Any]:
        return {
            "schema_version": cls.SCHEMA_VERSION,
            "pause_required": False,
            "updated_at": None,
            "released_at": None,
            "events": [],
        }

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("invalid safety state")
            data: dict[str, Any] = raw
            if data.get("schema_version") != self.SCHEMA_VERSION or not isinstance(data.get("events"), list):
                raise ValueError("unsupported safety state schema")
            return data
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return self._recover_corrupt_state(exc)

    def _recover_corrupt_state(self, exc: Exception) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        timestamp = self._timestamp().replace(":", "-")
        evidence_path = self.root / f"state.corrupt-{timestamp}.json"
        if self.path.exists():
            with suppress(OSError):
                os.replace(self.path, evidence_path)
        state = self._empty()
        state["pause_required"] = True
        state["updated_at"] = self._timestamp()
        state["events"] = [
            {
                "id": uuid.uuid4().hex,
                "code": "safety-state-corrupt",
                "message": "The durable safety state could not be read",
                "severity": "critical",
                "details": {"error": type(exc).__name__},
                "active": True,
                "occurrences": 1,
                "first_seen_at": state["updated_at"],
                "last_seen_at": state["updated_at"],
                "acknowledged_at": None,
                "acknowledged_by": None,
                "cleared_at": None,
                "resolution": None,
            }
        ]
        self._write(state)
        return state

    def _write(self, state: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp_path = self.path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        payload = json.dumps(state, indent=2, sort_keys=True) + "\n"
        try:
            descriptor = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
            if os.name != "nt":
                os.chmod(self.path, 0o600)
        finally:
            with suppress(OSError):
                temp_path.unlink(missing_ok=True)

    @staticmethod
    def _public(state: dict[str, Any]) -> dict[str, Any]:
        snapshot = deepcopy(state)
        snapshot["status"] = "paused" if snapshot["pause_required"] else "ready"
        snapshot["active_count"] = sum(bool(event.get("active")) for event in snapshot["events"])
        snapshot["unacknowledged_count"] = sum(event.get("acknowledged_at") is None for event in snapshot["events"])
        return snapshot

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._public(self._read())

    def trigger(
        self,
        code: str,
        message: str,
        *,
        severity: str = "critical",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not code.strip() or not message.strip():
            raise ValueError("Safety event code and message are required")
        with self._lock:
            state = self._read()
            events: list[dict[str, Any]] = state["events"]
            timestamp = self._timestamp()
            event = next(
                (item for item in events if item.get("code") == code and item.get("active")),
                None,
            )
            if event is None:
                event = {
                    "id": uuid.uuid4().hex,
                    "code": code,
                    "message": message,
                    "severity": severity,
                    "details": details or {},
                    "active": True,
                    "occurrences": 1,
                    "first_seen_at": timestamp,
                    "last_seen_at": timestamp,
                    "acknowledged_at": None,
                    "acknowledged_by": None,
                    "cleared_at": None,
                    "resolution": None,
                }
                events.append(event)
            else:
                event.update(
                    {
                        "message": message,
                        "severity": severity,
                        "details": details or {},
                        "last_seen_at": timestamp,
                        "occurrences": int(event.get("occurrences", 1)) + 1,
                    }
                )
            state["pause_required"] = True
            state["updated_at"] = timestamp
            self._trim(state)
            self._write(state)
            return deepcopy(event)

    def acknowledge(self, event_id: str, *, actor: str = "operator") -> dict[str, Any]:
        with self._lock:
            state = self._read()
            events: list[dict[str, Any]] = state["events"]
            event = next((item for item in events if item.get("id") == event_id), None)
            if event is None:
                raise KeyError(f"Unknown safety event: {event_id}")
            if event.get("acknowledged_at") is None:
                event["acknowledged_at"] = self._timestamp()
                event["acknowledged_by"] = actor.strip() or "operator"
                state["updated_at"] = event["acknowledged_at"]
                self._write(state)
            return deepcopy(event)

    def clear(self, code: str, *, resolution: str = "Condition rechecked and cleared") -> dict[str, Any]:
        with self._lock:
            state = self._read()
            events: list[dict[str, Any]] = state["events"]
            event = next(
                (item for item in events if item.get("code") == code and item.get("active")),
                None,
            )
            if event is None:
                raise KeyError(f"Unknown active safety event: {code}")
            event["active"] = False
            event["cleared_at"] = self._timestamp()
            event["resolution"] = resolution
            state["updated_at"] = event["cleared_at"]
            self._write(state)
            return deepcopy(event)

    def can_release(self) -> tuple[bool, list[str]]:
        with self._lock:
            state = self._read()
            reasons = []
            active = [event for event in state["events"] if event.get("active")]
            unacknowledged = [event for event in state["events"] if event.get("acknowledged_at") is None]
            if active:
                reasons.append(f"{len(active)} active safety event(s) remain")
            if unacknowledged:
                reasons.append(f"{len(unacknowledged)} event(s) still require acknowledgement")
            return not reasons, reasons

    def release_pause(self) -> dict[str, Any]:
        with self._lock:
            allowed, reasons = self.can_release()
            if not allowed:
                raise ValueError(f"Safety pause cannot be released: {'; '.join(reasons)}")
            state = self._read()
            state["pause_required"] = False
            state["released_at"] = self._timestamp()
            state["updated_at"] = state["released_at"]
            self._write(state)
            return self._public(state)

    def _trim(self, state: dict[str, Any]) -> None:
        if len(state["events"]) <= self.max_events:
            return
        active = [event for event in state["events"] if event.get("active")]
        inactive = [event for event in state["events"] if not event.get("active")]
        if len(active) >= self.max_events:
            state["events"] = active
            return
        state["events"] = inactive[-(self.max_events - len(active)) :] + active


def record_safety_event(settings, foreman, code: str, message: str, **details: Any) -> dict[str, Any]:
    """Persist a safety event and idempotently pause every local worker."""

    userdata_path = settings.get_userdata_path()
    if not isinstance(userdata_path, (str, Path)) or not os.fspath(userdata_path):
        raise ValueError("A concrete user-data path is required for durable safety state")
    event = SafetyState(userdata_path).trigger(code, message, details=details)
    if foreman is None:
        try:
            from compresso.libs.uiserver import CompressoRunningThreads

            foreman = CompressoRunningThreads().get_compresso_running_thread("foreman")
        except (AttributeError, KeyError, TypeError):
            foreman = None
    if foreman is not None:
        foreman.safety_latched = True
        foreman.pause_all_worker_threads(record_paused=True)
    return event
