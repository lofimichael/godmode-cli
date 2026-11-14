#!/usr/bin/env python3
"""Capture actual Godmode PTY states with isolated, synthetic data only."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=REPO / 'target/visual-tour')
OUTPUT = parser.parse_args().output.resolve()
OUTPUT.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location('demo', REPO / 'scripts/record-demo.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)

with tempfile.TemporaryDirectory(prefix='godmode-visual-tour-', dir='/private/tmp' if Path('/private/tmp').is_dir() else None) as temp:
    root = Path(temp)
    home = root / '.godmode'
    binary = home / 'bin/godmode'
    binary.parent.mkdir(parents=True, mode=0o700)
    home.chmod(0o700)
    subprocess.run([sys.executable, str(REPO / 'scripts/build.py'), '--output', str(binary)],
                   check=True, stdout=subprocess.DEVNULL)
    env = {'HOME': str(root), 'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
           'TERM': 'xterm-256color', 'COLORTERM': 'truecolor', 'PYTHONUTF8': '1'}
    def command(*args, data=None):
        return subprocess.run([str(binary), *args], env=env, input=data, text=True,
                              check=True, capture_output=True)
    command('set', 'DEMO_TOKEN', '--stdin', data='synthetic_visual_tour_key_12345')
    for field, value in (('operator_name', 'Alex Example'), ('business_name', 'Example Studio'),
                         ('website', 'https://example.test')):
        command('profile', 'set', field, '--stdin', data=value)
    marker = home / 'intro.seen'
    marker.touch(mode=0o600)
    for folder in ('.claude', '.codex', '.gemini', '.copilot', '.config/opencode'):
        (root / folder).mkdir(parents=True, exist_ok=True)
    metadata = {'caption': 'Godmode CLI · 2026-11-14',
                'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'states': []}
    def record(name, args, waiting, actions=(), cols=80, rows=24, theme='dark'):
        terminal = demo.Terminal([str(binary), *args], env, cols=cols, rows=rows)
        recorder = demo.Recorder(terminal, cols, rows, demo.font_path(None), theme,
                                 caption='Godmode CLI · 2026-11-14')
        try:
            recorder.wait_for(waiting)
            for event, expected in actions:
                if isinstance(event, tuple):
                    terminal.paste(event[0])
                else:
                    terminal.send(event)
                recorder.wait_for(expected)
            recorder.capture(1000)
            destination = OUTPUT / (name + '.png')
            recorder.frames[-1].save(destination)
            capture = bytes(terminal.capture)
            for secret in (b'synthetic_visual_tour_key_12345', b'DEMO_ONLY_LINE_ONE', b'DEMO_ONLY_LINE_TWO'):
                assert secret not in capture, 'synthetic value echoed'
            metadata['states'].append({'file': destination.name, 'columns': cols, 'rows': rows,
                                       'theme': theme, 'command': 'godmode ' + ' '.join(args)})
            terminal.send(b'\x03')
            terminal.done(130)
        finally:
            terminal.close()
    record('01-profile', ['profile'], 'Legal name')
    record('02-profile-field', ['profile'], 'Legal name', ((b'\r', 'Enter skips'),))
    record('03-agent-preview', ['agents'], 'Add to 5 agents')
    record('04-provider-search', ['setup'], 'Another key', ((b'/cloud', '/ cloud'),))
    record('05-narrow-home', [], 'Esc quit', cols=40, rows=12)
    invalid = ('DEMO_ONLY_LINE_ONE\nDEMO_ONLY_LINE_TWO',)
    record('06-key-error', ['set', 'ACME_TOKEN'], 'Paste your token:', ((invalid, 'Ctrl-U clears'),))
    record('07-narrow-key-error', ['set', 'ACME_TOKEN'], 'Paste your token:',
           ((invalid, 'Ctrl-U clears'),), cols=40, rows=12)
    record('08-profile-light', ['profile'], 'Legal name', theme='light')
    record('09-agent-preview-light', ['agents'], 'Add to 5 agents', theme='light')
    record('10-provider-search-light', ['setup'], 'Another key', ((b'/cloud', '/ cloud'),), theme='light')
    assert not (root / '.claude/rules/godmode.md').exists(), 'agent instructions changed'
    assert command('list').stdout == 'DEMO_TOKEN\n', 'unexpected credential write'
    assert json.loads(command('profile', 'show').stdout) == {
        'operator_name': 'Alex Example', 'business_name': 'Example Studio', 'website': 'https://example.test'}
    (OUTPUT / 'receipt.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print('Captured %d actual terminal states; synthetic data preserved.' % len(metadata['states']))
