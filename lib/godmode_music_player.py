"""Optional music session owner. Stdlib only; never imports credentials or core UI.

The private socket accepts semantic music commands, never arbitrary mpv commands.
mpv receives an inherited socketpair, so its unrestricted IPC has no named socket.
"""
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import random
import select
import shutil
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import uuid
import wave

from godmode_music import _music_root, _music_directory, _music_bytes, _music_config, _music_songs, _music_text, _music_env, _music_lock, _music_render, _music_levels, _music_end, _music_atomic, _music_sha, _music_validate_cache

MUSIC_PROTOCOL_LIMIT = 1024 * 1024
MUSIC_QUEUE_LIMIT = 10000


def _music_stopped():
    return {"state": "stopped", "track": None, "queue": [], "index": -1,
            "position": 0.0, "duration": 0.0, "volume": 35.0,
            "repeat": "off", "shuffle": False, "levels": [], "message": "Stopped",
            "clock_source": "unavailable", "clock_age": None}


def _music_track(base, path):
    relative = str(path.relative_to(base))
    parent = str(path.relative_to(base).parent)
    return {"id": relative, "title": _music_text(path.stem),
            "collection": "Library" if parent == "." else _music_text(parent)}


def _music_saved(root):
    data = _music_stopped()
    try:
        saved = json.loads(_music_bytes(root / "session.json", MUSIC_PROTOCOL_LIMIT))
    except FileNotFoundError:
        return data, 180.0
    if not isinstance(saved, dict) or saved.get("version") != 1:
        raise ValueError("Invalid saved music session.")
    ids = saved.get("ids")
    if (not isinstance(ids, list) or len(ids) > MUSIC_QUEUE_LIMIT or any(
            not isinstance(item, str) or not item or len(item) > 4096 or Path(item).is_absolute()
            or ".." in Path(item).parts or Path(item).suffix.lower() != ".ootrs" for item in ids)):
        raise ValueError("Invalid saved music queue.")
    index = saved.get("index", -1)
    if isinstance(index, bool) or not isinstance(index, int) or not -1 <= index < max(1, len(ids)):
        raise ValueError("Invalid saved music index.")
    if not ids:
        index = -1
    data["queue"] = [_music_track(Path("."), Path(item)) for item in ids]
    data.update(index=index, track=data["queue"][index] if index >= 0 else None,
                volume=_music_number(saved.get("volume", 35), 0, 100, "Saved volume"))
    if saved.get("repeat") not in ("off", "all", "one") or not isinstance(saved.get("shuffle"), bool):
        raise ValueError("Invalid saved music playback modes.")
    data.update(repeat=saved["repeat"], shuffle=saved["shuffle"])
    seconds = _music_number(saved.get("seconds", 180), 1, 3600, "Saved render duration")
    return data, seconds


def music_library(home=None):
    result = {"configured": False, "tracks": [], "player_available": bool(shutil.which("mpv")),
              "no_motion": os.environ.get("GODMODE_NO_MOTION", "").lower() not in ("", "0", "false", "no")}
    try:
        config = _music_config(_music_root(home))
        base = Path(config["songs"])
        result.update(configured=True, backend=config["backend"], songs=config["songs"],
                      tracks=[_music_track(base, path) for path in _music_songs(base)])
    except (OSError, ValueError, TypeError) as error:
        result["error"] = _music_text(str(error))
    return result


def _music_session_path(root, create=False):
    _music_directory(root, create)
    directory = root / "session"
    _music_directory(directory, create)
    if directory.exists() and directory.stat().st_mode & 0o077:
        raise ValueError("Music session directory must be private (mode 0700).")
    path = directory / "control.sock"
    if len(os.fsencode(path)) >= 104:
        # Unix socket names are short on macOS. Hash only the already-validated
        # home, under an owned private directory; never trust a PID or /tmp link.
        base = Path("/tmp").resolve() / ("godmode-music-" + str(os.geteuid()))
        _music_directory(base, create)
        if base.exists() and base.stat().st_mode & 0o077:
            raise ValueError("Music runtime directory must be private (mode 0700).")
        directory = base / hashlib.sha256(os.fsencode(root)).hexdigest()[:24]
        _music_directory(directory, create)
        if directory.exists() and directory.stat().st_mode & 0o077:
            raise ValueError("Music runtime directory must be private (mode 0700).")
        path = directory / "control.sock"
    if os.path.lexists(path):
        info = path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError("Unsafe music session socket.")
    return path


