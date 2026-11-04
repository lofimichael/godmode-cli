"""Optional Picard media. Nothing here loads the credential file."""
import contextlib
import fcntl
import hashlib
import os
from pathlib import Path
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time

PICARD_SOURCE_URL = "https://picard.ytmnd.com/"
PICARD_MEDIA = {
    "audio": ("https://users.content.ytmnd.com/d/0/3/d0330b0d03957ad58853427a6513e793.wav",
              "d69a477ba3b9a8d454512db12b2ce3da05ec72ffa36d7ab313b0ed8aff764db8", 351860, "excerpt.wav"),
    "image": ("https://users.content.ytmnd.com/f/8/c/f8cd26d2ab99e2f44562fb050d74c9a2.jpg",
              "5f35ea6e9fb61e7091da79b8c6086fff53f5aefacf778ad076214fcf6b0455bf", 58375, "portrait.jpg"),
}
PICARD_LIMIT = 1048576


class _PicardCancelled(Exception):
    pass


def _picard_directory(path, create=False):
    for directory in reversed((path,) + tuple(path.parents)):
        if create and not os.path.lexists(directory):
            directory.mkdir(mode=0o700)
        if os.path.lexists(directory) and not stat.S_ISDIR(directory.lstat().st_mode):
            raise ValueError("Picard cache paths must not contain symlinks.")
    if path.exists():
        info = path.stat()
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("Picard cache must be yours and mode 0700.")


def _picard_env():
    names = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "TERM", "COLORTERM", "TMPDIR",
             "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "PULSE_SERVER")
    return {name: os.environ[name] for name in names if name in os.environ}


def _picard_run(command, cancelled=lambda: False, timeout=25, output=subprocess.DEVNULL, limit_file=None):
    """Wait on one owned child, and always reap it when interrupted."""
    if cancelled():
        raise _PicardCancelled()
    child = subprocess.Popen(command, env=_picard_env(), stdin=subprocess.DEVNULL,
                             stdout=output, stderr=subprocess.DEVNULL)
    started = time.monotonic()
    handlers = {}
    def interrupt(signum, frame):
        raise KeyboardInterrupt()
    try:
        for signum in (signal.SIGTERM, signal.SIGHUP):
            handlers[signum] = signal.signal(signum, interrupt)
        while child.poll() is None:
            if cancelled():
                raise _PicardCancelled()
            if timeout is not None and time.monotonic() - started > timeout:
                raise ValueError("Picard operation timed out.")
            if limit_file is not None and limit_file.stat().st_size > PICARD_LIMIT:
                raise ValueError("Picard download exceeded its size limit.")
            time.sleep(0.05)
        if child.returncode:
            raise ValueError("Picard media command failed; use `godmode picard open`.")
    finally:
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                child.kill()
        child.wait()


def _picard_verified(path, digest, size):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise ValueError("Unsafe Picard cache file.")
        data = source.read(PICARD_LIMIT + 1)
    if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Picard cache failed its source checksum; remove that cache file to retry.")


