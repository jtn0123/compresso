# SPDX-License-Identifier: GPL-3.0-only

"""Read-only deployment readiness checks for master and worker nodes."""

from __future__ import annotations

import argparse
import contextlib
import ipaddress
import json
import os
import platform
import plistlib
import re
import shutil
import socket
import sqlite3
import sys
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests

from compresso import metadata
from compresso.config import Config
from compresso.libs.constants import API_AUTH_HEADER_NAME
from compresso.libs.json_state import atomic_json_write
from compresso.libs.worker_capabilities import WorkerCapabilities

SCHEMA_VERSION = 1
REPORT_TTL_HOURS = 24
SECRET_KEYS = ("authorization", "cookie", "password", "secret", "token")
REPORT_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,126}\.json")
PEER_API_PATHS = {
    "readiness": "/compresso/api/v2/healthcheck/readiness",
    "version": "/compresso/api/v2/version/read",
    "capabilities": "/compresso/api/v2/system/capabilities",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _redact(value: object, key: str = "") -> object:
    if any(fragment in key.lower() for fragment in SECRET_KEYS):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(item_key): _redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def _atomic_json_write(path: Path, payload: dict[str, object]) -> None:
    atomic_json_write(path, payload, mode=0o600)


def _report_destination(report_dir: Path, output_name: str | None, default_name: str) -> Path:
    name = output_name or default_name
    if Path(name).name != name or REPORT_NAME_PATTERN.fullmatch(name) is None:
        raise ValueError("report output must be a JSON filename without directory components")
    root = report_dir.resolve()
    destination = (root / name).resolve()
    if not destination.is_relative_to(root):
        raise ValueError("report output filename escapes the readiness directory")
    return destination


def _validated_peer_base(peer: str) -> str:
    """Return a normalized HTTPS origin after rejecting unsafe targets."""
    parsed = urlsplit(peer)
    if parsed.scheme != "https":
        raise ValueError("peer URL must use HTTPS")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("peer URL must contain a host and no embedded credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("peer URL must be an origin without a path, query, or fragment")
    try:
        port = parsed.port
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    except (OSError, ValueError) as error:
        raise ValueError("peer host could not be safely resolved") from error
    if not addresses:
        raise ValueError("peer host did not resolve")
    for _family, _kind, _protocol, _canonical, sockaddr in addresses:
        address = ipaddress.ip_address(sockaddr[0])
        if (
            address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise ValueError("peer host resolves to a blocked address")
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _configured_peer_base(settings: Config, selector: str) -> str:
    """Resolve a CLI selector only through the persisted linked-peer allowlist."""
    selected = selector.strip().casefold().rstrip("/")
    if not selected:
        raise ValueError("peer selector is empty")
    remotes = settings.get_remote_installations()
    if not isinstance(remotes, list):
        raise ValueError("linked installation configuration is invalid")
    for remote in remotes:
        if not isinstance(remote, dict):
            continue
        address_value = remote.get("address")
        if not isinstance(address_value, str) or not address_value.strip():
            continue
        candidates = {
            str(remote.get("name") or "").strip().casefold(),
            str(remote.get("uuid") or "").strip().casefold(),
            address_value.strip().casefold().rstrip("/"),
        }
        if selected not in candidates:
            continue
        configured_address = address_value.strip()
        if not configured_address.casefold().startswith("https://"):
            raise ValueError("linked peer address must use HTTPS")
        return _validated_peer_base(configured_address)
    raise ValueError("peer is not an existing linked installation")


@dataclass(frozen=True)
class CheckResult:
    """One stable readiness assertion with safe evidence and remediation."""

    check_id: str
    category: str
    status: str
    blocking: bool
    summary: str
    evidence: dict[str, object] = field(default_factory=dict)
    remediation: str = ""

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["evidence"] = _redact(payload["evidence"])
        return payload


@dataclass
class DoctorReport:
    """Versioned, expiring deployment-readiness report."""

    report_id: str
    generated_at: datetime
    expires_at: datetime
    role: str
    node: dict[str, object]
    overall_status: str
    strict: bool
    checks: list[CheckResult]

    @classmethod
    def create(
        cls,
        role: str,
        checks: list[CheckResult],
        *,
        node: dict[str, object] | None = None,
        now: datetime | None = None,
        strict: bool = False,
    ) -> DoctorReport:
        generated_at = now or _utc_now()
        has_failure = any(check.status == "fail" and check.blocking for check in checks)
        has_warning = any(check.status == "warn" for check in checks)
        if has_failure or (strict and has_warning):
            overall = "fail"
        elif has_warning:
            overall = "warn"
        else:
            overall = "pass"
        return cls(
            report_id=str(uuid.uuid4()),
            generated_at=generated_at,
            expires_at=generated_at + timedelta(hours=REPORT_TTL_HOURS),
            role=role,
            node=dict(node or {}),
            overall_status=overall,
            strict=strict,
            checks=list(checks),
        )

    @property
    def exit_code(self) -> int:
        return 1 if self.overall_status == "fail" else 0

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "report_id": self.report_id,
            "generated_at": self.generated_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "role": self.role,
            "node": _redact(self.node),
            "overall_status": self.overall_status,
            "strict": self.strict,
            "checks": [check.to_dict() for check in self.checks],
        }

    def save(self, userdata_path: str, output_name: str | None = None) -> Path:
        report_dir = Path(userdata_path) / "readiness"
        destination = _report_destination(
            report_dir,
            output_name,
            f"{self.generated_at:%Y%m%dT%H%M%SZ}-{self.role}.json",
        )
        payload = self.to_dict()
        _atomic_json_write(destination, payload)
        _atomic_json_write(report_dir / "latest.json", payload)
        return destination


def load_latest_report(userdata_path: str) -> dict[str, object] | None:
    path = Path(userdata_path) / "readiness" / "latest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) and payload.get("schema_version") == SCHEMA_VERSION else None


class DeploymentDoctor:
    """Collect machine-verifiable readiness evidence without changing settings."""

    def __init__(
        self,
        settings: Config,
        role: str,
        *,
        peers: list[str] | None = None,
        peer_token: str = "",
        strict: bool = False,
        capability_probe: Callable[[Config], dict[str, object]] | None = None,
    ) -> None:
        if role not in {"master", "worker"}:
            raise ValueError("role must be 'master' or 'worker'")
        self.settings = settings
        self.role = role
        self.peers = list(peers or [])
        self.peer_token = peer_token
        self.strict = strict
        self.capability_probe = capability_probe or (lambda current: WorkerCapabilities().snapshot(current))

    @staticmethod
    def _result(
        check_id: str,
        category: str,
        ok: bool,
        summary: str,
        *,
        blocking: bool = True,
        evidence: dict[str, object] | None = None,
        remediation: str = "",
        warning: bool = False,
    ) -> CheckResult:
        status = "pass" if ok else ("warn" if warning else "fail")
        return CheckResult(check_id, category, status, blocking, summary, evidence or {}, remediation)

    @staticmethod
    def _probe_directory(path: str, *, writable: bool) -> tuple[bool, str]:
        candidate = Path(path).expanduser().resolve()
        if not candidate.is_dir():
            return False, "directory does not exist"
        if not os.access(candidate, os.R_OK | os.X_OK):
            return False, "directory is not readable"
        if not writable:
            return True, "directory is readable"
        if not os.access(candidate, os.W_OK):
            return False, "directory is not writable"
        source = candidate / f".compresso-doctor-{uuid.uuid4().hex}.tmp"
        destination = source.with_suffix(".ready")
        try:
            with open(source, "wb") as output:
                output.write(b"compresso-doctor")
                output.flush()
                os.fsync(output.fileno())
            os.replace(source, destination)
            destination.unlink()
            return True, "write, fsync, and atomic rename succeeded"
        except OSError as error:
            for leftover in (source, destination):
                with contextlib.suppress(OSError):
                    leftover.unlink()
            return False, str(error)

    def _runtime_checks(self) -> list[CheckResult]:
        python_ok = tuple(sys.version_info[:2]) >= (3, 13)
        checks = [
            self._result(
                "runtime.python",
                "runtime",
                python_ok,
                f"Python {sys.version_info[0]}.{sys.version_info[1]}",
                evidence={"version": platform.python_version()},
                remediation="Install Python 3.13 or newer.",
            )
        ]
        for executable in ("ffmpeg", "ffprobe"):
            path = shutil.which(executable)
            checks.append(
                self._result(
                    f"runtime.{executable}",
                    "runtime",
                    bool(path),
                    f"{executable} is available" if path else f"{executable} is missing",
                    evidence={"path": path},
                    remediation="Install FFmpeg and ensure both ffmpeg and ffprobe are on PATH.",
                )
            )
        return checks

    def _path_checks(self) -> list[CheckResult]:
        checks = []
        paths = {
            "config": (self.settings.get_config_path(), True),
            "cache": (self.settings.get_cache_path(), True),
            "library": (self.settings.get_library_path(), self.role == "master"),
        }
        for name, (path, writable) in paths.items():
            if name == "library" and self.role == "worker":
                checks.append(CheckResult("path.library", "storage", "skipped", False, "Worker does not own the library"))
                continue
            ok, detail = self._probe_directory(path, writable=writable)
            checks.append(
                self._result(
                    f"path.{name}",
                    "storage",
                    ok,
                    f"{name} path: {detail}",
                    evidence={"path": os.path.abspath(path)},
                    remediation=f"Provide a {'writable' if writable else 'readable'} {name} directory.",
                )
            )
        cache = Path(self.settings.get_cache_path()).expanduser().resolve()
        config = Path(self.settings.get_config_path()).expanduser().resolve()
        library = Path(self.settings.get_library_path()).expanduser().resolve()
        separated = not any(
            cache == durable or cache.is_relative_to(durable) or durable.is_relative_to(cache) for durable in (config, library)
        )
        checks.append(
            self._result(
                "path.cache_separation",
                "storage",
                separated,
                "Cache is separate from config and library" if separated else "Cache overlaps a durable path",
                remediation="Place the cache on a separate fast writable path.",
            )
        )
        try:
            disk = shutil.disk_usage(cache)
            reserve = int(float(self.settings.get_minimum_free_space_gb()) * 1024**3)
            checks.append(
                self._result(
                    "path.cache_reserve",
                    "storage",
                    int(disk.free) >= reserve,
                    "Cache reserve is available" if int(disk.free) >= reserve else "Cache reserve is exhausted",
                    evidence={"free_bytes": int(disk.free), "reserve_bytes": reserve},
                    remediation="Free cache space or increase cache capacity before processing.",
                )
            )
        except OSError as error:
            checks.append(self._result("path.cache_reserve", "storage", False, str(error)))
        return checks

    def _database_check(self) -> CheckResult:
        path = Path(self.settings.get_config_path()) / "compresso.db"
        if not path.exists():
            return CheckResult(
                "database.integrity",
                "database",
                "warn",
                False,
                "Database does not exist yet",
                {"path": str(path)},
                "Start Compresso once before the strict deployment gate.",
            )
        try:
            uri = f"file:{path.resolve().as_posix()}?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=5) as connection:
                result = connection.execute("PRAGMA quick_check").fetchone()
            ok = bool(result and result[0] == "ok")
            return self._result(
                "database.integrity",
                "database",
                ok,
                "SQLite quick_check passed" if ok else "SQLite quick_check failed",
                evidence={"result": result[0] if result else None},
                remediation="Restore a verified backup before starting workers.",
            )
        except sqlite3.Error as error:
            return self._result(
                "database.integrity",
                "database",
                False,
                "SQLite integrity check could not run",
                evidence={"error": str(error)},
                remediation="Stop Compresso and inspect or restore the database.",
            )

    def _security_checks(self) -> list[CheckResult]:
        auth_enabled = bool(self.settings.get_api_auth_enforced() and self.settings.get_api_auth_token())
        csrf_enabled = bool(self.settings.get_csrf_protection_enforced())
        address = str(self.settings.get_ui_address() or "")
        exposed = address in {".".join(("0", "0", "0", "0")), "::", "*"}
        tls = bool(self.settings.get_ssl_enabled())
        checks = [
            self._result(
                "security.request_boundary",
                "security",
                auth_enabled and csrf_enabled,
                "API authentication and CSRF protection are enabled",
                evidence={"auth_enabled": auth_enabled, "csrf_enabled": csrf_enabled},
                remediation="Enable API authentication and CSRF protection before LAN access.",
            ),
            self._result(
                "security.network_exposure",
                "security",
                not exposed or tls,
                (
                    "Listener is restricted or protected by TLS"
                    if not exposed or tls
                    else "Listener accepts all interfaces without TLS"
                ),
                blocking=False,
                warning=True,
                evidence={"address": address, "tls": tls},
                remediation="Use localhost, a trusted LAN/VPN, or a TLS-authenticated reverse proxy.",
            ),
        ]
        trusted = {item.strip() for item in os.environ.get("COMPRESSO_TRUSTED_PLUGIN_IDS", "").split(",") if item.strip()}
        untrusted = []
        plugin_root = Path(self.settings.get_plugins_path())
        if plugin_root.is_dir():
            for info_path in plugin_root.glob("*/info.json"):
                try:
                    info = json.loads(info_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    untrusted.append(info_path.parent.name)
                    continue
                if not isinstance(info, dict):
                    untrusted.append(info_path.parent.name)
                    continue
                plugin_id = str(info.get("id") or info_path.parent.name)
                if not info.get("bundled") and plugin_id not in trusted:
                    untrusted.append(plugin_id)
        checks.append(
            self._result(
                "security.plugins",
                "security",
                not untrusted,
                "No untrusted external plugins are active" if not untrusted else "Untrusted external plugins were found",
                evidence={"untrusted_plugin_ids": sorted(untrusted)},
                remediation="Remove external plugins or explicitly allowlist reviewed plugin IDs.",
            )
        )
        return checks

    def _role_checks(self, capabilities: dict[str, object]) -> list[CheckResult]:
        scanner_enabled = bool(self.settings.get_enable_library_scanner())
        safe_defaults = bool(self.settings.get_large_library_safe_defaults())
        checks = [
            self._result(
                "settings.safe_defaults",
                "configuration",
                safe_defaults,
                "Large-library safe defaults are enabled",
                remediation="Enable large_library_safe_defaults.",
            )
        ]
        if self.role == "master":
            checks.append(
                self._result(
                    "role.master_scanner_enabled",
                    "role",
                    scanner_enabled,
                    "Master owns scanning" if scanner_enabled else "Master scanning is disabled",
                    remediation="Enable scanning only on the authoritative master.",
                )
            )
        else:
            checks.append(
                self._result(
                    "role.worker_scanner_disabled",
                    "role",
                    not scanner_enabled,
                    "Worker scanning is disabled" if not scanner_enabled else "Worker scanning is enabled",
                    remediation="Disable library scanning and inotify on every remote worker.",
                )
            )
        raw_encoders = capabilities.get("video_encoders")
        encoders = (
            set(raw_encoders)
            if isinstance(raw_encoders, list) and all(isinstance(item, str) for item in raw_encoders)
            else set()
        )
        if self.role == "worker" and platform.system() == "Darwin" and platform.machine() == "arm64":
            required = {"h264_videotoolbox", "hevc_videotoolbox"}
            checks.append(
                self._result(
                    "role.m4_videotoolbox",
                    "capability",
                    required.issubset(encoders),
                    (
                        "M4 VideoToolbox encoders are available"
                        if required.issubset(encoders)
                        else "M4 VideoToolbox encoders are incomplete"
                    ),
                    evidence={"required": sorted(required), "available": sorted(encoders)},
                    remediation="Install an FFmpeg build with h264_videotoolbox and hevc_videotoolbox.",
                )
            )
            checks.append(self._mac_power_check())
        return checks

    @staticmethod
    def _mac_power_check() -> CheckResult:
        power_preferences = Path("/Library/Preferences/SystemConfiguration/com.apple.PowerManagement.plist")
        try:
            with open(power_preferences, "rb") as source:
                preferences = plistlib.load(source)
            custom = preferences.get("Custom Profile", {}) if isinstance(preferences, dict) else {}
            ac_profile = custom.get("AC Power", {}) if isinstance(custom, dict) else {}
            sleep_disabled = int(ac_profile.get("System Sleep Timer", -1)) == 0
        except (OSError, plistlib.InvalidFileException, TypeError, ValueError):
            sleep_disabled = False
        return DeploymentDoctor._result(
            "role.m4_sleep",
            "power",
            sleep_disabled,
            "macOS system sleep is disabled" if sleep_disabled else "macOS sleep settings need review",
            blocking=False,
            warning=True,
            evidence={"power_preferences_readable": power_preferences.is_file()},
            remediation="Run the worker under caffeinate or configure AC-power sleep to 0.",
        )

    def _peer_checks(self) -> list[CheckResult]:
        if not self.peers:
            return [
                CheckResult(
                    "peer.optional",
                    "network",
                    "warn",
                    False,
                    "No linked peer supplied",
                    {},
                    "Pass --peer for the final distributed strict gate.",
                )
            ]
        checks = []
        local_version = metadata.read_version_string("short")
        local_compatibility = ".".join(local_version.split(".")[:2])
        for index, peer in enumerate(self.peers):
            try:
                peer_base = _configured_peer_base(self.settings, peer)
            except ValueError as error:
                checks.append(
                    self._result(
                        f"peer.{index}.target",
                        "network",
                        False,
                        f"Peer {index + 1} target is unsafe",
                        evidence={"peer": peer, "error": str(error)},
                        remediation="Select an existing linked installation by name or UUID on the trusted LAN/VPN.",
                    )
                )
                continue
            headers = {"Accept": "application/json"}
            if self.peer_token:
                headers[API_AUTH_HEADER_NAME] = self.peer_token
            payloads = {}
            current_endpoint = "readiness"
            try:
                for name, path in PEER_API_PATHS.items():
                    current_endpoint = name
                    response = requests.get(
                        peer_base + path,
                        headers=headers,
                        timeout=5,
                        allow_redirects=False,
                    )
                    response.raise_for_status()
                    payloads[name] = response.json()
                readiness = payloads["readiness"]
                ready = bool(isinstance(readiness, dict) and readiness.get("ready", readiness.get("success", False)))
                checks.append(
                    self._result(
                        f"peer.{index}.readiness",
                        "network",
                        ready,
                        f"Peer {index + 1} is ready" if ready else f"Peer {index + 1} is not ready",
                        evidence={"peer": peer},
                        remediation="Start the peer and resolve its readiness errors.",
                    )
                )
                version_payload = payloads["version"]
                peer_version = str(version_payload.get("version") or "") if isinstance(version_payload, dict) else ""
                peer_compatibility = ".".join(peer_version.split(".")[:2])
                compatible = bool(peer_compatibility and peer_compatibility == local_compatibility)
                checks.append(
                    self._result(
                        f"peer.{index}.version",
                        "network",
                        compatible,
                        f"Peer {index + 1} version is compatible" if compatible else f"Peer {index + 1} version differs",
                        evidence={"peer": peer, "local_version": local_version, "peer_version": peer_version},
                        remediation="Install the same Compresso major/minor release on master and worker.",
                    )
                )
                peer_capabilities = payloads["capabilities"]
                encoders = peer_capabilities.get("video_encoders") if isinstance(peer_capabilities, dict) else None
                checks.append(
                    self._result(
                        f"peer.{index}.capabilities",
                        "network",
                        isinstance(encoders, list) and bool(encoders),
                        (
                            f"Peer {index + 1} reported encoder capabilities"
                            if isinstance(encoders, list) and bool(encoders)
                            else f"Peer {index + 1} did not report usable encoders"
                        ),
                        evidence={"peer": peer, "video_encoders": encoders or []},
                        remediation="Verify FFmpeg encoder discovery on the peer.",
                    )
                )
            except (OSError, ValueError, requests.RequestException) as error:
                checks.append(
                    self._result(
                        f"peer.{index}.{current_endpoint}",
                        "network",
                        False,
                        f"Peer {index + 1} {current_endpoint} endpoint failed",
                        evidence={"peer": peer, "endpoint": current_endpoint, "error": str(error)},
                        remediation="Verify the trusted LAN/VPN address and peer service.",
                    )
                )
        return checks

    def run(self) -> DoctorReport:
        try:
            capabilities = self.capability_probe(self.settings)
            if not isinstance(capabilities, dict):
                capabilities = {}
            capability_check = self._result(
                "capability.snapshot",
                "capability",
                bool(capabilities),
                "Capability snapshot collected" if capabilities else "Capability snapshot is unavailable",
                remediation="Verify FFmpeg and system telemetry access.",
            )
        except Exception as error:
            capabilities = {}
            capability_check = self._result(
                "capability.snapshot",
                "capability",
                False,
                "Capability snapshot failed",
                evidence={"error": str(error)},
                remediation="Verify FFmpeg and system telemetry access.",
            )
        checks = [
            *self._runtime_checks(),
            *self._path_checks(),
            self._database_check(),
            *self._security_checks(),
            capability_check,
            *self._role_checks(capabilities),
            *self._peer_checks(),
        ]
        node = {
            "role": self.role,
            "platform": {"system": platform.system(), "machine": platform.machine()},
            "compresso_version": metadata.read_version_string("short"),
            "installation_name": getattr(self.settings, "get_installation_name", lambda: "")(),
            "capabilities": capabilities,
        }
        return DoctorReport.create(self.role, checks, node=node, strict=self.strict)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="compresso doctor", description=__doc__)
    parser.add_argument("--role", choices=("master", "worker"), required=True)
    parser.add_argument("--peer", action="append", default=[])
    parser.add_argument(
        "--peer-token-env",
        default="COMPRESSO_DOCTOR_PEER_TOKEN",
        help="Environment variable containing the peer API token.",
    )
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output", help="JSON filename stored under the user-data readiness directory.")
    parser.add_argument("--config-path")
    args = parser.parse_args(argv)
    settings = Config(config_path=args.config_path) if args.config_path else Config()
    peer_token = os.environ.get(args.peer_token_env, "")
    report = DeploymentDoctor(
        settings,
        args.role,
        peers=args.peer,
        peer_token=peer_token,
        strict=args.strict,
    ).run()
    destination = report.save(settings.get_userdata_path(), args.output)
    sys.stdout.write(json.dumps({**report.to_dict(), "saved_to": str(destination)}, indent=2, sort_keys=True) + "\n")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
