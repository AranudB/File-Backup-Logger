"""
engine.py
Core backup engine: copies or zips a source folder to a versioned destination.

Supports
--------
* Plain copy  – shutil.copytree() with a per-file progress hook
* ZIP backup  – zipfile.ZipFile with ZIP_DEFLATED compression
* Graceful abort via threading.Event
* Returns a rich stats dict for logging and GUI display
"""
from __future__ import annotations
import os
import shutil
import threading
import time
import zipfile
from dataclasses import dataclass, field
from typing import Callable

from .config    import BackupConfig
from .logger    import BackupLogger
from .versioner import BackupVersioner

ProgressCallback = Callable[[int, int, str], None]  # (current, total, filename)


@dataclass
class BackupStats:
    """Result of a single backup run."""
    backup_name:    str   = ""
    backup_path:    str   = ""
    mode:           str   = "plain"      # "plain" | "zip"
    files_copied:   int   = 0
    total_size_bytes: int = 0
    duration_seconds: float = 0.0
    errors:         list[str] = field(default_factory=list)
    status:         str   = "pending"   # "success" | "partial" | "failed" | "stopped"

    @property
    def size_mb(self) -> float:
        return self.total_size_bytes / (1024 * 1024)


class BackupEngine:
    """
    Orchestrates a single backup: versioning → copy/zip → log → prune.

    Designed to run in a background thread; ``stop()`` can be called from
    any thread to request a graceful abort.
    """

    def __init__(
        self,
        config:    BackupConfig    | None = None,
        logger:    BackupLogger    | None = None,
        versioner: BackupVersioner | None = None,
    ) -> None:
        self.config    = config    or BackupConfig()
        self.logger    = logger    or BackupLogger()
        # Versioner is created lazily with the real destination when run() is called
        self._versioner_factory = versioner
        self._stop_event = threading.Event()
        self._lock       = threading.Lock()
        self._running    = False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def stop(self) -> None:
        """Signal the engine to abort after the current file."""
        self._stop_event.set()

    def run(
        self,
        source:      str,
        destination: str,
        use_zip:     bool | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> BackupStats:
        """
        Perform a backup of *source* into a versioned subfolder of *destination*.

        Parameters
        ----------
        source:
            Folder to back up.
        destination:
            Root folder where backups are stored.
        use_zip:
            If *None*, the value from ``config.use_zip`` is used.
        on_progress:
            Optional ``fn(current, total, filename)`` called for each file.

        Returns
        -------
        :class:`BackupStats`
        """
        stats = BackupStats()
        stats.mode = "zip" if (use_zip if use_zip is not None else self.config.get("use_zip")) else "plain"
        self._stop_event.clear()

        with self._lock:
            self._running = True

        try:
            # ── validation ──────────────────────────────────────────────
            if not os.path.isdir(source):
                raise NotADirectoryError(f"Source '{source}' is not a directory.")
            os.makedirs(destination, exist_ok=True)

            # ── versioning ──────────────────────────────────────────────
            versioner = self._versioner_factory or BackupVersioner(
                destination,
                auto_detect=self.config.get("auto_detect_version"),
            )
            versioner.destination = destination
            backup_name = versioner.next_name(source)
            stats.backup_name = backup_name

            self.logger.log_start(source, destination, stats.mode)

            # ── count files ─────────────────────────────────────────────
            total_files = self._count_files(source)

            # ── do the copy ─────────────────────────────────────────────
            start = time.monotonic()
            if stats.mode == "zip":
                dest_path = os.path.join(destination, backup_name + ".zip")
                stats = self._zip_backup(source, dest_path, stats, total_files, on_progress)
            else:
                dest_path = os.path.join(destination, backup_name)
                stats = self._plain_backup(source, dest_path, stats, total_files, on_progress)

            stats.backup_path    = dest_path
            stats.duration_seconds = time.monotonic() - start

            if self._stop_event.is_set():
                stats.status = "stopped"
            elif stats.errors:
                stats.status = "partial"
            else:
                stats.status = "success"

            # ── log result ──────────────────────────────────────────────
            if stats.status in ("success", "partial"):
                self.logger.log_success(
                    name=backup_name,
                    source=source,
                    dest=dest_path,
                    mode=stats.mode,
                    files=stats.files_copied,
                    size_mb=stats.size_mb,
                    duration=stats.duration_seconds,
                )
            if stats.errors:
                for err in stats.errors:
                    self.logger.log_warning(err)

            # ── prune old backups ────────────────────────────────────────
            max_keep = self.config.get("max_versions", 10)
            removed  = versioner.prune_old(max_keep)
            if removed:
                self.logger.log_prune(removed)

        except (NotADirectoryError, PermissionError, OSError) as exc:
            stats.status = "failed"
            self.logger.log_failure(source, str(exc))
            stats.errors.append(str(exc))
        finally:
            with self._lock:
                self._running = False

        return stats

    # ------------------------------------------------------------------ #
    # Private: plain copy
    # ------------------------------------------------------------------ #

    def _plain_backup(
        self,
        source:      str,
        dest_path:   str,
        stats:       BackupStats,
        total:       int,
        on_progress: ProgressCallback | None,
    ) -> BackupStats:
        copied   = [0]
        size_acc = [0]

        def copy_fn(src: str, dst: str) -> None:
            if self._stop_event.is_set():
                raise InterruptedError("Backup stopped by user.")
            try:
                shutil.copy2(src, dst)
                copied[0]   += 1
                size_acc[0] += os.path.getsize(dst)
                if on_progress:
                    on_progress(copied[0], total, os.path.basename(src))
            except (PermissionError, OSError) as exc:
                stats.errors.append(f"Could not copy '{src}': {exc}")

        try:
            shutil.copytree(source, dest_path, copy_function=copy_fn)
        except InterruptedError:
            pass  # stopped cleanly
        except Exception as exc:
            stats.errors.append(str(exc))

        stats.files_copied    = copied[0]
        stats.total_size_bytes = size_acc[0]
        return stats

    # ------------------------------------------------------------------ #
    # Private: ZIP backup
    # ------------------------------------------------------------------ #

    def _zip_backup(
        self,
        source:      str,
        dest_path:   str,
        stats:       BackupStats,
        total:       int,
        on_progress: ProgressCallback | None,
    ) -> BackupStats:
        copied   = 0
        size_acc = 0
        src_parent = os.path.dirname(source)

        try:
            with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _dirs, files in os.walk(source):
                    for filename in files:
                        if self._stop_event.is_set():
                            break
                        file_path = os.path.join(root, filename)
                        arcname   = os.path.relpath(file_path, src_parent)
                        try:
                            zf.write(file_path, arcname)
                            copied   += 1
                            size_acc += os.path.getsize(file_path)
                            if on_progress:
                                on_progress(copied, total, filename)
                        except (PermissionError, OSError) as exc:
                            stats.errors.append(f"Could not zip '{file_path}': {exc}")
        except Exception as exc:
            stats.errors.append(str(exc))

        stats.files_copied     = copied
        stats.total_size_bytes = size_acc
        return stats

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _count_files(path: str) -> int:
        total = 0
        for _, _, files in os.walk(path):
            total += len(files)
        return total