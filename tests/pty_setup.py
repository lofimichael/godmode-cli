#!/usr/bin/env python3
"""Exercise the inline setup wizard with synthetic credentials in a real PTY.

No normal Godmode state, browser, provider account, or installed binary is used.
The raw transcript stays in memory and assertions never print secret values.
An optional second argument selects an installer script for regression checks.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import termios
import time

from pty_smoke import Terminal as BoardTerminal, values


SGR = re.compile(rb'\x1b\[[0-9;:]*m')


def plain_text(transcript):
    return SGR.sub(b'', bytes(transcript))


def has_style(transcript):
    return any(match.group() not in (b'\x1b[m', b'\x1b[0m')
               for match in SGR.finditer(transcript))


class Terminal(BoardTerminal):
    """The prompt wizard restores the terminal without an alternate screen."""

    def done(self, expected=0):
        self.wait(lambda: self.process.poll() is not None)
        self.drain()
        assert self.process.returncode == expected, 'unexpected setup exit status'
        match = re.search(rb'__PTY_FLAGS=(\d+)__', self.capture)
        assert match, 'terminal wrapper did not report flags'
        mask = termios.ECHO | termios.ICANON | termios.ISIG
        assert int(match[1]) & mask == self.original[3] & mask, 'terminal flags not restored'
        assert b'\x1b[?2004l' in self.capture, 'bracketed paste not disabled'
        assert b'\x1b[?1049h' not in self.capture, 'setup unexpectedly used an alternate screen'

    def expect(self, text, since=0):
        self.wait(lambda: text.encode() in plain_text(self.capture[since:]))

    def quiet(self, duration=0.15):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            self.drain(0.02)


def main():
    binary = Path(sys.argv[1] if len(sys.argv) > 1 else 'target/debug/godmode').resolve()
    assert binary.is_file(), 'build the binary before running setup PTY checks'
    installer = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / 'install.sh').resolve()
    assert installer.is_file(), 'installer script is missing'
    sessions = []
    token = 'github_pat_SETUP_SYNTHETIC_31a7df8c'
    replacement = 'github_pat_REPLACED_SYNTHETIC_64e02fc1'
    cancelled = 'CANCELLED_SETUP_SENTINEL_937e021a'
    wrong_prompt = 'MISPLACED_CREDENTIAL_SENTINEL_c8821be9'
    installed_token = 'github_pat_INSTALL_PIPE_SENTINEL_f41a7db5'
    invalid = 'INVALID_SETUP_SENTINEL_59f2\nSECOND_LINE'
    large = json.dumps({'type': 'service_account',
                        'private_key': 'JSON_SETUP_SENTINEL_4e28_' + 'z' * 14000,
                        'client_email': 'fixture@example.invalid'}, indent=2)
    with tempfile.TemporaryDirectory(prefix='godmode-setup-pty-') as raw_root:
        root = Path(raw_root).resolve()
        config = root / '.godmode'
        env_file = config / '.env.godmode'
        env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(root),
               'TERM': 'xterm-256color', 'COLORTERM': 'truecolor'}
        browser_log = root / 'opened-links'
        stub_bin = root / 'test-bin'
        stub_bin.mkdir()
        for name in ['open', 'xdg-open']:
            stub = stub_bin / name
            stub.write_text("#!/bin/sh\nprintf '%s\\n' \"$1\" >> " + shlex.quote(str(browser_log)) + "\n")
            stub.chmod(0o700)
        env['PATH'] = str(stub_bin) + ':' + env['PATH']
        command = [str(binary), '--home', str(config)]

        def start(args, term='xterm-256color', cols=110, no_color=False):
            session_env = dict(env, TERM=term)
            if no_color:
                session_env['NO_COLOR'] = '1'
            session = Terminal(command + args, session_env, cols=cols, rows=36)
            sessions.append(session)
            session.expect('Godmode setup')
            return session

        def provider(name, term='xterm-256color', no_color=False):
            session = start(['setup', name], term=term, no_color=no_color)
            session.expect('Enter to add keys;')
            assert b'No existing Godmode setup found' not in session.capture
            return session

        def key_prompt(session, name):
            session.expect('Paste ' + name + ' (masked;')

        try:
            # Interactive init is the wizard, and cancelling its first-run notice writes nothing.
            initial = start(['init'])
            initial.expect('No existing Godmode setup found')
            initial.expect('Type GODMODE to continue')
            initial.send(b'\x1b')
            initial.done(expected=2)
            assert not config.exists(), 'cancel before acknowledgement created configuration'
            assert not browser_log.exists(), 'setup opened a browser before a request'

            # A bare interactive command reaches setup. Paste at a menu is rejected without echo.
            first = start([], term='dumb')
            first.expect('Type GODMODE to continue')
            first.send(b'GODMODE\r')
            first.expect('Provider number or name')
            first.paste(wrong_prompt)
            first.expect('Paste credentials only at the masked key prompt')
            first.paste('github\r\n')
            first.quiet()
            assert not browser_log.exists(), 'selecting a provider opened a browser'
            first.send(b'\r')
            first.expect('Enter to add keys;')
            import tomllib
            registry = tomllib.loads((Path(__file__).resolve().parent.parent / 'registry/providers.toml').read_text())
            github = registry['provider'][0]
            expected_links = []
            for key, field in [(b'l', 'login'), (b'o', 'console'), (b'd', 'docs'), (b'o', 'console')]:
                mark = len(first.capture)
                first.send(key + b'\r')
                expected_links.append(github[field])
                first.wait(lambda: browser_log.exists() and len(browser_log.read_text().splitlines()) == len(expected_links))
                first.expect('Enter to add keys;', since=mark)
            assert browser_log.read_text().splitlines() == expected_links, 'link dispatch changed a full provider URL'
            first.send(b'\r')
            key_prompt(first, 'GH_TOKEN')
            before = env_file.read_bytes()
            first.paste('\r\n' + token + '\r\n')
            first.quiet()
            assert env_file.read_bytes() == before, 'pasting submitted before Enter'
            first.send(b'\r')
            first.wait(lambda: values(env_file).get('GH_TOKEN') == token)
            first.expect('GH_TOKEN saved.')
            first.expect('Provider number or name', since=mark)
            first.send(b'\r')
            first.done()
            assert not SGR.search(first.capture), 'TERM=dumb emitted style escapes'
            assert env_file.stat().st_mode & 0o777 == 0o600
            rules = config / 'AGENTS.md'
            rules.write_text('SYNTHETIC_RULES_PRESERVE_BYTES\n')
            original = env_file.read_bytes()

            # Keeping an existing value is the default; no value is preloaded or displayed.
            keep = provider('github')
            keep.send(b'\r')
            keep.expect('Enter to keep it / r to replace:')
            keep.send(b'\r')
            keep.done()
            assert env_file.read_bytes() == original, 'keeping a key changed its file'

            skip_provider = provider('github')
            skip_provider.send(b's\r')
            skip_provider.done()
            assert env_file.read_bytes() == original, 'skipping a provider changed credentials'

            # Plain terminals receive the same masked prompt; empty input skips a missing key.
            skip_key = provider('cloudflare', term='dumb')
            skip_key.send(b'\r')
            key_prompt(skip_key, 'CLOUDFLARE_API_TOKEN')
            skip_key.send(b'\r')
            skip_key.done()
            assert env_file.read_bytes() == original, 'empty input wrote or removed a key'

            # NO_COLOR removes styling but keeps paste protection and masked entry.
            monochrome = provider('cloudflare', no_color=True)
            monochrome.send(b'\r')
            key_prompt(monochrome, 'CLOUDFLARE_API_TOKEN')
            mark = len(monochrome.capture)
            monochrome.paste(cancelled)
            monochrome.quiet()
            assert b'****' in monochrome.capture[mark:], 'NO_COLOR input was not masked'
            monochrome.send(b'\x03')
            monochrome.done(expected=2)
            assert not SGR.search(monochrome.capture), 'NO_COLOR emitted style escapes'
            assert env_file.read_bytes() == original, 'NO_COLOR cancellation changed credentials'

            for cancel_key in [b'\x1b', b'\x03']:
                cancel = provider('github')
                cancel.send(b'\r')
                cancel.expect('Enter to keep it / r to replace:')
                cancel.send(b'r\r')
                key_prompt(cancel, 'GH_TOKEN')
                mark = len(cancel.capture)
                cancel.paste(cancelled)
                cancel.quiet()
                rendered = cancel.capture[mark:]
                assert has_style(rendered), 'normal terminal masked input has no styling'
                assert b'****' in plain_text(rendered), 'styled input was not masked'
                cancel.send(cancel_key)
                cancel.done(expected=2)
                assert env_file.read_bytes() == original, 'cancelled replacement changed credentials'

            # Invalid literal input retries at the same masked prompt without replacing the old key.
            retry = provider('github')
            retry.send(b'\r')
            retry.expect('Enter to keep it / r to replace:')
            retry.send(b'r\r')
            key_prompt(retry, 'GH_TOKEN')
            mark = len(retry.capture)
            retry.paste(invalid)
            retry.send(b'\r')
            retry.expect('No value was saved. Paste again', since=mark)
            retry.expect('Paste GH_TOKEN (masked;', since=mark)
            assert env_file.read_bytes() == original, 'invalid replacement changed credentials'
            retry.paste(cancelled)
            retry.send(b'\x15')  # Ctrl-U clears the unsaved value.
            retry.paste(replacement + 'x')
            retry.send(b'\x7f')  # Backspace removes the final synthetic character.
            retry.send(b'\r')
            retry.done()
            assert values(env_file)['GH_TOKEN'] == replacement, 'replacement editing changed literal input'

            raw_json = provider('google')
            raw_json.send(b'\r')
            key_prompt(raw_json, 'GOOGLE_ADS_SERVICE_ACCOUNT_JSON')
            before = env_file.read_bytes()
            raw_json.paste(large)
            raw_json.quiet()
            assert env_file.read_bytes() == before, 'multiline paste submitted before Enter'
            raw_json.send(b'\r')
            key_prompt(raw_json, 'GOOGLE_SEARCH_CONSOLE_SERVICE_ACCOUNT_JSON')
            raw_json.send(b'\r')
            raw_json.done()
            stored = values(env_file)
            assert json.loads(stored['GOOGLE_ADS_SERVICE_ACCOUNT_JSON']) == json.loads(large), 'raw JSON changed'
            assert stored['GH_TOKEN'] == replacement, 'JSON save changed an unrelated key'
            assert rules.read_bytes() == b'SYNTHETIC_RULES_PRESERVE_BYTES\n', 'setup changed operating rules'
            assert browser_log.read_text().splitlines() == expected_links, 'an unrequested link opened'
            # Exercise the actual Rust binary through the piped installer. A shell
            # fixture can read /dev/tty successfully while macOS kqueue cannot poll
            # that alias; this must use the real event reader and controlling PTY.
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            preserved = env_file.read_bytes()
            for action in ['save', 'cancel']:
                installed_home = root / ('installed-' + action)
                install_args = ['sh', '-s', '--', '--binary', str(binary), '--sha256', digest,
                                '--home', str(installed_home), '--setup']
                pipeline = 'cat ' + shlex.quote(str(installer)) + ' | ' + shlex.join(install_args)
                launched = Terminal(['sh', '-c', pipeline], env)
                sessions.append(launched)
                launched.expect('Starting interactive setup...')
                launched.expect('No existing Godmode setup found')
                launched.expect('Type GODMODE to continue')
                launched.send(b'GODMODE\r')
                launched.expect('Provider number or name')
                launched.send(b'github\r')
                launched.expect('Enter to add keys;')
                launched.send(b'\r')
                key_prompt(launched, 'GH_TOKEN')
                installed_env = installed_home / '.env.godmode'
                before = installed_env.read_bytes()
                launched.paste(installed_token)
                launched.quiet()
                assert installed_env.read_bytes() == before, 'installer-launched paste submitted before Enter'
                if action == 'save':
                    launched.send(b'\r')
                    launched.expect('GH_TOKEN saved.')
                    launched.send(b'\r')
                    launched.done()
                    assert values(installed_env)['GH_TOKEN'] == installed_token, 'installer-launched setup did not save'
                    assert installed_env.stat().st_mode & 0o777 == 0o600
                else:
                    launched.send(b'\x1b')
                    launched.done(expected=2)
                    assert installed_env.read_bytes() == before, 'installer-launched cancellation changed credentials'
                assert (installed_home / 'bin/godmode').read_bytes() == binary.read_bytes(), 'installer changed binary bytes'
                assert env_file.read_bytes() == preserved, 'installer setup changed the other configuration'

            # Finite commands use the same terminal-aware palette; JSON remains machine-readable.
            def finite(args, no_color=False):
                command_env = dict(env)
                if no_color:
                    command_env['NO_COLOR'] = '1'
                session = BoardTerminal(command + args, command_env)
                sessions.append(session)
                session.wait(lambda: session.process.poll() is not None)
                session.drain()
                assert session.process.returncode == 0, 'finite command failed'
                flags = re.search(rb'__PTY_FLAGS=(\d+)__', session.capture)
                assert flags, 'finite command wrapper did not report terminal flags'
                mask = termios.ECHO | termios.ICANON | termios.ISIG
                assert int(flags[1]) & mask == session.original[3] & mask, 'finite command changed terminal flags'
                return bytes(session.capture)

            for args in [['--help'], ['providers'], ['guide', 'github'], ['status'], ['doctor']]:
                assert has_style(finite(args)), 'terminal command did not use its color palette'
            for args in [['status', '--json'], ['providers', '--json'], ['doctor', '--json']]:
                output = finite(args)
                assert not SGR.search(output), 'JSON output contains terminal styles'
                payload = re.sub(rb'__PTY_FLAGS=\d+__\r?\n?', b'', output).decode().strip()
                assert json.loads(payload) is not None, 'JSON command returned no data'
            for args in [['--help'], ['guide', 'github']]:
                assert not SGR.search(finite(args, no_color=True)), 'NO_COLOR command emitted styles'
            for args in [['--help'], ['providers'], ['guide', 'github'], ['status'], ['doctor']]:
                output = subprocess.run(command + args, env=env, capture_output=True, check=True)
                assert not SGR.search(output.stdout), 'redirected command output contains terminal styles'

            for session in sessions:
                for sentinel in [token, replacement, cancelled, wrong_prompt, installed_token,
                                 'INVALID_SETUP_SENTINEL_59f2', 'JSON_SETUP_SENTINEL_4e28_']:
                    assert sentinel.encode() not in plain_text(session.capture), 'setup exposed synthetic credential input'
            print('Setup PTY passed: default/init routing, first-run cancel/ack, exact requested links, '
                  'masked paste, Enter-only save, clipboard CRLF, keep/skip/replace, invalid retry, '
                  'Ctrl-U/Backspace, Esc/Ctrl-C, 14 KB JSON, styled input/commands, plain JSON/redirection, '
                  'NO_COLOR, TERM=dumb, actual piped-installer save/cancel and terminal restoration.')
        finally:
            for session in sessions:
                session.close()


if __name__ == '__main__':
    main()
