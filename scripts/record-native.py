#!/usr/bin/env python3
"""Capture the native Godmode TUI in real PTYs, using synthetic local data only.

Requires scripts/demo-requirements.txt. Every subprocess receives an isolated,
resolved HOME. The recorder never reads the user's Godmode files, opens provider
links, launches audio, or contacts a provider. Raw PTY captures stay in memory.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import date

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tests'))
from test_native_cli import NativeTerminal

SPEC = importlib.util.spec_from_file_location('godmode_demo', REPO / 'scripts/record-demo.py')
DEMO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEMO)

SYNTHETIC = 'synthetic_NATIVE_DEMO_TOKEN_00015'
MASKED = 'syn•••••015'
PREFIX = b'# Existing agent rules\r\nKeep this exact text and line ending.'


class NativeScreen(DEMO.pyte.Screen):
    """Add the VT scroll operations used by Bubble Tea's native renderer."""
    def scroll_up(self, count=1):
        top, bottom = self.margins or (0, self.lines - 1)
        previous = self.cursor.y
        self.cursor.y = bottom
        for _ in range(min(count or 1, bottom - top + 1)):
            self.index()
        self.cursor.y = previous

    def scroll_down(self, count=1):
        top, bottom = self.margins or (0, self.lines - 1)
        previous = self.cursor.y
        self.cursor.y = top
        for _ in range(min(count or 1, bottom - top + 1)):
            self.reverse_index()
        self.cursor.y = previous


class NativeStream(DEMO.pyte.Stream):
    csi = dict(DEMO.pyte.Stream.csi, S='scroll_up', T='scroll_down')
    events = DEMO.pyte.Stream.events | frozenset(('scroll_up', 'scroll_down'))


class Recorder(DEMO.Recorder):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.screen = NativeScreen(self.cols, self.rows)
        self.stream = NativeStream(self.screen)


def check_terminal_model():
    screen = NativeScreen(5, 4)
    stream = NativeStream(screen)
    stream.feed('A\r\nB\r\nC\r\nD\x1b[2;4r\x1b[2;3H\x1b[1S')
    assert [line.strip() for line in screen.display] == ['A', 'C', 'D', '']
    assert (screen.cursor.y, screen.cursor.x) == (1, 2)
    stream.feed('\x1b[1T')
    assert [line.strip() for line in screen.display] == ['A', '', 'C', 'D']
    assert (screen.cursor.y, screen.cursor.x) == (1, 2)


