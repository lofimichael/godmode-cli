#!/usr/bin/env python3
"""Build the optional Music Pack's isolated readable Python engine and assets."""
import argparse
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def runtime_bundle():
    manifest = json.loads((ROOT / "music_assets/manifest.json").read_text())
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for relative, info in sorted(manifest["files"].items()):
            member = Path(relative)
            source = ROOT / "music_assets/runtime" / member
            if member.is_absolute() or ".." in member.parts or source.is_symlink():
                raise ValueError("Unsafe music asset path: " + relative)
            data = source.read_bytes()
            if len(data) != info["size"] or hashlib.sha256(data).hexdigest() != info["sha256"]:
                raise ValueError("Music asset differs from its manifest: " + relative)
            entry = zipfile.ZipInfo(relative, (1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100600 << 16
            zipped.writestr(entry, data)
    return manifest, base64.b64encode(archive.getvalue()).decode("ascii")


ENTRY = '''
def music_pack_main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    home = None
    while argv:
        if argv[0] == "--home":
            if len(argv) < 2:
                raise ValueError("--home needs a folder.")
            home = argv[1]
            argv = argv[2:]
        elif argv[0].startswith("--home="):
            home = argv.pop(0).split("=", 1)[1]
        elif argv[0] in ("--plain", "--no-motion"):
            os.environ["GODMODE_PLAIN" if argv.pop(0) == "--plain" else "GODMODE_NO_MOTION"] = "1"
        else:
            break
    if home is not None:
        os.environ["GODMODE_HOME"] = os.path.abspath(os.path.expanduser(home))
    if argv and argv[0] in ("--version", "version"):
        print("godmode-music " + MUSIC_PACK_VERSION)
        return 0
    if argv and argv[0] in ("--help", "-h", "help"):
        print("GODMODEBEATZ Music Pack")
        print("music setup --songs DIR    Build the owned offline music engine")
        print("music [COMMAND]           Browse, play, queue, or control local tracks")
        print("jingle play [NAME]         Play a short local cue")
        print("jingle list                List available cues")
        print("--home DIR --plain --no-motion")
        return 0
    if argv and argv[0] == "jingle":
        if "jingle_main" not in globals():
            raise ValueError("Jingle support is not included in this Music Pack build.")
        return jingle_main(argv[1:], home=home)
    if argv and argv[0] == "music":
        argv = argv[1:]
    return music_main(argv, home=home, terminal=(_Keyboard, _draw, Cancelled))


if __name__ == "__main__":
    try:
        raise SystemExit(music_pack_main())
    except KeyboardInterrupt:
        print("\\nMusic command cancelled.", file=sys.stderr)
        raise SystemExit(130)
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print("Music: " + _music_text(str(error)), file=sys.stderr)
        raise SystemExit(1)
'''


def build_script():
    version = (ROOT / "VERSION").read_text().strip()
    sections = ["#!/usr/bin/env python3\n# Optional Godmode Music Pack; no credential or business modules.\n"
                "import sys\nif sys.version_info < (3, 9):\n    sys.exit('Music Pack needs Python 3.9 or newer.')\n"
                "MUSIC_PACK_VERSION = " + repr(version) + "\n"]
    names = ["godmode_terminal.py", "godmode_music.py", "godmode_music_player.py", "godmode_music_runtime.py"]
    if (ROOT / "lib/godmode_jingle.py").is_file():
        names.append("godmode_jingle.py")
    manifest, bundle = runtime_bundle()
    for name in names:
        module = "\n".join(line for line in (ROOT / "lib" / name).read_text().splitlines()
                           if not line.lstrip().startswith("from godmode_")) + "\n"
        if name == "godmode_music_runtime.py":
            module = module.replace("MUSIC_RUNTIME_MANIFEST = None  # The optional builder inserts the verified manifest.",
                                    "MUSIC_RUNTIME_MANIFEST = " + repr(manifest))
            module = module.replace("MUSIC_RUNTIME_BUNDLE = None  # The optional builder inserts compressed runtime sources/assets.",
                                    "MUSIC_RUNTIME_BUNDLE = " + repr(bundle))
        sections.append("\n# --- " + name + " ---\n" + module)
    sections.append(ENTRY)
    source = "\n".join(sections)
    ast.parse(source)
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "internal/musiccore/player.py")
    parser.add_argument("--verify", type=Path, metavar="SCRIPT", help="compare with a rebuild; write nothing")
    args = parser.parse_args()
    source = build_script().encode()
    if args.verify:
        if args.verify.read_bytes() != source:
            parser.exit(1, "Music Pack source differs from a rebuild. No files changed.\n")
        print("Music Pack source matches: SHA-256 " + hashlib.sha256(source).hexdigest())
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(source)
    args.output.chmod(0o755)
    print(str(args.output))


if __name__ == "__main__":
    main()
