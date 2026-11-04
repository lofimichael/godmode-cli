"""PTY checks use synthetic values only and never print the captured input."""
import fcntl
import hashlib
import os
from pathlib import Path
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import godmode_terminal as terminal

TERM_HARNESS = '''
import hashlib, os, termios
import godmode_terminal
from godmode_terminal import read_secret, read_choice, Cancelled
godmode_terminal.TERM_MAX_INPUT = int(os.environ.get("MAX_FIELD_SIZE", 1024 * 1024))
before = termios.tcgetattr(0)
try:
    if os.environ['PROMPT_MODE'] == 'choice':
        value = read_choice('Select provider:', ['', 'github', 'q', 'café'])
    else:
        value = read_secret('Paste key (hidden; Enter saves):')
    print('ACCEPTED ' + hashlib.sha256(value.encode()).hexdigest())
except Cancelled:
    print('CANCELLED')
except ValueError:
    print('REJECTED')
finally:
    print('RESTORED ' + str(termios.tcgetattr(0) == before))
'''


class Session:
    def __init__(self, mode="secret", limit=1024 * 1024):
        self.master, self.slave = os.openpty()
        # A new PTY starts at 0x0. Give it a real terminal geometry instead of
        # depending on Python-version-specific get_terminal_size fallbacks.
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
        os.set_blocking(self.master, False)
        self.output = bytearray()
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
               "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "lib"),
               "TERM": "xterm-256color", "PROMPT_MODE": mode, "MAX_FIELD_SIZE": str(limit)}
        self.process = subprocess.Popen([sys.executable, "-c", TERM_HARNESS],
                                        stdin=self.slave, stdout=self.slave,
                                        stderr=self.slave, env=env)
        self.wait(b"> ")

    def send(self, data):
        pending = memoryview(data)
        deadline = time.monotonic() + 5
        while pending:
            if time.monotonic() > deadline:
                raise AssertionError("PTY write timed out; capture withheld")
            try:
                pending = pending[os.write(self.master, pending):]
            except BlockingIOError:
                self.drain(0.02)

    def drain(self, duration=0.1):
        end = time.monotonic() + duration
        while time.monotonic() < end:
            if select.select([self.master], [], [], 0.02)[0]:
                self.output.extend(os.read(self.master, 65536))

    def wait(self, marker):
        end = time.monotonic() + 5
        while marker not in self.output:
            if time.monotonic() > end:
                raise AssertionError("prompt state timed out; capture withheld")
            self.drain(0.03)

    def accepted(self, expected):
        self.wait(b"RESTORED True")
        self.process.wait(timeout=5)
        digest = hashlib.sha256(expected.encode()).hexdigest().encode()
        assert b"ACCEPTED " + digest in self.output, "wrong value; capture withheld"
        assert b"\x1b[?2004l" in self.output
        assert self.process.returncode == 0

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=5)
        os.close(self.master)
        os.close(self.slave)


class TerminalTests(unittest.TestCase):
    def start(self, mode="secret", limit=1024 * 1024):
        session = Session(mode, limit)
        self.addCleanup(session.close)
        return session

    def test_multiline_bracketed_paste_waits_for_enter_and_stays_hidden(self):
        session = self.start()
        secret = '{\n  "key": "SYNTHETIC_ONLY_ä_42"\n}'
        # Deliberately split both bracketed-paste markers across reads.
        session.send(b"\x1b[20")
        time.sleep(0.02)
        session.send(b"0~" + secret.encode() + b"\x1b[20")
        time.sleep(0.02)
        session.send(b"1~")
        session.wait(b"*" * len(secret))
        self.assertIsNone(session.process.poll())
        self.assertNotIn(b"ACCEPTED", session.output)
        self.assertIn(b"****", session.output)
        self.assertNotIn(b"SYNTHETIC_ONLY", session.output)
        session.send(b"\r")
        session.accepted(secret)

    def test_large_json_and_input_limit(self):
        session = self.start()
        secret = '{\n "synthetic": "' + 'x' * 14000 + '"\n}'
        session.send(b"\x1b[200~" + secret.encode() + b"\x1b[201~")
        session.drain()
        self.assertNotIn(b"ACCEPTED", session.output)
        self.assertNotIn(b"synthetic", session.output)
        session.send(b"\r")
        session.accepted(secret)
        too_large = self.start(limit=32)
        too_large.send(b"\x1b[200~" + b"x" * 40 + b"\x1b[201~")
        too_large.wait(b"RESTORED True")
        self.assertIn(b"REJECTED", too_large.output)

    def test_editing_unicode_and_arrow_keys(self):
        session = self.start()
        session.send("éx".encode() + b"\x7f\x1b[D")
        session.send(b"\r")
        session.accepted("é")
        cleared = self.start()
        cleared.send("SYNTHETIC_DELETE_emoji_😀".encode() + b"\x15")
        cleared.send("new😀".encode() + b"\x7f\r")
        cleared.accepted("new")
        self.assertNotIn(b"SYNTHETIC_DELETE", cleared.output)

    def test_choice_rejects_accidental_secret_paste_without_echo(self):
        session = self.start("choice")
        accidental = b"SYNTHETIC_MISPLACED_credential_9437"
        session.send(b"\x1b[200~" + accidental + b"\x1b[201~github\r")
        session.accepted("github")
        self.assertNotIn(accidental, session.output)
        unicode_choice = self.start("choice")
        unicode_choice.send("café\r".encode())
        unicode_choice.accepted("café")

    def test_cancel_and_signal_restore_terminal(self):
        for cancel in (b"\x1b", b"\x03", b"\x04"):
            with self.subTest(cancel=cancel):
                session = self.start()
                session.send(b"SYNTHETIC_CANCEL" + cancel)
                session.wait(b"RESTORED True")
                self.assertIn(b"CANCELLED", session.output)
                self.assertNotIn(b"SYNTHETIC_CANCEL", session.output)
        for number in (signal.SIGTERM, signal.SIGHUP):
            session = self.start()
            os.kill(session.process.pid, number)
            session.wait(b"RESTORED True")
            self.assertIn(b"CANCELLED", session.output)

    def test_invalid_utf8_and_nul_restore_terminal(self):
        for value in (b"\xff\r", b"\x1b[200~bad\0paste\x1b[201~"):
            session = self.start()
            session.send(value)
            session.wait(b"RESTORED True")
            self.assertIn(b"REJECTED", session.output)

    def test_color_opt_out_and_redirected_text(self):
        class Output:
            def __init__(self, tty):
                self.tty = tty
            def isatty(self):
                return self.tty
        with patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=True):
            self.assertTrue(terminal.color_enabled(Output(True)))
            self.assertFalse(terminal.color_enabled(Output(False)))
            for name, value in (("NO_COLOR", ""), ("CLICOLOR", "0"), ("TERM", "dumb")):
                with patch.dict(os.environ, {name: value}):
                    self.assertFalse(terminal.color_enabled(Output(True)))


if __name__ == "__main__":
    unittest.main()
