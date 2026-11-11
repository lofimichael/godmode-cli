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

DOT = "•".encode()
DOTS = DOT * 5

TERM_HARNESS = '''
import hashlib, os, termios
import godmode_terminal
from godmode_terminal import read_secret, read_choice, Cancelled, Prompt

class Strict(Prompt):
    actions = {'?': lambda: ['HELP_ROWS_PRINTED']}
    def ready(self, value):
        return value != 'not yet'

godmode_terminal.TERM_MAX_INPUT = int(os.environ.get("MAX_FIELD_SIZE", 1024 * 1024))
before = termios.tcgetattr(0)
try:
    if os.environ['PROMPT_MODE'] == 'choice':
        value = read_choice('Select provider:', ['', 'github', 'q', 'café'])
    elif os.environ['PROMPT_MODE'] == 'strict':
        value = read_secret(Strict('Paste key (hidden; Enter saves):'))
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
        self.wait(b"Select provider:" if mode == "choice" else b"Paste key")

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

    def until(self, predicate):
        end = time.monotonic() + 5
        while not predicate():
            if time.monotonic() > end:
                raise AssertionError("prompt state timed out; capture withheld")
            self.drain(0.03)

    def wait(self, marker, start=0):
        end = time.monotonic() + 5
        while marker not in self.output[start:]:
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
        session.wait(DOTS)
        self.assertIsNone(session.process.poll())
        self.assertNotIn(b"ACCEPTED", session.output)
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

    def test_mask_shows_at_most_a_quarter_and_three_characters_per_end(self):
        with patch.object(terminal, "glyph", lambda fancy, plain: fancy):
            self.assertEqual(terminal.mask(""), "")
            self.assertEqual(terminal.mask("short12"), "•••••")
            self.assertEqual(terminal.mask("abcdefgh"), "a•••••h")
            self.assertEqual(terminal.mask("abcdefghijklmnop"), "ab•••••op")
            self.assertEqual(terminal.mask("sk_test_" + "x" * 30 + "123"), "sk_•••••123")
            self.assertEqual(terminal.mask("sk_test_" + "x" * 30 + "123", reveal=False), "•" * 24)
            self.assertEqual(terminal.mask("abc", reveal=False), "•••")
            self.assertEqual(terminal.mask(" b\ncdefghijklm\tn"), "•b" + "•••••" + "•n")
            self.assertEqual(terminal.mask("é" * 30), "•" * 11)
        for length in range(0, 80):
            value = "".join(chr(65 + i % 26) for i in range(length))
            shown = terminal.mask(value).replace("•", "").replace("*", "")
            self.assertLessEqual(len(shown), min(6, length // 4))
            self.assertLessEqual(len(terminal.mask(value)), 11)
            self.assertEqual(terminal.mask(value, reveal=False).strip("•*"), "")

    def test_pasted_value_shows_its_ends_but_typing_and_editing_do_not(self):
        pasted = self.start()
        secret = "sk_live_SYNTHETIC_MIDDLE_ONLY_987"
        pasted.send(b"\x1b[200~" + secret.encode() + b"\x1b[201~")
        pasted.wait("sk_•••••987".encode())
        pasted.send(b"\r")
        pasted.accepted(secret)
        self.assertNotIn(b"SYNTHETIC_MIDDLE", pasted.output)
        typed = self.start()
        for char in b"typed_SYNTHETIC_only_42":
            typed.send(bytes([char]))
            typed.drain(0.02)
        typed.send(b"\r")
        typed.accepted("typed_SYNTHETIC_only_42")
        self.assertIn("•".encode() * 23, typed.output)
        for leak in (b"t" + DOT, DOT + b"2", b"typ", b"_42"):
            self.assertNotIn(leak, typed.output)
        edited = self.start()
        short = "sk_live_SYNTH_MID_9876"
        edited.send(b"\x1b[200~" + short.encode() + b"\x1b[201~")
        edited.wait("sk•••••76".encode())
        for count in range(1, 4):
            mark = len(edited.output)
            edited.send(b"\x7f")  # One at a time, so every intermediate state is drawn.
            edited.until(lambda: bytes(edited.output[mark:]).endswith(
                "› ".encode() + DOT * (len(short) - count)))
            drawn = bytes(edited.output[mark:])
            self.assertNotIn(b"sk", drawn)
            self.assertNotIn(DOT + short[-2 - count:-count].encode(), drawn)
        edited.send(b"\r")
        edited.accepted(short[:-3])

    def test_pasting_again_replaces_and_help_keys_never_change_a_paste(self):
        session = self.start("strict")
        session.send(b"\x1b[200~first_SYNTHETIC_value_0001\x1b[201~")
        session.wait("fir•••••001".encode())
        session.send(b"\x1b[200~second_SYNTHETIC_value_0002\x1b[201~")
        session.wait("sec•••••002".encode())
        session.send(b"?")
        session.wait(b"HELP_ROWS_PRINTED")
        session.send(b"\r")
        session.accepted("second_SYNTHETIC_value_0002")
        self.assertNotIn(b"first_SYNTHETIC", session.output)
        typed = self.start()
        typed.send(b"ab")
        typed.drain(0.1)
        typed.send(b"\x1b[200~cd\x1b[201~\r")
        typed.accepted("abcd")  # A paste after typing appends, and stays fully masked.
        self.assertNotIn(b"ab" + DOTS, typed.output)

    def test_enter_waits_until_ready_and_actions_only_run_before_input(self):
        session = self.start("strict")
        session.send(b"?")
        session.wait(b"HELP_ROWS_PRINTED")
        session.send(b"not yet\r")
        session.drain(0.2)
        self.assertNotIn(b"ACCEPTED", session.output)
        self.assertIn(b"\a", session.output)
        session.send(b"?\r")
        session.accepted("not yet?")
        self.assertEqual(session.output.count(b"HELP_ROWS_PRINTED"), 1)
        self.assertIn(b"\x1b[?2004l", session.output)

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
