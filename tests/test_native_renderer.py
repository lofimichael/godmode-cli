"""Real-PTY intro transport regressions; requires scripts/demo-requirements.txt.

Only temporary homes and disposable PTYs are touched. No user's terminal flags,
Godmode files, provider credentials, or audio are accessed.
"""
import codecs
import importlib.util
import os
from pathlib import Path
import re
import sys
import tempfile
import termios
import time
import unittest

from test_native_cli import BINARY, NativeTerminal

ROOT = Path(__file__).resolve().parents[1]
HAS_RENDERER = importlib.util.find_spec("pyte") is not None and importlib.util.find_spec("PIL") is not None


@unittest.skipUnless(BINARY.exists() and HAS_RENDERER, "Build native CLI and install scripts/demo-requirements.txt.")
class NativeRenderer(unittest.TestCase):
    def check_newline_mapping(self, mapping):
        spec = importlib.util.spec_from_file_location("renderer_record", ROOT / "scripts/record-v019.py")
        record = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(record)
        record.NATIVE.check_terminal_model()
        with tempfile.TemporaryDirectory(prefix="godmode-render-transport-") as root:
            env = {"HOME": root, "PATH": os.environ["PATH"], "TERM": "xterm-256color",
                   "COLORTERM": "truecolor", "COLORFGBG": "15;0"}
            # Read output flags after the app restores them, while the session
            # is still alive; macOS rejects ioctl on the hung-up PTY afterward.
            wrapper = ("import subprocess,sys,termios; "
                       "code=subprocess.call(sys.argv[1:]); "
                       "print('__PTY_OFLAGS=' + str(termios.tcgetattr(0)[1]) + '__', flush=True); "
                       "sys.exit(code)")
            terminal = NativeTerminal([sys.executable, "-c", wrapper, str(BINARY), "intro"], env, cols=120, rows=32)
            screen = record.NATIVE.NativeScreen(120, 32)
            stream = record.CaptureStream(screen)
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            read_at = 0

            def sync():
                nonlocal read_at
                data = bytes(terminal.capture[read_at:])
                read_at = len(terminal.capture)
                stream.feed(decoder.decode(data))

            try:
                terminal.expect("Enter I understand")
                terminal.settle(.15)
                sync()
                top = next(i for i, row in enumerate(screen.display) if "██████╗" in row)
                expected = screen.display[top:top + 6]
                self.assertEqual(len(expected), 6)
                self.assertTrue(all(row.strip() for row in expected))

                if mapping == "onlcr":
                    # Simulate a host that processes output after the app's
                    # raw-mode setup. This is this test's PTY, never /dev/tty.
                    attributes = termios.tcgetattr(terminal.slave)
                    attributes[1] |= termios.OPOST | termios.ONLCR
                    termios.tcsetattr(terminal.slave, termios.TCSANOW, attributes)
                else:
                    # Terminal LNM has the same LF->CRLF effect independently
                    # of kernel termios, as can an emulator's convertEol option.
                    stream.feed("\x1b[20h")

                # Several complete intro-animation cycles; sampling stays
                # independent of whether animation timers happen to be idle.
                deadline = time.monotonic() + 8.2
                while time.monotonic() < deadline:
                    terminal.drain(.02)
                    sync()
                # Drain every immediately available chunk before comparing
                # cells, avoiding a partially read terminal write.
                while True:
                    before = len(terminal.capture)
                    terminal.drain(.005)
                    sync()
                    if len(terminal.capture) == before:
                        break
                self.assertEqual(screen.display[top:top + 6], expected,
                                 "LF mapping moved animated logo fragments into the left gutter")
                self.assertFalse((Path(root) / ".godmode").exists(), "intro wrote files without acknowledgement")
                terminal.send(b"\x03")
                terminal.done(130)
                restored = re.search(rb"__PTY_OFLAGS=(\d+)__", terminal.capture)
                self.assertIsNotNone(restored, "output terminal flags were not observed before hangup")
                self.assertEqual(int(restored[1]), terminal.original[1],
                                 "output terminal flags were not restored")
            finally:
                terminal.close()

    def test_intro_animation_with_output_newline_mapping(self):
        self.check_newline_mapping("onlcr")

    def test_intro_animation_with_terminal_newline_mode(self):
        self.check_newline_mapping("lnm")


if __name__ == "__main__":
    unittest.main()
