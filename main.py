"""
main.py
Entry point for the File Backup Logger.

Usage
-----
    python main.py           # launch GUI (default)
"""
from __future__ import annotations
import tkinter as tk

from backup.gui import BackupGUI


def main() -> None:
    root = tk.Tk()
    _app = BackupGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()