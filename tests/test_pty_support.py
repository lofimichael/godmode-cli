"""The terminal harness must not add filesystem effects to the tested command."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

from pty_support import Terminal


class TerminalHarnessTests(unittest.TestCase):
    def test_noop_command_does_not_create_python_startup_cache_in_home(self):
        with tempfile.TemporaryDirectory(prefix="godmode-pty-harness-") as directory:
            root = Path(directory)
            environment = {"HOME": str(root), "PATH": os.environ["PATH"],
                           "TERM": "xterm-256color"}
            # Isolate the no-op child so any files would come from the harness.
            terminal = Terminal([sys.executable, "-I", "-S", "-B", "-c", "pass"], environment)
            try:
                terminal.wait(lambda: terminal.process.poll() is not None)
                self.assertEqual(terminal.process.returncode, 0)
            finally:
                terminal.close()
            self.assertEqual(list(root.iterdir()), [], "PTY wrapper created files in the tested HOME")


if __name__ == "__main__":
    unittest.main()
