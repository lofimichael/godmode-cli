"""Native paste boundaries and terminal teardown, with synthetic homes only."""
import os
from pathlib import Path
import tempfile
import unittest

from test_native_cli import BINARY, NativeTerminal
from license_support import provision

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(BINARY.exists(), 'Build the native candidate first.')
class NativeInput(unittest.TestCase):
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

    def tty(self, *args):
        session = NativeTerminal([str(BINARY), *args], self.env)
        self.sessions.append(session)
        return session

    def test_partial_paste_cancels_and_discards_queued_tail(self):
        for cancel in (b'\x03', b'\x04'):
            with self.subTest(cancel=cancel):
                terminal = self.tty('set', 'SYNTHETIC_TOKEN')
                terminal.expect('Paste your token:')
                terminal.send(b'\x1b[200~synthetic_PRIVATE_PARTIAL')
                terminal.settle(.1)
                # Queue the rest with the cancel key while the CLI still owns
                # the terminal. A later write could arrive after echo returns.
                terminal.send(cancel + b'synthetic_PRIVATE_QUEUED_TAIL\n\x1b[201~')
                terminal.done(130)
                self.assertFalse((self.home / '.env.godmode').exists())
                self.assertNotIn(b'PRIVATE_PARTIAL', terminal.capture)
                self.assertNotIn(b'PRIVATE_QUEUED_TAIL', terminal.capture)

    def test_oversized_fragmented_paste_is_refused_without_submission(self):
        terminal = self.tty('set', 'SYNTHETIC_TOKEN')
        terminal.expect('Paste your token:')
        terminal.send(b'\x1b[200~')
        chunk = b'PRIVATE_OVERSIZED_' * 256
        for _ in range(260):
            terminal.send(chunk)
        terminal.send(b'\x1b[201~\rsynthetic_PRIVATE_AFTER_LIMIT\r')
        terminal.done(1)
        self.assertFalse((self.home / '.env.godmode').exists())
        self.assertNotIn(b'PRIVATE_OVERSIZED', terminal.capture)
        self.assertNotIn(b'PRIVATE_AFTER_LIMIT', terminal.capture)
        self.assertIn(b'Paste exceeds 1 MiB', terminal.capture)

    def test_complete_paste_newlines_stay_data_until_enter(self):
        terminal = self.tty('set', 'SYNTHETIC_TOKEN')
        terminal.expect('Paste your token:')
        terminal.paste('synthetic_PRIVATE_COMPLETE_12345\r\n')
        terminal.expect('syn•••••345')
        self.assertFalse((self.home / '.env.godmode').exists())
        terminal.send(b'\r')
        terminal.done()
        self.assertTrue((self.home / '.env.godmode').exists())
        self.assertNotIn(b'PRIVATE_COMPLETE', terminal.capture)

    def test_paste_bytes_that_decoder_would_alter_are_explicitly_refused(self):
        for bad in (b'\xff', '\ufffd'.encode()):
            with self.subTest(bad=bad):
                terminal = self.tty('set', 'SYNTHETIC_TOKEN')
                terminal.expect('Paste your token:')
                terminal.send(b'\x1b[200~synthetic_PRIVATE_' + bad + b'_VALUE\x1b[201~\r')
                terminal.done(1)
                self.assertFalse((self.home / '.env.godmode').exists())
                self.assertNotIn(b'synthetic_PRIVATE', terminal.capture)
                self.assertIn(b'invalid UTF-8 or a replacement character', terminal.capture)

    def test_menu_paste_is_ignored_and_exit_drops_queued_tail(self):
        terminal = self.tty()
        terminal.expect('Business: Automatic')
        terminal.paste('synthetic_PRIVATE_MENU\n\n')
        terminal.settle(.1)
        # End selects Done; Enter exits with the synthetic tail already queued.
        terminal.send(b'\x1b[F\rsynthetic_PRIVATE_EXIT_TAIL\r')
        terminal.done()
        self.assertFalse((self.home / 'profile.json').exists())
        self.assertFalse((self.home / '.env.godmode').exists())
        self.assertNotIn(b'PRIVATE_MENU', terminal.capture)
        self.assertNotIn(b'PRIVATE_EXIT_TAIL', terminal.capture)


if __name__ == '__main__':
    unittest.main()
