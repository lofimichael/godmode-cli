"""Optional local Darunia adapter. No network, downloaded code, catalog, or music assets.

Remove this file and its command/build hooks to remove music. Nothing imports
the key store. Darunia runs as a separate, explicitly initialized program.
"""
import argparse
import array
import contextlib
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import select
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import wave

MUSIC_SOURCE = "https://github.com/lofimichael/darunias-cli"
MUSIC_LIMIT = 700 * 1024 * 1024
MUSIC_CONFIG_LIMIT = 65536


def _music_root(home=None):
    selected = home or os.environ.get("GODMODE_HOME") or str(Path.home() / ".godmode")
    return Path(os.path.abspath(os.path.expanduser(str(selected)))) / "state" / "music"


def _music_text(value):
    # File names and upstream metadata cannot write terminal controls.
    return "".join(c for c in str(value) if c.isprintable())


def _music_directory(path, create=False):
    for directory in reversed((path,) + tuple(path.parents)):
        if create and not os.path.lexists(directory):
            directory.mkdir(mode=0o700)
        if os.path.lexists(directory) and not stat.S_ISDIR(directory.lstat().st_mode):
            raise ValueError("Music paths must not contain symlinks.")
    if path.exists():
        info = path.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise ValueError("Music files must be yours and not writable by other users.")


def _music_bytes(path, limit=MUSIC_CONFIG_LIMIT):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or info.st_mode & 0o022 or info.st_size > limit):
            raise ValueError("Unsafe music file: " + _music_text(path.name))
        return stream.read(limit + 1)


def _music_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


@contextlib.contextmanager
def _music_lock(root):
    _music_directory(root, True)
    path = root / ".lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
            raise ValueError("Unsafe music lock.")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Music is running. Stop it before changing its cache.") from None
        yield
    finally:
        os.close(fd)


