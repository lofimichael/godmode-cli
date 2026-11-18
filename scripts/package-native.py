#!/usr/bin/env python3
"""Build four native releases and a complete, offline-buildable source archive."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    'aarch64-apple-darwin': ('darwin', 'arm64'),
    'x86_64-apple-darwin': ('darwin', 'amd64'),
    'x86_64-unknown-linux-musl': ('linux', 'amd64'),
    'aarch64-unknown-linux-musl': ('linux', 'arm64'),
}
SOURCE_FILES = ('LICENSE', 'README.md', 'READTHIS.NFO', 'SECURITY.md', 'VERSION',
                'godmode.py', 'providers.json', 'install.sh', 'go.mod', 'go.sum', '.gitignore',
                '.gitattributes')
SOURCE_DIRS = ('cmd', 'internal', 'lib', 'scripts', 'tests', 'docs', 'registry', 'vendor',
               'music_assets', '.github')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def files_under(directory):
    """Explicit trees only; never include local caches, compiled tests or private state."""
    for path in sorted(directory.rglob('*')):
        if '__pycache__' in path.parts or path.suffix in ('.pyc', '.pyo', '.tmp') or path.name == '.DS_Store':
            continue
        if path.is_symlink():
            raise ValueError('Source tree contains a symlink: ' + str(path.relative_to(ROOT)))
        if path.is_file():
            yield path


def verify_native(path, target):
    """Refuse mislabeled executables before an updater can choose the wrong CPU."""
    with path.open('rb') as stream:
        header = stream.read(64)
    if target.endswith('apple-darwin'):
        expected = 0x0100000c if target.startswith('aarch64-') else 0x01000007
        if len(header) < 8 or header[:4] != b'\xcf\xfa\xed\xfe' or struct.unpack('<I', header[4:8])[0] != expected:
            raise ValueError('Expected a ' + target + ' Mach-O executable: ' + str(path))
    else:
        expected = 183 if target.startswith('aarch64-') else 62
        if (len(header) < 20 or header[:6] != b'\x7fELF\x02\x01'
                or struct.unpack('<H', header[18:20])[0] != expected):
            raise ValueError('Expected a ' + target + ' ELF executable: ' + str(path))


def write_archive(path, entries, epoch):
    """Sorted files, fixed owners/modes/times, and a filename-free gzip header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='.' + path.name + '.', dir=path.parent, delete=False) as temporary:
        staging = Path(temporary.name)
        try:
            with gzip.GzipFile(filename='', mode='wb', fileobj=temporary, mtime=epoch, compresslevel=9) as zipped:
                with tarfile.open(fileobj=zipped, mode='w', format=tarfile.PAX_FORMAT) as archive:
                    for name, source in sorted(entries.items()):
                        if name.startswith('/') or '..' in Path(name).parts:
                            raise ValueError('Unsafe archive member: ' + name)
                        if isinstance(source, Path) and source.is_symlink():
                            raise ValueError('Archive source is a symlink: ' + str(source))
                        data = source.read_bytes() if isinstance(source, Path) else source
                        info = tarfile.TarInfo(name)
                        info.size, info.mtime = len(data), epoch
                        info.uid = info.gid = 0
                        info.uname = info.gname = ''
                        info.mode = (0o755 if name in ('godmode', 'install.sh') or
                                     (isinstance(source, Path) and source.stat().st_mode & 0o111) else 0o644)
                        archive.addfile(info, io.BytesIO(data))
            temporary.flush()
            os.fsync(temporary.fileno())
            os.replace(staging, path)
        finally:
            staging.unlink(missing_ok=True)


def git_value(*args):
    result = subprocess.run(['git', *args], cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, check=True)
    return result.stdout.strip()


