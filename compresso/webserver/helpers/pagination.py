"""Shared parsing for paginated table and API requests."""

from collections.abc import Mapping
from dataclasses import dataclass

from compresso.libs import narrowing


@dataclass(frozen=True, slots=True)
class PageParams:
    """Normalized pagination fields used by task and history helpers."""

    start: int
    length: int
    search_value: str
    library_ids: tuple[int, ...]
    draw: int | None = None


def parse_page_params(params: Mapping[str, object], *, data_tables: bool = False) -> PageParams:
    """Parse stringly wire values once before they reach query code."""

    if data_tables:
        search = params.get("search")
        search_value = narrowing.strict_str(search.get("value")) if isinstance(search, Mapping) else ""
        draw = narrowing.coerce_int(params.get("draw"))
    else:
        search_value = narrowing.strict_str(params.get("search_value"))
        draw = None

    return PageParams(
        start=narrowing.coerce_int(params.get("start")),
        length=narrowing.coerce_int(params.get("length")),
        search_value=search_value,
        library_ids=tuple(narrowing.int_list(params.get("library_ids"), coerce=True)),
        draw=draw,
    )
