"""Optional, offline music runtime setup; independent of key/business state.

Readable source lives in music_assets/runtime. Music-enabled builds embed the
same verified files. Decoding/extraction occurs only for explicit setup.
"""
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile

from godmode_music import _music_root, _music_directory, _music_bytes, _music_lock, _music_atomic, _music_env, _music_run, _music_sha, _music_songs, _music_end

MUSIC_RUNTIME_MANIFEST = None  # The optional builder inserts the verified manifest.
MUSIC_RUNTIME_BUNDLE = None  # The optional builder inserts compressed runtime sources/assets.
MUSIC_RUNTIME_FILE_LIMIT = 8 * 1024 * 1024
MUSIC_RUNTIME_TOTAL_LIMIT = 32 * 1024 * 1024


def _music_runtime_manifest():
    if MUSIC_RUNTIME_MANIFEST is None:
        base = Path(__file__).resolve().parents[1] / "music_assets"
        manifest = json.loads((base / "manifest.json").read_bytes())
    else:
        manifest = MUSIC_RUNTIME_MANIFEST
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(manifest, dict) or manifest.get("version") != 1 or not isinstance(files, dict) or not 1 <= len(files) <= 1000:
        raise ValueError("Invalid bundled music manifest.")
    total = 0
    for name, info in files.items():
        path = PurePosixPath(name)
        if (not isinstance(name, str) or not name or path.is_absolute() or ".." in path.parts
                or str(path) != name or "\\" in name or not isinstance(info, dict)):
            raise ValueError("Unsafe path in bundled music manifest.")
        size, digest = info.get("size"), info.get("sha256")
        if (isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= MUSIC_RUNTIME_FILE_LIMIT
                or not isinstance(digest, str) or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)):
            raise ValueError("Invalid bundled music file metadata.")
        total += size
    if total > MUSIC_RUNTIME_TOTAL_LIMIT:
        raise ValueError("Bundled music runtime is too large.")
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return manifest, hashlib.sha256(encoded).hexdigest()


def _music_runtime_files(manifest):
    expected = manifest["files"]
    if MUSIC_RUNTIME_BUNDLE is None:
        base = Path(__file__).resolve().parents[1] / "music_assets/runtime"
        for name, info in expected.items():
            path = base / name
            _music_directory(path.parent)
            data = _music_bytes(path, MUSIC_RUNTIME_FILE_LIMIT)
            if len(data) != info["size"] or hashlib.sha256(data).hexdigest() != info["sha256"]:
                raise ValueError("Bundled music source checksum failed: " + name)
            yield name, data
        return
    if len(MUSIC_RUNTIME_BUNDLE) > MUSIC_RUNTIME_TOTAL_LIMIT * 2:
        raise ValueError("Bundled music archive is too large.")
    archive = base64.b64decode(MUSIC_RUNTIME_BUNDLE, validate=True)
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        entries = zipped.infolist()
        if len(entries) != len(expected) or len({entry.filename for entry in entries}) != len(entries):
            raise ValueError("Bundled music archive has duplicate or unexpected files.")
        for entry in entries:
            info = expected.get(entry.filename)
            mode = entry.external_attr >> 16
            if (info is None or entry.is_dir() or stat.S_ISLNK(mode)
                    or entry.file_size != info["size"] or entry.file_size > MUSIC_RUNTIME_FILE_LIMIT):
                raise ValueError("Unsafe bundled music archive entry.")
            data = zipped.read(entry)
            if len(data) != info["size"] or hashlib.sha256(data).hexdigest() != info["sha256"]:
                raise ValueError("Bundled music archive checksum failed.")
            yield entry.filename, data


