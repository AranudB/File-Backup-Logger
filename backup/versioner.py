"""
versioner.py
Generates versioned backup names and manages backup retention.

Naming scheme
-------------
  backup_YYYY-MM-DD_v<version>   when a version is detected in the source
  backup_YYYY-MM-DD_v<N>         incrementing counter otherwise

Examples
--------
  backup_2025-05-01_v2.7.3       (from package.json / pyproject.toml / …)
  backup_2025-05-01_v1           (no detectable version, first backup today)
  backup_2025-05-01_v2           (second backup on the same day)
"""
from __future__ import annotations
import os
import re
import shutil
from datetime import datetime


class BackupVersioner:
    """
    Handles version detection and backup-name generation.

    Version detection is attempted by scanning common project-metadata files
    in the source directory (``package.json``, ``pyproject.toml``, etc.).
    When no version can be found, a daily auto-increment counter is used.
    """

    DATE_FORMAT = "%Y-%m-%d"
    PREFIX      = "backup_"

    # (filename, regex) – first capture group must be the version string
    _DETECTORS: list[tuple[str, str]] = [
        ("package.json",   r'"version"\s*:\s*"([^"]+)"'),
        ("pyproject.toml", r'version\s*=\s*["\']([^"\']+)["\']'),
        ("setup.cfg",      r'(?m)^version\s*=\s*(.+)$'),
        ("setup.py",       r'version\s*=\s*["\']([^"\']+)["\']'),
        ("CMakeLists.txt", r'VERSION\s+([\d]+\.[\d]+\.[\d]+)'),
        ("VERSION",        r'^(.+)$'),
        ("version.txt",    r'^(.+)$'),
    ]

    def __init__(self, destination: str, auto_detect: bool = True) -> None:
        """
        Args:
            destination:  Root folder where backup copies are stored.
            auto_detect:  Whether to probe the source for a version string.
        """
        self.destination = destination
        self.auto_detect = auto_detect

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def next_name(self, source: str) -> str:
        """
        Return the next available backup folder/zip name (without extension).

        The name is unique inside *destination*.
        """
        date_str = datetime.now().strftime(self.DATE_FORMAT)
        version  = self.detect_version(source) if self.auto_detect else None

        if version:
            base = f"{self.PREFIX}{date_str}_v{version}"
            return self._ensure_unique(base)

        # Auto-increment counter (per day)
        counter = 1
        while True:
            name = f"{self.PREFIX}{date_str}_v{counter}"
            if not self._exists(name):
                return name
            counter += 1

    def detect_version(self, source: str) -> str | None:
        """
        Probe *source* for a recognisable version string.
        Returns the version string or *None*.
        """
        for filename, pattern in self._DETECTORS:
            filepath = os.path.join(source, filename)
            if not os.path.isfile(filepath):
                continue
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read(4096)
                match = re.search(pattern, content)
                if match:
                    version = match.group(1).strip()
                    # Sanitise: replace spaces/slashes
                    version = re.sub(r'[\s/\\]', '-', version)
                    return version
            except OSError:
                continue
        return None

    def list_backups(self) -> list[str]:
        """
        Return a sorted list of backup names (oldest first) in *destination*.
        Both plain folders and ``.zip`` files are included.
        """
        if not os.path.isdir(self.destination):
            return []
        names = []
        for entry in os.scandir(self.destination):
            name = entry.name
            if name.endswith(".zip"):
                name = name[:-4]
            if name.startswith(self.PREFIX):
                names.append(name)
        return sorted(set(names))

    def prune_old(self, max_keep: int) -> list[str]:
        """
        Delete the oldest backups so that at most *max_keep* remain.

        Args:
            max_keep: Maximum backups to retain; 0 means unlimited.

        Returns:
            List of names that were deleted.
        """
        if max_keep <= 0:
            return []
        backups = self.list_backups()
        to_delete = backups[: max(0, len(backups) - max_keep)]
        deleted = []
        for name in to_delete:
            # Try plain folder
            path = os.path.join(self.destination, name)
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
                deleted.append(name)
            # Try zip
            zip_path = path + ".zip"
            if os.path.isfile(zip_path):
                os.remove(zip_path)
                if name not in deleted:
                    deleted.append(name)
        return deleted

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _exists(self, name: str) -> bool:
        """True if *name* (as folder OR zip) exists in destination."""
        base = os.path.join(self.destination, name)
        return os.path.exists(base) or os.path.exists(base + ".zip")

    def _ensure_unique(self, base: str) -> str:
        """Append ``_1``, ``_2``… until the name is free."""
        if not self._exists(base):
            return base
        counter = 1
        while True:
            candidate = f"{base}_{counter}"
            if not self._exists(candidate):
                return candidate
            counter += 1