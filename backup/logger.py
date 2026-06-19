"""
logger.py
Structured logging for the File Backup Logger.

Every entry is written to a persistent ``.log`` file and forwarded to
registered callbacks (e.g. the tkinter GUI log panel).

Log format
----------
  YYYY-MM-DD HH:MM:SS | LEVEL    | MESSAGE
  ...                  | BACKUP   | name=<name> source=<src> dest=<dst>
                                    mode=<zip|plain> files=<N>
                                    size=<X MB> duration=<Y s> status=<OK|FAIL>
"""
from __future__ import annotations
import logging
import os
from datetime import datetime
from typing import Callable

LogCallback = Callable[[str, str], None]   # (level, message)


class BackupLogger:
    """
    Wraps Python's :mod:`logging` with structured backup-specific helpers
    and an optional list of live callbacks (for the GUI).
    """

    _FMT    = "%(asctime)s | %(levelname)-8s | %(message)s"
    _DATEFMT = "%Y-%m-%d %H:%M:%S"

    def __init__(
        self,
        log_dir:   str = ".",
        log_level: int = logging.INFO,
    ) -> None:
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = os.path.join(log_dir, f"backup_{ts}.log")

        self._callbacks: list[LogCallback] = []

        self._log = logging.getLogger(f"BackupLogger.{id(self)}")
        self._log.setLevel(log_level)
        self._log.propagate = False
        self._log.handlers.clear()

        fmt = logging.Formatter(self._FMT, datefmt=self._DATEFMT)

        fh = logging.FileHandler(self.log_path, encoding="utf-8")
        fh.setFormatter(fmt)
        self._log.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        self._log.addHandler(ch)

    # ------------------------------------------------------------------ #
    # Callback management
    # ------------------------------------------------------------------ #

    def add_callback(self, cb: LogCallback) -> None:
        self._callbacks.append(cb)

    def remove_callback(self, cb: LogCallback) -> None:
        self._callbacks = [c for c in self._callbacks if c is not cb]

    # ------------------------------------------------------------------ #
    # Semantic helpers
    # ------------------------------------------------------------------ #

    def log_start(self, source: str, destination: str, mode: str) -> None:
        self._emit("INFO",
            f"START  source={source!r}  dest={destination!r}  mode={mode}")

    def log_success(
        self,
        name:     str,
        source:   str,
        dest:     str,
        mode:     str,
        files:    int,
        size_mb:  float,
        duration: float,
    ) -> None:
        self._emit("INFO",
            f"BACKUP name={name}  source={source!r}  dest={dest!r}  "
            f"mode={mode}  files={files}  size={size_mb:.2f}MB  "
            f"duration={duration:.1f}s  status=OK")

    def log_failure(self, source: str, reason: str) -> None:
        self._emit("ERROR", f"BACKUP source={source!r}  status=FAIL  reason={reason}")

    def log_prune(self, removed: list[str]) -> None:
        if removed:
            self._emit("INFO", f"PRUNE  removed={removed}")

    def log_error(self, message: str) -> None:
        self._emit("ERROR", message)

    def log_warning(self, message: str) -> None:
        self._emit("WARNING", message)

    def log_info(self, message: str) -> None:
        self._emit("INFO", message)

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _emit(self, level: str, message: str) -> None:
        getattr(self._log, level.lower())(message)
        for cb in self._callbacks:
            try:
                cb(level, message)
            except Exception:
                pass