def _music_atomic(path, data):
    if os.path.lexists(path):
        _music_bytes(path)
    fd, name = tempfile.mkstemp(prefix=".config-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _music_config(root, verify=True):
    _music_directory(root)
    try:
        data = json.loads(_music_bytes(root / "config.json"))
    except FileNotFoundError:
        raise ValueError("Darunia is not linked. Run godmode music init SYNTH_FOLDER --songs TRACK_FOLDER.\n"
                         + MUSIC_SOURCE) from None
    if (not isinstance(data, dict) or data.get("version") != 1
            or any(not isinstance(data.get(k), str) for k in ("backend", "songs", "sha256"))):
        raise ValueError("Invalid music config. Run godmode music init DIR --songs DIR.")
    backend, songs = Path(data["backend"]), Path(data["songs"])
    if not backend.is_absolute() or not songs.is_absolute():
        raise ValueError("Music paths must be absolute.")
    _music_directory(backend)
    _music_directory(songs)
    if verify:
        script = _music_bytes(backend / "synthesize.py", 1024 * 1024)
        if hashlib.sha256(script).hexdigest() != data["sha256"]:
            raise ValueError("Darunia's synth changed. Review it, then run godmode music init again.")
    return data


def music_available(home=None):
    try:
        _music_config(_music_root(home))
        return True
    except (OSError, ValueError, TypeError):
        return False


def _music_init(root, backend, songs):
    backend = Path(os.path.abspath(os.path.expanduser(str(backend))))
    songs = Path(os.path.abspath(os.path.expanduser(str(songs))))
    _music_directory(backend)
    _music_directory(songs)
    if not songs.is_dir():
        raise ValueError("The song folder does not exist.")
    script = _music_bytes(backend / "synthesize.py", 1024 * 1024)
    required = (backend / "tools/render_synth", backend / "tools/seq64/build/seq64_console",
                backend / "tools/florestan-subset.sf2", backend / "oot-instruments.json")
    if any(not p.is_file() for p in required) or not shutil.which("ffmpeg"):
        raise ValueError("Darunia's synthesis tools are missing. Follow " + MUSIC_SOURCE + "/blob/main/docs/SYNTHESIS.md")
    data = {"version": 1, "backend": str(backend), "songs": str(songs),
            "sha256": hashlib.sha256(script).hexdigest()}
    count = len(_music_songs(songs))
    with _music_lock(root):
        _music_atomic(root / "config.json", (json.dumps(data, indent=2) + "\n").encode())
    print("Darunia's CLI linked. " + str(count) + " local tracks.")


def _music_songs(base):
    """Only local regular files; never walk symlinked directories."""
    result = []
    for directory, dirs, files in os.walk(base, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not Path(directory, d).is_symlink())
        for name in sorted(files):
            path = Path(directory, name)
            if path.suffix.lower() == ".ootrs" and not path.is_symlink() and path.is_file():
                result.append(path)
                if len(result) > 10000:
                    raise ValueError("Music folders can hold at most 10,000 tracks.")
    return sorted(result, key=lambda p: str(p.relative_to(base)).casefold())


def _music_select(base, query, menu=None):
    songs = _music_songs(base)
    if query:
        exact = [p for p in songs if str(p.relative_to(base)).casefold() == query.casefold()]
        songs = exact or [p for p in songs if query.casefold() in str(p.relative_to(base)).casefold()]
    if not songs:
        raise ValueError("No local tracks match. Run godmode music list.")
    if len(songs) == 1:
        return songs[0]
    if menu is not None and sys.stdin.isatty() and sys.stdout.isatty():
        items = [(_music_text(p.stem), "", _music_text(str(p.relative_to(base).parent))) for p in songs]
        items.append(("Back", "", ""))
        choice = menu(items, title="Music", hint="↑↓ choose  Enter play  Esc back", searchable=True)
        return None if choice is None or choice == len(songs) else songs[choice]
    raise ValueError(str(len(songs)) + " tracks match. Use the path shown by godmode music list.")


def _music_env():
    names = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "TERM", "COLORTERM", "TMPDIR",
             "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "PULSE_SERVER")
    return {key: os.environ[key] for key in names if key in os.environ}


def _music_animated():
    return (sys.stdout.isatty() and sys.stdin.isatty() and os.environ.get("TERM", "dumb") not in ("", "dumb")
            and os.environ.get("GODMODE_PLAIN", "").lower() in ("", "0", "false", "no")
            and os.environ.get("GODMODE_NO_MOTION", "").lower() in ("", "0", "false", "no"))


def _music_color(text, code):
    if (sys.stdout.isatty() and "NO_COLOR" not in os.environ and os.environ.get("CLICOLOR") != "0"
            and os.environ.get("TERM", "dumb") not in ("", "dumb")
            and os.environ.get("GODMODE_PLAIN", "").lower() in ("", "0", "false", "no")):
        return "\x1b[" + code + "m" + text + "\x1b[0m"
    return text


@contextlib.contextmanager
def _music_controls(interactive, terminal):
    keyboard_factory, _, cancelled = terminal
    if interactive:
        try:
            with keyboard_factory() as keyboard:
                if _music_animated():
                    sys.stdout.write("\x1b[?25l")
                    sys.stdout.flush()
                try:
                    yield keyboard
                finally:
                    # A paste can span multiple OS writes. Keep echo off until
                    # input has been quiet briefly, then _Keyboard flushes it.
                    deadline = time.monotonic() + 0.5
                    while time.monotonic() < deadline:
                        if not select.select([keyboard.fd], [], [], 0.08)[0]:
                            break
                        if not os.read(keyboard.fd, 4096):
                            break
        except cancelled:
            raise KeyboardInterrupt() from None
        return
    handlers = {}
    def stop(signum, frame):
        raise KeyboardInterrupt()
    try:
        for signum in (signal.SIGTERM, signal.SIGHUP):
            handlers[signum] = signal.signal(signum, stop)
        yield None
    finally:
        for signum, handler in handlers.items():
            signal.signal(signum, handler)


def _music_quit(keyboard):
    if keyboard is not None:
        while True:
            event = keyboard.poll()
            if event is None:
                break
            kind, key = event
            if (kind == "text" and key in (b"q", b"Q")) or (kind == "key" and key == "esc"):
                return True
            # Pasted bytes, including q/newlines, are data and are always ignored.
    return False


def _music_end(child):
    # synthesize.py owns converter/renderer children; stop its whole process group.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(child.pid, signal.SIGTERM)
    if child.poll() is None:
        try:
            child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
    # A converter can outlive its Python parent or ignore SIGTERM.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(child.pid, signal.SIGKILL)
    child.wait()


def _music_run(command, frame=None, active=False, timeout=180, keyboard=None):
    with tempfile.TemporaryFile() as output:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                 env=_music_env(), start_new_session=True)
        started = time.monotonic()
        try:
            while child.poll() is None:
                elapsed = time.monotonic() - started
                if _music_quit(keyboard):
                    raise KeyboardInterrupt()
                if elapsed > timeout:
                    raise ValueError("Music timed out.")
                if os.fstat(output.fileno()).st_size > 1024 * 1024:
                    raise ValueError("The music program produced too much output.")
                if frame:
                    frame(elapsed)
                time.sleep(0.06)
            output.seek(0)
            log = output.read(65536).decode("utf-8", "replace")
            if child.returncode:
                raise ValueError("Darunia or the local audio player failed. Check godmode music status.")
            return log
        finally:
            _music_end(child)


