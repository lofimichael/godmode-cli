"""Legacy receipt commands stay strict while ordinary local use remains free."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from license_support import provision
from test_native_cli import NativeTerminal

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / 'target/godmode-native-test'


@unittest.skipUnless(BINARY.exists(), 'Build scripts/build-license-test.sh first.')
class NativeLicenseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / '.godmode'
        self.env = dict(HOME=str(self.root), PATH=os.environ['PATH'], TERM='dumb',
                        HTTPS_PROXY='http://127.0.0.1:9', GODMODE_EXECUTABLE='/usr/bin/true')

    def command(self, *args, input=None, binary=BINARY):
        return subprocess.run([str(binary), '--home', str(self.home), *args], input=input,
                              text=True, capture_output=True, env=self.env, timeout=10)

    def test_local_commands_need_no_receipt(self):
        result = self.command('set', 'SYNTHETIC_KEY', '--stdin', input='synthetic-private-key-value')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.home / 'license.json').exists())
        self.assertFalse((self.home / 'installation.json').exists())
        self.assertNotIn('synthetic-private-key-value', result.stdout + result.stderr)
        self.assertEqual(self.command('help').returncode, 0)
        self.assertEqual(self.command('source').returncode, 0)

    def test_tampered_receipt_does_not_block_local_use_or_get_rewritten(self):
        provision(self.home)
        result = self.command('set', 'SYNTHETIC_KEY', '--stdin', input='synthetic-private-key-value')
        self.assertEqual(result.returncode, 0, result.stderr)
        before = (self.home / '.env.godmode').read_bytes()
        result = self.command('license', 'status', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['license']['kind'], 'evaluation')
        receipt = json.loads((self.home / 'license.json').read_text())
        receipt['license']['signature'] = 'bad'
        (self.home / 'license.json').write_text(json.dumps(receipt))
        receipt_bytes = (self.home / 'license.json').read_bytes()
        self.assertEqual(self.command('license', 'check').returncode, 2)
        result = self.command('run', 'SYNTHETIC_KEY', '--', 'python3', '-c',
                              'import os; assert os.environ["SYNTHETIC_KEY"] == "synthetic-private-key-value"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.home / '.env.godmode').read_bytes(), before)
        self.assertEqual((self.home / 'license.json').read_bytes(), receipt_bytes)

    @unittest.skipUnless((ROOT / 'target/godmode-native').exists(), 'Build production candidate first.')
    def test_production_binary_does_not_trust_synthetic_test_key(self):
        provision(self.home)
        result = self.command('license', 'check', binary=ROOT / 'target/godmode-native')
        self.assertEqual(result.returncode, 2)

    def test_hidden_entry_paste_requires_enter_and_cancel_restores_terminal(self):
        for partial in (False, True):
            terminal = NativeTerminal([str(BINARY), '--home', str(self.home), 'license', 'activate'],
                                      dict(self.env, TERM='xterm-256color'), cols=80, rows=24)
            self.addCleanup(terminal.close)
            terminal.expect('License key:')
            if partial:
                terminal.send(b'\x1b[200~synthetic_LICENSE_PRIVATE')
            else:
                terminal.paste('synthetic_LICENSE_PRIVATE\n')
                terminal.settle(.1)
                self.assertIsNone(terminal.process.poll())
            terminal.send(b'\x03')
            terminal.done(130)
            self.assertNotIn(b'LICENSE_PRIVATE', terminal.capture)
            self.assertFalse(self.home.exists())


if __name__ == '__main__':
    unittest.main()
