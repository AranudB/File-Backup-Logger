"""
File Backup Logger – backup package.

Core exports (no GUI dependency):
  BackupConfig    – JSON preferences manager
  BackupVersioner – versioned naming + retention pruning
  BackupLogger    – structured .log file + callbacks
  BackupEngine    – copy / zip / stats engine
  BackupStats     – result dataclass

GUI import (requires tkinter):
  from backup.gui import BackupGUI
"""
from .config    import BackupConfig
from .versioner import BackupVersioner
from .logger    import BackupLogger
from .engine    import BackupEngine, BackupStats

__all__ = [
    "BackupConfig",
    "BackupVersioner",
    "BackupLogger",
    "BackupEngine",
    "BackupStats",
]