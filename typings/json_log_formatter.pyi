import logging


class JSONFormatter(logging.Formatter):
    def json_record(
        self,
        message: str,
        extra: dict[str, object],
        record: logging.LogRecord,
    ) -> dict[str, object]: ...

    def format(self, record: logging.LogRecord) -> str: ...