def _music_runtime_output(root, name, data, executable=False):
    path = root / name
    _music_directory(path.parent, True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o700 if executable else 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
    return path


def music_runtime_validate(runtime, manifest_hash=None):
    """Verify the owned source/assets and compiled executables before reuse."""
    runtime = Path(runtime)
    _music_directory(runtime)
    manifest, expected_hash = _music_runtime_manifest()
    if manifest_hash is not None and manifest_hash != expected_hash:
        raise ValueError("Music engine version changed. Run godmode music setup --songs TRACK_FOLDER.")
    receipt = json.loads(_music_bytes(runtime / "runtime.json", 1024 * 1024))
    if (not isinstance(receipt, dict) or receipt.get("version") != 1
            or receipt.get("manifest_sha256") != expected_hash
            or receipt.get("platform") != sys.platform or receipt.get("machine") != platform.machine()):
        raise ValueError("Music runtime needs setup for this version and machine.")
    for name, info in manifest["files"].items():
        path = runtime / name
        _music_directory(path.parent)
        data = _music_bytes(path, MUSIC_RUNTIME_FILE_LIMIT)
        if len(data) != info["size"] or hashlib.sha256(data).hexdigest() != info["sha256"]:
            raise ValueError("Owned music runtime changed. Run godmode music setup --songs TRACK_FOLDER.")
    outputs = receipt.get("outputs")
    required = {"tools/render_synth", "tools/seq64/build/seq64_console", "tools/seq64/abi/4 - Zelda.xml"}
    if not isinstance(outputs, dict) or set(outputs) != required:
        raise ValueError("Invalid music runtime build receipt.")
    for name, digest in outputs.items():
        path = runtime / name
        _music_directory(path.parent)
        data = _music_bytes(path, 32 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("Owned music executable changed. Run godmode music setup --songs TRACK_FOLDER.")
        if name != "tools/seq64/abi/4 - Zelda.xml" and not os.access(path, os.X_OK):
            raise ValueError("Owned music executable is not executable. Run music setup again.")
    return receipt


def _music_setup_run(command, label, started):
    print(label + " · " + str(round(time.monotonic() - started, 1)) + "s elapsed", flush=True)
    last = [time.monotonic()]
    def progress(elapsed):
        if time.monotonic() - last[0] >= 3:
            print(label + " · " + str(round(time.monotonic() - started, 1)) + "s elapsed", flush=True)
            last[0] = time.monotonic()
    try:
        return _music_run(command, frame=progress, timeout=300)
    except ValueError:
        raise ValueError(label + " failed. Existing music setup was preserved.") from None


def _music_setup_probe(stage, started):
    with tempfile.TemporaryDirectory(prefix=".probe-", dir=stage) as folder:
        folder = Path(folder)
        midi = folder / "input.mid"
        events = bytes.fromhex("00c00000903c5060803c0000ff2f00")
        midi.write_bytes(b"MThd" + struct.pack(">IHHH", 6, 0, 1, 96) + b"MTrk" + struct.pack(">I", len(events)) + events)
        converter = stage / "tools/seq64/build/seq64_console"
        sequence, converted = folder / "test.seq", folder / "converted.mid"
        _music_setup_run([str(converter), "abi=4 - Zelda", "in=" + str(midi), "out=" + str(sequence)], "Checking converter", started)
        _music_setup_run([str(converter), "abi=4 - Zelda", "in=" + str(sequence), "out=" + str(converted)], "Checking sequence output", started)
        if not converted.read_bytes().startswith(b"MThd"):
            raise ValueError("Music converter probe did not produce MIDI.")
        mapping = folder / "mapping.tsv"
        mapping.write_text("")
        pcm, log = folder / "probe.s16", folder / "probe.log"
        with pcm.open("wb") as output, log.open("wb") as errors:
            child = subprocess.Popen([str(stage / "tools/render_synth"), "-", str(stage / "tools/florestan-subset.sf2"),
                                      str(midi), "0.1", str(mapping)], stdin=subprocess.DEVNULL,
                                     stdout=output, stderr=errors, env=_music_env(), start_new_session=True)
            try:
                child.wait(timeout=10)
                if child.returncode:
                    raise ValueError("Music renderer probe failed.")
            finally:
                _music_end(child)
        data = pcm.read_bytes()
        if len(data) != 4410 * 4 or not any(data):
            raise ValueError("Music renderer probe did not produce the expected audio.")


def music_setup(home=None, songs=None):
    if songs is None:
        raise ValueError("Music setup needs --songs TRACK_FOLDER.")
    started = time.monotonic()
    root = _music_root(home)
    songs = Path(os.path.abspath(os.path.expanduser(str(songs))))
    _music_directory(songs)
    if not songs.is_dir():
        raise ValueError("The song folder does not exist.")
    count = len(_music_songs(songs))
    if sys.platform not in ("darwin", "linux"):
        raise ValueError("Owned music setup supports macOS and Linux.")
    tools = {name: shutil.which(name) for name in ("cc", "c++", "cmake", "ffmpeg")}
    missing = [name for name, path in tools.items() if not path]
    if missing:
        raise ValueError("Music setup needs installed tools: " + ", ".join(missing) + ". No files changed.")
    manifest, digest = _music_runtime_manifest()
    # Validate the complete in-memory payload before creating or compiling files.
    print("Checking bundled music files", flush=True)
    payload = list(_music_runtime_files(manifest))
    runtime_base = root / "runtime"
    runtime_name = digest[:20] + "-" + sys.platform + "-" + platform.machine()
    runtime = runtime_base / runtime_name
    reused = False
    with _music_lock(root):
        _music_directory(runtime_base, True)
        candidates = [runtime]
        with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
            current = json.loads(_music_bytes(root / "config.json"))
            owned = Path(current["backend"])
            if current.get("runtime") == "owned" and owned.parent == runtime_base:
                candidates.insert(0, owned)
        for candidate in candidates:
            try:
                music_runtime_validate(candidate, digest)
                runtime, reused = candidate, True
                break
            except (OSError, ValueError, TypeError):
                continue
        if not reused:
            with tempfile.TemporaryDirectory(prefix=".setup-", dir=runtime_base) as temporary:
                stage = Path(temporary) / "engine"
                _music_directory(stage, True)
                for name, data in payload:
                    _music_runtime_output(stage, name, data)
                build = stage / ".build"
                _music_setup_run([tools["cmake"], "-S", str(stage), "-B", str(build),
                                  "-DCMAKE_CXX_COMPILER=" + tools["c++"]], "Configuring converter", started)
                _music_setup_run([tools["cmake"], "--build", str(build), "--parallel", str(min(4, os.cpu_count() or 1))],
                                 "Building converter", started)
                _music_runtime_output(stage, "tools/seq64/build/seq64_console",
                                      _music_bytes(build / "seq64_console", 32 * 1024 * 1024), executable=True)
                _music_runtime_output(stage, "tools/seq64/abi/4 - Zelda.xml",
                                      _music_bytes(stage / "vendor/seq64/abi/4 - Zelda.xml", 1024 * 1024))
                _music_setup_run([tools["cc"], "-O2", "-I", str(stage), str(stage / "experiments/render_synth.c"),
                                  "-o", str(stage / "tools/render_synth"), "-lm"], "Building renderer", started)
                (stage / "tools/render_synth").chmod(0o700)
                _music_setup_probe(stage, started)
                shutil.rmtree(build)
                outputs = {name: _music_sha(stage / name) for name in (
                    "tools/render_synth", "tools/seq64/build/seq64_console", "tools/seq64/abi/4 - Zelda.xml")}
                receipt = {"version": 1, "manifest_sha256": digest, "platform": sys.platform,
                           "machine": platform.machine(), "outputs": outputs,
                           "setup_seconds": round(time.monotonic() - started, 3)}
                _music_runtime_output(stage, "runtime.json", (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode())
                music_runtime_validate(stage, digest)
                if os.path.lexists(runtime):
                    runtime = runtime_base / (runtime_name + "-" + uuid.uuid4().hex[:8])
                os.replace(stage, runtime)
        config = {"version": 1, "backend": str(runtime), "songs": str(songs),
                  "sha256": manifest["files"]["synthesize.py"]["sha256"],
                  "runtime": "owned", "runtime_manifest": digest}
        _music_atomic(root / "config.json", (json.dumps(config, indent=2) + "\n").encode())
    elapsed = round(time.monotonic() - started, 3)
    runtime_bytes = sum(path.stat().st_size for path in runtime.rglob("*") if path.is_file())
    print(("Reused" if reused else "Built") + " Godmode music engine · " + str(count) + " local tracks · " + str(elapsed) + "s", flush=True)
    if not shutil.which("mpv"):
        print("Rendering is ready. Playback also needs mpv.")
    return {"runtime": str(runtime), "reused": reused, "seconds": elapsed,
            "runtime_bytes": runtime_bytes, "tracks": count, "manifest_sha256": digest}