def _picard_cached(root, kind, cancelled=lambda: False):
    if cancelled():
        raise _PicardCancelled()
    url, digest, size, name = PICARD_MEDIA[kind]
    destination = root / name
    if os.path.lexists(destination):
        _picard_verified(destination, digest, size)
        return destination
    curl = shutil.which("curl")
    if not curl:
        raise ValueError("Picard downloads need curl; use `godmode picard open`.")
    fd, raw_path = tempfile.mkstemp(prefix=".download-", dir=root)
    os.close(fd)
    temporary = Path(raw_path)
    try:
        _picard_run([curl, "--disable", "--fail", "--silent", "--location", "--proto", "=https",
                     "--proto-redir", "=https", "--connect-timeout", "5", "--max-time", "20",
                     "--max-filesize", str(PICARD_LIMIT), "--output", str(temporary), "--", url],
                    cancelled, limit_file=temporary)
        _picard_verified(temporary, digest, size)
        os.link(temporary, destination)  # Never replace a cache file that appeared concurrently.
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def _picard_bmp(data):
    """Decode bounded, uncompressed 24/32-bit BMP produced by macOS sips."""
    if len(data) < 54 or data[:2] != b"BM":
        raise ValueError("Invalid converted Picard image.")
    offset, header = struct.unpack_from("<II", data, 10)
    width, height, planes, bits, compression = struct.unpack_from("<iiHHI", data, 18)
    if (header < 40 or offset < 14 + header or not 0 < width <= 436
            or not 0 < abs(height) <= 574 or planes != 1 or bits not in (24, 32) or compression != 0):
        raise ValueError("Unsupported Picard bitmap dimensions or format.")
    stride = ((width * bits + 31) // 32) * 4
    if offset + stride * abs(height) > len(data):
        raise ValueError("Truncated Picard bitmap.")
    rows = []
    for y in range(abs(height)):
        row = y if height < 0 else abs(height) - y - 1
        rows.append([tuple(reversed(data[offset + row * stride + x * (bits // 8):
                                        offset + row * stride + x * (bits // 8) + 3])) for x in range(width)])
    return rows


def _picard_render(rows, columns, lines, monochrome):
    scale = min(columns / len(rows[0]), (lines * 2) / len(rows))
    width, height = max(1, int(len(rows[0]) * scale)), max(2, int(len(rows) * scale))
    shades = " .:-=+*#%@"
    for y in range(0, height - 1, 2):
        cells = []
        for x in range(width):
            top = rows[min(len(rows) - 1, int(y / scale))][min(len(rows[0]) - 1, int(x / scale))]
            bottom = rows[min(len(rows) - 1, int((y + 1) / scale))][min(len(rows[0]) - 1, int(x / scale))]
            if monochrome:
                luminance = sum((a + b) * weight for a, b, weight in zip(top, bottom, (299, 587, 114))) // 2000
                cells.append(shades[luminance * (len(shades) - 1) // 255])
            else:
                cells.append("\033[38;2;%d;%d;%dm\033[48;2;%d;%d;%dm▀" % (top + bottom))
        print("".join(cells) + ("" if monochrome else "\033[0m"))


def _picard_show(root):
    if not sys.stdout.isatty():
        raise ValueError("Picard's picture needs a terminal; use `godmode picard link`.")
    chafa = shutil.which("chafa")
    sips = Path("/usr/bin/sips") if sys.platform == "darwin" else None
    if not chafa and not (sips and sips.is_file()):
        raise ValueError("Terminal pictures need chafa on this machine; `godmode picard open` opens the original.")
    _picard_directory(root, create=True)
    image = _picard_cached(root, "image")
    columns, lines = shutil.get_terminal_size((80, 24))
    columns, lines = max(1, min(columns, 100)), max(1, min(lines - 3, 45))
    monochrome = "NO_COLOR" in os.environ or os.environ.get("CLICOLOR") == "0" or os.environ.get("TERM") == "dumb"
    if chafa:
        args = [chafa, "--format", "symbols", "--size", "%dx%d" % (columns, lines)]
        if monochrome:
            args += ["--colors", "none", "--symbols", "ascii"]
        _picard_run(args + [str(image)], output=None)
    else:
        with tempfile.TemporaryDirectory(prefix=".image-", dir=root) as temporary:
            bitmap = Path(temporary) / "portrait.bmp"
            _picard_run([str(sips), "-s", "format", "bmp", str(image), "--out", str(bitmap)])
            if bitmap.stat().st_size > PICARD_LIMIT:
                raise ValueError("Converted Picard image exceeds its size limit.")
            _picard_render(_picard_bmp(bitmap.read_bytes()), columns, lines, monochrome)
    print(PICARD_SOURCE_URL)


def _picard_socket(path):
    if not os.path.lexists(path):
        return None
    info = path.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("Unsafe Picard control socket.")
    return info.st_dev, info.st_ino


def _picard_receive(connection, count):
    data = b""
    while len(data) < count:
        chunk = connection.recv(count - len(data))
        if not chunk:
            break
        data += chunk
    return data


def _picard_stop(root):
    _picard_directory(root)
    path = root / "p.sock"
    if _picard_socket(path) is None:
        return False
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(2)
        try:
            client.connect(str(path))
        except (FileNotFoundError, ConnectionRefusedError):
            return False
        client.sendall(b"STOP\n")
        if _picard_receive(client, 3) != b"OK\n":
            raise ValueError("Picard did not confirm stopping; close its foreground terminal.")
    return True


def _picard_play(root):
    backend = next(([path] + args for name, args in
                    (("afplay", []), ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]), ("aplay", ["-q"]))
                    for path in [shutil.which(name)] if path), None)
    if not backend:
        raise ValueError("Picard needs afplay, ffplay or aplay; use `godmode picard open`.")
    _picard_directory(root, create=True)
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    listener, pending, identity, handlers = None, None, None, {}
    path = root / "p.sock"
    stopped = False
    def interrupt(signum, frame):
        nonlocal stopped
        stopped = True
    def cancelled():
        nonlocal pending
        if stopped or pending is not None:
            return True
        try:
            connection, _ = listener.accept()
        except BlockingIOError:
            return False
        connection.settimeout(0.1)
        try:
            if _picard_receive(connection, 5) == b"STOP\n":
                pending = connection
                return True
        except OSError:
            pass
        connection.close()
        return False
    try:
        try:
            fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError("Picard is already playing; use `godmode picard stop`.") from None
        if _picard_socket(path) is not None:
            with socket.socket(socket.AF_UNIX) as existing:
                existing.settimeout(0.2)
                try:
                    existing.connect(str(path))
                except (FileNotFoundError, ConnectionRefusedError):
                    path.unlink()
                else:
                    raise ValueError("A Picard controller is already using this socket.")
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(str(path))
        os.chmod(path, 0o600)
        identity = _picard_socket(path)
        listener.listen(1)
        listener.setblocking(False)
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            handlers[signum] = signal.signal(signum, interrupt)
        audio = _picard_cached(root, "audio", cancelled)
        print("Playing Picard. Ctrl-C or `godmode picard stop` stops it.", flush=True)
        while not cancelled():
            _picard_run(backend + [str(audio)], cancelled, timeout=None)
    except _PicardCancelled:
        pass
    finally:
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
        if listener is not None:
            listener.close()
        if identity is not None and _picard_socket(path) == identity:
            path.unlink()
        os.close(directory)
        if pending is not None:
            with contextlib.suppress(OSError):
                pending.sendall(b"OK\n")
            pending.close()


def picard(action, state_dir=None):
    """Public opt-in entry point. Link/open do not touch cache or credentials."""
    if action == "link":
        print(PICARD_SOURCE_URL)
        return 0
    if action == "open":
        opener = "/usr/bin/open" if sys.platform == "darwin" else shutil.which("xdg-open")
        if not opener:
            raise ValueError("Open " + PICARD_SOURCE_URL + " in your browser.")
        _picard_run([opener, PICARD_SOURCE_URL])
        return 0
    if action not in ("show", "play", "stop"):
        raise ValueError("Use picard link, open, show, play or stop.")
    selected = state_dir or os.environ.get("GODMODE_STATE_DIR") or Path(os.environ.get("GODMODE_HOME", str(Path.home() / ".godmode"))) / "state"
    root = Path(os.path.abspath(os.path.expanduser(str(selected)))) / "picard"
    try:
        if action == "show":
            _picard_show(root)
        elif action == "play":
            _picard_play(root)
        else:
            print("Picard stopped." if _picard_stop(root) else "No Picard player is running.")
    except OSError:
        raise ValueError("Cannot access Picard media or its local player.") from None
    return 0
