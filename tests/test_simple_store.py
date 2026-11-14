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
from godmode_store import SEAL_PREFIX, STORE_GUIDE_NAME, STORE_SEALED, Store, move_and_seal, normalize, plain_source, seal, unseal, valid_key


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
        """A plain-text file (one not yet sealed) stays shell-readable."""
        value = "fixture ' quoted $VALUE # $(touch MUST_NOT_EXIST) `touch ALSO_NOT_EXIST`"
        self.write("# plain file\n")
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

    def test_unusual_line_breaks_are_left_for_the_editor(self):
        for text in ["A=1\rKEY=old\rB=2\r", "KEY=old\rB=2\n", "A=1\x0cKEY=old\n", "A=1\u2028KEY=old\n"]:
            self.write(text)
            before = self.store.env_path.read_bytes()
            with self.assertRaisesRegex(ValueError, "unusual line breaks.*godmode edit"):
                self.store.set("KEY", "synthetic")
            self.assertEqual(self.store.env_path.read_bytes(), before)

    def test_plan_describes_the_edit_without_values(self):
        self.write("A=1\nexport KEY=fixture_secret\nKEY=dup\r\n")
        plan = self.store.plan("KEY")
        self.assertEqual(plan, {"lines": [2, 3], "sealed": False, "plain": False, "kept_cr": False, "crlf": False, "separate": False})
        self.assertNotIn("fixture_secret", repr(plan))
        self.write("KEY=old\r\nB=2\r\n")
        self.assertEqual(self.store.plan("KEY")["kept_cr"], True)
        self.assertEqual(self.store.plan("NEW"), {"lines": [], "sealed": False, "plain": False, "kept_cr": False, "crlf": True, "separate": False})

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

    def test_resolves_symlinked_parent_but_refuses_symlinked_home_and_nonregular_file(self):
        (self.root / "actual").mkdir(mode=0o700)
        (self.root / "alias").symlink_to(self.root / "actual", target_is_directory=True)
        Store(self.root / "alias/config").set("KEY", "synthetic")  # A linked parent, like macOS /var.
        self.assertEqual(Store(self.root / "actual/config").values(["KEY"]), {"KEY": "synthetic"})
        (self.root / "linked-home").symlink_to(self.root / "actual/config", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "is a symlink or not a directory"):
            Store(self.root / "linked-home").set("OTHER", "synthetic")
        self.assertEqual(Store(self.root / "actual/config").names(), ["KEY"])
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
        self.assertNotIn(b"KEY=", self.store.env_path.read_bytes())

    def test_new_files_are_sealed_and_read_back_only_through_the_store(self):
        secret = "github_pat_SYNTHETIC_" + "x" * 40
        self.store.set("GH_TOKEN", secret)
        self.store.set("SERVICE_JSON", '{"type": "service_account", "k": "SYNTHETIC"}')
        text = self.store.env_path.read_text()
        self.assertTrue(text.startswith(STORE_SEALED + "\n"))
        self.assertIn("godmode run NAME -- command", text)  # The file explains itself to anyone who reads it.
        self.assertNotIn("SYNTHETIC", text)
        self.assertRegex(text, r"\nGH_TOKEN=sealed:v1:[A-Za-z0-9_-]+\n")
        key = self.store.key_path
        self.assertEqual((stat.S_IMODE(key.stat().st_mode), len(key.read_text().strip())), (0o600, 64))
        self.assertEqual(self.store.values(["GH_TOKEN"]), {"GH_TOKEN": secret})
        self.assertEqual(self.store.values(["SERVICE_JSON"])["SERVICE_JSON"], '{"type":"service_account","k":"SYNTHETIC"}')
        self.assertEqual(self.store.states(), {"GH_TOKEN": "set", "SERVICE_JSON": "set"})
        self.assertEqual(self.store.names(), ["GH_TOKEN", "SERVICE_JSON"])
        # Replacing a key keeps the file sealed and the line in place.
        self.store.set("GH_TOKEN", "replacement_SYNTHETIC_value")
        self.assertEqual(self.store.values(["GH_TOKEN"]), {"GH_TOKEN": "replacement_SYNTHETIC_value"})
        self.assertEqual(self.store.env_path.read_text().count("GH_TOKEN="), 1)
        with self.assertRaisesRegex(ValueError, "MISSING is not saved"):
            self.store.values(["GH_TOKEN", "MISSING"])

    def test_sealed_values_are_bound_to_their_name_and_key(self):
        key, other = os.urandom(32), os.urandom(32)
        token = seal(key, "GH_TOKEN", "synthetic ünïcode value")
        self.assertTrue(token.startswith(SEAL_PREFIX))
        self.assertNotEqual(token, seal(key, "GH_TOKEN", "synthetic ünïcode value"))  # A fresh nonce each time.
        self.assertEqual(unseal(key, "GH_TOKEN", token), "synthetic ünïcode value")
        for name, use, damaged in (("OTHER_TOKEN", key, token), ("GH_TOKEN", other, token),
                                   ("GH_TOKEN", key, token[:-2] + ("AA" if token[-2:] != "AA" else "BB")),
                                   ("GH_TOKEN", key, SEAL_PREFIX + "AAAA")):
            with self.assertRaises(ValueError):
                unseal(use, name, damaged)
        self.store.set("GH_TOKEN", "synthetic")
        self.store.key_path.unlink()
        with self.assertRaisesRegex(ValueError, "seal.key is missing"):
            self.store.values(["GH_TOKEN"])
        self.store.key_path.write_text("00" * 32 + "\n")
        self.store.key_path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "mode 0600"):
            self.store.values(["GH_TOKEN"])

    def test_plain_text_keys_move_into_a_sealed_file(self):
        self.write("# my note\nZETA_TOKEN=zeta_SYNTHETIC_1 \nALPHA_KEY='alpha SYNTHETIC two'\nEMPTY=\nexport GMAIL_USER=me@example.com\n")
        before = dict(self.store.values(["ZETA_TOKEN", "ALPHA_KEY", "GMAIL_USER"]))
        target = Store(self.root / "home")
        self.assertEqual(move_and_seal(self.store, target), (3, 1))  # Three keys, one comment line.
        sealed = target.env_path.read_text()
        self.assertNotIn("SYNTHETIC", sealed)
        self.assertNotIn("me@example.com", sealed)
        self.assertNotIn("my note", sealed)  # Free text never goes under the sealed header.
        names = [line.split("=")[0] for line in sealed.splitlines() if "=" in line and not line.startswith("#")]
        self.assertEqual(names, ["ALPHA_KEY", "GMAIL_USER", "ZETA_TOKEN"])  # Sorted; the blank one is dropped.
        self.assertEqual(target.values(list(before)), before)
        self.assertEqual(target.plain_names(), [])
        # The old file keeps no values: where they went, then its own comments as they were.
        old = self.store.env_path.read_text()
        self.assertNotIn("SYNTHETIC", old)
        self.assertNotRegex(old, r"(?m)^[A-Z_]+=")
        self.assertIn(str(target.env_path), old)
        self.assertTrue(old.endswith("kept as they were:\n# my note\n"))
        self.assertEqual(stat.S_IMODE(self.store.env_path.stat().st_mode), 0o600)
        with self.assertRaisesRegex(ValueError, "no plain-text keys"):
            move_and_seal(target, target)

    def test_moving_refuses_anything_it_cannot_carry_exactly(self):
        target = Store(self.root / "home")
        known = ["GMAIL_USER", "GMAIL_APP_PASSWORD"]
        for text, reason in (("A=1\nA=2\n", "A is saved more than once"),
                             ("A=two words\n", r"line 1 \(A\) has unquoted spaces"),
                             ("# ok\nA=SYNTHETIC_1 # note SYNTHETIC_2\n", r"line 2 \(A\) has a comment after its value"),
                             ("A=1\nSTRAY-NAME=SYNTHETIC\nB: SYNTHETIC\nSYNTHETIC\n", "line 2 is not NAME=value; line 3 is not"),
                             ("GMAIL_USER=me@example.comGMAIL_APP_PASSWORD=SYNTHETIC\n", r"line 1 \(GMAIL_USER\) also holds GMAIL_APP_PASSWORD="),
                             ("A_JSON=SYNTHETIC\n", r"line 1 \(A_JSON\): This key needs the JSON")):
            with self.subTest(reason=reason):
                self.write(text)
                with self.assertRaisesRegex(ValueError, "Nothing was changed. .*" + reason) as caught:
                    move_and_seal(self.store, target, known)
                self.assertNotIn("SYNTHETIC", str(caught.exception))  # Line numbers and names, never values.
                self.assertEqual(self.store.env_path.read_text(), text)
                self.assertFalse(target.env_path.exists())
        self.assertEqual(self.store.plain_names(), ["A_JSON"])  # Still offered, so migrate names the line.
        # A leading byte-order mark is not part of the first name.
        self.write("\ufeffBOM_KEY=bom_SYNTHETIC\n")
        self.assertEqual(self.store.plain_names(), ["BOM_KEY"])
        self.assertEqual(move_and_seal(self.store, target), (1, 0))
        self.assertEqual(target.values(["BOM_KEY"]), {"BOM_KEY": "bom_SYNTHETIC"})
        # Moving joins keys already sealed in the target. A name in both must agree.
        self.write("A=moved_SYNTHETIC\nBOM_KEY=different_SYNTHETIC\n")
        with self.assertRaisesRegex(ValueError, "BOM_KEY has a different value in"):
            move_and_seal(self.store, target)
        self.assertIn("A=moved_SYNTHETIC", self.store.env_path.read_text())
        self.assertNotIn("A=", target.env_path.read_text())
        # An interrupted move (the target written, the old file not yet emptied) finishes on the next run.
        self.write("A=moved_SYNTHETIC\nBOM_KEY=bom_SYNTHETIC\n")
        already = [line for line in target.env_path.read_text().splitlines() if line.startswith("BOM_KEY=")]
        self.assertEqual(move_and_seal(self.store, target), (2, 0))
        self.assertEqual([line for line in target.env_path.read_text().splitlines() if line.startswith("BOM_KEY=")],
                         already)  # A key already sealed there is left exactly as it was.
        self.assertEqual(target.values(["A", "BOM_KEY"]), {"A": "moved_SYNTHETIC", "BOM_KEY": "bom_SYNTHETIC"})
        self.assertNotIn("SYNTHETIC", self.store.env_path.read_text() + target.env_path.read_text())
        self.assertEqual(target.env_path.read_text().count("BOM_KEY="), 1)
        # A plain value added to a sealed file by hand is sealed where it is.
        sealed_text = target.env_path.read_text()
        with open(target.env_path, "a") as extra:
            extra.write("# old: SYNTHETIC_in_a_note\nHAND_ADDED=hand_SYNTHETIC\n")
        self.assertEqual((target.plain_names(), target.loose()), (["HAND_ADDED"], 2))
        lines = len(sealed_text.splitlines())
        with self.assertRaisesRegex(ValueError, "line %d is a comment, which a sealed file cannot keep" % (lines + 1)):
            move_and_seal(target, target)  # A note cannot be sealed, and the header says the file shows no keys.
        target.env_path.write_text(sealed_text + "HAND_ADDED=hand_SYNTHETIC\n")
        self.assertEqual(move_and_seal(target, target), (1, 0))
        self.assertEqual(target.values(["HAND_ADDED"]), {"HAND_ADDED": "hand_SYNTHETIC"})
        self.assertNotIn("SYNTHETIC", target.env_path.read_text())
        self.assertEqual(target.loose(), 0)
        self.assertIsNone(plain_source(target, explicit=True))
        with open(target.env_path, "a") as extra:  # A note alone, with no plain value.
            extra.write("# old: SYNTHETIC_note\n")
        self.assertEqual((target.plain_names(), target.loose()), ([], 1))
        self.assertEqual(plain_source(target, explicit=True), (target, target))
        with self.assertRaisesRegex(ValueError, "is a comment, which a sealed file cannot keep"):
            move_and_seal(target, target)
        target.env_path.write_text(target.env_path.read_text().replace("# old: SYNTHETIC_note\n", ""))
        # A blank NAME= beside a hand-added value: the value is sealed and the name kept once.
        with open(target.env_path, "a") as extra:
            extra.write("BLANK_FIRST=\nBLANK_FIRST=blank_SYNTHETIC\n")
        self.assertEqual(move_and_seal(target, target), (1, 0))
        self.assertEqual(target.env_path.read_text().count("BLANK_FIRST="), 1)
        self.assertEqual(target.values(["BLANK_FIRST"]), {"BLANK_FIRST": "blank_SYNTHETIC"})
        # A key rotated by appending a plain line is still found, and the duplicate is named.
        with open(target.env_path, "a") as extra:
            extra.write("HAND_ADDED='rotated_SYNTHETIC'\n")
        self.assertEqual(target.plain_names(), ["HAND_ADDED"])
        self.assertEqual(plain_source(target, explicit=True), (target, target))
        with self.assertRaisesRegex(ValueError, "HAND_ADDED is saved more than once"):
            move_and_seal(target, target)
        target.env_path.write_text(sealed_text + "HAND_ADDED=hand_SYNTHETIC\n")
        move_and_seal(target, target)
        # Sealing a plain file in place, without moving.
        self.write("A=in_place_SYNTHETIC\n")
        self.assertEqual(move_and_seal(self.store, self.store), (1, 0))
        self.assertNotIn("SYNTHETIC", self.store.env_path.read_text())
        self.assertEqual(self.store.values(["A"]), {"A": "in_place_SYNTHETIC"})

    def test_a_home_with_a_seal_key_stays_sealed_and_never_gets_a_second_key(self):
        self.store.set("A", "first_SYNTHETIC")
        for left in ("\n", "# my notes\n"):  # Every line, or the header and every key, deleted in an editor.
            self.store.env_path.write_text(left)
            self.assertTrue(self.store.sealed())
            self.store.set("B", "second_SYNTHETIC")
            self.assertNotIn("SYNTHETIC", self.store.env_path.read_text())
            self.assertTrue(self.store.env_path.read_text().startswith(STORE_SEALED + "\n"))  # The header is back.
            self.assertEqual(self.store.values(["B"]), {"B": "second_SYNTHETIC"})
        self.store.key_path.unlink()  # Sealed values whose key is gone: refuse rather than start a new key.
        with self.assertRaisesRegex(ValueError, "seal.key is missing"):
            self.store.set("C", "third_SYNTHETIC")
        self.assertFalse(self.store.key_path.exists())
        self.assertNotIn("C=", self.store.env_path.read_text())

    def test_a_refused_seal_leaves_no_new_seal_key(self):
        target = Store(self.root / "home")
        target.config_dir.mkdir(mode=0o700)
        target.env_path.write_text("A=target_SYNTHETIC\n")  # A plain target holding another value.
        target.env_path.chmod(0o600)
        self.write("A=source_SYNTHETIC\n")
        with self.assertRaisesRegex(ValueError, "A has a different value"):
            move_and_seal(self.store, target)
        self.assertFalse(target.key_path.exists())
        self.assertFalse(target.sealed())
        import godmode_store
        self.write("BIG=" + "x" * 100 + "\n")
        with mock.patch.object(godmode_store, "STORE_MAX_SIZE", 300):  # Sealing makes it too large to save.
            with self.assertRaisesRegex(ValueError, "would exceed"):
                move_and_seal(self.store, self.store)
        self.assertFalse(self.store.key_path.exists())

    def test_the_old_home_is_used_only_while_it_holds_keys(self):
        with mock.patch.dict(os.environ, {"HOME": str(self.root)}, clear=True):
            legacy = self.root / ".config/godmode"
            legacy.mkdir(parents=True, mode=0o700)
            (self.root / ".config").chmod(0o700)
            for text in ("", "GH_TOKEN=\nCLOUDFLARE_API_TOKEN= # blank\n",
                         "# Godmode keys moved to /x/.godmode/.env.godmode and are sealed there.\n"):
                (legacy / ".env.godmode").write_text(text)
                self.assertEqual(Store().config_dir, self.root / ".godmode")
            (legacy / ".env.godmode").write_text("# moved\nexport GH_TOKEN='SYNTHETIC'\n")
            (legacy / ".env.godmode").chmod(0o600)
            self.assertEqual(Store().config_dir, legacy)
            Store().set("NEW_KEY", "new_SYNTHETIC")  # Kept in plain text there until moved.
            self.assertIn("NEW_KEY=new_SYNTHETIC", (legacy / ".env.godmode").read_text())
            self.assertFalse((legacy / "seal.key").exists())
            # Moving again: Godmode's own 'moved to' line is not counted as your comment.
            (legacy / ".env.godmode").write_text(
                "# Godmode keys moved to %s and are sealed there.\nLATE_KEY=late_SYNTHETIC\n" % (self.root / ".godmode/.env.godmode"))
            source, target = plain_source(Store())
            self.assertEqual(move_and_seal(source, target), (1, 0))
            self.assertEqual((legacy / ".env.godmode").read_text().count("Godmode keys moved to"), 1)

    def test_a_sealed_copy_that_does_not_read_back_changes_nothing(self):
        import godmode_store
        real = godmode_store.seal
        target = Store(self.root / "home")
        broken = lambda key, name, value: real(key, name + "_WRONG", value)  # Bound to the wrong name.
        self.write("A=plain_SYNTHETIC\n")
        with mock.patch.object(godmode_store, "seal", broken):
            with self.assertRaisesRegex(ValueError, "did not read back correctly"):
                move_and_seal(self.store, target)
            self.assertFalse(target.env_path.exists())
            self.assertFalse(target.key_path.exists())
            self.assertEqual(self.store.env_path.read_text(), "A=plain_SYNTHETIC\n")
            with self.assertRaisesRegex(ValueError, "did not read back correctly"):
                move_and_seal(self.store, self.store)  # In place: the plain file stays as it was.
            self.assertEqual(self.store.env_path.read_text(), "A=plain_SYNTHETIC\n")
            self.assertFalse(self.store.key_path.exists())
        self.assertEqual(move_and_seal(self.store, target), (1, 0))

    def test_a_sealed_home_holds_a_signpost_for_agents(self):
        guide = self.store.config_dir / STORE_GUIDE_NAME
        self.store.set("A", "a_SYNTHETIC")
        self.assertIn("godmode run", guide.read_text())
        self.assertNotIn("SYNTHETIC", guide.read_text())
        guide.write_text("my own notes\n")  # Never overwritten.
        self.store.set("B", "b_SYNTHETIC")
        self.assertEqual(guide.read_text(), "my own notes\n")
        # A plain home gets none, a home sealed by a move does, and a Git checkout never gets an untracked file.
        plain = Store(self.root / "plain")
        plain.config_dir.mkdir(mode=0o700)
        plain.env_path.write_text("A=1\n")
        plain.env_path.chmod(0o600)
        plain.set("B", "b_SYNTHETIC")
        self.assertFalse((plain.config_dir / STORE_GUIDE_NAME).exists())
        moved = Store(self.root / "moved")
        move_and_seal(plain, moved)
        self.assertTrue((moved.config_dir / STORE_GUIDE_NAME).exists())
        self.assertFalse((plain.config_dir / STORE_GUIDE_NAME).exists())
        checkout = Store(self.root / "checkout")
        checkout.config_dir.mkdir(mode=0o700)
        env = {"PATH": os.environ.get("PATH", ""), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
        subprocess.run(["git", "init", "-q", str(checkout.config_dir)], env=env, check=True)
        (checkout.config_dir / ".gitignore").write_text(".env.godmode\nseal.key\n")
        checkout.set("A", "a_SYNTHETIC")
        self.assertFalse((checkout.config_dir / STORE_GUIDE_NAME).exists())

    def test_moving_into_blank_names_fills_them_once(self):
        target = Store(self.root / "home")
        target.config_dir.mkdir(mode=0o700)
        target.env_path.write_text("A=\nB=\nA=\n")  # A template of blank names, one listed twice.
        target.env_path.chmod(0o600)
        self.write("A=a_SYNTHETIC\n")
        self.assertEqual(move_and_seal(self.store, target), (1, 0))
        text = target.env_path.read_text()
        self.assertEqual((text.count("A="), text.count("B=\n")), (1, 1))
        self.assertLess(text.index("A="), text.index("B="))  # Filled in where it was listed.
        self.assertEqual(target.values(["A"]), {"A": "a_SYNTHETIC"})

    def test_a_problem_in_the_old_file_names_that_file(self):
        with mock.patch.dict(os.environ, {"HOME": str(self.root)}, clear=True):
            legacy = Store(self.root / ".config/godmode")
            legacy.config_dir.mkdir(parents=True, mode=0o700)
            (self.root / ".config").chmod(0o700)
            home = Store(self.root / ".godmode")
            home.set("A", "a_SYNTHETIC")
            with open(home.env_path, "a") as extra:
                extra.write("EXTRA=extra_SYNTHETIC\n")
            legacy.env_path.write_text("# only a note\n")
            legacy.env_path.chmod(0o644)  # Not a key home: no value, so it is not even read.
            self.assertEqual([found.config_dir for found in plain_source(Store())], [home.config_dir] * 2)
            legacy.env_path.write_text("B=b_SYNTHETIC\n")  # Holds a value but is unsafe to read.
            with self.assertRaisesRegex(ValueError, "^" + str(legacy.env_path) + ": The credential file must be yours"):
                plain_source(Store())

    def test_sealing_finds_plain_keys_in_the_old_home(self):
        with mock.patch.dict(os.environ, {"HOME": str(self.root)}, clear=True):
            legacy = Store(self.root / ".config/godmode")
            legacy.config_dir.mkdir(parents=True, mode=0o700)
            (self.root / ".config").chmod(0o700)
            self.assertIsNone(plain_source(Store()))
            legacy.env_path.write_text("A=old_SYNTHETIC\n")
            legacy.env_path.chmod(0o600)
            source, target = plain_source(Store())
            self.assertEqual((source.config_dir, target.config_dir), (legacy.config_dir, self.root / ".godmode"))
            Store(self.root / ".godmode").set("B", "new_SYNTHETIC")  # Moved part way: still offered.
            source, target = plain_source(Store())
            self.assertEqual((source.config_dir, target.config_dir), (legacy.config_dir, self.root / ".godmode"))
            explicit = Store(legacy.config_dir)
            self.assertEqual(plain_source(explicit, explicit=True), (explicit, explicit))
            move_and_seal(source, target)
            self.assertIsNone(plain_source(Store()))

    def test_default_home_preserves_legacy_configuration(self):
        with mock.patch.dict(os.environ, {"HOME": str(self.root)}, clear=True):
            fresh = Store()
            self.assertEqual(fresh.config_dir, self.root / ".godmode")
            self.assertFalse(fresh.config_dir.exists())
            legacy = self.root / ".config/godmode"
            legacy.mkdir(parents=True)
            (self.root / ".godmode/bin").mkdir(parents=True)
            (self.root / ".godmode/env").write_text("# shell setup")
            self.assertEqual(Store().config_dir, self.root / ".godmode")  # A rules checkout alone is not a key home.
            (legacy / ".env.godmode").write_text("A=1\n")
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
        with self.assertRaisesRegex(ValueError, "Keep seal.key ignored"):
            self.store.set("KEY", "synthetic")  # Sealing would put seal.key in the checkout.
        self.assertFalse(self.store.key_path.exists())
        (self.store.config_dir / ".gitignore").write_text(".env.godmode\nseal.key\n")
        self.store.set("KEY", "synthetic")
        subprocess.run(["git", "-C", str(self.store.config_dir), "add", "-f", ".env.godmode"], env=env, check=True)
        with self.assertRaises(ValueError):
            self.store.set("KEY", "replacement")


if __name__ == "__main__":
    unittest.main()
