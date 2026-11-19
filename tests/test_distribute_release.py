import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/distribute_release.py'
SPEC = importlib.util.spec_from_file_location('distribute_release', SCRIPT)
DISTRIBUTE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DISTRIBUTE)
VERSION = 'v1.2.3'
SOURCE_SHA = '1234567890abcdef' * 2 + '12345678'
BRANCH = 'automation/cli-' + VERSION
PR_URL = 'https://github.com/lofimichael/godmode-build/pull/42'
PREPARE = '''
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('directory', type=Path)
parser.add_argument('--version')
parser.add_argument('--source-sha')
args = parser.parse_args()
latest = Path('public/releases/latest.json')
if latest.read_text() != args.version:
    latest.write_text(args.version)
    bundle = latest.parent / args.version
    bundle.mkdir()
    (bundle / 'archive').write_bytes((args.directory / 'archive').read_bytes())
    Path('public/install.sh').write_text(args.version)
    Path('content/docs/providers.json').write_text('[]')
    Path('content/docs/manifest.json').write_text(json.dumps({
        'version': args.version, 'cliCommit': args.source_sha
    }))
'''


class DownloadTests(unittest.TestCase):
    def test_rejects_malformed_inputs(self):
        for version, sha in (('v1.2.03', SOURCE_SHA), ('main', SOURCE_SHA),
                             (VERSION, '0' * 40), (VERSION, 'a1b2')):
            with self.subTest(version=version, sha=sha), self.assertRaises(DISTRIBUTE.PromotionError):
                DISTRIBUTE.validate(version, sha)

    def test_rejects_wrong_tag_or_unpublished_assets(self):
        assets = [{'name': name} for name in DISTRIBUTE.artifact_names(VERSION)]
        release = {'isDraft': False, 'isPrerelease': False, 'tagName': VERSION, 'assets': assets}
        with patch.object(DISTRIBUTE, 'command', return_value='a' * 40) as command:
            with self.assertRaisesRegex(DISTRIBUTE.PromotionError, 'Git tag'):
                DISTRIBUTE.download(VERSION, SOURCE_SHA, Path('unused'))
            command.assert_called_once()
        for error in ({'isDraft': True}, {'isPrerelease': True}, {'assets': assets[1:]},
                      {'assets': assets + assets[:1]}):
            with self.subTest(error=error), patch.object(DISTRIBUTE, 'command', side_effect=[
                    SOURCE_SHA, '', json.dumps({**release, **error})]) as command:
                with self.assertRaisesRegex(DISTRIBUTE.PromotionError, 'stable release'):
                    DISTRIBUTE.download(VERSION, SOURCE_SHA, Path('unused'))
                self.assertEqual(command.call_count, 3)


class PromotionTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.remote = self.root / 'remote.git'
        self.command('git', 'init', '--quiet', '--bare', '--initial-branch=main', str(self.remote))
        base = self.clone('base')
        for relative, data in {
            'scripts/prepare-cli-release.py': PREPARE,
            'public/releases/latest.json': 'v1.2.2',
            'content/docs/manifest.json': '{}',
            'notes.md': 'Original notes\n',
        }.items():
            file = base / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(data)
        self.commit(base, 'Baseline')
        self.git(base, 'push', '--quiet', 'origin', 'main')
        self.assets = self.root / 'assets'
        self.assets.mkdir()
        (self.assets / 'archive').write_bytes(b'tested payload')
        self.pr_state = None
        self.fail_open = False
        self.opens = 0
        mock = patch.object(DISTRIBUTE, 'command', side_effect=self.provider_command)
        mock.start()
        self.addCleanup(mock.stop)

    command = staticmethod(DISTRIBUTE.command)

    def git(self, repo, *args):
        return self.command('git', '-C', str(repo), *args).strip()

    def clone(self, name):
        repo = self.root / name
        self.command('git', 'clone', '--quiet', str(self.remote), str(repo))
        return repo

    def commit(self, repo, message):
        self.git(repo, 'add', '--all')
        self.git(repo, '-c', 'user.name=Test', '-c', 'user.email=test@example.test',
                 'commit', '--quiet', '-m', message)

    def remote_sha(self):
        return self.git(self.remote, 'rev-parse', '--verify', f'refs/heads/{BRANCH}')

    def provider_command(self, *args):
        # Git transfers and branch creation exercise a real bare remote. Only GitHub identity/PR
        # operations are simulated, so retries cannot accidentally post externally.
        if args[-3:] == ('remote', 'get-url', 'origin'):
            return 'https://github.com/lofimichael/godmode-build\n'
        if args[:3] == ('gh', 'pr', 'list'):
            if not self.pr_state:
                return '[]'
            return json.dumps([{'state': self.pr_state, 'url': PR_URL, 'headRefName': BRANCH,
                                'headRefOid': self.remote_sha(), 'isCrossRepository': False}])
        if args[:3] == ('gh', 'pr', 'create'):
            self.opens += 1
            self.assertIn(BRANCH, args)
            self.assertIn(DISTRIBUTE.SITE_REPO, args)
            self.assertIn(SOURCE_SHA, args[-1])
            if self.fail_open:
                raise subprocess.CalledProcessError(1, args)
            self.pr_state = 'OPEN'
            return PR_URL
        return self.command(*args)

    def promote(self, clone):
        DISTRIBUTE.promote(VERSION, SOURCE_SHA, clone, self.assets)

    def edit_branch(self, relative, text):
        editor = self.root / ('editor-' + relative.name)
        self.command('git', 'clone', '--quiet', '--branch', BRANCH, str(self.remote), str(editor))
        (editor / relative).write_text(text)
        self.commit(editor, 'Review edit')
        self.git(editor, 'push', '--quiet', 'origin', BRANCH)

    def test_open_and_retry_preserves_editorial_changes_and_rejects_asset_changes(self):
        self.promote(self.clone('first'))
        self.edit_branch(Path('notes.md'), 'Reviewed\n')
        reviewed = self.remote_sha()
        self.promote(self.clone('retry'))
        self.assertEqual(self.remote_sha(), reviewed)
        self.assertEqual(self.opens, 1)
        self.edit_branch(Path('public/releases') / VERSION / 'archive', 'different')
        with self.assertRaisesRegex(DISTRIBUTE.PromotionError, 'existing distribution PR differs'):
            self.promote(self.clone('reject'))

    def test_recovers_an_existing_branch_if_pr_creation_failed(self):
        self.fail_open = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.promote(self.clone('first'))
        pending = self.remote_sha()
        self.fail_open = False
        self.promote(self.clone('retry'))
        self.assertEqual(self.remote_sha(), pending)
        self.assertEqual(self.pr_state, 'OPEN')

    def test_merged_candidate_is_noop_and_closed_pr_stays_closed(self):
        self.promote(self.clone('first'))
        self.pr_state = 'CLOSED'
        with self.assertRaisesRegex(DISTRIBUTE.PromotionError, 'prior distribution PR is closed'):
            self.promote(self.clone('closed'))
        merger = self.clone('merge')
        self.git(merger, 'merge', '--ff-only', f'origin/{BRANCH}')
        self.git(merger, 'push', '--quiet', 'origin', 'main')
        self.promote(self.clone('after'))
        self.assertEqual(self.opens, 1)


if __name__ == '__main__':
    unittest.main()
