"""Named contexts isolate business facts and selected credentials without copying values."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ContextTests(unittest.TestCase):
    native = False

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='godmode-contexts-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / '.godmode'
        self.env = dict(HOME=str(self.root), PATH=os.environ['PATH'], TERM='dumb')
        self.entry = ([str(ROOT / 'target/godmode-native')] if self.native else
                      [sys.executable, str(ROOT / 'godmode.py')])

    def command(self, *args, input=None, expected=0):
        result = subprocess.run(self.entry + ['--home', str(self.home), *args], input=input,
                                text=True, capture_output=True, env=self.env, timeout=10)
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def test_shared_keys_selected_overrides_and_profiles(self):
        for name, value in [('STRIPE_SECRET_KEY', 'synthetic-base'), ('ACME_STRIPE', 'synthetic-acme'),
                            ('OTHER_STRIPE', 'synthetic-other'), ('CLOUDFLARE_API_TOKEN', 'synthetic-shared')]:
            self.command('set', name, '--stdin', input=value)
        self.command('profile', 'set', 'business_name', '--stdin', input='Default business')
        preserved = {p.name: p.read_bytes() for p in self.home.iterdir() if p.is_file()}
        for name, saved, business in [('acme', 'ACME_STRIPE', 'Acme business'), ('other', 'OTHER_STRIPE', 'Other business')]:
            self.command('context', 'create', name)
            self.command('context', 'map', name, 'STRIPE_SECRET_KEY', saved)
            self.command('--context', name, 'profile', 'set', 'business_name', '--stdin', input=business)
            self.assertEqual(self.command('--context', name, 'profile', 'get', 'business_name').stdout.strip(), business)
        self.assertEqual(self.command('profile', 'get', 'business_name').stdout.strip(), 'Default business')
        def run_context(name):
            self.command('--context', name, 'run', 'STRIPE_SECRET_KEY', 'CLOUDFLARE_API_TOKEN', '--',
                         sys.executable, '-c', 'import os; assert os.environ["STRIPE_SECRET_KEY"] == '
                         + repr('synthetic-' + name) + '; assert os.environ["CLOUDFLARE_API_TOKEN"] == "synthetic-shared"')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(run_context, ['acme', 'other']))
        self.assertEqual({p.name: p.read_bytes() for p in self.home.iterdir() if p.is_file()}, preserved)
        self.assertEqual(self.command('context', 'list').stdout.splitlines(), ['acme', 'other'])
        details = json.loads(self.command('context', 'show', 'acme').stdout)
        self.assertEqual(details['keys'], {'STRIPE_SECRET_KEY': 'ACME_STRIPE'})
        for path in (self.home / 'contexts').rglob('*.json'):
            self.assertNotIn('synthetic-', path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_missing_override_fails_before_child_and_never_uses_shared_key(self):
        self.command('set', 'STRIPE_SECRET_KEY', '--stdin', input='synthetic-base')
        self.command('context', 'create', 'acme')
        self.command('context', 'map', 'acme', 'STRIPE_SECRET_KEY', 'MISSING_KEY')
        marker = self.root / 'child-ran'
        result = self.command('--context', 'acme', 'run', 'STRIPE_SECRET_KEY', '--', sys.executable,
                              '-c', 'from pathlib import Path; Path(' + repr(str(marker)) + ').touch()', expected=2)
        self.assertFalse(marker.exists())
        self.assertNotIn('synthetic-base', result.stdout + result.stderr)
        self.command('context', 'unmap', 'acme', 'STRIPE_SECRET_KEY')
        self.command('--context', 'acme', 'run', 'STRIPE_SECRET_KEY', '--', sys.executable,
                     '-c', 'import os; assert os.environ["STRIPE_SECRET_KEY"] == "synthetic-base"')

    def test_context_selection_never_mutates_shared_keys(self):
        self.command('context', 'create', 'acme')
        self.command('--context', 'acme', 'set', 'SHARED', '--stdin', input='must-not-save', expected=2)
        self.assertFalse((self.home / '.env.godmode').exists())
        self.command('--context=', 'profile', 'show', expected=2)
        self.command('--context', 'acme', '--context', 'acme', 'profile', 'show', expected=2)
        self.command('--context', 'missing', 'profile', 'show', expected=2)
        self.assertFalse((self.home / 'contexts/missing').exists())
        self.command('context', 'create', '../escape', expected=2)
        self.command('context', 'create', 'acme', expected=2)

    def test_context_symlink_is_refused(self):
        self.home.mkdir(mode=0o700)
        other = self.root / 'other'
        other.mkdir(mode=0o700)
        (self.home / 'contexts').symlink_to(other, target_is_directory=True)
        self.command('context', 'create', 'acme', expected=2)
        self.assertEqual(list(other.iterdir()), [])


@unittest.skipUnless((ROOT / 'target/godmode-native').exists(), 'Build native candidate first.')
class NativeContextTests(ContextTests):
    native = True


if __name__ == '__main__':
    unittest.main()
