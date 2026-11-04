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
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait()
        os.close(self.master)
        os.close(self.slave)


def values(path):
    result = {}
    for line in path.read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            key, raw = line.split('=', 1)
            parsed = shlex.split(raw, comments=True)
            if len(parsed) == 1:
                result[key] = parsed[0]
    return result
