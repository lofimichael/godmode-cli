"""NFO artwork never hides account-use consequences or changes setup navigation."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from pty_support import Screen, Terminal, plain

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('godmode_nfo_test', REPO / 'godmode.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class NfoIdentityTests(unittest.TestCase):
    def test_every_ready_size_shows_all_consequences_and_fits(self):
        for width in (8, 20, 24, 32, 40, 60, 80, 110):
            for height in (5, 10, 12, 18, 24, 36):
                with self.subTest(width=width, height=height):
                    rows, ready = cli.intro_rows(0, None, width, height, setup_next=True)
                    text = ' '.join(' '.join(rows).split())
                    if ready:
                        for fact in ('Agents use these keys as you.', 'spend money', 'change live systems', 'delete data', 'Enter accept'):
                            self.assertIn(fact, text)
                        self.assertLessEqual(cli.drawn_height(rows + [''], width), height - 1)
                        self.assertTrue(all(cli.cells(row) < width for row in rows))
                    else:
                        self.assertIn('Enlarge', text)
                        self.assertNotIn('Enter accept', text)

    def test_art_shrinks_without_losing_brand_or_copy(self):
        with patch.object(cli, 'glyph', side_effect=lambda fancy, plain: fancy):
            full, full_ready = cli.intro_rows(0, None, 80, 24)
            narrow, narrow_ready = cli.intro_rows(0, None, 40, 24)
            self.assertTrue(full_ready and narrow_ready)
            self.assertIn(cli.NFO_LOGO[0].strip(), '\n'.join(full))
            self.assertIn(cli.LOGO[0], '\n'.join(narrow))
            self.assertNotIn(cli.NFO_LOGO[0].strip(), '\n'.join(narrow))

    def test_plain_home_counts_do_not_need_graphics(self):
        state = dict(fields=[], errors=set(), providers=0, key_count=0, started=[], agents=[], by_hand=False, agent=0)
        with patch.object(cli, 'plain_mode', return_value=True):
            self.assertEqual([row[1] for row in cli.home_items(state)], ['0 fields', '0 keys saved', '0 notes added'])

    def test_short_home_keeps_every_choice_reachable(self):
        with tempfile.TemporaryDirectory(prefix='godmode-nfo-short-') as directory:
            root = Path(directory)
            home = root / '.godmode'
            home.mkdir(mode=0o700)
            (home / 'intro.seen').touch(mode=0o600)
            env = dict(HOME=str(root), PATH=os.environ.get('PATH', '/usr/bin:/bin'),
                       TERM='xterm-256color', NO_COLOR='1', PYTHONUTF8='1')
            terminal = Terminal([sys.executable, str(REPO / 'tests/engine_fixture.py'), str(REPO / 'godmode.py')], env, cols=40, rows=12)
            try:
                terminal.expect('Esc quit')
                terminal.settle(.05)
                screen = '\n'.join(Screen(40).feed(terminal.capture).lines())
                self.assertIn('Environment default', screen)
                self.assertNotIn('Setup 0%', screen)
                labels = ('Business', 'Providers', 'Agents', 'Environments', 'Doctor', 'Update', 'Help / FAQ', 'Music', 'Done')
                for index, label in enumerate(labels):
                    if index:
                        terminal.send(b'\x1b[B')
                    terminal.wait(lambda: any(row.startswith('❯ ' + label)
                                             for row in Screen(40).feed(terminal.capture).lines()))
                terminal.send(b'\x1b')
                terminal.done()
            finally:
                terminal.close()

    def test_escaping_each_section_preserves_the_selected_section(self):
        with tempfile.TemporaryDirectory(prefix='godmode-nfo-navigation-') as directory:
            root = Path(directory)
            home = root / '.godmode'
            home.mkdir(mode=0o700)
            (home / 'intro.seen').touch(mode=0o600)
            env = dict(HOME=str(root), PATH=os.environ.get('PATH', '/usr/bin:/bin'),
                       TERM='xterm-256color', NO_COLOR='1', PYTHONUTF8='1')
            terminal = Terminal([sys.executable, str(REPO / 'tests/engine_fixture.py'), str(REPO / 'godmode.py')], env, cols=80, rows=24)
            try:
                def selected(name):
                    terminal.wait(lambda: any(row.startswith('❯ ' + name)
                                             for row in Screen(80).feed(terminal.capture).lines()))
                terminal.expect('Esc quit')
                selected('Business')
                terminal.send(b'\r')
                selected('Edit profile')
                terminal.send(b'\r')
                terminal.expect('Your name')
                terminal.send(b'\x1b')
                selected('Edit profile')
                terminal.send(b'\x1b')
                selected('Business')
                terminal.send(b'\x1b[B')
                selected('Providers')
                terminal.send(b'\r')
                terminal.expect('Another key')
                terminal.send(b'\x1b')
                selected('Providers')
                terminal.send(b'\x1b[B')
                selected('Agents')
                mark = len(terminal.capture)
                terminal.send(b'\r')
                terminal.after(mark, 'No agent folders found.')
                terminal.send(b'\x1b')
                selected('Agents')
                terminal.send(b'\x1b[B' * 4)
                selected('Help / FAQ')
                mark = len(terminal.capture)
                terminal.send(b'\r')
                terminal.after(mark, 'What is sealed(...)?')
                terminal.send(b'\x1b')
                selected('Help / FAQ')
                terminal.send(b'\x1b')
                terminal.done()
                self.assertFalse((home / 'profile.json').exists())
                self.assertEqual(cli.Store(str(home)).states(), {})
                self.assertFalse((home / 'agent.added').exists())
            finally:
                terminal.close()


if __name__ == '__main__':
    unittest.main()
