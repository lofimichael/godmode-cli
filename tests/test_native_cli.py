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
from license_support import provision

ROOT = Path(__file__).resolve().parents[1]
# Ordinary UI tests exercise the production candidate. The separate signed-key
# fixture belongs only to test_license_native.py.
BINARY = Path(os.environ.get('GODMODE_TEST_NATIVE_BINARY', ROOT / 'target/godmode-native'))


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
        provision(self.home)
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
        terminal.expect('Business: Automatic')
        terminal.paste('synthetic_PASTED_MENU_SECRET\n\n')
        terminal.settle(.15)
        self.assertNotIn(b'PASTED_MENU_SECRET', terminal.capture)
        self.assertFalse((self.home / '.env.godmode').exists())
        self.assertFalse((self.home / 'profile.json').exists())
        terminal.send(b'\x03')
        terminal.done(130)

    def test_environment_copy_form_selects_an_independent_key_file(self):
        self.assertEqual(self.command('set', 'DEMO_TOKEN', '--stdin', data='synthetic_COPY_SOURCE').returncode, 0)
        self.assertEqual(self.command('context', 'create', 'acme').returncode, 0)
        terminal = self.tty('--context', 'acme')
        terminal.expect('Esc quit')
        terminal.send(b'e\r')
        terminal.expect('New environment')
        terminal.send(b'\x1b[B\r')
        terminal.expect('Copy current')
        terminal.send(b'\x1b[B\r')
        terminal.send(b'acme-test')
        terminal.expect('Later edits stay separate.')
        self.assertFalse((self.home / '.env.godmode.acme-test').exists())
        terminal.send(b'\r')
        terminal.expect('Created acme-test.')
        terminal.send(b'\t')
        terminal.settle(.1)  # Bubble Tea may update only the changed title suffix.
        terminal.send(b'\x1b')
        terminal.settle(.1)
        terminal.send(b'\x1b')
        terminal.settle(.1)
        terminal.send(b'\x1b')
        terminal.done()
        result = self.command('--env', 'acme-test', 'list')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'DEMO_TOKEN')
        self.assertEqual(self.command('--env', 'acme-test', 'set', 'DEMO_TOKEN', '--stdin', data='synthetic_COPY_CHANGED').returncode, 0)
        unchanged = self.command('run', 'DEMO_TOKEN', '--', sys.executable, '-c',
                                 'import os; assert os.environ["DEMO_TOKEN"] == "synthetic_COPY_SOURCE"')
        self.assertEqual(unchanged.returncode, 0, unchanged.stderr)

    def test_new_business_form_and_profile_return(self):
        terminal = self.tty()
        terminal.expect('Esc quit')
        terminal.send(b'\r')
        terminal.expect('Edit profile')
        terminal.send(b'\x1b[B\x1b[B\r')
        terminal.expect('Profile starts empty.')
        terminal.send(b'acme')
        self.assertFalse((self.home / 'contexts/acme/context.json').exists())
        terminal.send(b'\r')
        terminal.expect('Created acme.')
        terminal.send(b'\r')
        terminal.expect('optional fields')
        terminal.send(b'\x1b')
        terminal.settle(.1)
        terminal.send(b'\x1b')
        terminal.settle(.1)
        terminal.send(b'\x1b')
        terminal.done()
        result = self.command('context', 'show', 'acme')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('contexts/acme/profile.json', result.stdout)

    def test_installed_agents_keep_selected_task_instruction(self):
        self.assertEqual(self.command('env', 'create', 'acme-test').returncode, 0)
        self.assertEqual(self.command('context', 'create', 'acme').returncode, 0)
        target = self.root / '.codex/AGENTS.md'
        target.parent.mkdir()
        original = '<!-- godmode:start -->\nSynthetic existing note.\n<!-- godmode:end -->\n'
        target.write_text(original)
        terminal = self.tty('--env', 'acme-test', '--context', 'acme', 'agents')
        terminal.expect('already added')
        terminal.expect('Copy for this task')
        terminal.expect('--env acme-test')
        terminal.expect('c copy')
        terminal.send(b'\x1b')
        terminal.done()
        self.assertEqual(target.read_text(), original)
        note = self.command('--env', 'acme-test', '--context', 'acme', 'agents', '--print')
        self.assertEqual(note.returncode, 0, note.stderr)
        self.assertIn('--env acme-test --context acme help', note.stdout)
        self.assertIn('.env.godmode.acme-test', note.stdout)

    def test_doctor_button_and_update_version_dispatch(self):
        terminal = self.tty()
        terminal.expect('Esc quit')
        terminal.send(b'd\r')
        terminal.expect('Read-only checks')
        terminal.expect('Python')
        terminal.send(b'\x1b')
        terminal.settle(.1)
        terminal.send(b'\x1b')
        terminal.done()
        # The test binary has no managed install receipt; update must reach the
        # updater gate, not interpret its requested release as CLI --version.
        result = self.command('update', '--version', 'v0.18.0')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('recorded install', result.stderr)
        self.assertEqual(result.stdout, '')
        terminal = self.tty()
        terminal.expect('Esc quit')
        terminal.send(b'u\r')
        terminal.done(2)
        restored = terminal.capture.find(b'\x1b[?1049l')
        refused = terminal.capture.find(b'A recorded install is required')
        self.assertGreaterEqual(restored, 0)
        self.assertGreater(refused, restored, 'updater ran before terminal restoration')


if __name__ == '__main__':
    unittest.main()
