"""
config.py
Manages user preferences via a JSON config file persisted to disk.
"""
from __future__ import annotations
import json
import os
from typing import Any


class BackupConfig:
    """
    Loads and saves user preferences to a JSON file.

    Any key not present in the file falls back to DEFAULTS,
    so the config is always forward-compatible.
    """

    DEFAULTS: dict[str, Any] = {
        "source_folder":       "",
        "destination_folder":  "",
        "use_zip":             False,
        "max_versions":        10,        # 0 = unlimited
        "auto_detect_version": True,
        "log_level":           "INFO",
    }

    def __init__(self, config_path: str | None = None) -> None:
        """
        Args:
            config_path: Path to the JSON config file.
                         Defaults to ``~/.file_backup_logger/config.json``.
        """
        if config_path is None:
            config_path = os.path.join(
                os.path.expanduser("~"), ".file_backup_logger", "config.json"
            )
        self._path = config_path
        self._data: dict[str, Any] = dict(self.DEFAULTS)
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._load()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for *key*, falling back to DEFAULTS then *default*."""
        return self._data.get(key, self.DEFAULTS.get(key, default))

    def set(self, key: str, value: Any) -> None:
        """Update *key* and persist immediately."""
        self._data[key] = value
        self._save()

    def update(self, mapping: dict[str, Any]) -> None:
        """Bulk-update multiple keys and persist once."""
        self._data.update(mapping)
        self._save()

    def reset(self) -> None:
        """Restore all keys to their default values."""
        self._data = dict(self.DEFAULTS)
        self._save()

    @property
    def path(self) -> str:
        return self._path

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                stored = json.load(fh)
            # Merge: stored values win, but missing keys get defaults
            self._data = {**self.DEFAULTS, **stored}
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[BackupConfig] Warning – could not load config: {exc}")

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
        except OSError as exc:
            print(f"[BackupConfig] Warning – could not save config: {exc}")