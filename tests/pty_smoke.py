#!/usr/bin/env python3
"""Exercise real terminal input using synthetic keys in an isolated directory.

Run after cargo build: python3 tests/pty_smoke.py [path/to/godmode]
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
        # Ratatui may advance the cursor over blank cells instead of emitting
        # literal spaces, especially with a terminal-default background. Match
        # the words across that positioning/style output as well as raw text.
        separator = rb'(?:\s|\x1b\[[0-?]*[ -/]*[@-~])+'
        pattern = re.compile(separator.join(re.escape(word.encode()) for word in text.split()))
        self.wait(lambda: bool(pattern.search(self.capture)))

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
        assert b'\x1b[?1049l' in self.capture, 'alternate screen not left'

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


def main():
    binary = Path(sys.argv[1] if len(sys.argv) > 1 else 'target/debug/godmode').resolve()
    assert binary.is_file(), 'build the binary before running PTY smoke'
    sessions = []
    with tempfile.TemporaryDirectory(prefix='godmode-pty-') as raw_root:
        root = Path(raw_root).resolve()
        config, state = root / 'config', root / 'state'
        env_file = config / '.env.godmode'
        env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(root),
               'TERM': 'xterm-256color', 'COLORTERM': 'truecolor',
               'GODMODE_REDUCE_MOTION': '1'}
        # Verify link dispatch without opening a browser or making a request.
        browser_log = root / 'opened-links'
        stub_bin = root / 'test-bin'
        stub_bin.mkdir()
        for name in ['open', 'xdg-open']:
            stub = stub_bin / name
            stub.write_text("#!/bin/sh\nprintf '%s\\n' \"$1\" >> " + shlex.quote(str(browser_log)) + "\n")
            stub.chmod(0o700)
        env['PATH'] = str(stub_bin) + ':' + env['PATH']
        command = [str(binary), '--config-dir', str(config), '--state-dir', str(state), '--no-motion']
        token = 'github_pat_PTY_SECRET_SENTINEL_9b6f2054'
        cancelled = 'CANCELLED_PRIVATE_SENTINEL_f08d'
        large = json.dumps({'type': 'service_account',
                            'private_key': 'MULTILINE_PTY_SENTINEL_21a0_' + 'z' * 14000,
                            'client_email': 'fixture@example.invalid'}, indent=2)
        try:
            first = Terminal(command + ['onboard'], env)
            sessions.append(first)
            first.seen('READTHIS.NFO')
            first.seen('No existing Godmode setup found')
            assert not browser_log.exists(), 'link opened before explicit request'
            assert not env_file.exists(), 'onboarding wrote before acknowledgement'
            first.send(b'GODMODE\r')
            first.seen('PROVIDERS')
            for index, key in enumerate([b'l', b'o', b'd']):
                first.send(key)
                first.wait(lambda: browser_log.exists() and len(browser_log.read_text().splitlines()) == index + 1)
            import tomllib
            registry = tomllib.loads((Path(__file__).resolve().parent.parent / 'registry/providers.toml').read_text())
            github = registry['provider'][0]
            assert browser_log.read_text().splitlines() == [github['login'], github['console'], github['docs']]
            first.send(b'\r')
            first.seen('ADD / REPLACE')
            first.paste(token)
            first.send(b'\r')
            first.wait(lambda: env_file.exists() and values(env_file).get('GH_TOKEN') == token)
            first.send(b'n')
            first.seen('Next provider selected')
            first.send(b'q')
            first.done()
            assert env_file.stat().st_mode & 0o777 == 0o600

            second = Terminal(command + ['set', 'GOOGLE_ADS_SERVICE_ACCOUNT_JSON'], env)
            sessions.append(second)
            second.seen('GODMODE / KEY ENTRY')
            second.paste(large)
            second.send(b'\r')
            second.done()
            stored = values(env_file)
            assert json.loads(stored['GOOGLE_ADS_SERVICE_ACCOUNT_JSON']) == json.loads(large), 'large JSON paste changed'
            assert stored['GH_TOKEN'] == token, 'unrelated key changed'

            before = env_file.read_bytes()
            third = Terminal(command + ['onboard'], env)
            sessions.append(third)
            third.seen('PROVIDERS')
            assert b'READTHIS.NFO' not in third.capture, 'acknowledgement did not persist'
            third.send(b'\r')
            third.seen('ADD / REPLACE')
            third.paste(cancelled)
            third.send(b'\x1b')
            third.seen('Cancelled.')
            third.send(b'q')
            third.done()
            assert env_file.read_bytes() == before, 'cancel changed credential file'

            fourth = Terminal(command + ['set', 'GH_TOKEN'], env)
            sessions.append(fourth)
            fourth.seen('GODMODE / KEY ENTRY')
            fourth.paste(cancelled)
            fourth.send(b'\x03')
            fourth.done(expected=2)
            assert env_file.read_bytes() == before, 'Ctrl-C changed credential file'

            for session in sessions:
                for sentinel in [token, cancelled, 'MULTILINE_PTY_SENTINEL_21a0_']:
                    assert sentinel.encode() not in session.capture, 'credential leaked into terminal output'
            print('PTY smoke passed: new-setup notice, acknowledgement, exact login/key/docs dispatch, guided next, provider save, 14 KB JSON paste, cancel, Ctrl-C, masking, terminal restoration.')
        finally:
            for session in sessions:
                session.close()


if __name__ == '__main__':
    main()
