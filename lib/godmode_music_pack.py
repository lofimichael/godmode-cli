"""Lightweight opt-in pack installer/router. No audio, synthesis, or key access."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import sys
import uuid
import urllib.error
import urllib.request

PACK_DOWNLOAD_LIMIT = 128 * 1024 * 1024
PACK_RELEASE_ROOT = 'https://godmode.build/packs/music'


class _PackNeedsRepair(ValueError):
    """Owned pack contents are damaged; path/ownership failures use other errors."""


def _pack_home(home):
    return Path(os.path.abspath(os.path.expanduser(str(home or os.environ.get('GODMODE_HOME') or Path.home() / '.godmode'))))


def _pack_dir(path, create=False):
    for item in reversed((path,) + tuple(path.parents)):
        if create and not os.path.lexists(item):
            item.mkdir(mode=0o700)
        if os.path.lexists(item) and not stat.S_ISDIR(item.lstat().st_mode):
            raise ValueError('Music Pack paths must not contain symlinks.')
    if path.exists():
        info = path.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise ValueError('Music Pack directories must be yours and not writable by others.')


def _pack_read(path, limit=65536):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
                or info.st_mode & 0o022 or info.st_size > limit):
            raise ValueError('Unsafe Music Pack file.')
        return stream.read(limit + 1)


def _pack_write(path, data, mode=0o600):
    if os.path.lexists(path):
        _pack_read(path, PACK_DOWNLOAD_LIMIT)
    fd, tmp = tempfile.mkstemp(prefix='.pack-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextlib.contextmanager
def _pack_lock(home, shared=False):
    directory = home / 'packs'
    _pack_dir(directory, True)
    fd = os.open(directory / '.music.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
                or info.st_mode & 0o022):
            raise ValueError('Unsafe Music Pack lock.')
        # The foreground router owns the lease. Neither the companion nor its
        # detached audio session may inherit it and prevent later removal.
        os.set_inheritable(fd, False)
        try:
            fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError:
            if shared:
                raise ValueError('Music Pack installation or removal is running. Retry when it finishes.') from None
            raise ValueError('Close Music Pack views or wait for setup/jingles or another install/removal '
                             'to finish, then retry.') from None
        yield fd
    finally:
        os.close(fd)


def _pack_env(home):
    names = ('PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TERM', 'COLORTERM',
             'TMPDIR', 'NO_COLOR', 'CLICOLOR', 'COLORFGBG', 'DISPLAY', 'WAYLAND_DISPLAY',
             'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS', 'PULSE_SERVER', 'GODMODE_PLAIN', 'GODMODE_NO_MOTION')
    env = {name: os.environ[name] for name in names if name in os.environ}
    env['GODMODE_HOME'] = str(home)
    return env


def _pack_target():
    system = platform.system().lower()
    arch = {'aarch64': 'arm64', 'arm64': 'arm64', 'x86_64': 'amd64', 'amd64': 'amd64'}.get(platform.machine().lower())
    if system not in ('darwin', 'linux') or arch is None:
        raise ValueError('The Music Pack supports macOS and Linux on arm64/amd64.')
    target = ('aarch64' if arch == 'arm64' else 'x86_64') + ('-apple-darwin' if system == 'darwin' else '-unknown-linux-gnu')
    return system, arch, target


def _pack_info(binary, home):
    result = subprocess.run([str(binary), '__pack_info'], env=_pack_env(home), stdin=subprocess.DEVNULL,
                            text=True, capture_output=True, timeout=5)
    if result.returncode or len(result.stdout) > 4096:
        raise ValueError('This file is not a compatible Godmode Music Pack.')
    try:
        info = json.loads(result.stdout)
    except ValueError:
        raise ValueError('This file is not a compatible Godmode Music Pack.') from None
    system, arch, _ = _pack_target()
    if (not isinstance(info, dict) or info.get('kind') != 'godmode-music-pack' or info.get('protocol') != 1
            or info.get('platform') != system or info.get('arch') != arch
            or not isinstance(info.get('version'), str)):
        raise ValueError('Music Pack version or platform is incompatible.')
    return info


def _pack_installed(home):
    directory = home / 'packs/music'
    _pack_dir(directory)
    # Inspect both known files before classifying damaged contents. A malformed
    # receipt must not hide a linked, foreign-owned, or shared-writable binary.
    files = {}
    for name, limit in (('receipt.json', 65536), ('godmode-music', PACK_DOWNLOAD_LIMIT)):
        try:
            files[name] = _pack_read(directory / name, limit)
        except FileNotFoundError:
            pass
    if not files and (not directory.exists() or not any(directory.iterdir())):
        return None
    if len(files) != 2:
        raise _PackNeedsRepair('Music Pack installation is incomplete. Reinstall with godmode music install.')
    try:
        receipt = json.loads(files['receipt.json'])
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise _PackNeedsRepair('Music Pack receipt is invalid. Reinstall with godmode music install.') from None
    if (not isinstance(receipt, dict) or type(receipt.get('schema')) is not int
            or receipt.get('schema') != 1 or not isinstance(receipt.get('sha256'), str)
            or not re.fullmatch(r'[a-f0-9]{64}', receipt['sha256'])):
        raise _PackNeedsRepair('Music Pack receipt is invalid. Reinstall with godmode music install.')
    if hashlib.sha256(files['godmode-music']).hexdigest() != receipt['sha256']:
        raise _PackNeedsRepair('Music Pack checksum changed. Reinstall with godmode music install.')
    binary = directory / 'godmode-music'
    if not os.access(binary, os.X_OK):
        raise _PackNeedsRepair('Music Pack is not executable. Reinstall with godmode music install.')
    return binary, receipt


def _pack_run(binary, home, args, capture=False):
    if capture:
        return subprocess.run([str(binary), '--home', str(home), *args], env=_pack_env(home),
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15, close_fds=True)
    child = subprocess.Popen([str(binary), '--home', str(home), *args], env=_pack_env(home), close_fds=True)
    previous = {}
    def forward(signum, frame):
        with contextlib.suppress(ProcessLookupError):
            child.send_signal(signum)
    try:
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous[signum] = signal.signal(signum, forward)
        code = child.wait()
        return 128 - code if code < 0 else code
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


class _PackNoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _pack_download():
    opener = urllib.request.build_opener(_PackNoRedirect())
    _, _, target = _pack_target()
    try:
        with opener.open(PACK_RELEASE_ROOT + '/latest.json', timeout=20) as response:
            data = response.read(65537)
        if len(data) > 65536:
            raise ValueError('Music Pack release manifest is too large.')
        manifest = json.loads(data)
        if not isinstance(manifest, dict):
            raise ValueError('Invalid Music Pack release manifest.')
        version = manifest.get('version', '')
        if (manifest.get('schema') != 1 or not isinstance(version, str)
                or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?', version)):
            raise ValueError('Invalid Music Pack release manifest.')
        artifacts = manifest.get('artifacts')
        if not isinstance(artifacts, list):
            raise ValueError('Invalid Music Pack artifact list.')
        matches = [entry for entry in artifacts if isinstance(entry, dict) and entry.get('platform') == target]
        if len(matches) != 1:
            raise ValueError('No Music Pack artifact matches this computer.')
        item = matches[0]
        name = 'godmode-music-v' + version + '-' + target
        digest, size = item.get('sha256'), item.get('size')
        if (item.get('file') != name or not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest)
                or type(size) is not int or not 1 <= size <= PACK_DOWNLOAD_LIMIT):
            raise ValueError('Invalid Music Pack artifact metadata.')
        with opener.open(PACK_RELEASE_ROOT + '/' + version + '/' + name, timeout=30) as response:
            data = response.read(size + 1)
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Music Pack download checksum failed. Nothing was installed.')
        return data, digest, {'kind': 'release', 'version': version}
    except (urllib.error.URLError, OSError):
        raise ValueError('Music Pack download is unavailable. For a local preview use: '
                         'godmode music install --file PACK --sha256 SHA256') from None


def _pack_external_source(path, home):
    resolved = path.resolve()
    for directory in (home / 'packs/music', home / 'state/music'):
        if resolved == directory.resolve() or directory.resolve() in resolved.parents:
            raise ValueError('Keep the local Music Pack artifact outside Godmode managed music folders '
                             'so it remains available for reinstall.')


def _pack_install(home, args):
    parser = argparse.ArgumentParser(prog='godmode music install')
    parser.add_argument('--file', type=Path)
    parser.add_argument('--sha256')
    options = parser.parse_args(args)
    if options.sha256 and not re.fullmatch(r'[a-fA-F0-9]{64}', options.sha256):
        parser.error('--sha256 needs 64 hexadecimal characters')
    if options.sha256 and options.file is None:
        parser.error('--sha256 belongs to --file')
    source = None
    if options.file:
        options.file = options.file.expanduser().absolute()
        _pack_external_source(options.file, home)
        data = _pack_read(options.file, PACK_DOWNLOAD_LIMIT)
        digest = hashlib.sha256(data).hexdigest()
        if options.sha256 and digest != options.sha256.lower():
            raise ValueError('Music Pack checksum failed. Nothing was installed.')
        source = {'kind': 'local', 'file': str(options.file), 'sha256': digest}
    else:
        try:
            existing = _pack_installed(home)
        except _PackNeedsRepair:
            directory = home / 'packs/music'
            if directory.exists() and {p.name for p in directory.iterdir()} - {'godmode-music', 'receipt.json'}:
                raise ValueError('Music Pack directory contains other files. No files replaced.')
            existing = None
        if existing:
            print('Music Pack is already installed. Run godmode music or godmode jingle play.')
            return 0
        try:
            source = json.loads(_pack_read(home / 'music-pack-source.json'))
        except FileNotFoundError:
            pass
        else:
            if not isinstance(source, dict) or source.get('kind') not in ('local', 'release'):
                raise ValueError('Invalid Music Pack source. Reinstall with --file and --sha256.')
        if source and source.get('kind') == 'local':
            if not isinstance(source.get('file'), str) or not Path(source['file']).is_absolute():
                raise ValueError('Invalid local Music Pack source.')
            _pack_external_source(Path(source['file']), home)
            data = _pack_read(Path(source['file']), PACK_DOWNLOAD_LIMIT)
            digest = hashlib.sha256(data).hexdigest()
            if digest != source.get('sha256'):
                raise ValueError('The local preview artifact changed. Reinstall with --file and --sha256.')
        else:
            print('Downloading Music Pack…', flush=True)
            data, digest, source = _pack_download()
    with _pack_lock(home):
        directory = home / 'packs/music'
        _pack_dir(directory)
        if directory.exists() and {p.name for p in directory.iterdir()} - {'godmode-music', 'receipt.json'}:
            raise ValueError('Music Pack directory contains other files. No files replaced.')
        with tempfile.TemporaryDirectory(prefix='.music-install-', dir=directory.parent) as work:
            candidate = Path(work) / 'godmode-music'
            _pack_write(candidate, data, 0o700)
            info = _pack_info(candidate, home)
            try:
                existing = _pack_installed(home)
            except _PackNeedsRepair:
                existing = None
            if existing or directory.exists():
                # Never execute the old file while repairing it. The candidate
                # has already passed byte verification and protocol/platform
                # validation, and knows how to stop this home's music session.
                stopped = _pack_run(candidate, home, ['music', 'stop'], capture=True)
                if stopped.returncode:
                    raise ValueError('Could not stop music with the replacement Music Pack. No files replaced.')
            receipt = {'schema': 1, 'sha256': digest, 'version': info['version'], 'protocol': 1,
                       'platform': info['platform'], 'arch': info['arch']}
            _pack_write(Path(work) / 'receipt.json', (json.dumps(receipt, indent=2) + '\n').encode())
            backup = directory.parent / ('.music-rollback-' + uuid.uuid4().hex)
            had_previous = directory.exists()
            if had_previous:
                os.replace(directory, backup)
            adopted = False
            try:
                os.replace(work, directory)
                adopted = True
                _pack_write(home / 'music-pack-source.json', (json.dumps(source, indent=2) + '\n').encode())
            except BaseException:
                if adopted:
                    os.replace(directory, work)
                if had_previous:
                    os.replace(backup, directory)
                raise
            if had_previous:
                shutil.rmtree(backup)
    print('Music Pack installed. Jingles are ready with mpv: godmode jingle play')
    print('Link your local tracks: godmode music setup --songs DIR')
    return 0


def _pack_validate_tree(directory):
    _pack_dir(directory)
    if not directory.exists():
        return
    for base, dirs, files in os.walk(directory, followlinks=False):
        for name in dirs:
            _pack_dir(Path(base) / name)
        for name in files:
            info = (Path(base) / name).lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1 or info.st_mode & 0o022:
                raise ValueError('Music Pack contains an unsafe managed file. Nothing was removed.')


def _pack_remove(home, args):
    if args:
        raise ValueError('Use: godmode music remove')
    pack = _pack_installed(home)
    if not pack:
        print('Music Pack is not installed.')
        return 0
    with _pack_lock(home):
        pack = _pack_installed(home)
        if not pack:
            print('Music Pack is not installed.')
            return 0
        stopped = _pack_run(pack[0], home, ['music', 'stop'], capture=True)
        if stopped.returncode:
            raise ValueError('Could not stop music. No pack files removed.')
        state = home / 'state/music'
        _pack_dir(state)
        source_songs = None
        try:
            config = json.loads(_pack_read(state / 'config.json'))
            if (not isinstance(config, dict) or not isinstance(config.get('songs'), str)
                    or not Path(config['songs']).is_absolute()):
                raise ValueError('Invalid source songs path.')
            source_songs = Path(config['songs']).resolve()
        except FileNotFoundError:
            pass
        except (ValueError, KeyError, TypeError):
            raise ValueError('Cannot identify source songs from music config. No files removed.') from None
        if source_songs:
            for protected in (state, home / 'packs/music'):
                try:
                    source_songs.relative_to(protected.resolve())
                except ValueError:
                    pass
                else:
                    raise ValueError('Move source songs outside Godmode managed music folders before removing the pack.')
        if {p.name for p in (home / 'packs/music').iterdir()} - {'godmode-music', 'receipt.json'}:
            raise ValueError('Music Pack directory contains other files. No files removed.')
        managed = [home / 'packs/music'] + [state / name for name in ('cache', 'runtime', 'session')]
        for directory in managed:
            _pack_validate_tree(directory)
        for name in ('config.json', 'session.json', '.lock'):
            if os.path.lexists(state / name):
                _pack_read(state / name, 1024 * 1024)
        for directory in managed:
            if directory.exists():
                shutil.rmtree(directory)
        for name in ('config.json', 'session.json', '.lock'):
            with contextlib.suppress(FileNotFoundError):
                (state / name).unlink()
        with contextlib.suppress(FileNotFoundError, OSError):
            state.rmdir()
    print('Music Pack removed, including its runtime and rendered cache. Source songs kept.')
    return 0


def music_pack_main(argv, home=None, command='music', **unused):
    home = _pack_home(home)
    if command == 'music' and argv == ['__manager']:
        while True:
            line = sys.stdin.buffer.readline(65537)
            if not line:
                break
            oversized = len(line) > 65536
            try:
                if oversized or json.loads(line) != {'action': 'state'}:
                    raise ValueError('Unknown Music Pack manager request.')
                installed = _pack_installed(home)
                reply = {'ok': True, 'data': {'installed': installed is not None}}
            except (OSError, ValueError, TypeError):
                reply = {'ok': False, 'error': 'Cannot inspect Music Pack. Run godmode music install to repair it.'}
            print(json.dumps(reply), flush=True)
            if oversized:
                return 1
        return 0
    if command == 'music' and argv[:1] == ['install']:
        return _pack_install(home, argv[1:])
    if command == 'music' and argv[:1] in (['remove'], ['uninstall']):
        return _pack_remove(home, argv[1:])
    installed = _pack_installed(home)
    if installed:
        with _pack_lock(home, shared=True):
            installed = _pack_installed(home)
            if installed:
                return _pack_run(installed[0], home, [command, *argv])
    if command == 'music' and argv[:1] in (['stop'], ['status']):
        if '--json' in argv:
            print(json.dumps({'installed': False, 'state': 'stopped', 'track': None, 'queue': [], 'index': -1}))
        else:
            print('Music Pack is not installed. Nothing is playing.')
        return 0
    if command == 'music' and not argv:
        print('GODMODE BEATZ · optional Music Pack')
        print('Installs the music player, included synth, instruments, and original jingles.')
        print('Install: godmode music install')
        print('Then:    godmode music setup --songs DIR')
        print('Remove:  godmode music remove')
        return 0
    raise ValueError('Music Pack is not installed. Run godmode music install first.')
