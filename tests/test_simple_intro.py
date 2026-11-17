"""First-run introduction behavior, exercised in real isolated terminals."""
import fcntl
import os
from pathlib import Path
import re
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import termios
import unittest

from pty_support import Screen, Terminal, plain


REPO = Path(__file__).resolve().parents[1]
WELCOME = "Agents use these keys as you."
MENU = "Esc quit"  # Only the home screen offers to quit.


def complete_intro(session):
    """Accept once after the complete account-access statement is visible."""
    session.expect("Enter accept")
    session.send(b"\r")


class ModularIntroTests(unittest.TestCase):
    bundled = False

    @classmethod
    def setUpClass(cls):
        cls.script = REPO / "godmode.py"
        if cls.bundled:
            build = tempfile.TemporaryDirectory(prefix="godmode-intro-build-")
            cls.addClassCleanup(build.cleanup)
            cls.script = Path(build.name) / "godmode"
            subprocess.run([sys.executable, str(REPO / "scripts/build.py"),
                            "--output", str(cls.script)], check=True,
                           stdout=subprocess.DEVNULL)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="godmode-intro-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.home = self.root / ".godmode"
        self.marker = self.home / "intro.seen"
        self.env = {"HOME": str(self.root), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "TERM": "xterm-256color", "SHELL": "/bin/sh", "NO_COLOR": "1",
                    "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}

    def terminal(self, *args, env=None, cols=110, rows=36):
        session = Terminal([sys.executable, str(REPO / 'tests/engine_fixture.py'), str(self.script), *args],
                           self.env if env is None else env, cols=cols, rows=rows)
        self.addCleanup(session.close)
        return session

    def cli(self, *args, input=None, env=None):
        return subprocess.run([sys.executable, str(REPO / 'tests/engine_fixture.py'), str(self.script), *args],
                              input=input, text=True, capture_output=True,
                              env=self.env if env is None else env,
                              cwd=self.root, timeout=10)

    def okay(self, *args, **kwargs):
        result = self.cli(*args, **kwargs)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def assert_only_marker(self, home=None):
        home = self.home if home is None else home
        marker = home / "intro.seen"
        self.assertEqual(sorted(p.name for p in home.iterdir()), ["intro.seen"])
        self.assertEqual(marker.read_bytes(), b"")
        self.assertEqual(stat.S_IMODE(marker.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(home.stat().st_mode), 0o700)
        self.assertEqual(marker.stat().st_nlink, 1)

    def assert_no_intro(self, session):
        self.assertNotIn(WELCOME, plain(session.capture))
        self.assertNotIn("Enter accept", plain(session.capture))

    def leave_menu(self, session):
        session.expect(MENU)
        session.send(b"\x1b")
        session.expect("Profile 0 optional fields")
        session.done()

    def test_default_and_init_finish_once_without_creating_optional_files(self):
        for route in ((), ("init",), ("onboard",)):
            with self.subTest(route=route):
                home = self.root / (route[0] if route else "default")
                prefix = ("--home", str(home))
                session = self.terminal(*prefix, *route)
                session.expect("Enter accept and set up")
                self.assertFalse(home.exists())
                session.send(b"\r")
                session.expect(MENU)
                self.assertIn('Enter accept and set up', plain(session.capture))
                self.assert_only_marker(home)
                self.leave_menu(session)
                repeated = self.terminal(*prefix, *route)
                repeated.expect(MENU)
                self.assert_no_intro(repeated)
                self.leave_menu(repeated)
                self.assert_only_marker(home)

    def test_explicit_intro_completes_and_replays_without_rewriting_marker(self):
        first = self.terminal("intro")
        complete_intro(first)
        first.done()
        self.assertIn('Enter accept', plain(first.capture))
        self.assertIn('Your accounts. Your consequences.', plain(first.capture))
        self.assertNotIn('accept and set up', plain(first.capture))
        self.assert_only_marker()
        before = self.marker.stat()
        replay = self.terminal("intro")
        complete_intro(replay)
        replay.done()
        self.assertNotIn(MENU, plain(replay.capture))
        after = self.marker.stat()
        self.assertEqual((after.st_ino, after.st_mtime_ns),
                         (before.st_ino, before.st_mtime_ns))
        cancelled = self.terminal("intro")
        cancelled.expect(WELCOME)
        cancelled.send(b"\x1b")
        cancelled.done(130)
        self.assert_only_marker()
        following = self.terminal()
        following.expect(MENU)
        self.assert_no_intro(following)
        self.leave_menu(following)

    def test_escape_exits_without_files(self):
        session = self.terminal()
        session.expect("Enter accept and set up")
        mark = len(session.capture)
        session.send(b"\x1b")
        session.done()  # Esc on the first page of setup leaves quietly: exit 0, nothing printed or saved.
        self.assertNotIn("Cancelled", plain(session.capture[mark:]))
        self.assertNotIn("set up", plain(session.capture[mark:]))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_cancelling_before_acceptance_never_marks_completed(self):
        for cancel in (b"\x03", b"\x04"):
            with self.subTest(cancel=cancel):
                session = self.terminal("intro")
                session.expect("Enter accept")
                self.assertEqual(list(self.root.iterdir()), [])
                session.send(cancel)
                session.done(130)
                self.assertEqual(list(self.root.iterdir()), [])

    def test_typed_and_pasted_secrets_are_never_echoed_or_used_to_advance(self):
        session = self.terminal("intro")
        secret = b"synthetic_SECRET_never_echo_98765"
        session.expect("Enter accept")
        session.send(secret)
        session.send(b"\x1b[20")
        session.send(b"0~" + secret + b"\r\nGODMODE\r\n\x1b[201")
        session.send(b"~")
        session.settle(.04)
        self.assertNotIn(secret, session.capture)
        self.assertIsNone(session.process.poll())
        self.assertFalse(self.marker.exists())
        session.send(b"\r")
        session.done()
        self.assert_only_marker()

    def test_credentials_from_onboarding_do_not_repeat_confirmation(self):
        for revisit in (False, True):
            with self.subTest(revisit=revisit):
                home = self.root / ("return" if revisit else "first")
                prefix = ("--home", str(home))
                if revisit:
                    seen = self.terminal(*prefix, "intro")
                    complete_intro(seen)
                    seen.done()
                session = self.terminal(*prefix)
                if not revisit:
                    complete_intro(session)
                session.expect(MENU)
                mark = len(session.capture)
                session.send(b"\x1b[B\r")  # Active setup is first; Providers is the next row.
                session.after(mark, "GitHub")
                output = plain(session.capture[mark:])
                self.assertNotIn("Enter accept", output)
                self.assertNotIn(WELCOME, output)
                mark = len(session.capture)
                session.send(b"\x1b")
                session.after(mark, MENU)
                session.send(b"\x1b")
                session.done()
                self.assertTrue((home / ".env.godmode").exists())
                self.assertFalse((home / "profile.json").exists())

    def test_direct_commands_keep_their_existing_contract_without_intro(self):
        for route in (("setup",), ("set", "DEMO_TOKEN")):
            with self.subTest(route=route):
                session = self.terminal(*route)
                session.expect("Enter accept · Esc cancel")
                self.assertIn("spend, publish and delete", plain(session.capture))
                session.send(b"\x1b")
                session.done(130)
                self.assertEqual(list(self.root.iterdir()), [])
        profile = self.terminal("profile")
        profile.expect("Your name")
        self.assert_no_intro(profile)
        profile.send(b"\x1b")
        profile.done()
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(self.okay("list"), "")
        self.assertIn("godmode provider", self.okay("help"))
        self.assertEqual(list(self.root.iterdir()), [])
        self.okay("set", "DEMO_TOKEN", "--stdin", input="synthetic_pipe_value")
        self.assertEqual(self.okay("list"), "DEMO_TOKEN\n")
        self.assertFalse(self.marker.exists())
        self.assertFalse((self.home / "profile.json").exists())

    def test_fresh_setup_shows_the_one_consent_and_godmode_then_opens_home(self):
        session = self.terminal("setup")
        session.expect("Enter accept · Esc cancel")
        self.assertFalse(self.home.exists())
        session.send(b"\r")
        session.expect("Another key")
        self.assertTrue(self.marker.exists())
        session.send(b"\x1b")
        session.expect("Profile 0 optional fields")
        session.done()
        following = self.terminal()
        following.expect(MENU)
        self.assert_no_intro(following)
        self.assertNotIn("Enter accept", plain(following.capture))
        self.leave_menu(following)

    def test_home_shows_scope_and_rows_in_every_terminal_mode(self):
        self.home.mkdir(mode=0o700)
        os.close(os.open(self.marker, os.O_WRONLY | os.O_CREAT, 0o600))
        for label, extra in (("no color", {}), ("ascii", {"TERM": "linux"}),
                             ("ascii locale", {"PYTHONIOENCODING": "ascii", "PYTHONUTF8": "0", "LC_ALL": "C"})):
            with self.subTest(mode=label):
                session = self.terminal(env=dict(self.env, **extra), cols=80, rows=24)
                session.expect(MENU)
                session.settle(.1)
                rows = Screen(80).feed(session.capture).lines()
                screen = "\n".join(rows)
                for text in ("Business", "Providers", "Agents", "Done", "Environment default", "~/.godmode", "0 keys saved", "0 notes added"):
                    self.assertIn(text, screen)
                self.assertTrue(all(len(row.rstrip()) <= 79 for row in rows))
                self.assertIsNone(re.search(rb"\x1b\[[0-9;]*m", session.capture))
                if label != "no color":
                    self.assertTrue(all(byte < 128 for byte in session.capture))
                    self.assertIn("Godmode", screen)
                self.assertNotIn("Setup 0%", screen)
                self.assertNotIn("\u2591" * 6, screen)
                self.leave_menu(session)

    def test_legacy_keys_remain_untouched_and_intro_uses_profile_home(self):
        legacy = self.root / ".config" / "godmode"
        legacy.mkdir(parents=True, mode=0o700)
        key = legacy / ".env.godmode"
        original = b"LEGACY_TOKEN='synthetic_legacy_value'\n"
        key.write_bytes(original)
        key.chmod(0o600)
        before = key.stat()
        self.assertEqual(self.okay("path").strip(), str(key))
        session = self.terminal("intro")
        complete_intro(session)
        session.done()
        self.assert_only_marker()
        self.assertEqual(key.read_bytes(), original)
        self.assertEqual(key.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertFalse((legacy / "intro.seen").exists())
        self.assertEqual(self.okay("path").strip(), str(key))

    def test_small_home_keeps_setup_count_and_all_three_components(self):
        self.home.mkdir(mode=0o700)
        os.close(os.open(self.marker, os.O_WRONLY | os.O_CREAT, 0o600))
        session = self.terminal(cols=40, rows=12)
        session.expect(MENU)
        screen = "\n".join(Screen(40).feed(session.capture).lines())
        for text in ("Environment default", "Business", "Providers", "Agents"):
            self.assertIn(text, screen)
        self.assertTrue(all(len(row) <= 39 for row in screen.splitlines()))
        session.send(b"\x1b")
        session.done()

    def test_home_options_select_marker_and_explicit_home_wins(self):
        for variable in ("GODMODE_HOME", "GODMODE_CONFIG_DIR"):
            with self.subTest(variable=variable):
                home = self.root / variable
                session = self.terminal("intro", env=dict(self.env, **{variable: str(home)}))
                complete_intro(session)
                session.done()
                self.assert_only_marker(home)
        chosen = self.root / "chosen home"
        ignored = self.root / "ignored"
        session = self.terminal("--home", str(chosen), "intro",
                                env=dict(self.env, GODMODE_HOME=str(ignored)))
        complete_intro(session)
        session.done()
        self.assert_only_marker(chosen)
        self.assertFalse(ignored.exists())
        self.assertFalse(self.home.exists())

    def test_unsafe_markers_are_rejected_without_clobbering_anything(self):
        self.home.mkdir(mode=0o700)
        unrelated = self.root / "unrelated"
        unrelated.write_bytes(b"do not change")
        for kind in ("nonempty", "symlink"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    self.marker.symlink_to(unrelated)
                else:
                    self.marker.write_bytes(b"not an introduction receipt")
                    self.marker.chmod(0o600)
                session = self.terminal()
                session.expect("intro.seen must be an empty, regular file")
                session.wait(lambda: session.process.poll() is not None)
                session.drain()
                self.assertEqual(session.process.returncode, 2)
                self.assert_no_intro(session)
                self.assertEqual(unrelated.read_bytes(), b"do not change")
                if kind == "symlink":
                    self.assertTrue(self.marker.is_symlink())
                else:
                    self.assertEqual(self.marker.read_bytes(), b"not an introduction receipt")
                self.assertEqual(sorted(p.name for p in self.home.iterdir()), ["intro.seen"])
                self.marker.unlink()

    def test_small_terminal_cannot_advance_until_resized(self):
        session = self.terminal("intro", cols=20, rows=5)
        session.expect("Enlarge")
        session.send(b"\r")
        session.settle(.05)
        self.assertNotIn("Enter accept", plain(session.capture))
        self.assertFalse(self.home.exists())
        mark = len(session.capture)
        fcntl.ioctl(session.slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
        session.after(mark, WELCOME)
        session.send(b"\r")
        session.done()
        self.assert_only_marker()

    def test_no_color_ascii_fallback_and_terminal_restoration(self):
        env = dict(self.env, PYTHONIOENCODING="ascii", PYTHONUTF8="0", LC_ALL="C")
        session = self.terminal("intro", env=env)
        complete_intro(session)
        session.done()
        self.assertIsNone(re.search(rb"\x1b\[[0-9;]*m", session.capture))
        self.assertTrue(all(byte < 128 for byte in session.capture))
        self.assertNotIn(" ? Esc", plain(session.capture))
        self.assertIn(" | Esc", plain(session.capture))
        self.assertIn("G O D M O D E", plain(session.capture))
        self.assertIn(b"\x1b[?25h", session.capture)
        self.assert_only_marker()

    def test_redirected_fails_and_dumb_terminal_uses_plain_acceptance(self):
        for route in (("intro",), (), ("init",)):
            with self.subTest(route=route):
                result = self.cli(*route)
                self.assertEqual(result.returncode, 2)
                self.assertIn("needs a terminal", result.stderr)
        session = self.terminal("intro", env=dict(self.env, TERM="dumb"))
        session.expect("Enter accept")
        self.assertFalse(self.home.exists())
        session.send(b"\r")
        session.done()
        self.assertNotIn(b"\x1b[?25", session.capture)
        self.assertNotIn(b"\x1b[J", session.capture)
        self.assert_only_marker()

    def test_termination_signal_restores_terminal_without_marking_complete(self):
        harness = ("import os,runpy,sys; print('INTRO_CHILD_PID=%d' % os.getpid(), flush=True); "
                   "sys.argv = [sys.argv[1], sys.argv[2], 'intro']; runpy.run_path(sys.argv[0], run_name='__main__')")
        session = Terminal([sys.executable, "-c", harness, str(REPO / 'tests/engine_fixture.py'), str(self.script)], self.env)
        self.addCleanup(session.close)
        session.expect("Enter accept")
        child = re.search(rb"INTRO_CHILD_PID=(\d+)", session.capture)
        self.assertIsNotNone(child)
        os.kill(int(child[1]), signal.SIGTERM)
        session.done(130)
        self.assertEqual(list(self.root.iterdir()), [])


class BundledIntroTests(ModularIntroTests):
    bundled = True


if __name__ == "__main__":
    unittest.main()
