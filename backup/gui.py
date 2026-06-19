"""
gui.py
tkinter front-end for the File Backup Logger.

Layout
------
  ┌─────────────────── Header ───────────────────────┐
  │          File Backup Logger                      │
  ├──── Folders ─────────────────────────────────────┤
  │  Source      [path entry]  [Browse]              │
  │  Destination [path entry]  [Browse]              │
  ├──── Options ─────────────────────────────────────┤
  │  [◉ Plain copy]  [◉ ZIP]   [☑ Auto-detect ver]  │
  ├──── Controls ────────────────────────────────────┤
  │  [▶ Start Backup]  [⏹ Stop]  [🗑 Clear Log]      │
  ├──── Progress ────────────────────────────────────┤
  │  ████████░░░░  62 %  – copying README.md         │
  ├──── Backup History ──────────────────────────────┤
  │  (scrollable list of existing backups)           │
  ├──── Activity Log ────────────────────────────────┤
  │  [dark terminal-style scrolled text]             │
  └──── Status bar ──────────────────────────────────┘
"""
from __future__ import annotations
import os
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .config    import BackupConfig
from .engine    import BackupEngine
from .logger    import BackupLogger
from .versioner import BackupVersioner

# ─────────────── colour palette ───────────────────────────────────────────
P = {
    "bg":      "#f5f5f5",
    "header":  "#1a1a2e",
    "accent":  "#16213e",
    "green":   "#27ae60",
    "red":     "#e74c3c",
    "steel":   "#7f8c8d",
    "blue":    "#2980b9",
    "purple":  "#8e44ad",
    "log_bg":  "#1e1e1e",
    "log_fg":  "#d4d4d4",
    "info_fg": "#4ec9b0",
    "warn_fg": "#dcdcaa",
    "err_fg":  "#f48771",
    "ts_fg":   "#569cd6",
}
CONTENT_W = 860


