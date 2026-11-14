"""Real native-terminal checks. Synthetic homes only; no account access."""
import fcntl
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import termios
import unittest

from pty_support import Terminal, plain

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / 'target/godmode-native'


class NativeTerminal(Terminal):
    def done(self, expected=0):
        self.wait(lambda: self.process.poll() is not None)
        self.drain()
        assert self.process.returncode == expected, 'unexpected native exit status'
        match = re.search(rb'__PTY_FLAGS=(\d+)__', self.capture)
        assert match, 'native terminal wrapper did not report flags'
        flags = termios.ECHO | termios.ICANON | termios.ISIG
        assert int(match[1]) & flags == self.original[3] & flags, 'native terminal flags not restored'
        assert b'\x1b[?2004l' in self.capture, 'native bracketed paste not disabled'
        if b'\x1b[?1049h' in self.capture:
            assert b'\x1b[?1049l' in self.capture, 'native alternate screen not restored'


@unittest.skipUnless(BINARY.exists(), 'Build the native candidate first.')
class NativeCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / '.godmode'
        self.home.mkdir(mode=0o700)
        (self.home / 'intro.seen').touch(mode=0o600)
        self.env = {'HOME': str(self.root), 'PATH': os.environ['PATH'], 'TERM': 'xterm-256color',
                    'GODMODE_NO_MOTION': '1', 'CODEX_HOME': str(self.root / '.codex'),
                    'COPILOT_HOME': str(self.root / '.copilot')}
        self.sessions = []

    def tearDown(self):
        for session in self.sessions:
            session.close()
        self.temp.cleanup()

    def tty(self, *args, cols=80, rows=24):
        terminal = NativeTerminal([str(BINARY), *args], self.env, cols=cols, rows=rows)
        self.sessions.append(terminal)
        return terminal

    def command(self, *args, data=None):
        return subprocess.run([str(BINARY), *args], env=self.env, input=data,
                              text=True, capture_output=True)

    def test_masked_key_round_trip_and_no_paste_submission(self):
        token = 'synthetic_NATIVE_PRIVATE_VALUE_12345'
        terminal = self.tty('set', 'DEMO_TOKEN')
        terminal.expect('Paste your token:')
        terminal.paste(token + '\n')
        terminal.expect('syn•••••345')
        terminal.settle(.1)
        self.assertFalse((self.home / '.env.godmode').exists())
        self.assertNotIn(b'NATIVE_PRIVATE_VALUE', terminal.capture)
        terminal.send(b'\r')
        terminal.done()
        result = self.command('run', 'DEMO_TOKEN', '--', sys.executable, '-c',
                              'import os,sys;sys.exit(0 if os.environ["DEMO_TOKEN"].startswith("synthetic_NATIVE") else 8)')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_edited_public_field_paste_stays_masked(self):
        terminal = self.tty('set', 'GMAIL_USER')
        terminal.expect('GMAIL_USER')
        terminal.paste('synthetic_PRIVATE_PASTED_VALUE@example.test')
        terminal.settle(.15)
        terminal.send(b'\x7fx')
        terminal.settle(.15)
        self.assertNotIn(b'PRIVATE_PASTED', terminal.capture)
        terminal.send(b'\r')
        terminal.done()
        self.assertNotIn(b'PRIVATE_PASTED', terminal.capture)

    def test_replace_cancel_keeps_exact_store(self):
        self.assertEqual(self.command('set', 'DEMO_TOKEN', '--stdin', data='synthetic_ORIGINAL_VALUE').returncode, 0)
        before = (self.home / '.env.godmode').read_bytes()
        terminal = self.tty('set', 'DEMO_TOKEN')
        terminal.expect('Replace')
        terminal.paste('synthetic_CANCELLED_PRIVATE_VALUE')
        terminal.expect('syn•••••LUE')
        terminal.send(b'\x03')
        terminal.done(130)
        self.assertEqual((self.home / '.env.godmode').read_bytes(), before)
        self.assertNotIn(b'CANCELLED_PRIVATE', terminal.capture)

    def test_agents_keep_existing_bytes_and_repeat_is_idempotent(self):
        target = self.root / '.codex/AGENTS.md'
        target.parent.mkdir()
        original = b'# Synthetic existing rules\r\nKeep this exact prefix.'
        target.write_bytes(original)
        terminal = self.tty('agents', cols=100, rows=40)
        terminal.expect('These files will be modified:')
        terminal.expect('godmode:end')
        terminal.send(b'\r')
        terminal.settle(.3)
        if terminal.process.poll() is None:
            terminal.send(b'\x1b')
        terminal.done()
        after = target.read_bytes()
        self.assertTrue(after.startswith(original))
        self.assertEqual(after.count(b'godmode:start'), 1)
        again = self.tty('agents', cols=100, rows=40)
        again.expect('already added')
        again.send(b'\x1b')
        again.done()
        self.assertEqual(target.read_bytes(), after)

    def test_resize_hides_write_until_preview_fits(self):
        terminal = self.tty('set', 'DEMO_TOKEN')
        terminal.expect('Paste your token:')
        terminal.paste('synthetic_RESIZE_PRIVATE_12345')
        terminal.expect('syn•••••345')
        fcntl.ioctl(terminal.slave, termios.TIOCSWINSZ, struct.pack('HHHH', 8, 20, 0, 0))
        terminal.settle(.2)
        terminal.send(b'\r')
        terminal.settle(.1)
        self.assertFalse((self.home / '.env.godmode').exists())
        fcntl.ioctl(terminal.slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
        terminal.settle(.2)
        terminal.send(b'\x03')
        terminal.done(130)
        self.assertNotIn(b'RESIZE_PRIVATE', terminal.capture)

    def test_menu_pastes_never_open_a_section(self):
        terminal = self.tty()
        terminal.expect('Setup 0%')
        terminal.paste('synthetic_PASTED_MENU_SECRET\n\n')
        terminal.settle(.15)
        self.assertNotIn(b'PASTED_MENU_SECRET', terminal.capture)
        self.assertFalse((self.home / '.env.godmode').exists())
        self.assertFalse((self.home / 'profile.json').exists())
        terminal.send(b'\x03')
        terminal.done(130)


if __name__ == '__main__':
    unittest.main()
