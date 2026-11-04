"""Synthetic file tests; never use the normal Godmode home or provider accounts."""
import fcntl
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from godmode_store import Store, normalize, valid_key


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="godmode-store-test-")
        self.root = Path(self.temp.name).resolve()
        self.store = Store(self.root / "config")

    def tearDown(self):
        self.temp.cleanup()

    def write(self, text):
        self.store.config_dir.mkdir(mode=0o700, exist_ok=True)
        self.store.env_path.write_bytes(text.encode("utf-8"))
        self.store.env_path.chmod(0o600)

    def test_manual_file_needs_no_state_or_initialization(self):
        self.write("# manual file with someone's comment\nCUSTOM='fixture value'\nEMPTY=''\n")
        self.assertEqual(self.store.states(), {"CUSTOM": "set", "EMPTY": "blank"})
        original = self.store.env_path.read_bytes()
        self.store.initialize()
        self.assertEqual(self.store.env_path.read_bytes(), original)
        self.assertEqual(list(self.store.config_dir.iterdir()), [self.store.env_path])
        self.write("MANUAL_REPLACEMENT=synthetic\n")
        self.assertEqual(self.store.states(), {"MANUAL_REPLACEMENT": "set"})

    def test_quotes_are_shell_readable_and_never_evaluated(self):
        value = "fixture ' quoted $VALUE # $(touch MUST_NOT_EXIST) `touch ALSO_NOT_EXIST`"
        self.store.set("CUSTOM", value)
        result = subprocess.run(
            ["/bin/sh", "-c", '. "$1"; test "$CUSTOM" = "$2"', "sh",
             str(self.store.env_path), value], cwd=self.root, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout + result.stderr, b"")
        self.assertFalse((self.root / "MUST_NOT_EXIST").exists())
        self.assertFalse((self.root / "ALSO_NOT_EXIST").exists())
        self.assertEqual(stat.S_IMODE(self.store.env_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.store.config_dir.stat().st_mode), 0o700)

    def test_preserves_unrelated_bytes_and_deduplicates_only_target(self):
        self.write("# comment\r\nOTHER='stay # literal'\nexport KEY = old\r\nKEY=duplicate\nopaque unchanged")
        self.store.set("KEY", "new synthetic value")
        self.assertEqual(self.store.env_path.read_bytes(),
                         b"# comment\r\nOTHER='stay # literal'\nKEY='new synthetic value'\r\nopaque unchanged")
        self.store.set("ADDED", "synthetic")
        self.assertTrue(self.store.env_path.read_bytes().endswith(b"opaque unchanged\r\nADDED=synthetic\r\n"))

    def test_states_are_redacted_and_detect_duplicate_and_bad_value(self):
        self.write("SET='fixture_secret'\nBLANK=\nSET=duplicate\nMULTI=two words\nHASH=#literal\nCOMMENT= # someone's key\nINLINE=value # someone's comment\n")
        self.assertEqual(self.store.states(),
                         {"SET": "duplicate", "BLANK": "blank", "MULTI": "malformed",
                          "HASH": "set", "COMMENT": "blank", "INLINE": "set"})

    def test_multiline_and_unfinished_manual_quotes_are_never_rewritten(self):
        for text in ["MULTILINE='first\nTARGET=embedded\nlast'\nOTHER=keep\n",
                     'MULTILINE="first\nTARGET=embedded\nlast"\nOTHER=keep\n',
                     "BROKEN='unterminated\nTARGET=embedded\n",
                     "MULTILINE=prefix#'first\nTARGET=embedded\nlast#'\nOTHER=keep\n"]:
            self.write(text)
            before = self.store.env_path.read_bytes()
            with self.assertRaisesRegex(ValueError, "godmode edit"):
                self.store.states()
            for key in ('TARGET', 'MULTILINE', 'NEW_KEY'):
                with self.assertRaisesRegex(ValueError, "godmode edit"):
                    self.store.set(key, 'synthetic replacement')
                self.assertEqual(self.store.env_path.read_bytes(), before)

    def test_clipboard_json_and_invalid_input(self):
        self.assertEqual(normalize("synthetic value\r\n"), "synthetic value")
        self.assertEqual(normalize("{\n  \"private_key\": \"fixture\\nvalue\"\n}\r\n"),
                         '{"private_key":"fixture\\nvalue"}')
        for key, value in [("BAD-KEY", "x"), ("GOOD", ""), ("GOOD", "bad\0value"),
                           ("GOOD", "one\ntwo"), ("CLIENT_JSON", "[]"), ("GOOD", "x" * (1024 * 1024 + 1))]:
            with self.assertRaises(ValueError):
                self.store.set(key, value)
        self.assertFalse(self.store.config_dir.exists())

    def test_refuses_unsafe_files_without_modifying_them(self):
        self.write("KEY=synthetic\n")
        original = self.store.env_path.read_bytes()
        self.store.env_path.chmod(0o644)
        for operation in [self.store.states, self.store.initialize, lambda: self.store.set("KEY", "other")]:
            with self.assertRaises(ValueError):
                operation()
        self.assertEqual(self.store.env_path.read_bytes(), original)
        self.store.env_path.chmod(0o600)
        os.link(self.store.env_path, self.root / "hardlink")
        with self.assertRaises(ValueError):
            self.store.set("KEY", "other")
        (self.root / "hardlink").unlink()
        self.store.env_path.unlink()
        target = self.root / "outside"
        target.write_text("untouched")
        self.store.env_path.symlink_to(target)
        with self.assertRaises(ValueError):
            self.store.set("KEY", "other")
        self.assertEqual(target.read_text(), "untouched")

    def test_refuses_symlinked_parent_and_nonregular_file(self):
        (self.root / "actual").mkdir(mode=0o700)
        (self.root / "alias").symlink_to(self.root / "actual", target_is_directory=True)
        with self.assertRaises(ValueError):
            Store(self.root / "alias/config").set("KEY", "synthetic")
        self.assertFalse((self.root / "actual/config").exists())
        self.store.config_dir.mkdir(mode=0o700)
        os.mkfifo(self.store.env_path, mode=0o600)
        with self.assertRaises(ValueError):
            self.store.states()

    def test_atomic_failure_and_changed_file_preserve_data(self):
        self.write("KEY=original\n")
        with mock.patch("godmode_store.os.replace", side_effect=OSError()):
            with self.assertRaises(ValueError):
                self.store.set("KEY", "replacement")
        self.assertEqual(self.store.env_path.read_bytes(), b"KEY=original\n")
        self.assertEqual(list(self.store.config_dir.iterdir()), [self.store.env_path])
        _, snapshot = self.store._read()
        self.write("KEY=manual-edit\n")
        with self.store._writer() as directory:
            with self.assertRaises(ValueError):
                self.store._write("KEY=stale-edit\n", snapshot, directory)
        self.assertEqual(self.store.env_path.read_bytes(), b"KEY=manual-edit\n")
        self.assertEqual(list(self.store.config_dir.iterdir()), [self.store.env_path])

    def test_other_writer_lock_prevents_save(self):
        self.store.initialize()
        fd = os.open(self.store.config_dir, os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(ValueError):
                self.store.set("KEY", "synthetic")
        finally:
            os.close(fd)
        self.assertEqual(self.store.env_path.read_bytes(), b"")

    def test_default_home_preserves_legacy_configuration(self):
        with mock.patch.dict(os.environ, {"HOME": str(self.root)}, clear=True):
            fresh = Store()
            self.assertEqual(fresh.config_dir, self.root / ".godmode")
            self.assertFalse(fresh.config_dir.exists())
            legacy = self.root / ".config/godmode"
            legacy.mkdir(parents=True)
            (self.root / ".godmode/bin").mkdir(parents=True)
            (self.root / ".godmode/env").write_text("# shell setup")
            self.assertEqual(Store().config_dir, legacy)
            (self.root / ".godmode/AGENTS.md").write_text("custom instructions")
            self.assertEqual(Store().config_dir, self.root / ".godmode")
            with mock.patch.dict(os.environ, {"GODMODE_HOME": str(self.root / "chosen")}):
                self.assertEqual(Store().config_dir, self.root / "chosen")
                self.assertEqual(Store(self.root / "explicit").config_dir, self.root / "explicit")

    def test_git_guard_requires_ignored_untracked_file(self):
        self.store.config_dir.mkdir(mode=0o700)
        env = {"PATH": os.environ.get("PATH", ""), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
        subprocess.run(["git", "init", "-q", str(self.store.config_dir)], env=env, check=True)
        with self.assertRaises(ValueError):
            self.store.initialize()
        self.assertFalse(self.store.env_path.exists())
        (self.store.config_dir / ".gitignore").write_text(".env.godmode\n")
        self.store.set("KEY", "synthetic")
        subprocess.run(["git", "-C", str(self.store.config_dir), "add", "-f", ".env.godmode"], env=env, check=True)
        with self.assertRaises(ValueError):
            self.store.set("KEY", "replacement")


if __name__ == "__main__":
    unittest.main()
