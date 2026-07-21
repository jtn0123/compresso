"""Shared runtime narrowing helpers for loosely-typed boundary data.

Two families with deliberately different semantics:

- ``strict_*`` helpers accept only the exact target type (``bool`` is never
  accepted as an int/float) and return the default for anything else. Use
  these where a mismatched type indicates a programming error and silent
  coercion would hide it.
- ``coerce_*`` helpers additionally convert compatible scalars (numeric
  strings, floats, bytes) and return the default only when conversion fails.
  Use these at wire, config, and database boundaries where stringly-typed
  values are legal inputs.

The ``*_or_none`` variants return ``None`` instead of a default so callers
can distinguish "absent/invalid" from a legitimate zero value and report it.
"""

from collections.abc import Mapping
from typing import cast

_COERCIBLE_SCALARS = (bool, int, float, str, bytes, bytearray)


def strict_str(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def strict_int(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def strict_int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def strict_bool(value: object, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def strict_float(value: object, default: float = 0.0) -> float:
    """Accept real numbers (int or float, never bool) and return them as float."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def coerce_int(value: object, default: int = 0) -> int:
    result = coerce_int_or_none(value)
    return default if result is None else result


def coerce_int_or_none(value: object) -> int | None:
    if not isinstance(value, _COERCIBLE_SCALARS):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def coerce_float(value: object, default: float = 0.0) -> float:
    result = coerce_float_or_none(value)
    return default if result is None else result


def coerce_float_or_none(value: object) -> float | None:
    if not isinstance(value, _COERCIBLE_SCALARS):
        return None
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def string_keyed_dict(value: object) -> dict[str, object]:
    """Return the value only if it is a dict keyed entirely by strings."""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return {}
    return cast("dict[str, object]", value)


def mapping_value(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def mapping_list(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def int_list(value: object, *, coerce: bool = False) -> list[int]:
    """Narrow a list to its integer members; with ``coerce`` numeric strings count."""
    if not isinstance(value, list):
        return []
    if not coerce:
        return [item for item in value if isinstance(item, int) and not isinstance(item, bool)]
    return [item for item in (coerce_int_or_none(entry) for entry in value) if item is not None]
