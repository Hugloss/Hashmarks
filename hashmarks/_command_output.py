from __future__ import annotations

import logging
import sys
from typing import TextIO
from weakref import WeakSet

_configured_loggers: WeakSet[logging.Logger] = WeakSet()


class _CurrentStreamHandler(logging.Handler):
    def __init__(
        self, stream_name: str, *, minimum_level: int = logging.NOTSET
    ) -> None:
        super().__init__(minimum_level)
        self._stream_name = stream_name

    def emit(self, record: logging.LogRecord) -> None:
        stream = getattr(sys, self._stream_name)
        stream.write(self.format(record))
        stream.write(getattr(record, "command_end", "\n"))
        if getattr(record, "command_flush", False):
            stream.flush()


class _MaximumLevelFilter(logging.Filter):
    def __init__(self, maximum_level: int) -> None:
        super().__init__()
        self._maximum_level = maximum_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self._maximum_level


def _configure(logger: logging.Logger) -> None:
    if logger in _configured_loggers:
        return
    stdout = _CurrentStreamHandler("stdout")
    stdout.addFilter(_MaximumLevelFilter(logging.INFO))
    logger.addHandler(stdout)
    logger.addHandler(_CurrentStreamHandler("stderr", minimum_level=logging.WARNING))
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _configured_loggers.add(logger)


def log_command_output(
    logger: logging.Logger,
    *values: object,
    sep: str = " ",
    end: str = "\n",
    file: TextIO | None = None,
    flush: bool = False,
) -> None:
    _configure(logger)
    level = logging.ERROR if file in {sys.stderr, sys.__stderr__} else logging.INFO
    logger.log(
        level,
        "%s",
        sep.join(str(value) for value in values),
        extra={"command_end": end, "command_flush": flush},
    )
