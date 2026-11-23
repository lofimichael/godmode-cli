"""Native release archives retain source, licenses and reproducible metadata."""
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('godmode_package_tests', REPO / 'scripts/package-native.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class NativePackagingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='godmode-native-package-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def git(self, *args):
        subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test', *args],
                       cwd=self.root, check=True, capture_output=True)

    def test_uncommitted_entrypoint_or_new_source_is_refused(self):
        self.git('init', '-q')
        entry = self.root / 'godmode.py'
        entry.write_text('original\n')
        self.git('add', 'godmode.py')
        self.git('commit', '-qm', 'Fixture')
        with mock.patch.object(package, 'ROOT', self.root):
            package.verify_committed_source()
            entry.write_text('changed\n')
            for staged in (False, True):
                if staged:
                    self.git('add', 'godmode.py')
                with self.assertRaisesRegex(ValueError, 'Commit every release source change'):
                    package.verify_committed_source()
            self.git('restore', '--staged', 'godmode.py')
            entry.write_text('original\n')
            package.verify_committed_source()
            for name in ('lib/new_module.py', 'internal/ui/new_view.go',
                         'scripts/new_builder.py'):
                with self.subTest(path=name):
                    source = self.root / name
                    source.parent.mkdir(parents=True, exist_ok=True)
                    source.write_text('uncommitted source\n')
                    with self.assertRaisesRegex(ValueError, 'Commit every release source change'):
                        package.verify_committed_source()
                    source.unlink()

    def test_archive_bytes_ignore_file_times_owner_and_gzip_name(self):
        script = self.root / 'install.sh'
        script.write_bytes(b'#!/bin/sh\nexit 0\n')
        binary = self.root / 'program'
        binary.write_bytes(b'native fixture')
        first, second = self.root / 'first.tar.gz', self.root / 'other.tar.gz'
        entries = {'godmode': binary, 'install.sh': script, 'LICENSE': b'Fixture license\n'}
        package.write_archive(first, entries, 12345678)
        os.utime(script, (456, 789))
        os.utime(binary, (123, 234))
        package.write_archive(second, dict(reversed(list(entries.items()))), 12345678)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with tarfile.open(first) as archive:
            self.assertEqual(archive.getnames(), ['LICENSE', 'godmode', 'install.sh'])
            for info in archive:
                self.assertEqual((info.uid, info.gid, info.uname, info.gname, info.mtime), (0, 0, '', '', 12345678))
                self.assertEqual(info.mode, 0o644 if info.name == 'LICENSE' else 0o755)
            self.assertEqual(archive.extractfile('godmode').read(), b'native fixture')

    def test_archive_rejects_traversal_and_cleans_incomplete_staging(self):
        output = self.root / 'broken.tar.gz'
        with self.assertRaisesRegex(ValueError, 'Unsafe archive'):
            package.write_archive(output, {'../outside': b'bad'}, 0)
        self.assertFalse(output.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_release_sources_refuse_tracked_symlinks(self):
        self.git('init', '-q')
        (self.root / 'README.md').symlink_to('outside.md')
        self.git('add', 'README.md')
        with mock.patch.object(package, 'ROOT', self.root), self.assertRaisesRegex(ValueError, 'symlink'):
            package.release_sources()

    def test_build_identity_requires_product_module_and_trimmed_paths_without_vcs_metadata(self):
        info = {'Path': 'godmode.build/cli/cmd/godmode', 'Main': {'Path': 'godmode.build/cli'},
                'Settings': [{'Key': '-trimpath', 'Value': 'true'}]}
        with mock.patch.object(package.subprocess, 'check_output', return_value=json.dumps(info)):
            package.verify_build_identity(self.root / 'godmode')
        for override in ({'Path': 'example.test/person/cli'}, {'Main': {'Path': 'example.test/person'}},
                         {'Settings': []}, {'Settings': info['Settings'] + [{'Key': 'vcs', 'Value': 'git'}]}):
            with self.subTest(override=override), mock.patch.object(
                    package.subprocess, 'check_output', return_value=json.dumps({**info, **override})):
                with self.assertRaises(ValueError):
                    package.verify_build_identity(self.root / 'godmode')

    def test_native_cpu_headers_are_checked_for_all_four_targets(self):
        binary = self.root / 'godmode'
        for target, (system, cpu) in package.TARGETS.items():
            header = bytearray(64)
            if system == 'darwin':
                header[:4] = b'\xcf\xfa\xed\xfe'
                struct.pack_into('<I', header, 4, 0x0100000c if cpu == 'arm64' else 0x01000007)
            else:
                header[:6] = b'\x7fELF\x02\x01'
                struct.pack_into('<H', header, 18, 183 if cpu == 'arm64' else 62)
            binary.write_bytes(header)
            package.verify_native(binary, target)
            for wrong, pair in package.TARGETS.items():
                if wrong != target:
                    with self.assertRaises(ValueError):
                        package.verify_native(binary, wrong)
        binary.write_bytes(b'#!/bin/sh\necho synthetic\n')
        with self.assertRaises(ValueError):
            package.verify_native(binary, 'aarch64-apple-darwin')

    def test_complete_source_and_licenses_are_packaged_without_universal_alias(self):
        for name in package.SOURCE_FILES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('0.15.0\n' if name == 'VERSION' else 'fixture\n')
        for name in ('vendor/modules.txt', 'vendor/example/library/LICENSE', 'cmd/godmode/main.go',
                     'internal/core/core.py', 'lib/core.py', 'scripts/build-native.sh',
                     'scripts/build.py', 'docs/SECURITY.md', 'docs/images/example.txt'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('inspectable fixture\n')
        (self.root / '.gitignore').write_text('local-*\n')
        self.git('init', '-q')
        self.git('add', '.')
        self.git('commit', '-qm', 'Release sources')
        private_files = ('docs/local-draft.md', 'docs/images/local-capture.png',
                         'vendor/example/local-info/LICENSE', 'lib/local-skill.py')
        for name in private_files:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('private fixture\n')
        binaries = self.root / 'native'
        for target, (system, cpu) in package.TARGETS.items():
            path = binaries / target / 'godmode'
            path.parent.mkdir(parents=True)
            header = bytearray(64)
            if system == 'darwin':
                header[:4] = b'\xcf\xfa\xed\xfe'
                struct.pack_into('<I', header, 4, 0x0100000c if cpu == 'arm64' else 0x01000007)
            else:
                header[:6] = b'\x7fELF\x02\x01'
                struct.pack_into('<H', header, 18, 183 if cpu == 'arm64' else 62)
            path.write_bytes(header)
        output = self.root / 'dist'
        argv = ['package-native.py', '--skip-build', '--binaries-dir', str(binaries),
                '--output-dir', str(output), '--epoch', '1234']
        with mock.patch.object(package, 'ROOT', self.root), mock.patch.object(package, 'verify_build_identity'), \
             mock.patch('sys.argv', argv), mock.patch('sys.stdout', io.StringIO()):
            package.main()
        archives = list(output.glob('*.tar.gz'))
        self.assertEqual(len(archives), 5)
        for path in archives:
            with tarfile.open(path) as archive:
                self.assertFalse(any('local-' in name for name in archive.getnames()))
        self.assertFalse((output / 'godmode-v0.15.0-unix.tar.gz').exists())
        with tarfile.open(output / 'godmode-v0.15.0-source.tar.gz') as archive:
            for name in ('cmd/godmode/main.go', 'internal/core/core.py', 'go.mod', 'go.sum',
                         'vendor/modules.txt', 'vendor/example/library/LICENSE', 'godmode.py',
                         'scripts/build.py', 'lib/core.py', 'docs/SECURITY.md'):
                self.assertIn(name, archive.getnames())
            self.assertEqual(archive.extractfile('lib/core.py').read(),
                             b'inspectable fixture\n')
        with tarfile.open(output / 'godmode-v0.15.0-aarch64-apple-darwin.tar.gz') as archive:
            for name in ('godmode', 'install.sh', 'BUILD.json', 'licenses/modules.txt', 'licenses/example/library/LICENSE'):
                self.assertIn(name, archive.getnames())
            self.assertNotIn('godmode.py', archive.getnames())
            self.assertFalse(any(name.startswith(('lib/', 'internal/', 'scripts/')) for name in archive.getnames()))
        for line in (output / 'SHA256SUMS').read_text().splitlines():
            checksum, name = line.split('  ')
            self.assertEqual(package.digest(output / name), checksum)


if __name__ == '__main__':
    unittest.main()
