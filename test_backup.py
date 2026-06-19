"""
test_backup.py
Unit tests for the File Backup Logger back-end.

Run with:
    python -m unittest test_backup -v
"""
from __future__ import annotations
import json
import os
import shutil
import tempfile
import time
import unittest
import zipfile

from backup.config    import BackupConfig
from backup.versioner import BackupVersioner
from backup.logger    import BackupLogger
from backup.engine    import BackupEngine, BackupStats


# ─────────────────────────────────────────────────────────────────────────────
class TestBackupConfig(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg_path = os.path.join(self.tmp, "config.json")
        self.cfg = BackupConfig(config_path=self.cfg_path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_defaults_present(self):
        for key in BackupConfig.DEFAULTS:
            self.assertEqual(self.cfg.get(key), BackupConfig.DEFAULTS[key])

    def test_set_and_get(self):
        self.cfg.set("use_zip", True)
        self.assertTrue(self.cfg.get("use_zip"))

    def test_persists_to_disk(self):
        self.cfg.set("source_folder", "/some/path")
        cfg2 = BackupConfig(config_path=self.cfg_path)
        self.assertEqual(cfg2.get("source_folder"), "/some/path")

    def test_update_bulk(self):
        self.cfg.update({"use_zip": True, "max_versions": 5})
        self.assertTrue(self.cfg.get("use_zip"))
        self.assertEqual(self.cfg.get("max_versions"), 5)

    def test_reset_restores_defaults(self):
        self.cfg.set("max_versions", 99)
        self.cfg.reset()
        self.assertEqual(self.cfg.get("max_versions"), BackupConfig.DEFAULTS["max_versions"])

    def test_as_dict_contains_all_defaults(self):
        d = self.cfg.as_dict()
        for key in BackupConfig.DEFAULTS:
            self.assertIn(key, d)

    def test_unknown_key_returns_default_arg(self):
        self.assertIsNone(self.cfg.get("nonexistent_key"))
        self.assertEqual(self.cfg.get("nonexistent_key", "fallback"), "fallback")


# ─────────────────────────────────────────────────────────────────────────────
class TestBackupVersioner(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.versioner = BackupVersioner(self.tmp, auto_detect=False)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _touch_dir(self, name: str) -> str:
        path = os.path.join(self.tmp, name)
        os.makedirs(path, exist_ok=True)
        return path

    def test_name_starts_with_prefix(self):
        src = tempfile.mkdtemp()
        try:
            name = self.versioner.next_name(src)
            self.assertTrue(name.startswith("backup_"))
        finally:
            shutil.rmtree(src)

    def test_counter_increments(self):
        src = tempfile.mkdtemp()
        try:
            n1 = self.versioner.next_name(src)
            self._touch_dir(n1)
            n2 = self.versioner.next_name(src)
            self.assertNotEqual(n1, n2)
        finally:
            shutil.rmtree(src)

    def test_list_backups_sorted(self):
        self._touch_dir("backup_2025-01-01_v1")
        self._touch_dir("backup_2025-01-01_v2")
        backups = self.versioner.list_backups()
        self.assertEqual(backups, sorted(backups))

    def test_list_includes_zip(self):
        open(os.path.join(self.tmp, "backup_2025-01-01_v1.zip"), "w").close()
        backups = self.versioner.list_backups()
        self.assertIn("backup_2025-01-01_v1", backups)

    def test_prune_removes_oldest(self):
        for i in range(1, 6):
            self._touch_dir(f"backup_2025-01-0{i}_v1")
        removed = self.versioner.prune_old(max_keep=3)
        self.assertEqual(len(removed), 2)
        self.assertEqual(len(self.versioner.list_backups()), 3)

    def test_prune_zero_means_unlimited(self):
        for i in range(1, 6):
            self._touch_dir(f"backup_2025-02-0{i}_v1")
        removed = self.versioner.prune_old(max_keep=0)
        self.assertEqual(removed, [])

    def test_detect_version_from_package_json(self):
        src = tempfile.mkdtemp()
        try:
            with open(os.path.join(src, "package.json"), "w") as f:
                json.dump({"version": "3.1.4"}, f)
            v = BackupVersioner(self.tmp, auto_detect=True).detect_version(src)
            self.assertEqual(v, "3.1.4")
        finally:
            shutil.rmtree(src)

    def test_detect_version_returns_none_when_no_file(self):
        src = tempfile.mkdtemp()
        try:
            v = BackupVersioner(self.tmp, auto_detect=True).detect_version(src)
            self.assertIsNone(v)
        finally:
            shutil.rmtree(src)

    def test_version_used_in_name(self):
        src = tempfile.mkdtemp()
        try:
            with open(os.path.join(src, "package.json"), "w") as f:
                json.dump({"version": "1.2.3"}, f)
            versioner = BackupVersioner(self.tmp, auto_detect=True)
            name = versioner.next_name(src)
            self.assertIn("1.2.3", name)
        finally:
            shutil.rmtree(src)


# ─────────────────────────────────────────────────────────────────────────────
class TestBackupLogger(unittest.TestCase):

    def setUp(self):
        self.tmp    = tempfile.mkdtemp()
        self.logger = BackupLogger(log_dir=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_log_file_created(self):
        logs = [f for f in os.listdir(self.tmp) if f.endswith(".log")]
        self.assertEqual(len(logs), 1)

    def test_callback_fired(self):
        received = []
        self.logger.add_callback(lambda lvl, msg: received.append((lvl, msg)))
        self.logger.log_info("hello")
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0], "INFO")

    def test_remove_callback(self):
        received = []
        cb = lambda lvl, msg: received.append(msg)
        self.logger.add_callback(cb)
        self.logger.remove_callback(cb)
        self.logger.log_info("should not appear")
        self.assertEqual(received, [])

    def test_log_success_writes_to_file(self):
        self.logger.log_success("bk_1", "/src", "/dst", "plain", 10, 2.5, 1.3)
        with open(self.logger.log_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("BACKUP", content)
        self.assertIn("OK", content)


# ─────────────────────────────────────────────────────────────────────────────
class TestBackupEngine(unittest.TestCase):

    def setUp(self):
        self.tmp    = tempfile.mkdtemp()
        self.src    = os.path.join(self.tmp, "source")
        self.dst    = os.path.join(self.tmp, "backups")
        os.makedirs(self.src)
        os.makedirs(self.dst)
        self.logger = BackupLogger(log_dir=os.path.join(self.tmp, "logs"))
        self.engine = BackupEngine(logger=self.logger)
        self.engine.config.set("max_versions", 0)   # no pruning in tests

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── helpers ──────────────────────────────────────────────────────────

    def _populate(self, files: dict[str, str]) -> None:
        """Create files in self.src with given content."""
        for name, content in files.items():
            path = os.path.join(self.src, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)

    # ── plain copy ───────────────────────────────────────────────────────

    def test_plain_backup_creates_folder(self):
        self._populate({"a.txt": "hello", "b.txt": "world"})
        stats = self.engine.run(self.src, self.dst, use_zip=False)
        self.assertEqual(stats.status, "success")
        self.assertTrue(os.path.isdir(stats.backup_path))

    def test_plain_backup_copies_files(self):
        self._populate({"readme.md": "# Hi", "sub/data.csv": "a,b,c"})
        stats = self.engine.run(self.src, self.dst, use_zip=False)
        self.assertEqual(stats.files_copied, 2)

    def test_plain_backup_preserves_subfolders(self):
        self._populate({"sub/nested.txt": "deep"})
        stats = self.engine.run(self.src, self.dst, use_zip=False)
        nested = os.path.join(stats.backup_path, "sub", "nested.txt")
        self.assertTrue(os.path.isfile(nested))

    # ── ZIP ──────────────────────────────────────────────────────────────

    def test_zip_backup_creates_zip(self):
        self._populate({"file.py": "print('hi')"})
        stats = self.engine.run(self.src, self.dst, use_zip=True)
        self.assertEqual(stats.status, "success")
        self.assertTrue(stats.backup_path.endswith(".zip"))
        self.assertTrue(zipfile.is_zipfile(stats.backup_path))

    def test_zip_contains_all_files(self):
        self._populate({"a.txt": "1", "b.txt": "2", "c/d.txt": "3"})
        stats = self.engine.run(self.src, self.dst, use_zip=True)
        with zipfile.ZipFile(stats.backup_path) as zf:
            self.assertEqual(len(zf.namelist()), 3)

    # ── stats ────────────────────────────────────────────────────────────

    def test_stats_file_count(self):
        self._populate({"x.txt": "x", "y.txt": "y", "z.txt": "z"})
        stats = self.engine.run(self.src, self.dst, use_zip=False)
        self.assertEqual(stats.files_copied, 3)

    def test_stats_duration_positive(self):
        self._populate({"f.txt": "data"})
        stats = self.engine.run(self.src, self.dst, use_zip=False)
        self.assertGreater(stats.duration_seconds, 0)

    def test_stats_size_positive(self):
        self._populate({"f.txt": "some content here"})
        stats = self.engine.run(self.src, self.dst, use_zip=False)
        self.assertGreater(stats.total_size_bytes, 0)

    # ── progress callback ────────────────────────────────────────────────

    def test_progress_callback_called(self):
        self._populate({"a.txt": "1", "b.txt": "2", "c.txt": "3"})
        calls = []
        self.engine.run(self.src, self.dst, use_zip=False,
                        on_progress=lambda c, t, n: calls.append(c))
        self.assertEqual(len(calls), 3)

    # ── error handling ───────────────────────────────────────────────────

    def test_invalid_source_returns_failed(self):
        stats = self.engine.run("/nonexistent_xyz", self.dst, use_zip=False)
        self.assertEqual(stats.status, "failed")
        self.assertTrue(len(stats.errors) > 0)

    # ── versioning ───────────────────────────────────────────────────────

    def test_two_backups_have_different_names(self):
        self._populate({"f.txt": "x"})
        s1 = self.engine.run(self.src, self.dst, use_zip=False)
        s2 = self.engine.run(self.src, self.dst, use_zip=False)
        self.assertNotEqual(s1.backup_name, s2.backup_name)

    # ── pruning ──────────────────────────────────────────────────────────

    def test_pruning_keeps_max_versions(self):
        self._populate({"f.txt": "x"})
        self.engine.config.set("max_versions", 3)
        for _ in range(5):
            self.engine.run(self.src, self.dst, use_zip=False)
            time.sleep(0.01)   # ensure distinct names
        versioner = BackupVersioner(self.dst)
        self.assertLessEqual(len(versioner.list_backups()), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)