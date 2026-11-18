#!/usr/bin/env python3
"""Experimental OOTRS synthesis: OoT instruments, or whole-song piano fallback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

HERE = Path(__file__).resolve().parent
FILTER = "volume=10dB,alimiter=limit=0.85:level=0"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cache_key(inputs):
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()


def cached_receipt(folder, key):
    try:
        receipt = json.loads((folder / "render.json").read_text())
        wav = folder / "render.wav"
        if (receipt["cache_key"] == key and wav.stat().st_size == receipt["wav_bytes"]
                and sha256(wav) == receipt["wav_sha256"]):
            return receipt
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def default_cache():
    if os.environ.get("XDG_CACHE_HOME"):
        base = Path(os.environ["XDG_CACHE_HOME"])
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Caches"
    else:
        base = Path.home() / ".cache"
    return base / "darunias-cli/synthesis"


def find_abi(seq64):
    # Mirror SEQ64's search from its executable toward the filesystem root.
    for parent in Path(seq64).resolve().parents:
        directory = parent / "abi"
        if directory.exists():
            abi = directory / "4 - Zelda.xml"
            if not abi.is_file():
                raise ValueError("Missing 4 - Zelda.xml in SEQ64's ABI directory")
            return abi
    raise ValueError("Missing SEQ64 ABI directory; run experiments/setup-synthesis.sh")


def unpack_sequence(path, destination=None):
    with zipfile.ZipFile(path) as archive:
        # Read named members directly; never extract ZIP paths to the filesystem.
        seqs = [i for i in archive.infolist() if i.filename.lower().endswith(".seq")]
        metas = [i for i in archive.infolist() if i.filename.lower().endswith(".meta")]
        if len(seqs) != 1 or len(metas) != 1:
            raise ValueError("Expected exactly one .seq and one .meta in the OOTRS")
        if seqs[0].file_size > 1024 * 1024 or metas[0].file_size > 64 * 1024:
            raise ValueError("Sequence or metadata exceeds experimental input limit")
        sequence = archive.read(seqs[0])
        if not sequence:
            raise ValueError("Empty sequence")
        if destination is not None:
            destination.write_bytes(sequence)
        meta = archive.read(metas[0]).decode("utf-8-sig").splitlines()
        return {"title": meta[0] if meta else path.stem,
                "instrument_bank": meta[1] if len(meta) > 1 else None,
                "custom_bank_ignored": any(i.filename.lower().endswith(".zbank") for i in archive.infolist()),
                "custom_samples_ignored": any(i.filename.lower().endswith(".zsound") for i in archive.infolist())}


def instrument_plan(details, mapping, font_dir):
    """Choose a bank candidate; the renderer checks EVERY MIDI event before use."""
    plan = {"candidate": "piano", "bank": None, "soundfont": None,
            "soundfont_sha256": None, "programs": {}, "fallback_reason": None}
    if details["custom_bank_ignored"] or details["custom_samples_ignored"]:
        plan["fallback_reason"] = "Custom banks or samples are not supported"
        return plan
    try:
        bank = f'{int(details["instrument_bank"].strip(), 16):02X}'
    except (TypeError, ValueError, AttributeError):
        bank = None
    plan["bank"] = bank
    spec = mapping["banks"].get(bank)
    if spec is None:
        plan["fallback_reason"] = f"Unsupported OoT bank {details['instrument_bank']!r}"
        return plan
    font = font_dir / spec["file"]
    plan["soundfont"] = spec["file"]
    if not font.is_file():
        plan["fallback_reason"] = f"Missing OoT SoundFont: {spec['file']}"
        return plan
    plan["soundfont_sha256"] = sha256(font)
    if plan["soundfont_sha256"] != spec["sha256"]:
        plan["fallback_reason"] = f"OoT SoundFont checksum mismatch: {spec['file']}"
        return plan
    plan.update(candidate="oot", programs=spec["programs"])
    return plan


def main():
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ootrs", type=Path)
    parser.add_argument("--output", type=Path, help="Optional export; otherwise play/use the cached WAV")
    parser.add_argument("--soundfont", type=Path, default=HERE / "tools/florestan-subset.sf2",
                        help="Fallback piano SoundFont (OoT remains the automatic first choice)")
    parser.add_argument("--oot-soundfonts", type=Path, default=HERE / "tools/oot-soundfonts",
                        help="Directory of installed, checksum-verified OoT bank SoundFonts")
    parser.add_argument("--seq64", default=os.environ.get("SEQ64", str(HERE / "tools/seq64/build/seq64_console")))
    parser.add_argument("--renderer", default=str(HERE / "tools/render_synth"))
    parser.add_argument("--seconds", type=float, default=20)
    parser.add_argument("--play", action="store_true")
    parser.add_argument("--cache-dir", type=Path, default=default_cache())
    args = parser.parse_args()
    if not 0 < args.seconds <= 3600:
        parser.error("--seconds must be between 0 and 3600")
    if args.output and args.output.suffix.lower() != ".wav":
        parser.error("--output must be a .wav file")
    executables = {}
    for name, executable in (("seq64", args.seq64), ("renderer", args.renderer), ("ffmpeg", "ffmpeg")):
        found = shutil.which(executable)
        if not found:
            raise ValueError(f"Missing executable: {executable}; see docs/SYNTHESIS.md")
        executables[name] = str(Path(found).resolve())
    if not args.soundfont.is_file():
        raise ValueError("Fallback piano SoundFont is missing; see docs/SYNTHESIS.md")
    abi = find_abi(executables["seq64"])
    mapping_path = HERE / "oot-instruments.json"
    mapping = json.loads(mapping_path.read_text())
    plan = instrument_plan(unpack_sequence(args.ootrs), mapping, args.oot_soundfonts)
    inputs = {"source_sha256": sha256(args.ootrs), "piano_soundfont_sha256": sha256(args.soundfont),
              "instruments": plan, "mapping_sha256": sha256(mapping_path),
              "tools": {name: sha256(path) for name, path in executables.items()},
              "abi_sha256": sha256(abi), "adapter_sha256": sha256(__file__),
              "seconds": args.seconds, "sample_rate": 44100, "channels": 2,
              "filter": FILTER, "byteorder": sys.byteorder, "policy": "oot-or-whole-song-piano-v1"}
    key = cache_key(inputs)
    folder = args.cache_dir.expanduser().resolve() / key
    details = cached_receipt(folder, key)
    hit = details is not None
    output = args.output.expanduser().resolve() if args.output else folder / "render.wav"
    # Refuse unrelated output before any synthesis. An identical export is reusable.
    if args.output and output.exists() and (not hit or sha256(output) != details["wav_sha256"]):
        raise ValueError("Output already exists with different or unverified content; choose another filename")
    if not hit:
        details = render(args, executables, inputs, key, folder)
    cached_wav = folder / "render.wav"
    if args.output and not output.exists():
        output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation avoids replacing a user's file in a concurrent run.
        with output.open("xb") as target, cached_wav.open("rb") as source:
            shutil.copyfileobj(source, target)
    if args.output:
        output.with_suffix(".synthesis.json").write_text(json.dumps(details, indent=2) + "\n")
    elapsed = time.perf_counter() - started
    label = "OoT SoundFont approximation" if details["mode"] == "oot" else "piano fallback (whole song)"
    print(details["title"] + " — " + label)
    if details["fallback_reason"]:
        print("Reason: " + details["fallback_reason"])
    print(f"{'Cache hit' if hit else 'Rendered'}: {elapsed:.4f}s preparation; {output}", flush=True)
    if args.play:
        if sys.platform == "darwin" and shutil.which("afplay"):
            return subprocess.call(["afplay", "-t", str(args.seconds), str(output)])
        if shutil.which("ffplay"):
            return subprocess.call(["ffplay", "-nodisp", "-autoexit", "-t", str(args.seconds), "-i", str(output)])
        raise ValueError("WAV created, but afplay/ffplay is unavailable")
    return 0


def render(args, executables, inputs, key, folder):
    folder.parent.mkdir(parents=True, exist_ok=True)
    lock = folder.with_name(folder.name + ".lock")
    try:
        lock.mkdir()
    except FileExistsError:
        raise ValueError(f"This render is already running (or left a stale lock): {lock}")
    try:
        return render_locked(args, executables, inputs, key, folder)
    finally:
        lock.rmdir()


def render_locked(args, executables, inputs, key, folder):
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="darunias-synth-") as temp:
        work = Path(temp)
        seq, midi, pcm = work / "input.seq", work / "converted.mid", work / "render.s16"
        details = unpack_sequence(args.ootrs, seq)
        details.update({"seconds": args.seconds,
                        "source_sha256": inputs["source_sha256"],
                        "cache_key": key, "inputs": inputs, "timings_seconds": {},
                        "rom_required": False,
                        "instrument_source": "Community OoT bank SoundFont or supplied fallback piano SoundFont",
                        "limitations": "Preflight covers the full converted MIDI, not unexported sequence branches. No exact tuning, effects, drum-key, or loop fidelity guarantee."})
        then = time.perf_counter()
        convert = subprocess.run([executables["seq64"], "abi=4 - Zelda", f"in={seq}", f"out={midi}"],
                                 capture_output=True, text=True, timeout=60)
        details["timings_seconds"]["conversion"] = time.perf_counter() - then
        details["conversion_log"] = convert.stdout + convert.stderr
        if convert.returncode or not midi.is_file():
            raise ValueError("SEQ64 failed:\n" + details["conversion_log"])
        plan = inputs["instruments"]
        mapping_file = work / "mapping.tsv"
        mapping_file.write_text("".join(f"{program}\t{name}\n" for program, name in plan["programs"].items()))
        oot_font = str(args.oot_soundfonts / plan["soundfont"]) if plan["candidate"] == "oot" else "-"
        then = time.perf_counter()
        with pcm.open("wb") as target:
            render = subprocess.run([executables["renderer"], oot_font, str(args.soundfont),
                                     str(midi), str(args.seconds), str(mapping_file)],
                                    stdout=target, stderr=subprocess.PIPE, text=True, timeout=120)
        details["renderer_log"] = render.stderr
        details["timings_seconds"]["synthesis"] = time.perf_counter() - then
        if render.returncode:
            raise ValueError("Renderer failed: " + render.stderr)
        stats = [json.loads(line[6:]) for line in render.stderr.splitlines() if line.startswith("STATS ")]
        if len(stats) != 1:
            raise ValueError("Renderer did not report its instrument mode")
        details["render_stats"] = stats[0]
        details["mode"] = stats[0]["mode"]
        details["fallback_reason"] = plan["fallback_reason"] or stats[0]["fallback_reason"] or None
        if (details["mode"] not in ("oot", "piano")
                or (stats[0]["mapped_note_ons"] and stats[0]["fallback_note_ons"])):
            raise ValueError("Renderer violated whole-song instrument selection")
        # Fixed gain and a limiter keep both modes audible with a bounded peak.
        endian = "s16le" if sys.byteorder == "little" else "s16be"
        temporary_wav = folder / "render.tmp.wav"
        then = time.perf_counter()
        try:
            subprocess.run([executables["ffmpeg"], "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
                            "-f", endian, "-ar", "44100", "-ac", "2", "-i", str(pcm),
                            "-af", FILTER, str(temporary_wav)], check=True, timeout=120)
            details["timings_seconds"]["wav_output"] = time.perf_counter() - then
            details["wav_sha256"] = sha256(temporary_wav)
            details["wav_bytes"] = temporary_wav.stat().st_size
            temporary_wav.replace(folder / "render.wav")
            receipt = folder / "render.json.part"
            receipt.write_text(json.dumps(details, indent=2) + "\n")
            receipt.replace(folder / "render.json")
        finally:
            temporary_wav.unlink(missing_ok=True)
    return details


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as error:
        print(f"synthesize: {error}", file=sys.stderr)
        sys.exit(1)
