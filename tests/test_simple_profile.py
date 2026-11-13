"""Synthetic profile tests. No real profile, credentials, or provider access."""
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from godmode_profile import PROFILE_FIELDS, PROFILE_MAX_SIZE, Profile


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="godmode-profile-test-")
        self.root = Path(self.temp.name).resolve()
        self.profile = Profile(self.root / "state")

    def tearDown(self):
        self.temp.cleanup()

    def seed(self, raw):
        self.profile.home.mkdir(mode=0o700, exist_ok=True)
        self.profile.path.write_bytes(raw.encode("utf-8") if isinstance(raw, str) else raw)
        self.profile.path.chmod(0o600)

    def test_absent_and_empty_profile_need_no_files(self):
        self.assertEqual(self.profile.read(), {})
        self.assertFalse(self.profile.write({}))
        self.assertFalse(self.profile.home.exists())

    def test_private_json_roundtrip_and_successive_edits(self):
        data = dict(zip(PROFILE_FIELDS, ("Zoë", "Example Studio", "Example LLC",
                                       "https://example.test", "hello@example.test",
                                       "123 Example Street\nExample City")))
        self.assertTrue(self.profile.write(data))
        self.assertEqual(self.profile.read(), data)
        self.assertEqual(json.loads(self.profile.path.read_text()), data)
        self.assertEqual(stat.S_IMODE(self.profile.home.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.profile.path.stat().st_mode), 0o600)
        self.assertEqual(list(self.profile.home.iterdir()), [self.profile.path])
        self.assertTrue(self.profile.write(dict(data, operator_name="Changed")))
        self.assertTrue(self.profile.write({}))  # Clearing all fields is explicit.
        self.assertEqual(self.profile.read(), {})

    def test_noop_preserves_formatting_timestamp_and_inode(self):
        raw = b'{ "website":"https://example.test", "operator_name" : "Example" }\n'
        self.seed(raw)
        data = self.profile.read()
        before = self.profile.path.stat()
        self.assertFalse(self.profile.write(data))
        self.assertEqual(self.profile.path.read_bytes(), raw)
        after = self.profile.path.stat()
        self.assertEqual((after.st_ino, after.st_mtime_ns), (before.st_ino, before.st_mtime_ns))

    def test_unknown_fields_survive_a_known_field_edit(self):
        unknown = {"future": {"tags": ["a", True, None, 4.5], "note": "line\nnext"}}
        self.seed(json.dumps(dict(unknown, operator_name="Before")))
        data = self.profile.read()
        data["operator_name"] = "After"
        self.profile.write(data)
        self.assertEqual(self.profile.read(), dict(unknown, operator_name="After"))
        data["future"]["tags"][1] = 1
        self.assertTrue(self.profile.write(data))  # JSON bool and int are different.
        self.assertIs(type(self.profile.read()["future"]["tags"][1]), int)

    def test_bad_existing_json_is_never_replaced(self):
        cases = [b"", b"{", b"[]", b"null", b"{} trailing", b"\xff", b'{"x":"\xff"}',
                 b'{"operator_name":"first","operator_name":"second"}',
                 b'{"unknown":{"duplicate":1,"duplicate":2}}',
                 b'{"operator_name":null}', b'{"operator_name":42}',
                 b'{"unknown":NaN}', b'{"unknown":Infinity}', b'{"unknown":-Infinity}',
                 b'{"operator_name":"\\ud800"}', b'{"unknown":"\\ud800"}',
                 b'{"operator_name":"\\u001b[2J"}',
                 b" " * (PROFILE_MAX_SIZE + 1), b"[" * 1100]
        for raw in cases:
            with self.subTest(raw=raw[:50]):
                self.seed(raw)
                profile = Profile(self.profile.home)
                for operation in (profile.read, lambda: profile.write({"operator_name": "Replacement"})):
                    with self.assertRaises(ValueError):
                        operation()
                    self.assertEqual(profile.path.read_bytes(), raw)

    def test_bad_new_values_do_not_create_files(self):
        cases = [[], {"operator_name": 1}, {"business_name": None},
                 {"legal_name": "hidden\x1b[2J"}, {"website": "x\ny"},
                 {"public_email": "x\ry"}, {"operator_name": "\u0085"},
                 {"business_mailing_address": "x\taddress"},
                 {"operator_name": "\ud800"}, {"unknown": float("nan")},
                 {"unknown": object()}, {"operator_name": "x" * PROFILE_MAX_SIZE}]
        for data in cases:
            with self.subTest(data=repr(data)[:50]):
                with self.assertRaises(ValueError):
                    self.profile.write(data)
                self.assertFalse(self.profile.home.exists())

    def test_stale_edits_do_not_overwrite_concurrent_changes(self):
        self.seed('{"operator_name":"Original"}')
        original = self.profile.read()
        other = Profile(self.profile.home)
        other.write({"operator_name": "Other editor", "future": "kept"})
        before = self.profile.path.read_bytes()
        for data in (original, dict(original, operator_name="Stale edit")):
            with self.assertRaisesRegex(ValueError, "changed before saving"):
                self.profile.write(data)
            self.assertEqual(self.profile.path.read_bytes(), before)
        fresh = self.profile.read()
        self.profile.write(dict(fresh, operator_name="Fresh edit"))
        self.assertEqual(self.profile.read()["future"], "kept")

    def test_concurrent_create_delete_and_same_content_replacement_are_detected(self):
        self.profile.read()
        other = Profile(self.profile.home)
        other.write({"operator_name": "Created"})
        with self.assertRaisesRegex(ValueError, "changed before saving"):
            self.profile.write({"operator_name": "Stale create"})
        self.profile.read()
        raw = self.profile.path.read_bytes()
        self.profile.path.unlink()
        with self.assertRaisesRegex(ValueError, "changed before saving"):
            self.profile.write({"operator_name": "Stale after deletion"})
        self.seed(raw)
        self.profile.read()
        replacement = self.root / "replacement"
        replacement.write_bytes(raw)
        replacement.chmod(0o600)
        os.replace(replacement, self.profile.path)
        with self.assertRaisesRegex(ValueError, "changed before saving"):
            self.profile.write({"operator_name": "Stale after replacement"})

    def test_atomic_failure_keeps_original_and_removes_temporary(self):
        self.seed('{"operator_name":"Original"}')
        before = self.profile.path.read_bytes()
        for operation in ("replace", "fsync"):
            with mock.patch("godmode_profile.os." + operation, side_effect=OSError()):
                with self.assertRaises(ValueError):
                    self.profile.write({"operator_name": "Replacement"})
            self.assertEqual(self.profile.path.read_bytes(), before)
            self.assertEqual(list(self.profile.home.iterdir()), [self.profile.path])

    def test_edit_during_temporary_write_is_detected(self):
        self.seed('{"operator_name":"Original"}')
        real_fsync = os.fsync
        def edit(fd):
            real_fsync(fd)
            self.seed('{"operator_name":"Manual concurrent edit"}')
        with mock.patch("godmode_profile.os.fsync", side_effect=edit):
            with self.assertRaisesRegex(ValueError, "changed before saving"):
                self.profile.write({"operator_name": "Replacement"})
        self.assertEqual(self.profile.read(), {"operator_name": "Manual concurrent edit"})
        self.assertEqual(list(self.profile.home.iterdir()), [self.profile.path])

    def test_another_writer_lock_prevents_save(self):
        self.seed('{}')
        directory = os.open(self.profile.home, os.O_RDONLY)
        try:
            fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, "Another editor"):
                self.profile.write({"operator_name": "Replacement"})
        finally:
            os.close(directory)
        self.assertEqual(self.profile.path.read_bytes(), b"{}")

    def test_unsafe_modes_ownership_and_hardlinks_are_refused(self):
        self.seed('{}')
        for path, mode, restored in ((self.profile.path, 0o644, 0o600),
                                     (self.profile.home, 0o755, 0o700)):
            path.chmod(mode)
            for operation in (self.profile.read, lambda: self.profile.write({"operator_name": "New"})):
                with self.assertRaises(ValueError):
                    operation()
            self.assertEqual(self.profile.path.read_bytes(), b"{}")
            path.chmod(restored)
        with mock.patch("godmode_profile.os.geteuid", return_value=os.geteuid() + 1):
            with self.assertRaises(ValueError):
                self.profile.read()
        os.link(self.profile.path, self.root / "hardlink")
        with self.assertRaises(ValueError):
            self.profile.write({"operator_name": "New"})
        self.assertEqual(self.profile.path.read_bytes(), b"{}")

    def test_symlinks_and_nonregular_files_are_refused(self):
        self.seed('{}')
        self.profile.path.unlink()
        outside = self.root / "outside"
        outside.write_text("untouched")
        outside.chmod(0o600)
        self.profile.path.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.profile.write({"operator_name": "New"})
        self.assertEqual(outside.read_text(), "untouched")
        self.profile.path.unlink()
        os.mkfifo(self.profile.path, mode=0o600)
        with self.assertRaises(ValueError):
            self.profile.read()
        alias = self.root / "alias"
        alias.symlink_to(self.profile.home, target_is_directory=True)
        with self.assertRaises(ValueError):
            Profile(alias / "new").write({"operator_name": "New"})
        self.assertFalse((self.profile.home / "new").exists())

    def test_git_checkout_requires_ignored_untracked_profile(self):
        self.profile.home.mkdir(mode=0o700)
        subprocess.run(["git", "init", "-q", str(self.profile.home)], check=True)
        with self.assertRaisesRegex(ValueError, "ignored and untracked"):
            self.profile.write({"operator_name": "Example"})
        self.assertFalse(self.profile.path.exists())
        (self.profile.home / ".gitignore").write_text("profile.json\n")
        self.assertTrue(self.profile.write({"operator_name": "Example"}))
        subprocess.run(["git", "-C", str(self.profile.home), "add", "-f", "profile.json"], check=True)
        with self.assertRaisesRegex(ValueError, "ignored and untracked"):
            self.profile.write({"operator_name": "New"})
        self.assertEqual(self.profile.read(), {"operator_name": "Example"})


if __name__ == "__main__":
    unittest.main()
