"""The readable Python entry delegates to the native verifier before local work."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('license_entry_cli', ROOT / 'godmode.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class LicenseEntryTests(unittest.TestCase):
    def test_source_refuses_unlicensed_use_without_creating_home_or_echoing_key(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder) / '.godmode'
            env = dict(HOME=folder, PATH=os.environ['PATH'], GODMODE_EXECUTABLE='/usr/bin/true')
            result = subprocess.run([sys.executable, str(ROOT / 'godmode.py'), '--home', str(home),
                                     'set', 'SYNTHETIC_TOKEN', '--stdin'],
                                    input='synthetic-private-token', text=True, capture_output=True, env=env)
            self.assertEqual(result.returncode, 2)
            self.assertIn('Use the native Godmode command', result.stderr)
            self.assertNotIn('synthetic-private-token', result.stdout + result.stderr)
            self.assertFalse(home.exists())

    def test_inspection_and_child_help_boundary(self):
        with patch.dict(os.environ, GODMODE_EXECUTABLE='/synthetic/verifier'), patch.object(cli.subprocess, 'run') as run:
            for args in (['help'], ['list'], ['path'], ['--version'], ['run', '--help']):
                cli.require_license(args, '/example')
            run.assert_not_called()
            with self.assertRaisesRegex(ValueError, 'Use the native Godmode command'):
                cli.require_license(['run', 'TOKEN', '--', 'child', '--help'], '/example')
            with self.assertRaisesRegex(ValueError, 'Use the native Godmode command'):
                cli.require_license(['__ui', '--help'], '/example')
            run.assert_not_called()

    def test_trailing_home_reaches_verifier_and_error_output_is_not_repeated(self):
        with patch.object(cli, '__file__', sys.executable), patch.object(cli.subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, b'', b'')
            cli.require_license(['profile', 'show', '--home', '/selected'], None)
            self.assertEqual(run.call_args.args[0], [str(Path(sys.executable).resolve()), '--home', '/selected', 'license', 'check'])


if __name__ == '__main__':
    unittest.main()