class BackupGUI:
    """Main application window."""

    APP_TITLE   = "File Backup Logger"
    WINDOW_SIZE = "880x720"
    MIN_SIZE    = (660, 540)

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self._configure_root()

        # tk variables
        self._src_var     = tk.StringVar()
        self._dst_var     = tk.StringVar()
        self._mode_var    = tk.StringVar(value="plain")
        self._autodet_var = tk.BooleanVar(value=True)
        self._status_var  = tk.StringVar(value="Ready.")
        self._pct_var     = tk.StringVar(value="0 %")
        self._progress_var = tk.IntVar(value=0)

        # Back-end
        self._config:   BackupConfig | None = None
        self._logger:   BackupLogger | None = None
        self._engine:   BackupEngine | None = None
        self._thread:   threading.Thread | None = None

        self._setup_backend()
        self._build_ui()
        self._load_config_into_ui()

    # ─────────────── window / back-end setup ──────────────────────────────

    def _configure_root(self) -> None:
        self.root.title(self.APP_TITLE)
        self.root.geometry(self.WINDOW_SIZE)
        self.root.minsize(*self.MIN_SIZE)
        self.root.configure(bg=P["bg"])

    def _setup_backend(self) -> None:
        base     = os.path.join(os.path.expanduser("~"), ".file_backup_logger")
        log_dir  = os.path.join(base, "logs")
        cfg_path = os.path.join(base, "config.json")

        self._config = BackupConfig(config_path=cfg_path)
        self._logger = BackupLogger(log_dir=log_dir)
        self._logger.add_callback(self._on_log_callback)
        self._engine = BackupEngine(config=self._config, logger=self._logger)

    def _load_config_into_ui(self) -> None:
        self._src_var.set(self._config.get("source_folder", ""))
        self._dst_var.set(self._config.get("destination_folder", ""))
        self._mode_var.set("zip" if self._config.get("use_zip") else "plain")
        self._autodet_var.set(self._config.get("auto_detect_version", True))

    # ─────────────── UI assembly ──────────────────────────────────────────

    def _build_ui(self) -> None:
        self._build_header()
        self._build_folders()
        self._build_options()
        self._build_controls()
        self._build_progress()
        self._build_history()
        self._build_log()
        self._build_status_bar()

    # ── header ──────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        f = tk.Frame(self.root, bg=P["header"], pady=14)
        f.pack(fill="x")
        tk.Label(f, text="💾  File Backup Logger",
                 font=("Segoe UI", 17, "bold"),
                 bg=P["header"], fg="white").pack()
        tk.Label(f, text="Versioned backups with ZIP support, logging and undo-safe history",
                 font=("Segoe UI", 9),
                 bg=P["header"], fg="#a0a8b8").pack()

    # ── folder pickers ──────────────────────────────────────────────────

    def _build_folders(self) -> None:
        lf = tk.LabelFrame(self.root, text="  📂  Folders  ",
                           font=("Segoe UI", 10, "bold"),
                           bg=P["bg"], padx=10, pady=8)
        lf.pack(fill="x", padx=16, pady=(12, 0))

        for label, var, cmd in [
            ("Source",      self._src_var, self._browse_source),
            ("Destination", self._dst_var, self._browse_dest),
        ]:
            row = tk.Frame(lf, bg=P["bg"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"{label}:", width=11, anchor="w",
                     font=("Segoe UI", 10), bg=P["bg"]).pack(side="left")
            tk.Entry(row, textvariable=var,
                     font=("Segoe UI", 10), relief="solid", bd=1).pack(
                         side="left", fill="x", expand=True, padx=(0, 8))
            self._btn(row, "Browse…", cmd, P["blue"]).pack(side="left")

    # ── options ─────────────────────────────────────────────────────────

    def _build_options(self) -> None:
        lf = tk.LabelFrame(self.root, text="  ⚙  Options  ",
                           font=("Segoe UI", 10, "bold"),
                           bg=P["bg"], padx=10, pady=6)
        lf.pack(fill="x", padx=16, pady=(6, 0))

        row = tk.Frame(lf, bg=P["bg"])
        row.pack(fill="x")

        tk.Label(row, text="Backup mode:", font=("Segoe UI", 10), bg=P["bg"]).pack(side="left", padx=(0, 8))
        for text, val in [("Plain copy", "plain"), ("ZIP archive", "zip")]:
            tk.Radiobutton(row, text=text, variable=self._mode_var, value=val,
                           font=("Segoe UI", 10), bg=P["bg"],
                           activebackground=P["bg"]).pack(side="left", padx=4)

        tk.Label(row, text="   ", bg=P["bg"]).pack(side="left")
        tk.Checkbutton(row, text="Auto-detect version from source",
                       variable=self._autodet_var,
                       font=("Segoe UI", 10), bg=P["bg"],
                       activebackground=P["bg"]).pack(side="left", padx=(12, 0))

    # ── controls ────────────────────────────────────────────────────────

    def _build_controls(self) -> None:
        f = tk.Frame(self.root, bg=P["bg"])
        f.pack(fill="x", padx=16, pady=8)

        self._btn_start = self._btn(f, "▶  Start Backup", self._start_backup, P["green"])
        self._btn_stop  = self._btn(f, "⏹  Stop",         self._stop_backup,  P["red"],
                                    state="disabled")
        for b in (self._btn_start, self._btn_stop):
            b.pack(side="left", padx=(0, 6))

        self._btn(f, "🔄  Refresh History", self._refresh_history,
                  P["purple"]).pack(side="left", padx=(0, 6))
        self._btn(f, "🗑  Clear Log", self._clear_log,
                  P["steel"]).pack(side="right")

    # ── progress ────────────────────────────────────────────────────────

    def _build_progress(self) -> None:
        f = tk.Frame(self.root, bg=P["bg"])
        f.pack(fill="x", padx=16, pady=(0, 6))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("BL.Horizontal.TProgressbar",
                        troughcolor="#dde", background=P["green"], thickness=18)
        self._progress_bar = ttk.Progressbar(
            f, variable=self._progress_var, maximum=100,
            style="BL.Horizontal.TProgressbar")
        self._progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Label(f, textvariable=self._pct_var,
                 font=("Segoe UI", 9, "bold"),
                 bg=P["bg"], width=5).pack(side="left")

    # ── history ─────────────────────────────────────────────────────────

    def _build_history(self) -> None:
        lf = tk.LabelFrame(self.root, text="  🗂  Backup History  ",
                           font=("Segoe UI", 10, "bold"),
                           bg=P["bg"], padx=6, pady=4)
        lf.pack(fill="x", padx=16, pady=(0, 4))

        self._history_text = scrolledtext.ScrolledText(
            lf, state="disabled", font=("Segoe UI", 9),
            bg="#eef2f7", fg="#2c3e50", height=4,
            wrap="none", relief="flat")
        self._history_text.pack(fill="both", expand=True)
        self._history_text.tag_config("name",  foreground=P["blue"],   font=("Segoe UI", 9, "bold"))
        self._history_text.tag_config("label", foreground="#7f8c8d")
        self._history_text.tag_config("zip",   foreground=P["purple"])

    # ── log ─────────────────────────────────────────────────────────────

    def _build_log(self) -> None:
        lf = tk.LabelFrame(self.root, text="  📋  Activity Log  ",
                           font=("Segoe UI", 10, "bold"),
                           bg=P["bg"], padx=6, pady=4)
        lf.pack(fill="both", expand=True, padx=16, pady=(0, 4))

        self._log_text = scrolledtext.ScrolledText(
            lf, state="disabled", font=("Courier New", 9),
            bg=P["log_bg"], fg=P["log_fg"],
            insertbackground="white", wrap="word", height=8, relief="flat")
        self._log_text.pack(fill="both", expand=True)
        self._log_text.tag_config("TS",      foreground=P["ts_fg"])
        self._log_text.tag_config("INFO",    foreground=P["info_fg"])
        self._log_text.tag_config("WARNING", foreground=P["warn_fg"])
        self._log_text.tag_config("ERROR",   foreground=P["err_fg"])

    # ── status bar ──────────────────────────────────────────────────────

    def _build_status_bar(self) -> None:
        f = tk.Frame(self.root, bg=P["accent"], pady=5)
        f.pack(fill="x", side="bottom")
        tk.Label(f, textvariable=self._status_var,
                 font=("Segoe UI", 9),
                 bg=P["accent"], fg="#ecf0f1").pack(side="left", padx=10)

    # ─────────────── button callbacks ─────────────────────────────────────

    def _browse_source(self) -> None:
        d = filedialog.askdirectory(title="Select source folder to back up")
        if d:
            self._src_var.set(d)
            self._config.set("source_folder", d)
            self._refresh_history()

    def _browse_dest(self) -> None:
        d = filedialog.askdirectory(title="Select backup destination folder")
        if d:
            self._dst_var.set(d)
            self._config.set("destination_folder", d)
            self._refresh_history()

    def _start_backup(self) -> None:
        src = self._src_var.get().strip()
        dst = self._dst_var.get().strip()
        if not src or not dst:
            messagebox.showwarning("Missing folder", "Please select both source and destination folders.")
            return
        if not os.path.isdir(src):
            messagebox.showerror("Invalid source", f"'{src}' is not a valid directory.")
            return

        use_zip = self._mode_var.get() == "zip"
        self._config.update({
            "source_folder":       src,
            "destination_folder":  dst,
            "use_zip":             use_zip,
            "auto_detect_version": self._autodet_var.get(),
        })
        # Re-create engine so it picks up updated config
        self._engine = BackupEngine(config=self._config, logger=self._logger)

        self._btn_start.config(state="disabled")
        self._btn_stop.config(state="normal")
        self._progress_var.set(0)
        self._pct_var.set("0 %")
        self._status_var.set("Backing up…")

        self._thread = threading.Thread(
            target=self._run_backup, args=(src, dst, use_zip), daemon=True)
        self._thread.start()

    def _run_backup(self, src: str, dst: str, use_zip: bool) -> None:
        def on_progress(current: int, total: int, filename: str) -> None:
            pct = int(current / total * 100) if total else 0
            self.root.after(0, self._update_progress, pct, current, total, filename)

        stats = self._engine.run(src, dst, use_zip=use_zip, on_progress=on_progress)
        self.root.after(0, self._backup_done, stats)

    def _update_progress(self, pct: int, current: int, total: int, filename: str) -> None:
        self._progress_var.set(pct)
        self._pct_var.set(f"{pct} %")
        self._status_var.set(f"Copying {current}/{total}: {filename}")

    def _backup_done(self, stats) -> None:
        self._btn_start.config(state="normal")
        self._btn_stop.config(state="disabled")
        self._progress_var.set(100 if stats.status == "success" else self._progress_var.get())
        emoji = "✔" if stats.status == "success" else ("⚠" if stats.status == "partial" else "✖")
        self._status_var.set(
            f"{emoji}  {stats.status.title()}  –  {stats.files_copied} files  "
            f"({stats.size_mb:.1f} MB)  in {stats.duration_seconds:.1f}s"
        )
        self._refresh_history()

    def _stop_backup(self) -> None:
        self._engine.stop()
        self._btn_stop.config(state="disabled")
        self._status_var.set("Stopping after current file…")

    def _clear_log(self) -> None:
        self._log_text.config(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.config(state="disabled")

    # ─────────────── history panel ────────────────────────────────────────

    def _refresh_history(self) -> None:
        dst = self._dst_var.get().strip()
        versioner = BackupVersioner(dst)
        backups   = versioner.list_backups() if dst else []

        self._history_text.config(state="normal")
        self._history_text.delete("1.0", "end")
        if not backups:
            self._history_text.insert("end", "  No backups found in destination folder.\n", "label")
        else:
            self._history_text.insert("end", f"  {len(backups)} backup(s) found\n", "label")
            for name in reversed(backups):
                is_zip = os.path.isfile(os.path.join(dst, name + ".zip"))
                tag    = "zip" if is_zip else "name"
                icon   = "🗜 " if is_zip else "📁 "
                self._history_text.insert("end", f"  {icon}", "label")
                self._history_text.insert("end", f"{name}", tag)
                self._history_text.insert("end", "  (.zip)\n" if is_zip else "\n", "label")
        self._history_text.config(state="disabled")

    # ─────────────── log panel ────────────────────────────────────────────

    def _on_log_callback(self, level: str, message: str) -> None:
        self.root.after(0, self._append_log, level, message)

    def _append_log(self, level: str, message: str) -> None:
        ts  = datetime.now().strftime("%H:%M:%S")
        tag = level if level in ("INFO", "WARNING", "ERROR") else "INFO"
        self._log_text.config(state="normal")
        self._log_text.insert("end", f"[{ts}] ", "TS")
        self._log_text.insert("end", f"[{level:<7}] ", tag)
        self._log_text.insert("end", f"{message}\n")
        self._log_text.see("end")
        self._log_text.config(state="disabled")

    # ─────────────── helper ───────────────────────────────────────────────

    @staticmethod
    def _btn(parent, text: str, command, bg: str, state: str = "normal") -> tk.Button:
        return tk.Button(
            parent, text=text, command=command,
            bg=bg, fg="white", font=("Segoe UI", 9, "bold"),
            relief="flat", padx=14, pady=6,
            cursor="hand2", state=state,
            activebackground=bg, activeforeground="white")