def _music_json_line(connection):
    data = bytearray()
    while b"\n" not in data:
        block = connection.recv(min(65536, MUSIC_PROTOCOL_LIMIT + 1 - len(data)))
        if not block:
            raise ValueError("Incomplete music request.")
        data.extend(block)
        if len(data) > MUSIC_PROTOCOL_LIMIT:
            raise ValueError("Music request is too large.")
    line, rest = data.split(b"\n", 1)
    if rest.strip():
        raise ValueError("Send one command per music connection.")
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError("Music requests must be JSON objects.")
    return value


def _music_encode(value):
    data = (json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n").encode()
    if len(data) > MUSIC_PROTOCOL_LIMIT:
        raise ValueError("Music response is too large; reduce the queue or library.")
    return data


def _music_contact(root, request):
    path = _music_session_path(root)
    if not path.exists():
        return None
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(3)
        try:
            client.connect(str(path))
        except (FileNotFoundError, ConnectionRefusedError):
            return None
        client.sendall(_music_encode(request))
        response = _music_json_line(client)
    if response.get("ok") is not True:
        raise ValueError(response.get("error", "Music session rejected the command."))
    return response["data"]


def _music_launch(root):
    _music_session_path(root, True)
    executable = os.environ.get("GODMODE_EXECUTABLE")
    if executable:
        executable = os.path.abspath(executable)
        command = [executable]
    else:
        executable = os.path.abspath(sys.argv[0])
        if not Path(executable).is_file():
            raise ValueError("Cannot locate Godmode to start the music session.")
        command = [sys.executable, executable]
    env = _music_env()
    env["GODMODE_HOME"] = str(root.parent.parent)
    # The owner has no inherited terminal, credential environment or open pipes.
    child = subprocess.Popen(command + ["music", "__serve"], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             env=env, start_new_session=True, close_fds=True)
    # Keep/reap our direct child while this client lives. If the short-lived CLI
    # exits first, the detached owner is adopted by the operating system.
    threading.Thread(target=child.wait, daemon=True).start()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = _music_contact(root, {"action": "status"})
        if status is not None:
            # Reap the losing process if a concurrent caller started the owner.
            if child.poll() is not None:
                child.wait()
            return
        if child.poll() is not None:
            # A concurrent owner may be between locking and binding.
            time.sleep(0.05)
        else:
            time.sleep(0.03)
    if child.poll() is None:
        _music_end(child)
    raise ValueError("Music session could not start. Check mpv and the music home permissions.")


def music_request(request, home=None):
    if not isinstance(request, dict) or not isinstance(request.get("action"), str):
        raise ValueError("Music request needs an action.")
    action = request["action"]
    fields = {"play": {"ids", "index", "seconds"}, "enqueue": {"ids"}, "seek": {"seconds"},
              "volume": {"value"}, "repeat": {"value"}, "shuffle": {"value"}, "remove": {"index"}}
    if set(request) - {"action"} - fields.get(action, set()):
        raise ValueError("Unknown field in music request.")
    _music_encode(request)  # Bound requests before opening/starting any process.
    if action in ("play", "enqueue"):
        ids = request.get("ids")
        if not isinstance(ids, list) or not ids or len(ids) > MUSIC_QUEUE_LIMIT or any(not isinstance(x, str) for x in ids):
            raise ValueError("Choose between 1 and 10,000 track IDs.")
    if action == "play":
        index = request.get("index", 0)
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(request["ids"]):
            raise ValueError("Invalid queue index.")
        _music_number(request.get("seconds", 180), 1, 3600, "Render duration")
    if action in ("seek", "volume"):
        _music_number(request.get("seconds" if action == "seek" else "value"),
                      -3600 if action == "seek" else 0, 3600 if action == "seek" else 100, action.title())
    if action == "repeat" and request.get("value") not in ("off", "one", "all"):
        raise ValueError("Repeat must be off, all, or one.")
    if action == "shuffle" and not isinstance(request.get("value"), bool):
        raise ValueError("Shuffle must be true or false.")
    if action == "library":
        return music_library(home)
    if action not in ("status", "play", "enqueue", "pause", "resume", "toggle", "next", "previous",
                      "seek", "volume", "repeat", "shuffle", "remove", "clear_queue", "stop"):
        raise ValueError("Unknown music action.")
    root = _music_root(home)
    result = _music_contact(root, request)
    if result is not None:
        return result
    if action in ("status", "stop", "clear_queue", "remove"):
        if action == "stop":
            try:
                return _music_saved(root)[0]
            except (OSError, ValueError, TypeError):
                return _music_stopped()
        data, seconds = _music_saved(root)
        if action == "remove":
            # Queue edits after Stop do not need a player, config, or daemon.
            if not root.exists():
                raise ValueError("Invalid queue index.")
            with _music_lock(root):
                session = _MusicSession(root)
                try:
                    return session.handle(request)
                finally:
                    session.close()
        if action == "clear_queue" and root.exists():
            with _music_lock(root):
                data.update(queue=[], index=-1, track=None)
                _music_save(root, data, seconds)
        return data
    if action not in ("play", "enqueue", "volume", "repeat", "shuffle"):
        raise ValueError("No music session is running. Choose a track first.")
    _music_config(root)  # Pin verification occurs before starting a session.
    if not shutil.which("mpv"):
        raise ValueError("Playback needs mpv. Install mpv, or use music play --render-only.")
    _music_launch(root)
    result = _music_contact(root, request)
    if result is None:
        raise ValueError("Music session exited before receiving the command.")
    return result


def music_session_bridge(home=None):
    """JSON lines until EOF. Disconnecting this client never stops playback."""
    while True:
        line = sys.stdin.buffer.readline(MUSIC_PROTOCOL_LIMIT + 1)
        if not line:
            return 0
        try:
            if len(line) > MUSIC_PROTOCOL_LIMIT or not line.endswith(b"\n"):
                raise ValueError("Music request is too large or incomplete.")
            result = {"ok": True, "data": music_request(json.loads(line), home)}
            encoded = _music_encode(result)
        except (OSError, ValueError, TypeError, KeyError) as error:
            result = {"ok": False, "error": _music_text(str(error))}
            encoded = _music_encode(result)
        try:
            sys.stdout.buffer.write(encoded)
            sys.stdout.buffer.flush()
        except (BrokenPipeError, OSError):
            return 0
        if len(line) > MUSIC_PROTOCOL_LIMIT:
            return 1


class _MusicMPV:
    """One process and one inherited local IPC connection; no exposed mpv socket."""
    def __init__(self, events, audio_output=None):
        executable = shutil.which("mpv")
        if not executable:
            raise ValueError("Playback needs mpv. Install mpv, or use music play --render-only.")
        self.events, self.pending = events, {}
        self.serial, self.closed = 0, False
        self.guard = threading.Lock()
        self.connection, inherited = socket.socketpair()
        command = [executable, "--no-config", "--idle=yes", "--terminal=no", "--vid=no",
                   "--audio-display=no", "--input-terminal=no", "--input-media-keys=no",
                   "--input-default-bindings=no", "--load-scripts=no", "--volume=35",
                   "--input-ipc-client=fd://" + str(inherited.fileno())]
        if audio_output:  # Explicit test construction only, never bridge-controlled.
            command.append("--ao=" + audio_output)
        try:
            self.child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL, env=_music_env(), start_new_session=True,
                                          pass_fds=(inherited.fileno(),))
        except BaseException:
            self.connection.close()
            raise
        finally:
            inherited.close()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            for number, name in enumerate(("audio-pts", "time-pos", "duration", "pause", "volume", "path"), 1):
                self.command("observe_property", number, name)
        except BaseException:
            self.close()
            raise

    def _read(self):
        try:
            with self.connection.makefile("rb") as stream:
                while True:
                    line = stream.readline(MUSIC_PROTOCOL_LIMIT + 1)
                    if not line or len(line) > MUSIC_PROTOCOL_LIMIT:
                        break
                    message = json.loads(line)
                    if "request_id" in message:
                        with self.guard:
                            waiting = self.pending.get(message["request_id"])
                        if waiting:
                            waiting.put(message)
                    elif message.get("event"):
                        self.events.put(message)
        except (OSError, ValueError):
            pass
        finally:
            self.events.put({"event": "transport-closed"})
            with self.guard:
                for waiting in self.pending.values():
                    waiting.put({"error": "connection closed"})

    def command(self, *command):
        waiting = queue.Queue()
        with self.guard:
            self.serial += 1
            serial = self.serial
            self.pending[serial] = waiting
        try:
            self.connection.sendall(_music_encode({"command": list(command), "request_id": serial}))
            try:
                reply = waiting.get(timeout=2)
            except queue.Empty:
                raise ValueError("mpv did not answer. Stop music and retry.") from None
            if reply.get("error") != "success":
                raise ValueError("mpv could not apply the playback command.")
            return reply.get("data")
        finally:
            with self.guard:
                self.pending.pop(serial, None)

    def close(self):
        if self.closed:
            return
        self.closed = True
        with contextlib.suppress(OSError):
            self.connection.shutdown(socket.SHUT_RDWR)
        self.connection.close()
        _music_end(self.child)
        self.reader.join(timeout=2)