def main():
    check_terminal_model()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=REPO / 'target/godmode-native')
    parser.add_argument('--output', type=Path, default=REPO / 'target/native-tour')
    parser.add_argument('--copy-to', type=Path, help='copy the verified outputs to a second directory')
    parser.add_argument('--font', type=Path)
    parser.add_argument('--date', default=date.today().isoformat(), help='source date in the image caption')
    args = parser.parse_args()
    binary, output = args.binary.resolve(), args.output.resolve()
    if not binary.is_file():
        parser.error('Build the native candidate first.')
    output.mkdir(parents=True, exist_ok=True)
    caption = 'Godmode CLI · ' + args.date
    font = DEMO.font_path(args.font)
    evidence = {'caption': caption, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                'screens': [], 'checks': []}

    with tempfile.TemporaryDirectory(prefix='godmode-native-record-',
                                     dir='/private/tmp' if Path('/private/tmp').is_dir() else None) as temp:
        root = Path(temp).resolve()
        home = root / '.godmode'
        env = {'HOME': str(root), 'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
               'TERM': 'xterm-256color', 'COLORTERM': 'truecolor', 'PYTHONUTF8': '1',
               'GODMODE_NO_MOTION': '1', 'CODEX_HOME': str(root / '.codex'),
               'COPILOT_HOME': str(root / '.copilot')}

        def command(*words, data=None):
            return subprocess.run([str(binary), *words], env=env, input=data, text=True,
                                  capture_output=True, check=True, timeout=15)

        def verify_capture(terminal):
            # Recognizable, synthetic secret middles must never reach any frame or log.
            for forbidden in (SYNTHETIC.encode(), b'NATIVE_DEMO_TOKEN', b'PRIVATE_NOT_FOR_FRAME'):
                assert forbidden not in terminal.capture, 'synthetic credential exposed by the UI'

        def shot(recorder, name, words, cols, rows, theme='dark', duration=1000):
            recorder.capture(duration)
            verify_capture(recorder.terminal)
            recorder.frames[-1].save(output / (name + '.png'))
            evidence['screens'].append({'file': name + '.png', 'command': 'godmode ' + ' '.join(words),
                                        'columns': cols, 'rows': rows, 'theme': theme})

        # One continuous session supplies the GIF: intro → home → provider → paste preview.
        cols, rows = 100, 32
        terminal = NativeTerminal([str(binary)], env, cols=cols, rows=rows)
        recorder = Recorder(terminal, cols, rows, font, caption=caption)
        try:
            recorder.wait_for('Enter accept and set up')
            shot(recorder, 'intro', [], cols, rows, duration=2400)
            terminal.send(b'\r')
            recorder.wait_for('Esc quit')
            shot(recorder, 'home-empty', [], cols, rows, duration=1300)
            terminal.send(b'\x1b[B\r')
            recorder.wait_for('Choose how powerful')
            shot(recorder, 'providers', ['setup'], cols, rows, duration=1000)
            terminal.send(b'/vercel')
            recorder.wait_for('/ vercel')
            terminal.send(b'\r')
            recorder.wait_for("Visit Vercel's token page")
            shot(recorder, 'vercel', ['setup', 'vercel'], cols, rows, duration=1800)
            terminal.paste(SYNTHETIC)
            recorder.wait_for('VERCEL_TOKEN=sealed(' + MASKED + ')')
            shot(recorder, 'key-preview', ['setup', 'vercel'], cols, rows, duration=1800)
            assert not (home / '.env.godmode').exists(), 'paste submitted the key without Enter'
            terminal.send(b'\r')
            recorder.wait_for('Choose how powerful')
            terminal.send(b'\x03')
            terminal.done(130)
            verify_capture(terminal)
            recorder.write(output / 'tour.gif')
        finally:
            terminal.close()
        assert command('list').stdout == 'VERCEL_TOKEN\n'
        assert SYNTHETIC not in (home / '.env.godmode').read_text()
        command('run', 'VERCEL_TOKEN', '--', sys.executable, '-c',
                'import os,sys;sys.exit(0 if os.environ["VERCEL_TOKEN"].startswith("synthetic_NATIVE_DEMO") else 9)')
        evidence['checks'] += ['complete paste stayed pending until Enter', 'saved key stayed sealed',
                               'godmode run supplied the exact synthetic key', 'native terminal restored on exit']

        for field, value in (('operator_name', 'Alex Example'), ('business_name', 'Example Studio'),
                             ('website', 'https://example.test')):
            command('profile', 'set', field, '--stdin', data=value)
        for folder in ('.claude', '.codex', '.gemini', '.copilot', '.config/opencode'):
            (root / folder).mkdir(parents=True, exist_ok=True)
        target = root / '.codex/AGENTS.md'
        target.write_bytes(PREFIX)
        target.chmod(0o600)

        def record(name, words, waiting, cols=100, rows=32, theme='dark', apply=False):
            session_env = dict(env, COLORFGBG='0;15' if theme == 'light' else '15;0')
            session = NativeTerminal([str(binary), *words], session_env, cols=cols, rows=rows)
            screen = Recorder(session, cols, rows, font, theme, caption=caption)
            try:
                screen.wait_for(waiting)
                shot(screen, name, words, cols, rows, theme)
                if apply:
                    screen.wait_for('godmode:end')
                    session.send(b'\r')
                    session.done()
                else:
                    session.send(b'\x03')
                    session.done(130)
                verify_capture(session)
            finally:
                session.close()

        record('home', [], 'Esc quit', cols=110, rows=32)
        record('home-80', [], 'Esc quit', cols=80, rows=24)
        record('home-40', [], 'Esc quit', cols=40, rows=12)
        record('home-light', [], 'Esc quit', cols=110, rows=32, theme='light')
        record('profile', ['profile'], 'Mailing address')
        record('faq', ['faq'], 'Does Godmode make network calls?')
        record('agents', ['agents'], 'These files will be modified:', apply=True)
        after = target.read_bytes()
        assert after.startswith(PREFIX), 'agent append changed existing bytes'
        assert after.count(b'godmode:start') == 1
        assert target.stat().st_mode & 0o777 == 0o600
        record('agents-added', ['agents'], 'already added')
        assert target.read_bytes() == after, 'viewing existing agent notes changed the file'
        assert command('list').stdout == 'VERCEL_TOKEN\n'
        evidence['checks'] += ['agent append preserved existing CRLF bytes and mode',
                               'existing agent notes stayed unchanged', 'synthetic key inventory stayed unchanged']

    if hashlib.sha256(binary.read_bytes()).hexdigest() != evidence['binary_sha256']:
        raise RuntimeError('Native binary changed during capture; record the final candidate again.')
    files = sorted(path for path in output.iterdir() if path.suffix in ('.png', '.gif'))
    evidence['artifacts'] = {path.name: {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                       'bytes': path.stat().st_size} for path in files}
    (output / 'receipt.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    if args.copy_to:
        destination = args.copy_to.resolve()
        destination.mkdir(parents=True, exist_ok=True)
        for path in files + [output / 'receipt.json']:
            shutil.copyfile(path, destination / path.name)
    print('Captured %d native screens and a %.1f-second GIF; synthetic preservation checks passed.'
          % (len(evidence['screens']), sum(recorder.durations) / 1000))
    print(output)


if __name__ == '__main__':
    main()
