"""Regression tests for candidate selection and interrupted release recovery."""

import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import release


SOURCE = '1' * 40
OTHER_SOURCE = '2' * 40
VERSION = 'v0.21.0'


class FakeGitHub:
    def __init__(self):
        self.references = {}
        self.releases = {}
        self.files = {}
        self.mutations = []
        self.interrupt_upload = False

    def require_main_commit(self, sha):
        if sha == OTHER_SOURCE:
            raise release.ReleaseError('Candidate commit is no longer reachable from main.')

    def tags(self):
        return dict(self.references)

    def tag_commit(self, value):
        return value

    def release(self, version):
        return copy.deepcopy(self.releases.get(version))

    def create_tag(self, version, sha):
        self.mutations.append(('tag', version))
        self.references[version] = sha

    def create_draft(self, version):
        self.mutations.append(('draft', version))
        self.releases[version] = {'id': 1, 'draft': True, 'assets': []}

    def upload(self, version, paths):
        rows = self.releases[version]['assets']
        for path in paths:
            self.mutations.append(('upload', path.name))
            asset_id = len(self.files) + 1
            data = path.read_bytes()
            self.files[asset_id] = data
            rows.append({'id': asset_id, 'name': path.name, 'size': len(data),
                         'state': 'uploaded', 'digest': 'sha256:' + hashlib.sha256(data).hexdigest()})
            if self.interrupt_upload:
                self.interrupt_upload = False
                raise OSError('interrupted while uploading')

    def download(self, asset, path):
        path.write_bytes(self.files[asset['id']])

    def delete_starter(self, asset_id):
        self.mutations.append(('delete-starter', asset_id))
        self.releases[VERSION]['assets'] = [
            row for row in self.releases[VERSION]['assets'] if row['id'] != asset_id
        ]

    def publish(self, release_id):
        self.mutations.append(('publish', release_id))
        self.releases[VERSION]['draft'] = False


class ReleasePlanTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        self.git('init', '-b', 'main')
        self.before = self.commit('0.20.0')
        self.github = FakeGitHub()

    def git(self, *args):
        return subprocess.check_output(['git', '-c', 'user.name=Release Test',
                                        '-c', 'user.email=release@example.test', *args], text=True).strip()

    def commit(self, version):
        (self.root / 'VERSION').write_text(version + '\n')
        self.git('add', 'VERSION')
        self.git('commit', '--allow-empty', '-m', version)
        return self.git('rev-parse', 'HEAD')

    def push(self, sha, **fields):
        event = {'ref': release.MAIN, 'before': self.before, 'after': sha, **fields}
        return release.plan('push', release.MAIN, sha, event, self.github)

    def dispatch(self, ref, sha, **inputs):
        return release.plan('workflow_dispatch', ref, sha, {'inputs': inputs}, self.github)

    def test_unchanged_version_skips_build(self):
        self.assertEqual(self.push(self.commit('0.20.0')), {'mode': 'skip'})

    def test_version_bump_selects_exact_push_head(self):
        self.commit('0.20.1')
        head = self.commit('0.21.0')
        self.assertEqual(self.push(head), {'mode': 'build', 'version': VERSION, 'source_sha': head})
        self.assertEqual(self.github.mutations, [])

    def test_dry_run_on_feature_ref_does_not_claim_a_tag(self):
        head = self.commit('0.21.0')
        self.github.references[VERSION] = OTHER_SOURCE
        self.assertEqual(self.dispatch('refs/heads/feature', head),
                         {'mode': 'dry-run', 'version': VERSION, 'source_sha': head})
        with self.assertRaisesRegex(release.ReleaseError, 'must run from main'):
            self.dispatch('refs/heads/feature', head, dry_run='false', commit=head)

    def test_real_dispatch_requires_explicit_candidate_and_rejects_mismatch(self):
        head = self.commit('0.21.0')
        with self.assertRaisesRegex(release.ReleaseError, 'explicit'):
            self.dispatch(release.MAIN, head, dry_run='false')
        self.github.references[VERSION] = OTHER_SOURCE
        with self.assertRaisesRegex(release.ReleaseError, 'different commit'):
            self.dispatch(release.MAIN, head, dry_run='false', commit=head)
        self.git('tag', 'v0.21.1', head)
        with self.assertRaisesRegex(release.ReleaseError, 'disagrees'):
            self.dispatch(release.MAIN, head, dry_run='false', tag='v0.21.1')

    def test_published_tag_reuses_release_bytes_even_with_newer_tag(self):
        head = self.commit('0.21.0')
        self.git('tag', VERSION, head)
        self.github.references.update({VERSION: head, 'v0.22.0': OTHER_SOURCE})
        self.github.releases[VERSION] = {'id': 1, 'draft': False}
        self.assertEqual(self.dispatch(release.MAIN, head, dry_run='false', tag=VERSION),
                         {'mode': 'reuse', 'version': VERSION, 'source_sha': head})

    def test_version_rollback_is_rejected(self):
        with self.assertRaisesRegex(release.ReleaseError, 'must increase'):
            self.push(self.commit('0.19.0'))


class ReleasePublishTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.directory = Path(scratch.name)
        self.github = FakeGitHub()
        self.bundle()

    def bundle(self):
        installer = b'#!/bin/sh\n'
        binary = b'example native data\n'
        names = release.artifacts(VERSION)
        build = json.dumps({
            'version': VERSION[1:], 'commit': SOURCE, 'source_archive': names['source'],
            'CGO_ENABLED': '0', 'binaries': {target: hashlib.sha256(binary).hexdigest()
                                            for target in release.TARGETS},
        }).encode()
        (self.directory / 'install.sh').write_bytes(installer)
        for target, name in names.items():
            files = {'BUILD.json': build, 'install.sh': installer}
            if target == 'source':
                files['VERSION'] = (VERSION[1:] + '\n').encode()
            else:
                files['godmode'] = binary
            with tarfile.open(self.directory / name, 'w:gz') as tar:
                for entry, data in files.items():
                    member = tarfile.TarInfo(entry)
                    member.size = len(data)
                    tar.addfile(member, io.BytesIO(data))
        self.checksum_file()

    def checksum_file(self):
        lines = [f'{release.digest_file(path)}  {path.name}\n'
                 for path in sorted(self.directory.iterdir()) if path.name != 'SHA256SUMS']
        (self.directory / 'SHA256SUMS').write_text(''.join(lines))

    def publish(self, directory):
        release.publish(self.github, VERSION, SOURCE, directory)

    def test_interrupted_upload_recovers_without_replacing_completed_assets(self):
        self.github.interrupt_upload = True
        with self.assertRaisesRegex(OSError, 'interrupted'):
            self.publish(self.directory)
        self.assertTrue(self.github.releases[VERSION]['draft'])
        completed = self.github.releases[VERSION]['assets'][0]
        self.github.releases[VERSION]['assets'].append(
            {'id': 100, 'name': 'install.sh', 'size': 0, 'state': 'starter'})
        self.publish(self.directory)
        self.assertFalse(self.github.releases[VERSION]['draft'])
        self.assertEqual(self.github.mutations.count(('upload', completed['name'])), 1)
        self.assertEqual(self.github.mutations.count(('delete-starter', 100)), 1)
        self.assertEqual(self.github.mutations.count(('publish', 1)), 1)
        mutations = list(self.github.mutations)
        self.publish(None)
        self.assertEqual(self.github.mutations, mutations)

    def test_unexpected_existing_asset_bytes_leave_the_draft_unpublished(self):
        self.github.interrupt_upload = True
        with self.assertRaises(OSError):
            self.publish(self.directory)
        asset = self.github.releases[VERSION]['assets'][0]
        asset['digest'] = 'sha256:' + '0' * 64
        mutations = list(self.github.mutations)
        with self.assertRaisesRegex(release.ReleaseError, 'differs from the tested bytes'):
            self.publish(self.directory)
        self.assertEqual(self.github.mutations, mutations)

    def test_published_recovery_rejects_corrupted_asset(self):
        self.publish(self.directory)
        asset = self.github.releases[VERSION]['assets'][0]
        self.github.files[asset['id']] = b'unexpected\n'
        mutations = list(self.github.mutations)
        with self.assertRaisesRegex(release.ReleaseError, 'SHA256SUMS'):
            self.publish(None)
        self.assertEqual(self.github.mutations, mutations)

    def test_invalid_bundle_or_older_version_cannot_create_a_tag(self):
        with self.assertRaisesRegex(release.ReleaseError, 'expected build'):
            release.verify_bundle(self.directory, VERSION, OTHER_SOURCE)
        self.github.references['v0.22.0'] = OTHER_SOURCE
        with self.assertRaisesRegex(release.ReleaseError, 'newer'):
            self.publish(self.directory)
        self.github.references.clear()
        path = self.directory / 'install.sh'
        path.write_text('#!/bin/sh\necho changed\n')
        self.checksum_file()
        with self.assertRaisesRegex(release.ReleaseError, 'metadata or installer differs'):
            self.publish(self.directory)
        self.assertEqual(self.github.mutations, [])

    def test_source_must_still_be_on_main(self):
        with self.assertRaisesRegex(release.ReleaseError, 'no longer reachable'):
            release.publish(self.github, VERSION, OTHER_SOURCE, self.directory)
        self.assertEqual(self.github.mutations, [])


if __name__ == '__main__':
    unittest.main()
