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
                        for fact in ("You will fuck shit up if you don't know what you're doing.",
                                     'Agents use these keys as you.', 'spend, publish and delete',
                                     'Put your agent to fucking work.', 'Keys stay local.', 'Enter accept'):
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

    def test_plain_home_shows_local_status_full_inventory_and_optional_examples(self):
        states = {'STRIPE_TEST_SECRET_KEY': 'set', 'GMAIL_USER': 'set', 'GH_TOKEN': 'duplicate',
                  'EXTRA_TOKEN': 'set', 'EXTRA_BROKEN': 'malformed'}
        state = dict(states=states, profile={'business_name': 'Studio'}, errors=set(),
                     agents=[], by_hand=False, ready=[{'id': 'stripe'}], started=[{'id': 'gmail'}])
        rows = cli.home_items(state)
        self.assertEqual([key for key in rows if key.startswith('provider:')][:2],
                         ['provider:stripe', 'provider:gmail'])
        self.assertEqual({key for key in rows if key.startswith('provider:')},
                         {'provider:' + p['id'] for p in cli.catalog()})
        self.assertEqual(rows['provider:stripe'][1][0], 'Saved (test)')
        self.assertEqual(rows['provider:gmail'][1][0], '1/2 keys')
        self.assertEqual(rows['provider:github'][1][0], 'Needs repair')
        self.assertEqual(rows['custom:EXTRA_TOKEN'][1][0], 'Saved')
        self.assertEqual(rows['custom:EXTRA_BROKEN'][1][0], 'Needs repair')
        self.assertEqual(rows['profile:business_name'][1], 'Studio')
        self.assertEqual(rows['profile:website'][2], 'Example: ' + cli.PROFILE_FORM['website'][3])
        self.assertIn('Studio', cli.home_title(state))
        self.assertEqual(rows['agents'][1], '0 agent files')
        state['by_hand'] = True
        self.assertEqual(cli.home_items(state)['agents'][1], 'Marked by hand')
        state['agents'] = ['Codex']
        self.assertEqual(cli.home_items(state)['agents'][1:], ('1 agent file', 'Codex'))
        state['errors'] = {'providers', 'profile'}
        rows = cli.home_items(state)
        self.assertEqual(rows['profile:website'][1], ('Unreadable', 'warning'))
        self.assertEqual(rows['profile:website'][2], '')
        self.assertEqual(rows['provider:github'][1], ('Unreadable', 'warning'))

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
                self.assertIn('Keys default', screen)
                self.assertNotIn('Setup 0%', screen)
                labels = [p['name'] for p in cli.catalog()] + ['Add custom key']
                labels += [row[0] for row in cli.PROFILE_FORM.values()]
                labels += ['Agent instructions', 'Switch loadout', 'Request a provider', 'Doctor', 'Update', 'Help / FAQ', 'Done']
                for index, label in enumerate(labels):
                    if index:
                        terminal.send(b'\x1b[B')
                    terminal.wait(lambda: any(row.startswith('❯ ' + label)
                                             for row in Screen(40).feed(terminal.capture).lines()))
                terminal.send(b'\x1b')
                terminal.done()
            finally:
                terminal.close()

    def test_text_loadout_saves_the_pair_only_after_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / '.godmode'
            cli.environment_create(home, 'preview')
            cli.context_create(home, 'studio')
            original = home / 'active.json'
            with patch.object(cli, 'ACTIVE_ENVIRONMENT', 'default'), patch.object(cli, 'ACTIVE_CONTEXT', None), \
                    patch.object(cli, 'ACTIVE_SOURCES', {}), patch.object(cli, 'SELECTION_SOURCE', 'default'):
                for apply in (False, True):
                    def choose(items, *args, **kwargs):
                        self.assertFalse(original.exists(), 'Browsing a loadout saved an intermediate pair')
                        label = next(selections)
                        return next(index for index, item in enumerate(items) if item and item[0] == label)
                    selections = iter(['Key environment', 'preview', 'Profile', 'studio',
                                       'Use this loadout' if apply else 'Back'])
                    with patch.object(cli, 'read_menu', side_effect=choose):
                        cli.active_screen(home)
                    self.assertEqual(original.exists(), apply)
                selected = cli.selection_resolve(home, environ={})
                self.assertEqual((selected['environment'], selected['context']), ('preview', 'studio'))

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
                selected('GitHub')
                terminal.send(b'switch')
                selected('Switch loadout')
                terminal.send(b'\r')
                selected('Key environment')
                terminal.send(b'\x1b')
                selected('Switch loadout')
                terminal.send(b'brand')
                selected('Brand name')
                terminal.send(b'\r')
                terminal.expect('Enter skips')
                terminal.send(b'\x1b')
                selected('Brand name')
                terminal.send(b'github')
                selected('GitHub')
                terminal.send(b'\r')
                terminal.expect('GH_TOKEN')
                terminal.send(b'\x1b')
                selected('GitHub')
                terminal.send(b'gmail')
                selected('Gmail')
                terminal.send(b'\r')
                terminal.expect('App password')
                terminal.send(b'\x1b')
                selected('Gmail')
                terminal.send(b'agent')
                selected('Agent instructions')
                mark = len(terminal.capture)
                terminal.send(b'\r')
                terminal.after(mark, 'No agent folders found.')
                terminal.send(b'\x1b')
                selected('Agent instructions')
                terminal.send(b'help')
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
