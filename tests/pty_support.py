#!/usr/bin/env python3
"""Exercise real terminal input using synthetic keys in an isolated directory.

Shared bounded PTY harness for the readable CLI and demo recorder.
The raw terminal capture stays in memory and is never printed or written.
"""
import errno
import fcntl
import json
import os
from pathlib import Path
import select
import re
import shlex
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time


class Terminal:
    def __init__(self, command, env, cols=110, rows=36):
        self.master, self.slave = os.openpty()
        os.set_blocking(self.master, False)
        self.original = termios.tcgetattr(self.slave)
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
        self.capture = bytearray()

        def controlling_terminal():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        wrapper = ("import subprocess,sys,termios; "
                   "code=subprocess.call(sys.argv[1:]); "
                   "print('__PTY_FLAGS=' + str(termios.tcgetattr(0)[3]) + '__', flush=True); "
                   "sys.exit(code)")
        self.process = subprocess.Popen([sys.executable, '-c', wrapper, *command], stdin=self.slave, stdout=self.slave,
                                        stderr=self.slave, env=env,
                                        preexec_fn=controlling_terminal)

    def drain(self, timeout=0.05):
        if select.select([self.master], [], [], timeout)[0]:
            try:
                data = os.read(self.master, 65536)
                self.capture.extend(data)
            except OSError as exc:
                if exc.errno not in (errno.EIO, errno.EAGAIN):
                    raise

    def wait(self, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > deadline:
                raise RuntimeError('PTY expectation timed out; capture suppressed')
            self.drain()
            if self.process.poll() is not None and not predicate():
                raise RuntimeError('PTY child exited before expected state; capture suppressed')

    def seen(self, text):
        # Match words across terminal positioning and style sequences.
        separator = rb'(?:\s|\x1b\[[0-?]*[ -/]*[@-~])+'
        pattern = re.compile(separator.join(re.escape(word.encode()) for word in text.split()))
        self.wait(lambda: bool(pattern.search(self.capture)))

    def settle(self, duration=0.4):
        """Keep reading until the deadline: for checks that something does not happen."""
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            self.drain(0.02)

    def after(self, mark, text, timeout=8):
        """Wait for text in the output written since mark, ignoring color and cursor codes."""
        self.wait(lambda: text in plain(self.capture[mark:]), timeout)

    def expect(self, text):
        self.seen(text)

    def send(self, data):
        view = memoryview(data)
        deadline = time.monotonic() + 10
        while view:
            if time.monotonic() > deadline:
                raise RuntimeError('PTY write timed out; capture suppressed')
            ready, writable, _ = select.select([self.master], [self.master], [], 0.05)
            if ready:
                self.drain(0)
            if writable:
                try:
                    sent = os.write(self.master, view[:1024])
                    view = view[sent:]
                except BlockingIOError:
                    pass

    def paste(self, text):
        self.send(b'\x1b[200~' + text.encode() + b'\x1b[201~')

    def done(self, expected=0):
        self.wait(lambda: self.process.poll() is not None)
        self.drain()
        assert self.process.returncode == expected, 'unexpected PTY exit status'
        match = re.search(rb'__PTY_FLAGS=(\d+)__', self.capture)
        assert match, 'terminal wrapper did not report flags'
        mask = termios.ECHO | termios.ICANON | termios.ISIG
        assert int(match[1]) & mask == self.original[3] & mask, 'terminal flags not restored'
        assert b'\x1b[?2004l' in self.capture, 'bracketed paste not disabled'
        assert b'\x1b[?1049h' not in self.capture, 'unexpected alternate screen'

    def close(self):
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass  # The session ended between the check and the kill.
            # A dying session leader waits for unread terminal output to drain; keep reading.
            deadline = time.monotonic() + 5
            while self.process.poll() is None and time.monotonic() < deadline:
                self.drain(0.05)
        os.close(self.master)
        os.close(self.slave)
        self.process.wait(timeout=5)


def plain(capture):
    """Terminal output without color or cursor sequences."""
    return re.sub(rb'\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07', b'', bytes(capture)).decode('utf-8', 'replace')


def values(path):
    """Saved values, read the way godmode reads them: sealed values are unsealed."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
    from godmode_store import Store
    store = Store(str(Path(path).parent))
    return store.values([name for name, state in store.states().items() if state == 'set'])


class Screen:
    """A small terminal model, enough to check that a prompt redraws in place.

    Handles printing with autowrap, CR, LF, cursor up (CSI n A) and erase below
    (CSI J); other escape sequences are ignored. Rows are kept without scrolling,
    so the whole session can be inspected.
    """
    def __init__(self, cols):
        self.cols, self.rows, self.x, self.y = cols, [[]], 0, 0

    def _row(self):
        while len(self.rows) <= self.y:
            self.rows.append([])
        return self.rows[self.y]

    def feed(self, data):
        text = bytes(data).decode('utf-8', 'replace')
        i = 0
        while i < len(text):
            char = text[i]
            if char == '\x1b':
                match = re.match(r'\x1b(?:\[([0-9;?]*)([@-~])|\][^\x07]*\x07|.)', text[i:], re.S)
                if match and match.group(2) == 'A':
                    self.y = max(0, self.y - int(match.group(1) or 1))
                elif match and match.group(2) == 'J':
                    del self._row()[self.x:]
                    del self.rows[self.y + 1:]
                i += match.end() if match else 1
                continue
            if char == '\r':
                self.x = 0
            elif char == '\n':
                self.y += 1
                self._row()
            elif char >= ' ':
                if self.x >= self.cols:
                    self.x, self.y = 0, self.y + 1
                row = self._row()
                row.extend(' ' * (self.x - len(row)))
                row[self.x:self.x + 1] = [char]
                self.x += 1
            i += 1
        return self

    def lines(self):
        return [''.join(row).rstrip() for row in self.rows]

    def count(self, text):
        return sum(text in row for row in self.lines())
