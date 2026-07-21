"""Typed adapters for the small untyped surface left by Peewee's stubs."""

from collections.abc import Callable, Iterable, Iterator
from typing import Protocol, cast

from peewee import Database
from playhouse.shortcuts import model_to_dict
from playhouse.sqliteq import SqliteQueueDatabase


class ExecutableQuery(Protocol):
    def execute(self) -> object: ...


class CountedRows(Protocol):
    """A Peewee ``.dicts()`` result: iterable string-keyed rows plus SQL ``count()``."""

    def __iter__(self) -> Iterator[dict[str, object]]: ...

    def count(self) -> int: ...


class IterableQuery[T](Protocol):
    def iterator(self) -> Iterable[T]: ...


def execute_count(query: object) -> int:
    """Execute a Peewee write query and require its affected-row result."""
    result = cast("ExecutableQuery", query).execute()
    if not isinstance(result, int):
        raise TypeError("Peewee write query did not return an integer row count")
    return result


def execute_write(query: object) -> None:
    """Execute a Peewee write query whose return value is intentionally unused."""
    cast("ExecutableQuery", query).execute()


def iterate_query[T](query: object, item_type: type[T]) -> Iterable[T]:
    """Iterate a Peewee select while making the expected model type explicit."""
    del item_type
    return cast("IterableQuery[T]", query).iterator()


def model_as_dict(model: object, *, backrefs: bool = False) -> dict[str, object]:
    serializer = cast("Callable[..., dict[str, object]]", model_to_dict)
    return serializer(model, backrefs=backrefs)


def create_sqlite_queue_database(
    path: str,
    *,
    use_gevent: bool,
    autostart: bool,
    queue_max_size: int | None,
    results_timeout: float,
    pragmas: tuple[tuple[str, object], ...],
) -> Database:
    factory = cast("Callable[..., Database]", SqliteQueueDatabase)
    return factory(
        path,
        use_gevent=use_gevent,
        autostart=autostart,
        queue_max_size=queue_max_size,
        results_timeout=results_timeout,
        pragmas=pragmas,
    )
