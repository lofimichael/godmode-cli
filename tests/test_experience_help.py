"""Local help, source verification and sparse provider instructions."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('experience_help', ROOT / 'godmode.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class ExperienceHelp(unittest.TestCase):
    def test_faq_resolves_explicit_home_without_reading_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / 'godmode'
            with patch.object(cli.Store, 'states', side_effect=AssertionError('read keys')):
                entries = dict(cli.faq_entries(home))
            self.assertIn(str(home / '.env.godmode'), entries['Where are my tokens?'][0])
            self.assertFalse(home.exists())
            self.assertIn('godmodeup', ' '.join(entries['Does Godmode make network calls?']))
            self.assertIn('An agent running as you can still get the keys.', ' '.join(entries['What is sealed(...)?']))

    def test_vercel_instructions_have_separate_title_link_and_bullet(self):
        provider = next(p for p in cli.catalog() if p['id'] == 'vercel')
        with tempfile.TemporaryDirectory() as directory:
            prompt = cli.KeyPrompt(cli.Store(Path(directory) / 'home'), provider['key'][0], provider)
            rows = prompt.guide(78)
        self.assertEqual(rows[0], "Visit Vercel's token page")
        self.assertTrue(rows[1].startswith('https://'))
        self.assertEqual(rows[2], '')
        self.assertTrue(rows[3].startswith('- Make a token'))

    def test_source_comparison_detects_tampering_without_executing_script(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'godmode'
            base = [sys.executable, str(ROOT / 'scripts/build.py')]
            subprocess.run(base + ['--output', str(path)], check=True, capture_output=True)
            good = subprocess.run(base + ['--verify', str(path)], capture_output=True, text=True)
            self.assertEqual(good.returncode, 0, good.stderr)
            path.write_text('raise SystemExit("do not run me")\n' + path.read_text())
            bad = subprocess.run(base + ['--verify', str(path)], capture_output=True, text=True)
            self.assertEqual(bad.returncode, 1)
            self.assertNotIn('do not run me', bad.stderr)
            self.assertIn('Source differs', bad.stderr)

    def test_no_music_build_keeps_key_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'godmode'
            home = Path(directory) / 'home'
            subprocess.run([sys.executable, str(ROOT / 'scripts/build.py'), '--without-music',
                            '--output', str(path)], check=True, capture_output=True)
            result = subprocess.run([sys.executable, str(ROOT / 'tests/engine_fixture.py'), str(path), '--home', str(home), 'list'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([sys.executable, str(ROOT / 'tests/engine_fixture.py'), str(path), '--home', str(home), 'music'],
                                    capture_output=True, text=True, cwd=directory)
            self.assertEqual(result.returncode, 2)
            self.assertIn('not included', result.stderr)
            self.assertFalse(home.exists())


if __name__ == '__main__':
    unittest.main()
