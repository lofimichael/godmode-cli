"""Free source entry works without activation and preserves legacy receipt files."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FreeEntryTests(unittest.TestCase):
    def test_source_can_save_and_use_a_key_without_a_license(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder) / '.godmode'
            env = dict(HOME=folder, PATH=os.environ['PATH'], HTTPS_PROXY='http://127.0.0.1:9')
            command = [sys.executable, str(ROOT / 'godmode.py'), '--home', str(home)]
            saved = subprocess.run(command + ['set', 'SYNTHETIC_TOKEN', '--stdin'],
                                   input='synthetic-private-token', text=True, capture_output=True, env=env)
            self.assertEqual(saved.returncode, 0, saved.stderr)
            self.assertNotIn('synthetic-private-token', saved.stdout + saved.stderr)
            self.assertFalse((home / 'license.json').exists())
            self.assertFalse((home / 'installation.json').exists())
            # Old/expired/corrupt receipts are data, not an operational gate.
            receipt = home / 'license.json'
            receipt.write_bytes(b'{"legacy":"unreadable synthetic receipt"}')
            receipt.chmod(0o600)
            before = {p.name: p.read_bytes() for p in home.iterdir() if p.is_file()}
            used = subprocess.run(command + ['run', 'SYNTHETIC_TOKEN', '--', sys.executable,
                                  '-c', 'import os; assert os.environ["SYNTHETIC_TOKEN"] == "synthetic-private-token"'],
                                  text=True, capture_output=True, env=env)
            self.assertEqual(used.returncode, 0, used.stderr)
            self.assertEqual({p.name: p.read_bytes() for p in home.iterdir() if p.is_file()}, before)


if __name__ == '__main__':
    unittest.main()
