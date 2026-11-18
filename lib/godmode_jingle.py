"""Original procedural cues for the optional music pack; no library or key access."""
import argparse
import contextlib
import json
import math
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import wave

from godmode_music import _music_env, _music_end

# Start, duration, and simultaneous frequencies. These are original short cues.
JINGLE_TONES = {
    "ready": ((0, .65, (392, 523.25, 587.33)),),
    "success": ((0, .25, (440, 554.37)), (.18, .68, (523.25, 659.25, 783.99))),
    "attention": ((0, .22, (440, 466.16)), (.33, .22, (440, 466.16))),
}
JINGLE_RATE = 24000


def _jingle_wave(path, name):
    tones = JINGLE_TONES[name]
    frames = round((max(start + duration for start, duration, _ in tones) + .1) * JINGLE_RATE)
    pcm = bytearray()
    for frame in range(frames):
        moment, value = frame / JINGLE_RATE, 0.0
        for start, duration, frequencies in tones:
            phase = moment - start
            if 0 < phase < duration:
                envelope = math.sin(math.pi * phase / duration) ** 2
                value += .35 * envelope * sum(math.sin(2 * math.pi * f * phase)
                                             for f in frequencies) / len(frequencies)
        pcm.extend(struct.pack("<h", round(value * 32767)))
    with wave.open(str(path), "wb") as audio:
        audio.setparams((1, 2, JINGLE_RATE, 0, "NONE", "not compressed"))
        audio.writeframes(pcm)
    return frames / JINGLE_RATE


@contextlib.contextmanager
def _jingle_interrupts():
    previous = {}
    def interrupt(signum, frame):
        raise KeyboardInterrupt()
    try:
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous[signum] = signal.signal(signum, interrupt)
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def _jingle_play(name, volume, popen=None, null_output=False):
    executable = shutil.which("mpv")
    if not executable:
        raise ValueError("Jingles need mpv. Install mpv, then run godmode jingle play.")
    with tempfile.TemporaryDirectory(prefix="godmode-jingle-") as directory:
        path = Path(directory) / "cue.wav"
        duration = _jingle_wave(path, name)
        command = [executable, "--no-config", "--load-scripts=no", "--terminal=no",
                   "--vid=no", "--audio-display=no", "--input-terminal=no",
                   "--input-media-keys=no", "--input-default-bindings=no",
                   "--audio-device=auto", "--volume=" + str(volume)]
        if null_output:  # Test construction only; no CLI option for player flags.
            command.append("--ao=null")
        command += ["--", str(path)]
        with _jingle_interrupts():
            child = (popen or subprocess.Popen)(command, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_music_env(),
                start_new_session=True, close_fds=True)
            try:
                if child.wait(timeout=duration + 3) != 0:
                    raise ValueError("Jingle playback failed. Check the default audio output and mpv.")
            except subprocess.TimeoutExpired:
                raise ValueError("Jingle playback timed out.") from None
            finally:
                if child.poll() is None:
                    _music_end(child)
    return {"state": "played", "name": name, "volume": volume, "duration": duration}


def jingle_main(argv, home=None):
    # home is accepted by the pack router; jingles never touch persistent state.
    parser = argparse.ArgumentParser(prog="godmode jingle", description="Play a short original sound cue.")
    parser.add_argument("action", choices=("play", "list"))
    parser.add_argument("name", nargs="?", choices=tuple(JINGLE_TONES))
    parser.add_argument("--volume", type=int, default=35, metavar="0..100")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not 0 <= args.volume <= 100:
        parser.error("volume must be between 0 and 100")
    if args.action == "list":
        if args.name:
            parser.error("list does not take a jingle name")
        print(json.dumps({"jingles": list(JINGLE_TONES)}) if args.json else "\n".join(JINGLE_TONES))
        return 0
    try:
        result = _jingle_play(args.name or "ready", args.volume)
    except KeyboardInterrupt:
        print("Jingle stopped.", file=sys.stderr)
        return 130
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result) if args.json else result["name"].capitalize() + " jingle played.")
    return 0