def _music_validate_cache(cache):
    _music_directory(cache)
    if not cache.exists():
        return
    for directory, dirs, files in os.walk(cache, followlinks=False):
        for name in dirs:
            _music_directory(Path(directory, name))
        for name in files:
            path = Path(directory, name)
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1 or info.st_mode & 0o022 or info.st_size > MUSIC_LIMIT):
                raise ValueError("Unsafe music cache. No files changed.")


def _music_print(text=""):
    sys.stdout.write(str(text).replace("\n", "\r\n") + "\r\n")
    sys.stdout.flush()


def _music_render(root, config, source, seconds, active=False, keyboard=None, draw=None):
    cache = root / "cache"
    _music_directory(cache, True)
    _music_validate_cache(cache)
    original_locks = set(cache.glob("*.lock"))
    # Darunia computes and verifies its own cache key from every input/tool/font.
    # An export gives us an exact path/receipt without parsing terminal output.
    with tempfile.TemporaryDirectory(prefix=".render-", dir=root) as work:
        export = Path(work) / "track.wav"
        command = [sys.executable, str(Path(config["backend"]) / "synthesize.py"), str(source),
                   "--seconds", str(seconds), "--cache-dir", str(cache), "--output", str(export)]
        spinner = ("|", "/", "-", "\\")
        drawn = []
        def frame(elapsed):
            nonlocal drawn
            width = shutil.get_terminal_size().columns
            label = "Synthesizing " + _music_text(source.stem)[:max(1, width - 32)] + " · q stop"
            if width < 30:
                label = "Rendering · q stop"[:max(1, width - 5)]
            drawn = draw(["  " + _music_color(spinner[int(elapsed * 8) % 4], "1;35") + " " + label], drawn)
        if not active:
            _music_print("Synthesizing " + _music_text(source.stem))
        try:
            log = _music_run(command, frame if active else None, active, keyboard=keyboard)
        finally:
            # SIGTERM can bypass Darunia's finally block. Only remove empty locks
            # this invocation created, after all its child processes have stopped.
            for lock in set(cache.glob("*.lock")) - original_locks:
                if not lock.is_symlink() and lock.is_dir():
                    with contextlib.suppress(OSError):
                        lock.rmdir()
            if active:
                draw([], drawn)
        details = json.loads(_music_bytes(export.with_suffix(".synthesis.json"), 1024 * 1024))
        key = details.get("cache_key", "")
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("Darunia returned an invalid cache key.")
        cached = cache / key / "render.wav"
        _music_validate_cache(cache)
        if (not cached.is_file() or cached.stat().st_size > MUSIC_LIMIT
                or _music_sha(cached) != details.get("wav_sha256")):
            raise ValueError("Music cache checksum failed. Run godmode music clear.")
        return cached, details, "Cache hit:" in log


