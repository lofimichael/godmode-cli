"""Real native-terminal checks. Synthetic homes only; no account access."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
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
_SCREEN_MODEL = None


class NativeTerminal(Terminal):
    def screen_text(self):
        """Reconstruct current cells; incremental redraws need not repeat whole words."""
        global _SCREEN_MODEL
        if _SCREEN_MODEL is None:
            if importlib.util.find_spec('pyte') is None or importlib.util.find_spec('PIL') is None:
                raise unittest.SkipTest('Screen assertions require scripts/demo-requirements.txt.')
            spec = importlib.util.spec_from_file_location('native_test_screen', ROOT / 'scripts/record-v019.py')
            _SCREEN_MODEL = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_SCREEN_MODEL)
        rows, cols, _, _ = struct.unpack('HHHH', fcntl.ioctl(self.slave, termios.TIOCGWINSZ, bytes(8)))
        screen = _SCREEN_MODEL.NATIVE.NativeScreen(cols, rows)
        _SCREEN_MODEL.CaptureStream(screen).feed(bytes(self.capture).decode('utf-8', 'replace'))
        return '\n'.join(screen.display)

    def expect_screen(self, text):
        self.wait(lambda: text in self.screen_text())

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

    def tty(self, *args, cols=80, rows=24, binary=None):
        terminal = NativeTerminal([str(binary or BINARY), *args], self.env, cols=cols, rows=rows)
        self.sessions.append(terminal)
        return terminal

    def command(self, *args, data=None, binary=None):
        return subprocess.run([str(binary or BINARY), *args], env=self.env, input=data,
                              text=True, capture_output=True)

    def open_agent_files(self, terminal, selection=0):
        terminal.expect('Copy instructions for chat')
        terminal.send(b'\x1b[B\r')
        terminal.expect_screen('All detected agents')
        terminal.send(b'\x1b[B' * selection + b'\r')

    def active(self):
        result = self.command('active', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

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
        self.open_agent_files(terminal)
        terminal.expect('These files will be modified:')
        terminal.expect('godmode:end')
        mark = len(terminal.capture)
        terminal.send(b'\r')
        terminal.after(mark, 'Added to 1 file.')
        terminal.send(b'\x03')
        terminal.done(130)
        after = target.read_bytes()
        self.assertTrue(after.startswith(original))
        self.assertEqual(after.count(b'godmode:start'), 1)
        again = self.tty('agents', cols=100, rows=40)
        self.open_agent_files(again, selection=1)  # All detected agents, already configured.
        again.expect('already added')
        again.expect_screen('Godmode note:')
        again.expect_screen('<!-- godmode:start -->')
        again.expect_screen('<!-- godmode:end -->')
        screen = again.screen_text()
        self.assertLess(screen.index('~/.codex/AGENTS.md'), screen.index('Godmode note:'))
        self.assertNotIn('+ <!-- godmode:start -->', screen)
        again.send(b'\r')
        again.settle(.1)
        self.assertEqual(target.read_bytes(), after)
        again.send(b'\x03')
        again.done(130)
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

    def test_returning_loadout_edits_a_profile_field_from_home(self):
        for name in ('GH_TOKEN', 'STRIPE_TEST_SECRET_KEY', 'STUDIO_API_KEY'):
            result = self.command('set', name, '--stdin', data='dashboard_FIXTURE_PRIVATE_value')
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.command('profile', 'set', 'business_name', '--stdin',
                                      data='Harbor Studio').returncode, 0)

        terminal = self.tty()
        for text in ('Harbor Studio', 'GitHub', 'Stripe', 'test', 'STUDIO_API_KEY',
                     'Agent instructions', 'Brand name'):
            terminal.expect_screen(text)
        self.assertNotIn(b'FIXTURE_PRIVATE', terminal.capture)
        terminal.send(b'\t\r')
        terminal.expect_screen('Ctrl-U')
        terminal.send(b'\x15')
        terminal.paste('Example Press')
        terminal.send(b'\r')
        terminal.expect_screen('Providers')
        terminal.expect_screen('Example Press')
        self.assertEqual(self.command('profile', 'get', 'business_name').stdout.strip(), 'Example Press')
        self.assertNotIn(b'FIXTURE_PRIVATE', terminal.capture)
        terminal.send(b'q')
        terminal.done()

    def test_menu_pastes_never_open_a_section(self):
        terminal = self.tty()
        terminal.expect_screen('Loadout')
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
        terminal.send(b's')
        terminal.expect('Key environment')
        terminal.send(b'\r')
        terminal.expect('New environment')
        terminal.send(b'\x1b[B\r')
        terminal.expect('Copy current')
        terminal.send(b'\x1b[B\r')
        terminal.send(b'acme-test')
        terminal.expect('Later edits stay separate.')
        self.assertFalse((self.home / '.env.godmode.acme-test').exists())
        terminal.send(b'\r')
        terminal.expect('Created acme-test.')
        self.assertEqual(self.active()['environment'], 'default', 'creation selected a staged environment')
        self.assertEqual(self.active()['context'], '', 'staging saved an intermediate business')
        terminal.send(b'\t')
        terminal.settle(.1)  # Bubble Tea may update only the changed title suffix.
        terminal.send(b'\x1b')
        terminal.settle(.1)
        terminal.send(b'\x1b')
        terminal.settle(.1)
        terminal.send(b'\x1b[B\x1b[B\r')  # Use this loadout applies both staged choices.
        terminal.expect('Using acme-test')
        terminal.send(b'\x03')
        terminal.done(130)
        self.assertEqual(self.active()['environment'], 'acme-test')
        self.assertEqual(self.active()['context'], 'acme')
        result = self.command('--env', 'acme-test', 'list')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'DEMO_TOKEN')
        self.assertEqual(self.command('--env', 'acme-test', 'set', 'DEMO_TOKEN', '--stdin', data='synthetic_COPY_CHANGED').returncode, 0)
        unchanged = self.command('--env', 'default', '--context', '-', 'run', 'DEMO_TOKEN', '--', sys.executable, '-c',
                                 'import os; assert os.environ["DEMO_TOKEN"] == "synthetic_COPY_SOURCE"')
        self.assertEqual(unchanged.returncode, 0, unchanged.stderr)

    def test_new_business_form_and_profile_return(self):
        terminal = self.tty()
        terminal.expect('Esc quit')
        terminal.send(b'\x0b')
        terminal.expect('Type to find')
        terminal.send(b'business profiles\r')
        terminal.expect('New profile')
        terminal.send(b'\x1b[B\r')
        terminal.expect('Profile starts empty.')
        terminal.send(b'acme')
        self.assertFalse((self.home / 'contexts/acme/context.json').exists())
        terminal.send(b'\r')
        terminal.expect_screen('Created and selected acme.')
        terminal.send(b'\x1b')
        terminal.settle(.1)
        terminal.send(b'\x15business details\r')
        terminal.expect('optional fields')
        terminal.send(b'\x1b')
        terminal.settle(.1)
        terminal.send(b'\x1b')
        terminal.settle(.1)
        terminal.send(b'\x03')
        terminal.done(130)
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
        terminal.expect('Copy instructions for chat')
        terminal.send(b'\r')
        terminal.expect('--env acme-test')
        terminal.expect('c copy')
        terminal.send(b'\x1b')
        terminal.settle(.1)
        terminal.send(b'\x03')
        terminal.done(130)
        self.assertEqual(target.read_text(), original)
        note = self.command('--env', 'acme-test', '--context', 'acme', 'agents', '--print')
        self.assertEqual(note.returncode, 0, note.stderr)
        self.assertIn('--env acme-test --context acme help', note.stdout)
        self.assertIn('.env.godmode.acme-test', note.stdout)

    def test_doctor_button_and_update_version_dispatch(self):
        # Update acts on the executable's sibling installer, independently of
        # HOME. Never dispatch it beside a user's real installation receipt.
        unmanaged = self.root / 'unmanaged-godmode'
        shutil.copyfile(BINARY, unmanaged)
        unmanaged.chmod(0o700)
        self.assertFalse((unmanaged.parent / '.godmode-install-receipt').exists())
        terminal = self.tty('settings', binary=unmanaged)
        terminal.expect('Replay intro')
        terminal.send(b'\x1b[B\r')
        terminal.expect('local files only')
        terminal.expect('Python')
        terminal.send(b'\x1b')
        terminal.settle(.1)
        terminal.send(b'\x1b')
        terminal.done()
        # This disposable copy has no managed install receipt; update must reach the
        # updater gate, not interpret its requested release as CLI --version.
        result = self.command('update', '--version', 'v0.18.0', binary=unmanaged)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('recorded install', result.stderr)
        self.assertEqual(result.stdout, '')
        terminal = self.tty('settings', binary=unmanaged)
        terminal.expect('Replay intro')
        terminal.send(b'\x1b[B\x1b[B\r')
        terminal.expect('Download and install the latest Godmode release.')
        self.assertIsNone(terminal.process.poll(), 'update ran without confirmation')
        terminal.send(b'\r')
        terminal.done(2)
        restored = terminal.capture.find(b'\x1b[?1049l')
        refused = terminal.capture.find(b'A recorded install is required')
        self.assertGreaterEqual(restored, 0)
        self.assertGreater(refused, restored, 'updater ran before terminal restoration')

    def test_compact_provider_paste_saves_only_after_explicit_enter(self):
        terminal = self.tty('setup', 'github', cols=40, rows=18)
        terminal.expect('Paste your token:')
        token = 'synthetic_COMPACT_PRIVATE_12345'
        terminal.paste(token)
        terminal.expect('syn•••••345')
        self.assertFalse((self.home / '.env.godmode').exists())
        self.assertNotIn(b'COMPACT_PRIVATE', terminal.capture)
        terminal.send(b'\r')
        terminal.wait(lambda: (self.home / '.env.godmode').exists())
        terminal.expect_screen('Saved GH_TOKEN.')
        terminal.send(b'\x03')
        terminal.done(130)
        supplied = self.command('run', 'GH_TOKEN', '--', sys.executable, '-c',
                                'import os; assert os.environ["GH_TOKEN"] == "synthetic_COMPACT_PRIVATE_12345"')
        self.assertEqual(supplied.returncode, 0, supplied.stderr)
        self.assertNotIn(b'COMPACT_PRIVATE', terminal.capture)

    def test_selected_agent_append_never_writes_other_detected_agent(self):
        codex = self.root / '.codex/AGENTS.md'
        claude = self.root / '.claude/CLAUDE.md'
        for target in (codex, claude):
            target.parent.mkdir()
            target.write_text('# Synthetic original rules\nKeep this sentence.\n')
        before = claude.read_bytes()
        terminal = self.tty('agents', cols=100, rows=40)
        self.open_agent_files(terminal, selection=1)  # Claude Code, then Codex.
        terminal.expect('These files will be modified:')
        terminal.expect('~/.codex/AGENTS.md')
        terminal.expect('godmode:end')
        terminal.send(b'\r')
        terminal.expect('Added to 1 file.')
        terminal.send(b'\x03')
        terminal.done(130)
        self.assertEqual(claude.read_bytes(), before)
        self.assertFalse((self.root / '.claude/rules/godmode.md').exists())
        self.assertTrue(codex.read_bytes().startswith(before))
        self.assertEqual(codex.read_bytes().count(b'godmode:start'), 1)

    def test_cancel_staged_setup_keeps_saved_selection(self):
        self.assertEqual(self.command('env', 'create', 'acme-test').returncode, 0)
        self.assertEqual(self.command('context', 'create', 'acme').returncode, 0)
        before = self.active()
        terminal = self.tty()
        terminal.expect('Esc quit')
        terminal.send(b's\r')
        terminal.expect('New environment')
        terminal.send(b'\x1b[B\r')
        terminal.expect('Use this loadout')
        terminal.send(b'\x1b[B\r')
        terminal.expect('New profile')
        terminal.send(b'\x1b[B\r')
        terminal.settle(.1)
        during = self.active()
        self.assertEqual((during['environment'], during['context']), (before['environment'], before['context']))
        terminal.send(b'\x1b')
        terminal.settle(.1)
        terminal.send(b'\x03')
        terminal.done(130)
        after = self.active()
        self.assertEqual((after['environment'], after['context']), (before['environment'], before['context']))
        self.assertFalse((self.home / '.env.godmode').exists())

    def test_named_loadout_creation_returns_home_after_explicit_apply(self):
        terminal = self.tty()
        terminal.expect_screen('Esc quit')
        terminal.send(b's\r')
        terminal.expect_screen('New environment')
        terminal.send(b'\x1b[B\r')
        terminal.expect_screen('Copy current')
        terminal.send(b'\r')
        terminal.expect_screen('Starts empty.')
        terminal.send(b'quest-test\r')
        terminal.expect_screen('Created quest-test.')
        terminal.send(b'\x1b')
        terminal.expect_screen('Pair a key environment with a profile')
        terminal.send(b'\x1b[B\r')
        terminal.expect_screen('New profile')
        terminal.send(b'\t')
        terminal.expect_screen('↑↓ scroll')
        terminal.expect_screen('environments/quest-test/profile.json')
        terminal.send(b'\x1b')
        terminal.expect_screen('New profile')
        terminal.send(b'\x1b[B\r')
        terminal.expect_screen('Profile starts empty.')
        terminal.send(b'quest-studio\r')
        terminal.expect_screen('Created quest-studio.')
        terminal.send(b'\x1b')
        terminal.expect_screen('Pair a key environment with a profile')
        self.assertEqual((self.active()['environment'], self.active()['context']), ('default', ''))
        terminal.send(b'\x1b[B\r')
        terminal.expect_screen('Esc quit')
        self.assertIn('Providers', terminal.screen_text())
        self.assertNotIn('Starts empty.', terminal.screen_text())
        self.assertEqual((self.active()['environment'], self.active()['context']), ('quest-test', 'quest-studio'))
        terminal.send(b'q')
        terminal.done()

    def test_help_command_and_plain_settings_keep_text_routes(self):
        for arguments in (('help', 'settings'), ('settings', '--help')):
            result = self.command(*arguments)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Usage: godmode settings', result.stdout)
            self.assertNotIn('\x1b[?1049h', result.stdout)
        plain_settings = self.command('--plain', 'settings')
        self.assertEqual(plain_settings.returncode, 0, plain_settings.stderr)
        self.assertIn('Motion:', plain_settings.stdout)
        self.assertIn('godmode settings motion off', plain_settings.stdout)
        self.assertNotIn('\x1b[?1049h', plain_settings.stdout)


if __name__ == '__main__':
    unittest.main()
