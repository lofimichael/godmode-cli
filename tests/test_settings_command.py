"""Direct Motion settings use only isolated, nonsecret UI preference files."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class SettingsCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='godmode-settings-')
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / '.godmode'
        self.env = {'HOME': str(self.root), 'GODMODE_HOME': str(self.home),
                    'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'TERM': 'dumb'}

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'godmode.py'), *args],
                              env=self.env, text=True, capture_output=True, timeout=10)

    def test_default_plain_inspection_is_read_only(self):
        result = self.run_cli('--plain', 'settings')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Motion: on', result.stdout)
        self.assertIn('settings motion off', result.stdout)
        self.assertIn(str(self.home), result.stdout)
        self.assertNotIn('\x1b', result.stdout)
        self.assertFalse(self.home.exists())

    def test_motion_roundtrip_and_json_path(self):
        for value, expected in [('off', False), ('on', True)]:
            saved = self.run_cli('settings', 'motion', value, '--plain')
            self.assertEqual(saved.returncode, 0, saved.stderr)
            self.assertIn('Motion: ' + value, saved.stdout)
            result = self.run_cli('--plain', 'settings', '--json')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {'motion': expected, 'path': str(self.home / 'ui.json')})
            self.assertEqual(json.loads((self.home / 'ui.json').read_text()), {'motion': expected})
        self.assertEqual((self.home / 'ui.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.home.stat().st_mode & 0o777, 0o700)
        self.assertEqual({path.name for path in self.home.iterdir()}, {'ui.json'})

    def test_unknown_arguments_do_not_write_or_echo_input(self):
        for args in [('unknown',), ('motion',), ('motion', 'synthetic_PRIVATE_INPUT'),
                     ('motion', 'on', 'extra'), ('--json', 'extra')]:
            result = self.run_cli('--plain', 'settings', *args)
            self.assertEqual(result.returncode, 2)
            self.assertIn('Use: godmode settings', result.stderr)
            self.assertNotIn('synthetic_PRIVATE_INPUT', result.stdout + result.stderr)
            self.assertFalse(self.home.exists())

    def test_preferences_remain_accessible_with_broken_selection_and_business_data(self):
        self.home.mkdir(mode=0o700)
        for name in ('active.json', 'profile.json', '.env.godmode'):
            path = self.home / name
            path.write_text('synthetic invalid data')
            path.chmod(0o600)
        self.env.update(GODMODE_ENV='missing-environment', GODMODE_CONTEXT='missing-business')
        result = self.run_cli('settings', 'motion', 'off')
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_cli('settings', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['motion'])
        for name in ('active.json', 'profile.json', '.env.godmode'):
            self.assertEqual((self.home / name).read_text(), 'synthetic invalid data')

    def test_settings_never_constructs_a_key_store_or_business_profile(self):
        spec = importlib.util.spec_from_file_location('settings_test_cli', ROOT / 'godmode.py')
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with patch.dict(os.environ, self.env, clear=True), \
                patch.object(sys, 'argv', ['godmode', '--plain', 'settings', '--json']), \
                patch.object(cli, 'Store', side_effect=AssertionError('opened keys')), \
                patch.object(cli, 'business_profile', side_effect=AssertionError('opened business profile')), \
                patch.object(cli, 'selection_resolve', side_effect=AssertionError('resolved selection')), \
                patch('builtins.print'):
            self.assertEqual(cli.main(), 0)

    def test_unsafe_or_malformed_preferences_fail_without_replacement(self):
        self.home.mkdir(mode=0o700)
        path = self.home / 'ui.json'
        path.write_text('{"motion":"invalid"}')
        path.chmod(0o600)
        result = self.run_cli('settings', 'motion', 'off')
        self.assertEqual(result.returncode, 2)
        self.assertIn('ui.json', result.stderr)
        self.assertEqual(path.read_text(), '{"motion":"invalid"}')
        path.unlink()
        outside = self.root / 'outside.json'
        outside.write_text('{"motion":true}')
        outside.chmod(0o600)
        path.symlink_to(outside)
        result = self.run_cli('settings', 'motion', 'off')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(outside.read_text(), '{"motion":true}')

    def test_help_documents_settings_without_creating_home(self):
        for args in [('settings', '--help'), ('help', 'settings')]:
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Usage: godmode settings', result.stdout)
            self.assertIn('settings motion off', result.stdout)
        self.assertIn('godmode settings', self.run_cli('--help').stdout)
        self.assertFalse(self.home.exists())

    def test_explicit_home_keeps_other_preferences_unchanged(self):
        self.assertEqual(self.run_cli('settings', 'motion', 'off').returncode, 0)
        other = self.root / 'other settings'
        result = self.run_cli('--home', str(other), '--plain', 'settings', 'motion', 'on')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads((other / 'ui.json').read_text())['motion'])
        self.assertFalse(json.loads((self.home / 'ui.json').read_text())['motion'])
        self.assertIn(str(other), result.stdout)


if __name__ == '__main__':
    unittest.main()