def _music_levels(audio, elapsed, count=24):
    """Log-spaced frequency bins from the PCM at the current playback position."""
    rate, channels = audio.getframerate(), audio.getnchannels()
    start = min(audio.getnframes(), max(0, int(elapsed * rate)))
    audio.setpos(start)
    values = array.array("h", audio.readframes(2048))
    if sys.byteorder != "little":
        values.byteswap()
    step = max(1, rate // 11025)
    mono = [sum(values[i:i + channels]) / (channels * 32768.0)
            for i in range(0, len(values) - channels + 1, channels * step)][:512]
    if not mono:
        return [0.0] * count
    size, sample_rate = len(mono), rate / step
    window = [x * (0.5 - 0.5 * math.cos(2 * math.pi * i / max(1, size - 1))) for i, x in enumerate(mono)]
    result = []
    for index in range(count):
        frequency = 70 * (min(4200, sample_rate * 0.45) / 70) ** (index / max(1, count - 1))
        coefficient = 2 * math.cos(2 * math.pi * frequency / sample_rate)
        first = second = 0.0
        for sample in window:
            current = sample + coefficient * first - second
            second, first = first, current
        power = max(0, first * first + second * second - coefficient * first * second)
        amplitude = math.sqrt(power) / size
        result.append(max(0.0, min(1.0, (20 * math.log10(amplitude + 1e-9) + 65) / 55)))
    return result


def _music_clock(seconds):
    return str(int(seconds) // 60) + ":" + str(int(seconds) % 60).zfill(2)


def music_visual_rows(levels, elapsed, duration, width=80, height=24):
    """Inspectable visualizer frame, also used by screenshot verification."""
    if width < 24 or height < 10:
        return [(_music_clock(elapsed) + " / " + _music_clock(duration))[:max(1, width - 1)],
                "q stop"[:max(1, width - 1)]]
    count = max(1, min(len(levels), (width - 6) // 3))
    tall = max(1, min(9, height - 9))
    colors = ("35", "35", "36", "36", "32", "33", "33", "31", "31")
    unicode = "utf" in (getattr(sys.stdout, "encoding", "") or "").lower() and os.environ.get("TERM") != "linux"
    block = "██" if unicode else "##"
    rows = []
    for row in range(tall, 0, -1):
        parts = [(_music_color(block, colors[min(8, row - 1)]) if level * tall >= row - 0.5 else "  ")
                 for level in levels[:count]]
        rows.append("  " + " ".join(parts))
    columns = max(1, min(66, width - 6))
    progress = int(columns * min(1, elapsed / duration)) if duration else 0
    rows += ["", "  " + _music_color("━" * progress if unicode else "#" * progress, "36")
             + _music_color("─" * (columns - progress) if unicode else "-" * (columns - progress), "2"),
             "  " + _music_clock(elapsed) + " / " + _music_clock(duration), "", "  q stop"]
    return rows


def _music_play(path, details, active=False, keyboard=None, draw=None):
    player = next(([exe] + flags for name, flags in
                   (("afplay", ["-v", "0.35"]), ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet", "-volume", "35"]),
                    ("aplay", ["-q"])) for exe in [shutil.which(name)] if exe), None)
    if not player:
        raise ValueError("Playback needs afplay, ffplay or aplay. The WAV is cached.")
    with wave.open(str(path), "rb") as audio:
        if audio.getsampwidth() != 2 or audio.getnchannels() not in (1, 2) or audio.getcomptype() != "NONE":
            raise ValueError("The music visualizer needs 16-bit PCM WAV audio.")
        duration = audio.getnframes() / audio.getframerate()
        drawn = []
        def frame(elapsed):
            nonlocal drawn
            width, height = shutil.get_terminal_size((80, 24))
            levels = _music_levels(audio, elapsed, max(1, min(24, (width - 6) // 3)))
            rows = music_visual_rows(levels, elapsed, duration, width, height)
            drawn = draw(rows, drawn)
        _music_print("\n  " + _music_color(_music_text(details.get("title", path.stem)), "1;36"))
        _music_print("  " + ("OoT instruments" if details.get("mode") == "oot" else "Piano") + "\n")
        if not active:
            _music_print("Playing " + _music_clock(duration) + ". Ctrl-C stops.")
        try:
            _music_run(player + [str(path)], frame if active else None, active, duration + 15, keyboard)
        finally:
            if active:
                _music_print()


def _music_clear(root):
    _music_directory(root)
    if not root.exists():
        print("Music cache is empty.")
        return
    with _music_lock(root):
        cache = root / "cache"
        _music_validate_cache(cache)
        if cache.exists():
            shutil.rmtree(cache)
    print("Music cache cleared.")


def music_main(argv, home=None, menu=None, terminal=None):
    if terminal is None:
        # Source-module use resolves core primitives here. Bundled entry points
        # inject these objects, so the removable adapter has no import hooks.
        import godmode_terminal as _music_core_terminal
        terminal = (_music_core_terminal._Keyboard, _music_core_terminal._draw, _music_core_terminal.Cancelled)
    parser = argparse.ArgumentParser(prog="godmode music", description="Local music through Darunia's CLI.")
    parser.add_argument("action", nargs="?", default="play", help="play, list, init, status, clear, or forget")
    parser.add_argument("query", nargs="?", default="", help="track name, or Darunia folder for init")
    parser.add_argument("--songs", type=Path, help="local .ootrs folder for init")
    parser.add_argument("--seconds", type=float, default=180, help="audio length, from 1 to 3600 seconds")
    parser.add_argument("--render-only", action="store_true", help="cache the WAV without playing")
    parser.add_argument("--no-motion", action="store_true", help="play without the visualizer")
    args = parser.parse_args(argv)
    if not math.isfinite(args.seconds) or not 1 <= args.seconds <= 3600:
        parser.error("--seconds must be from 1 to 3600")
    if args.songs is not None and args.action != "init":
        parser.error("--songs belongs to music init")
    if args.action in ("clear", "forget", "status") and args.query:
        parser.error("this command takes no track name")
    root = _music_root(home)
    if args.action == "init":
        if not args.query or not args.songs:
            parser.error("init needs a Darunia folder and --songs DIR")
        _music_init(root, args.query, args.songs)
        return 0
    if args.action == "clear":
        _music_clear(root)
        return 0
    if args.action == "forget":
        _music_directory(root)
        if root.exists():
            with _music_lock(root):
                config = root / "config.json"
                if os.path.lexists(config):
                    _music_bytes(config)
                    config.unlink()
        print("Darunia link removed.")
        return 0
    config = _music_config(root)
    base = Path(config["songs"])
    if args.action == "status":
        print("Darunia  " + _music_text(config["backend"]))
        print("Tracks   " + _music_text(base))
        print("Cache    " + _music_text(root / "cache"))
        print("Source   " + MUSIC_SOURCE)
        return 0
    if args.action == "list":
        for song in _music_songs(base):
            name = str(song.relative_to(base))
            if args.query.casefold() in name.casefold():
                print(_music_text(name))
        return 0
    query = args.query if args.action == "play" else args.action
    source = _music_select(base, query, menu)
    if source is None:
        return 0
    active = _music_animated() and not args.no_motion
    try:
        with _music_lock(root), _music_controls(sys.stdin.isatty() and sys.stdout.isatty(), terminal) as keyboard:
            path, details, cached = _music_render(root, config, source, args.seconds, active, keyboard, terminal[1])
            _music_print("  " + ("Cached" if cached else "Synthesized") + " · " + _music_clock(args.seconds))
            if args.render_only:
                _music_print(str(path))
            else:
                _music_play(path, details, active, keyboard, terminal[1])
    except KeyboardInterrupt:
        print("\nMusic stopped.")
        return 130
    return 0