def _music_number(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(label + " is outside its allowed range.")
    return float(value)


def _music_save(root, data, seconds):
    saved = {"version": 1, "ids": [track["id"] for track in data["queue"]], "index": data["index"],
             "volume": data["volume"], "repeat": data["repeat"], "shuffle": data["shuffle"], "seconds": seconds}
    _music_atomic(root / "session.json", _music_encode(saved), MUSIC_PROTOCOL_LIMIT)


def _music_file_stamp(path):
    """Changes include inode/ctime, so restoring mtime cannot hide a replacement."""
    if not os.path.lexists(path):
        return (str(path), None)
    link = path.lstat()
    resolved = path.resolve()
    info = resolved.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Music preparation dependency is not a regular file.")
    return (str(path), link.st_dev, link.st_ino, link.st_ctime_ns, str(resolved),
            info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_mode, info.st_uid, info.st_nlink)


def _music_prepared_signature(config, source, details, verify=False):
    """Reuse only this known receipt policy; unknown adapters still render normally.

Verify every Darunia input against its receipt once, then compare full file
identity/change stamps on each reuse. Dynamic executable/ABI/font resolution is
repeated, including a previously missing font becoming available.
"""
    inputs = details.get("inputs")
    if not isinstance(inputs, dict) or inputs.get("policy") != "oot-or-whole-song-piano-v1":
        return None
    backend = Path(config["backend"])
    try:
        seq64 = backend / "tools/seq64/build/seq64_console"
        abi = None
        for parent in seq64.resolve().parents:
            if (parent / "abi").exists():
                abi = parent / "abi/4 - Zelda.xml"
                break
        ffmpeg = shutil.which("ffmpeg")
        if abi is None or not ffmpeg:
            return None
        files = [(source, inputs["source_sha256"]), (backend / "synthesize.py", inputs["adapter_sha256"]),
                 (backend / "oot-instruments.json", inputs["mapping_sha256"]),
                 (backend / "tools/florestan-subset.sf2", inputs["piano_soundfont_sha256"]),
                 (backend / "tools/render_synth", inputs["tools"]["renderer"]),
                 (seq64, inputs["tools"]["seq64"]), (Path(ffmpeg), inputs["tools"]["ffmpeg"]),
                 (abi, inputs["abi_sha256"])]
        instruments = inputs["instruments"]
        font = instruments.get("soundfont")
        if font:
            if not isinstance(font, str) or Path(font).is_absolute() or ".." in Path(font).parts:
                return None
            files.append((backend / "tools/oot-soundfonts" / font, instruments.get("soundfont_sha256")))
        signature = [config["backend"], config["songs"], config["sha256"]]
        for path, expected in files:
            before = _music_file_stamp(path)
            if verify:
                if expected is None:
                    if path.exists():
                        return None
                elif (not isinstance(expected, str) or len(expected) != 64
                      or _music_sha(path) != expected or before != _music_file_stamp(path)):
                    return None
            signature.append(before)
        return tuple(signature)
    except (OSError, KeyError, TypeError, ValueError):
        return None


class _MusicSession:
    def __init__(self, root, player_factory=_MusicMPV):
        self.root, self.player_factory = root, player_factory
        self.data, self.seconds = _music_saved(root)
        self.data["session_id"] = uuid.uuid4().hex
        self.events, self.rendered = queue.Queue(), queue.Queue()
        self.player = None
        self.worker, self.cancel = None, None
        self.generation = 0
        self.pending = None
        self.want_pause = False
        self.ending = False
        self.audio = None
        self.clock_at = None
        self.audio_clock_at = None
        self.started_at = None
        self.loaded_path = None
        self.history = []
        self.remaining = [i for i in range(len(self.data["queue"])) if i != self.data["index"]]
        random.shuffle(self.remaining)
        self.last_levels = 0
        self.awaiting_start = True
        self.entry_id = None
        self.closed = False
        self.prepared = {}
        self.prefetch_for = None

    def _resolve(self, ids):
        if not isinstance(ids, list) or not ids or len(ids) > MUSIC_QUEUE_LIMIT or any(not isinstance(x, str) for x in ids):
            raise ValueError("Choose between 1 and 10,000 track IDs.")
        config = _music_config(self.root)
        base = Path(config["songs"])
        library = {str(path.relative_to(base)): _music_track(base, path) for path in _music_songs(base)}
        if any(item not in library for item in ids):
            raise ValueError("A track is missing from the local library. Refresh the library.")
        return [dict(library[item]) for item in ids]

    def _cancel_work(self):
        self.generation += 1
        self.pending = None
        self.prefetch_for = None
        if self.cancel:
            self.cancel.set()
        if self.audio:
            self.audio.close()
            self.audio = None
        self.loaded_path = None
        if self.player:
            try:
                self.player.command("stop")
            except (OSError, ValueError):
                self.player.close()
                self.player = None
        while True:
            try:
                self.events.get_nowait()
            except queue.Empty:
                break
        self.awaiting_start, self.entry_id = True, None
        self.clock_at = self.audio_clock_at = None
        self.data.update(position=0.0, duration=0.0, levels=[], clock_source="unavailable", clock_age=None)

    def _start(self, index, remember=True, paused=False):
        if not 0 <= index < len(self.data["queue"]):
            return
        # Saved queue entries may have moved since the previous session.
        self._resolve([self.data["queue"][index]["id"]])
        previous = self.data["index"]
        if remember and previous >= 0 and previous != index:
            self.history.append(previous)
        self._cancel_work()
        self.data.update(index=index, track=self.data["queue"][index], state="preparing", message="Preparing audio")
        self.want_pause = paused
        self.started_at = time.monotonic()
        self.pending = (self.generation, dict(self.data["track"]), self.seconds, "play")
        self.remaining = [value for value in self.remaining if value != index]

    def _begin_render(self):
        if self.worker is not None or self.pending is None:
            return
        generation, track, seconds, purpose = self.pending
        self.pending = None
        cancel = self.cancel = threading.Event()
        remembered = self.prepared.get((track["id"], seconds))
        def render():
            try:
                config = _music_config(self.root)
                source = Path(config["songs"]) / track["id"]
                _music_directory(source.parent)
                _music_bytes(source, 700 * 1024 * 1024)
                value, signature = None, None
                if remembered:
                    old_value, old_signature, wav_stamp = remembered
                    current = _music_prepared_signature(config, source, old_value[1])
                    _music_validate_cache(self.root / "cache")
                    if current is not None and current == old_signature and _music_file_stamp(old_value[0]) == wav_stamp:
                        value, signature = old_value, current
                if value is None:
                    value = _music_render(self.root, config, source, seconds, cancel=cancel, quiet=True)
                    signature = _music_prepared_signature(config, source, value[1], verify=True)
                self.rendered.put((generation, purpose, track["id"], seconds, value, signature, None))
            except (Exception, KeyboardInterrupt) as error:
                self.rendered.put((generation, purpose, track["id"], seconds, None, None, error))
        self.worker = threading.Thread(target=render, daemon=True)
        self.worker.start()

    def _finish_render(self):
        try:
            generation, purpose, track_id, seconds, value, signature, error = self.rendered.get_nowait()
        except queue.Empty:
            return
        self.worker.join(timeout=0.1)
        self.worker = None
        if generation != self.generation:
            return
        if error is not None:
            if purpose == "play":
                self.data.update(state="error", message=_music_text(str(error)) or "Audio preparation failed")
            return
        if signature is not None:
            key = (track_id, seconds)
            self.prepared.pop(key, None)
            self.prepared[key] = (value, signature, _music_file_stamp(value[0]))
            while len(self.prepared) > 4:
                del self.prepared[next(iter(self.prepared))]
        if purpose == "prefetch":
            return
        path, details, cached = value
        try:
            audio = wave.open(str(path), "rb")
            if audio.getsampwidth() != 2 or audio.getnchannels() not in (1, 2) or audio.getcomptype() != "NONE":
                audio.close()
                raise ValueError("Music playback needs 16-bit PCM WAV audio.")
            self.audio = audio
            self.data["duration"] = audio.getnframes() / audio.getframerate()
            if self.player is None:
                self.player = self.player_factory(self.events)
            self.player.command("set_property", "volume", self.data["volume"])
            self.player.command("set_property", "pause", self.want_pause)
            self.loaded_path = str(path)
            self.player.command("loadfile", self.loaded_path, "replace")
            self.data["message"] = "Starting audio"
        except (OSError, ValueError, wave.Error) as failure:
            self.data.update(state="error", message=_music_text(str(failure)))

    def _next(self, natural=False):
        count, current = len(self.data["queue"]), self.data["index"]
        if not count:
            return
        if natural and self.data["repeat"] == "one":
            self._start(current, remember=False)
            return
        if self.data["shuffle"]:
            if not self.remaining and (not natural or self.data["repeat"] == "all"):
                self.remaining = [i for i in range(count) if i != current]
                random.shuffle(self.remaining)
                if not self.remaining and self.data["repeat"] == "all":
                    self.remaining = [current]
            target = self.remaining.pop() if self.remaining else None
        else:
            target = current + 1
            if target >= count:
                target = 0 if self.data["repeat"] == "all" else None
        if target is None:
            self._cancel_work()
            self.data.update(state="stopped", message="Queue finished")
        else:
            self._start(target)
        _music_save(self.root, self.data, self.seconds)

    def _process_event(self, event):
        kind = event.get("event")
        if kind == "transport-closed":
            if not self.ending:
                self.data.update(state="error", message="Audio player exited. Choose a track to retry.", levels=[])
                if self.player:
                    self.player.close()
                    self.player = None
            return
        if kind == "start-file" and self.loaded_path:
            self.awaiting_start = False
            self.entry_id = event.get("playlist_entry_id")
            return
        if kind == "end-file":
            if self.entry_id is not None and event.get("playlist_entry_id") != self.entry_id:
                return
            if event.get("reason") == "eof" and self.loaded_path and not self.awaiting_start and self.data["state"] in ("playing", "paused"):
                self._next(natural=True)
            elif event.get("reason") == "error" and self.loaded_path:
                self.data.update(state="error", message="mpv could not play the rendered audio.", levels=[])
            return
        if kind != "property-change" or not self.loaded_path or self.awaiting_start:
            return
        name, value = event.get("name"), event.get("data")
        if name in ("audio-pts", "time-pos") and isinstance(value, (int, float)) and math.isfinite(value):
            now = time.monotonic()
            if name == "audio-pts":
                self.audio_clock_at = now
            elif self.audio_clock_at is not None and now - self.audio_clock_at < 0.5:
                return
            self.clock_at = now
            self.data.update(position=max(0.0, min(float(value), self.data["duration"])),
                             clock_source="mpv:" + name, state="paused" if self.want_pause else "playing",
                             message="Paused" if self.want_pause else "Playing")
        elif name == "duration" and isinstance(value, (int, float)) and math.isfinite(value):
            self.data["duration"] = max(0.0, float(value))
        elif name == "pause" and isinstance(value, bool):
            self.want_pause = value
            if self.data["state"] in ("playing", "paused"):
                self.data.update(state="paused" if value else "playing", message="Paused" if value else "Playing")

    def tick(self):
        self._finish_render()
        while True:
            try:
                self._process_event(self.events.get_nowait())
            except queue.Empty:
                break
            except (OSError, ValueError, TypeError) as error:
                self.data.update(state="error", message=_music_text(str(error)), levels=[])
        self._begin_render()
        if (self.worker is None and self.pending is None and self.data["state"] == "playing"
                and self.data["queue"]):
            current, count = self.data["index"], len(self.data["queue"])
            if self.data["repeat"] == "one":
                target = current
            elif self.data["shuffle"]:
                target = self.remaining[-1] if self.remaining else None
            else:
                target = current + 1 if current + 1 < count else (0 if self.data["repeat"] == "all" else None)
            if target is not None:
                track = self.data["queue"][target]
                key = (self.generation, track["id"], self.seconds)
                if self.prefetch_for != key and (track["id"], self.seconds) not in self.prepared:
                    self.prefetch_for = key
                    self.pending = (self.generation, dict(track), self.seconds, "prefetch")
                    self._begin_render()

    def snapshot(self):
        now = time.monotonic()
        self.data["clock_age"] = None if self.clock_at is None else max(0.0, now - self.clock_at)
        if self.data["state"] == "preparing" and self.started_at is not None:
            self.data["message"] = ("Starting audio" if self.loaded_path else "Preparing audio") + " · " + str(int(now - self.started_at)) + "s"
        if self.data["state"] == "playing" and self.clock_at is not None and now - self.clock_at > 2:
            self.data["message"] = "Waiting for audio clock"
            self.data["levels"] = []
        elif self.audio and self.data["state"] == "playing" and now - self.last_levels >= 0.08:
            try:
                self.data["levels"] = _music_levels(self.audio, self.data["position"])
                self.last_levels = now
            except (OSError, ValueError, wave.Error):
                self.data["levels"] = []
        elif self.data["state"] != "playing":
            self.data["levels"] = []
        # Serialize to copy nested queue objects before the next mutation.
        return json.loads(json.dumps(self.data))

    def handle(self, request):
        action = request.get("action")
        if action == "status":
            return self.snapshot()
        if action == "play":
            tracks = self._resolve(request.get("ids"))
            _music_encode({"queue": tracks, "reserved": " " * 4096})
            index = request.get("index", 0)
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(tracks):
                raise ValueError("Invalid queue index.")
            seconds = _music_number(request.get("seconds", 180), 1, 3600, "Render duration")
            self.data["queue"], self.seconds = tracks, seconds
            self.data["index"] = -1
            self.history = []
            self.remaining = list(range(len(tracks)))
            random.shuffle(self.remaining)
            self._start(index)
        elif action == "enqueue":
            tracks = self._resolve(request.get("ids"))
            old = len(self.data["queue"])
            if old + len(tracks) > MUSIC_QUEUE_LIMIT:
                raise ValueError("The queue can hold at most 10,000 tracks.")
            _music_encode({"queue": self.data["queue"] + tracks, "reserved": " " * 4096})
            self.data["queue"].extend(tracks)
            self.remaining.extend(range(old, old + len(tracks)))
            random.shuffle(self.remaining)
        elif action in ("pause", "resume", "toggle"):
            if self.data["state"] not in ("playing", "paused", "preparing"):
                raise ValueError("Choose a track to play first.")
            self.want_pause = not self.want_pause if action == "toggle" else action == "pause"
            if self.player and self.loaded_path:
                self.player.command("set_property", "pause", self.want_pause)
            if self.data["state"] != "preparing":
                self.data.update(state="paused" if self.want_pause else "playing", message="Paused" if self.want_pause else "Playing")
        elif action == "next":
            self._next()
        elif action == "previous":
            target = self.history.pop() if self.history else max(0, self.data["index"] - 1)
            self._start(target, remember=False)
        elif action == "seek":
            offset = _music_number(request.get("seconds"), -3600, 3600, "Seek offset")
            if not self.player or not self.loaded_path or self.data["state"] not in ("playing", "paused"):
                raise ValueError("Audio must be ready before seeking.")
            target = max(0.0, min(self.data["duration"], self.data["position"] + offset))
            self.player.command("seek", target, "absolute+exact")
            self.data.update(levels=[], message="Seeking")
            self.audio_clock_at = None
            self.clock_at = None
        elif action == "volume":
            value = _music_number(request.get("value"), 0, 100, "Volume")
            if self.player:
                self.player.command("set_property", "volume", value)
            self.data["volume"] = value
        elif action == "repeat":
            value = request.get("value")
            if value not in ("off", "all", "one"):
                raise ValueError("Repeat must be off, all, or one.")
            self.data["repeat"] = value
        elif action == "shuffle":
            value = request.get("value")
            if not isinstance(value, bool):
                raise ValueError("Shuffle must be true or false.")
            self.data["shuffle"] = value
            self.remaining = [i for i in range(len(self.data["queue"])) if i != self.data["index"]]
            random.shuffle(self.remaining)
        elif action == "remove":
            index = request.get("index")
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(self.data["queue"]):
                raise ValueError("Invalid queue index.")
            current = self.data["index"]
            previous_state = self.data["state"]
            preserve_pause = previous_state == "paused" or (previous_state == "preparing" and self.want_pause)
            self.data["queue"].pop(index)
            self.history = [i - (i > index) for i in self.history if i != index]
            self.remaining = [i - (i > index) for i in self.remaining if i != index]
            if index == current:
                if self.data["queue"]:
                    replacement = min(index, len(self.data["queue"]) - 1)
                    if previous_state in ("playing", "paused", "preparing"):
                        self._start(replacement, remember=False, paused=preserve_pause)
                    else:
                        self._cancel_work()
                        self.data.update(index=replacement, track=self.data["queue"][replacement],
                                         state="stopped", message="Stopped")
                else:
                    self._cancel_work()
                    self.data.update(index=-1, track=None, state="stopped", message="Queue empty")
            elif index < current:
                self.data["index"] -= 1
        elif action in ("clear_queue", "stop"):
            self._cancel_work()
            self.data.update(state="stopped", message="Stopped")
            if action == "clear_queue":
                self.data.update(queue=[], index=-1, track=None)
            self.history, self.remaining = [], []
            if action == "stop":
                self.ending = True
        else:
            raise ValueError("Unknown music action.")
        _music_save(self.root, self.data, self.seconds)
        return self.snapshot()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.ending = True
        if self.cancel:
            self.cancel.set()
        if self.worker:
            self.worker.join(timeout=4)
        if self.audio:
            self.audio.close()
        if self.player:
            self.player.close()


def music_session_serve(home=None):
    root = _music_root(home)
    os.umask(0o077)
    path = _music_session_path(root, True)
    # The existing music lock also guards clear/init/forget and simultaneous starts.
    try:
        with _music_lock(root):
            if path.exists():
                path.unlink()  # Safe owner-only socket; the lifetime lock proves no live owner.
            session = _MusicSession(root)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(path))
                os.chmod(path, 0o600)
                server.listen(8)
                server.settimeout(0.05)
                def finish(signum, frame):
                    session.ending = True
                previous = {signum: signal.signal(signum, finish) for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
                try:
                    while not session.ending:
                        session.tick()
                        try:
                            client, _ = server.accept()
                        except socket.timeout:
                            continue
                        with client:
                            client.settimeout(0.5)
                            try:
                                request = _music_json_line(client)
                                result = {"ok": True, "data": session.handle(request)}
                                if session.ending:
                                    session.close()
                                    with contextlib.suppress(FileNotFoundError):
                                        path.unlink()
                            except (OSError, ValueError, TypeError, KeyError) as error:
                                result = {"ok": False, "error": _music_text(str(error))}
                            try:
                                encoded = _music_encode(result)
                            except (ValueError, TypeError):
                                encoded = _music_encode({"ok": False, "error": "Music response exceeds the protocol limit."})
                            with contextlib.suppress(OSError):
                                client.sendall(encoded)
                finally:
                    session.close()
                    with contextlib.suppress(FileNotFoundError):
                        path.unlink()
                    for signum, handler in previous.items():
                        signal.signal(signum, handler)
    except ValueError as error:
        if "Music is running" not in str(error):
            raise
        # Another launch won the same per-home lifetime lock.
    return 0
