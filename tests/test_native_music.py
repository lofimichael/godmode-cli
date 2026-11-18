"""Real music-terminal navigation in synthetic homes; never starts audio."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_native_cli import BINARY as CORE_BINARY, NativeTerminal

ROOT = Path(__file__).resolve().parents[1]
MUSIC_BINARY = Path(os.environ.get("GODMODE_TEST_MUSIC_BINARY", ROOT / "target/godmode-music-pack"))


@unittest.skipUnless(MUSIC_BINARY.exists(), 'Build the optional music companion first.')
class NativeMusic(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='godmode-native-music-')
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / '.godmode'
        self.env = {'HOME': str(self.root), 'GODMODE_HOME': str(self.home),
                    'PATH': os.environ['PATH'], 'TERM': 'xterm-256color',
                    'GODMODE_NO_MOTION': '1', 'NO_COLOR': '1'}
        self.sessions = []

    def tearDown(self):
        for term in self.sessions:
            term.close()
        subprocess.run([str(MUSIC_BINARY), 'music', 'stop'], env=self.env,
                       capture_output=True, timeout=10)
        self.temp.cleanup()

    def library(self):
        synth = self.root / 'synth'
        songs = self.root / 'songs'
        synth.mkdir(mode=0o700)
        script = synth / 'synthesize.py'
        script.write_text('raise AssertionError("This navigation test must never synthesize")\n')
        for name in ('Alpha/First.ootrs', 'Alpha/Second.ootrs', 'Beta/Third.ootrs'):
            path = songs / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic sequence fixture')
        state = self.home / 'state/music'
        state.mkdir(parents=True, mode=0o700)
        config = state / 'config.json'
        config.write_text(json.dumps({'version': 1, 'backend': str(synth), 'songs': str(songs),
                                      'sha256': hashlib.sha256(script.read_bytes()).hexdigest()}))
        config.chmod(0o600)
        # Enqueue requires an available player, but it must never invoke it.
        bindir = self.root / 'bin'
        bindir.mkdir()
        player = bindir / 'mpv'
        player.write_text('#!/bin/sh\nexit 99\n')
        player.chmod(0o700)
        self.env['PATH'] = str(bindir) + ':' + self.env['PATH']

    def tty(self, cols=80, rows=24):
        term = NativeTerminal([str(MUSIC_BINARY), 'music'], self.env, cols=cols, rows=rows)
        self.sessions.append(term)
        return term

    def status(self):
        result = subprocess.run([str(MUSIC_BINARY), 'music', 'status', '--json'], env=self.env,
                                text=True, capture_output=True, timeout=10, check=True)
        return json.loads(result.stdout)

    def test_narrow_setup_has_actionable_command_and_clean_exit(self):
        term = self.tty(40, 18)
        term.expect_screen('godmode music setup')
        term.expect_screen('--songs DIR')
        term.expect_screen('.ootrs')
        # Tool guidance lives in the scrollable body on a narrow terminal.
        for _ in range(4):
            if 'brew install mpv ffmpeg cmake' in term.screen_text():
                break
            term.send(b'\x1b[6~')
            term.settle(.12)
        term.expect_screen('brew install mpv ffmpeg cmake')
        term.send(b'q')
        term.done(0)
        self.assertFalse(self.home.exists())

    def test_search_preserves_query_and_back_and_never_starts_playback(self):
        self.library()
        term = self.tty(40, 18)
        term.expect_screen('All tracks')
        term.send(b'\x1b[B\r')
        term.expect_screen('Library / Alpha')
        term.send(b'/nothing-matches')
        term.expect_screen('nothing-matches')
        term.expect_screen('No tracks match')
        term.send(b'\x1b')
        term.expect_screen('Library / Alpha')
        term.send(b'\x1b')
        term.expect_screen('Collections')
        self.assertEqual(self.status()['state'], 'stopped')
        term.send(b'/Second\r')
        term.expect_screen('Enter replaces queue')
        self.assertEqual(self.status()['state'], 'stopped')
        self.assertEqual(self.status()['queue'], [])
        term.send(b'a')
        term.expect_screen('Added to queue')
        self.assertEqual([t['title'] for t in self.status()['queue']], ['Second'])
        self.assertEqual(self.status()['state'], 'stopped')
        term.send(b'q')
        term.done(0)
        self.assertNotRegex(bytes(term.capture), rb'\x1b\[[0-9:;]*m')

    def test_queue_survives_view_exit_and_stop_preserves_it(self):
        self.library()
        term = self.tty()
        term.expect_screen('All tracks')
        term.send(b'a')
        term.expect_screen('Added to queue')
        term.send(b'\t')
        term.expect_screen('First')
        self.assertEqual(len(self.status()['queue']), 3)
        term.send(b'd')
        term.expect_screen('Removed from queue')
        term.send(b'q')
        term.done(0)
        s = self.status()
        self.assertEqual(len(s['queue']), 2)
        self.assertEqual(s['state'], 'stopped')
        term = self.tty()
        term.expect_screen('All tracks')
        term.send(b'\t')
        term.expect_screen('Second')
        term.send(b'x')
        term.expect_screen('Stopped')
        term.send(b'q')
        term.done(0)
        self.assertEqual(len(self.status()['queue']), 2)
        self.assertEqual(self.status()['state'], 'stopped')
        # Reattach to the stopped last-played row. Removing it must edit the
        # queue without starting the replacement's renderer or audio player.
        saved_path = self.home / 'state/music/session.json'
        saved = json.loads(saved_path.read_text())
        saved['index'] = 0
        saved_path.write_text(json.dumps(saved))
        term = self.tty()
        term.expect_screen('All tracks')
        term.send(b'\t')
        term.expect_screen('Second')
        term.send(b'd')
        term.expect_screen('Removed from queue')
        term.settle(.3)
        self.assertEqual(self.status()['state'], 'stopped')
        self.assertEqual([t['title'] for t in self.status()['queue']], ['Third'])
        term.send(b'q')
        term.done(0)


@unittest.skipUnless(CORE_BINARY.exists(), 'Build the core native candidate first.')
class NativeMusicOptIn(unittest.TestCase):
    def test_uninstalled_core_card_escape_does_not_mutate_home(self):
        for cols, rows in ((40, 18), (80, 24)):
            with self.subTest(columns=cols, rows=rows), tempfile.TemporaryDirectory(prefix='godmode-music-optin-') as temp:
                root = Path(temp).resolve()
                home = root / '.godmode'
                env = {'HOME': str(root), 'GODMODE_HOME': str(home),
                       'PATH': os.environ['PATH'], 'TERM': 'xterm-256color',
                       'GODMODE_NO_MOTION': '1', 'NO_COLOR': '1'}
                before = set(root.iterdir())
                term = NativeTerminal([str(CORE_BINARY), 'music'], env, cols=cols, rows=rows)
                try:
                    term.expect_screen('OPTIONAL MUSIC PACK')
                    term.expect_screen('Enter install')
                    term.expect_screen('Esc back')
                    term.send(b'\x1b')
                    term.done(0)
                finally:
                    term.close()
                self.assertEqual(set(root.iterdir()), before, 'Cancelling pack installation changed HOME')
                self.assertFalse(home.exists())


if __name__ == '__main__':
    unittest.main()
