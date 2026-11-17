"""Native startup failures preserve actionable selection errors without stderr capture."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from pty_support import Terminal, plain

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(os.environ.get('GODMODE_TEST_NATIVE_BINARY', ROOT / 'target/godmode-native'))


@unittest.skipUnless(BINARY.exists(), 'Build the native candidate first.')
class NativeSelectionTests(unittest.TestCase):
    def test_invalid_saved_selection_reports_the_repair_in_a_terminal(self):
        cases = [('{broken', 'Repair the active selection file'),
                 (json.dumps({'schema': 1, 'environment': 'missing', 'context': ''}), 'godmode env create missing'),
                 (json.dumps({'schema': 1, 'environment': 'default', 'context': 'missing'}), 'godmode context create NAME')]
        for contents, repair in cases:
            with self.subTest(repair=repair), tempfile.TemporaryDirectory(prefix='godmode-native-selection-') as directory:
                root = Path(directory)
                home = root / '.godmode'
                home.mkdir(mode=0o700)
                active = home / 'active.json'
                active.write_text(contents)
                active.chmod(0o600)
                env = {'HOME': str(root), 'PATH': os.environ['PATH'], 'TERM': 'xterm-256color', 'NO_COLOR': '1'}
                terminal = Terminal([str(BINARY), '--home', str(home)], env)
                try:
                    terminal.wait(lambda: terminal.process.poll() is not None)
                    terminal.drain()
                    self.assertEqual(terminal.process.returncode, 1)
                    output = plain(terminal.capture)
                    self.assertIn(repair, output)
                    self.assertNotIn('unreadable reply', output)
                    self.assertNotIn('Traceback', output)
                    self.assertEqual(active.read_text(), contents)
                finally:
                    terminal.close()


if __name__ == '__main__':
    unittest.main()