def verify_committed_source():
    if git_value('status', '--porcelain', '--untracked-files=all', '--', *SOURCE_FILES, *SOURCE_DIRS):
        raise ValueError('Commit every release source change before packaging; the archive must match its recorded commit.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'target/dist')
    parser.add_argument('--binaries-dir', type=Path, default=ROOT / 'target/native')
    parser.add_argument('--skip-build', action='store_true', help='Package prebuilt TARGET/godmode files.')
    parser.add_argument('--epoch', type=int, help='Archive timestamp; defaults to SOURCE_DATE_EPOCH or the commit time.')
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    args.binaries_dir = args.binaries_dir.resolve()
    version = (ROOT / 'VERSION').read_text().strip()
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version):
        parser.error('VERSION must be X.Y.Z')
    if not (ROOT / 'vendor/modules.txt').is_file():
        parser.error('Run go mod vendor before packaging; source releases include every dependency.')
    try:
        verify_committed_source()
    except ValueError as error:
        parser.error(str(error))
    epoch = args.epoch
    if epoch is None:
        epoch = int(os.environ.get('SOURCE_DATE_EPOCH') or git_value('show', '-s', '--format=%ct', 'HEAD'))
    if not 0 <= epoch <= 0xffffffff:
        parser.error('Archive time must fit the gzip timestamp range.')
    release = 'godmode-v' + version
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = [release + '-' + name + '.tar.gz' for name in [*TARGETS, 'source']] + ['install.sh', 'SHA256SUMS']
    for name in outputs:
        if (args.output_dir / name).is_symlink():
            parser.error('Output is a symlink: ' + str(args.output_dir / name))
    if (args.output_dir / (release + '-unix.tar.gz')).exists():
        parser.error('Use an output directory without a ' + release + '-unix.tar.gz archive.')
    if not args.skip_build:
        for target, (system, cpu) in TARGETS.items():
            output = args.binaries_dir / target / 'godmode'
            env = dict(os.environ, GOOS=system, GOARCH=cpu, CGO_ENABLED='0', GOTOOLCHAIN='local', GOPROXY='off')
            subprocess.run(['sh', str(ROOT / 'scripts/build-native.sh'), '--output', str(output)],
                           cwd=ROOT, env=env, check=True)
    binaries = {target: args.binaries_dir / target / 'godmode' for target in TARGETS}
    for target, path in binaries.items():
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            parser.error('Missing native executable: ' + str(path))
        verify_native(path, target)
    # Building regenerates the embedded engine. It must still match the commit.
    verify_committed_source()
    build = {'version': version, 'commit': git_value('rev-parse', 'HEAD'),
             'go': subprocess.check_output(['go', 'version'], text=True).strip(),
             'CGO_ENABLED': '0', 'source_archive': release + '-source.tar.gz',
             'source_date_epoch': epoch,
             'binaries': {target: digest(path) for target, path in binaries.items()}}
    build_json = (json.dumps(build, indent=2, sort_keys=True) + '\n').encode()
    common = {name: ROOT / name for name in ('LICENSE', 'README.md', 'READTHIS.NFO', 'install.sh')}
    common['BUILD.json'] = build_json
    for path in sorted((ROOT / 'docs').glob('*.md')):
        common[str(path.relative_to(ROOT))] = path
    for path in files_under(ROOT / 'docs/images'):
        common[str(path.relative_to(ROOT))] = path
    # Module attribution accompanies binaries; complete dependency source is in -source.
    common['licenses/modules.txt'] = ROOT / 'vendor/modules.txt'
    for path in files_under(ROOT / 'vendor'):
        if path.name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE')):
            common['licenses/' + str(path.relative_to(ROOT / 'vendor'))] = path
    artifacts = []
    for target, binary in binaries.items():
        archive = args.output_dir / (release + '-' + target + '.tar.gz')
        write_archive(archive, dict(common, godmode=binary), epoch)
        artifacts.append(archive)
    source = {name: ROOT / name for name in SOURCE_FILES if (ROOT / name).is_file()}
    for directory in SOURCE_DIRS:
        for path in files_under(ROOT / directory):
            source[str(path.relative_to(ROOT))] = path
    source['BUILD.json'] = build_json
    archive = args.output_dir / (release + '-source.tar.gz')
    write_archive(archive, source, epoch)
    artifacts.append(archive)
    installer = args.output_dir / 'install.sh'
    shutil.copyfile(ROOT / 'install.sh', installer)
    installer.chmod(0o755)
    artifacts.append(installer)
    sums = ''.join(digest(path) + '  ' + path.name + '\n' for path in sorted(artifacts))
    (args.output_dir / 'SHA256SUMS').write_text(sums)
    for path in artifacts + [args.output_dir / 'SHA256SUMS']:
        print(path)


if __name__ == '__main__':
    main()
