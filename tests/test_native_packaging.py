"""Native release archives retain source, licenses and reproducible metadata."""
import importlib.util
import io
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

    def test_uncommitted_entrypoint_or_new_source_is_refused(self):
        def git(*args):
            subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test', *args],
                           cwd=self.root, check=True, capture_output=True)
        git('init', '-q')
        entry = self.root / 'godmode.py'
        entry.write_text('original\n')
        git('add', 'godmode.py')
        git('commit', '-qm', 'Fixture')
        with mock.patch.object(package, 'ROOT', self.root):
            package.verify_committed_source()
            entry.write_text('changed\n')
            for staged in (False, True):
                if staged:
                    git('add', 'godmode.py')
                with self.assertRaisesRegex(ValueError, 'Commit every release source change'):
                    package.verify_committed_source()
            git('restore', '--staged', 'godmode.py')
            entry.write_text('original\n')
            package.verify_committed_source()
            for name in ('lib/new_module.py', 'music_assets/manifest.json',
                         'music_assets/runtime/tools/synth.c'):
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
                self.assertEqual((info.uid, info.gid, info.mtime), (0, 0, 12345678))
                self.assertEqual(info.mode, 0o644 if info.name == 'LICENSE' else 0o755)
            self.assertEqual(archive.extractfile('godmode').read(), b'native fixture')

    def test_archive_rejects_traversal_and_cleans_incomplete_staging(self):
        output = self.root / 'broken.tar.gz'
        with self.assertRaisesRegex(ValueError, 'Unsafe archive'):
            package.write_archive(output, {'../outside': b'bad'}, 0)
        self.assertFalse(output.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_source_walk_omits_caches_and_refuses_links(self):
        (self.root / '__pycache__').mkdir()
        (self.root / '__pycache__/ignore.pyc').write_bytes(b'cache')
        (self.root / 'source.py').write_text('x = 1\n')
        self.assertEqual(list(package.files_under(self.root)), [self.root / 'source.py'])
        (self.root / 'linked').symlink_to(self.root / 'source.py')
        with mock.patch.object(package, 'ROOT', self.root), self.assertRaisesRegex(ValueError, 'symlink'):
            list(package.files_under(self.root))

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
                     'scripts/build-music.py', 'music_assets/manifest.json',
                     'music_assets/runtime/tools/instrument.sf2',
                     'docs/MUSIC.md', 'docs/images/example.txt'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('inspectable fixture\n')
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
        with mock.patch.object(package, 'ROOT', self.root), mock.patch.object(package, 'git_value', side_effect=lambda *args: '' if args[0] == 'status' else 'a'*40), \
             mock.patch.object(package.subprocess, 'check_output', return_value='go fixture\n'), \
             mock.patch('sys.argv', argv), mock.patch('sys.stdout', io.StringIO()):
            package.main()
        self.assertEqual(len(list(output.glob('*.tar.gz'))), 5)
        self.assertFalse((output / 'godmode-v0.15.0-unix.tar.gz').exists())
        with tarfile.open(output / 'godmode-v0.15.0-source.tar.gz') as archive:
            for name in ('cmd/godmode/main.go', 'internal/core/core.py', 'go.mod', 'go.sum',
                         'vendor/modules.txt', 'vendor/example/library/LICENSE', 'godmode.py',
                         'scripts/build-music.py', 'music_assets/manifest.json',
                         'music_assets/runtime/tools/instrument.sf2'):
                self.assertIn(name, archive.getnames())
            self.assertEqual(archive.extractfile('music_assets/runtime/tools/instrument.sf2').read(),
                             b'inspectable fixture\n')
        with tarfile.open(output / 'godmode-v0.15.0-aarch64-apple-darwin.tar.gz') as archive:
            for name in ('godmode', 'install.sh', 'BUILD.json', 'licenses/modules.txt', 'licenses/example/library/LICENSE'):
                self.assertIn(name, archive.getnames())
            self.assertNotIn('godmode.py', archive.getnames())
            self.assertFalse(any(name.startswith('music_assets/') for name in archive.getnames()))
        for line in (output / 'SHA256SUMS').read_text().splitlines():
            checksum, name = line.split('  ')
            self.assertEqual(package.digest(output / name), checksum)


if __name__ == '__main__':
    unittest.main()
