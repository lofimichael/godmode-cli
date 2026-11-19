#!/usr/bin/env python3
"""Advise when the checked-out CLI runtime differs from the release customers receive."""

import json
from pathlib import Path, PurePosixPath
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
LIVE_MANIFEST = "https://godmode.build/releases/latest.json"
VERSION = re.compile(r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")
RUNTIME_FILES = (
    "go.mod", "go.sum", "godmode.py", "install.sh", "providers.json",
    "scripts/build.py", "scripts/build-native.sh", "vendor/modules.txt",
)
RUNTIME_DIRS = ("cmd", "internal", "lib", "registry", "vendor")
RUNTIME_EXTENSIONS = {".c", ".go", ".h", ".json", ".py", ".s", ".syso", ".toml", ".yaml", ".yml"}
NON_RUNTIME_DIRS = {".github", "docs", "examples", "test", "testdata", "tests"}


def live_version():
    result = subprocess.run(
        ["curl", "--disable", "--fail", "--silent", "--max-time", "4",
         "--max-filesize", "16384", LIVE_MANIFEST],
        capture_output=True, check=True, timeout=5,
    )
    manifest = json.loads(result.stdout)
    version = manifest.get("version") if isinstance(manifest, dict) else None
    if not isinstance(version, str) or len(version) > 40 or not VERSION.fullmatch(version):
        raise ValueError("The live manifest does not name a stable version.")
    return version


def runtime_path(name):
    if name in RUNTIME_FILES:
        return True
    path = PurePosixPath(name)
    if NON_RUNTIME_DIRS.intersection(path.parts[1:-1]):
        return False
    if path.name.startswith("test_") or path.stem.endswith("_test"):
        return False
    return path.suffix.lower() in RUNTIME_EXTENSIONS


def changed_runtime_paths(repo, version):
    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, check=True, timeout=5,
        ).stdout

    baseline = f"refs/tags/{version}^{{commit}}"
    if git("show", f"{baseline}:VERSION").strip() != version[1:].encode():
        raise ValueError("The checked-out tag does not declare the live version.")
    git("merge-base", "--is-ancestor", baseline, "HEAD")
    delta = git("diff", "--no-ext-diff", "--name-only", "--no-renames", "-z", baseline, "HEAD",
                "--", *RUNTIME_FILES, *RUNTIME_DIRS)
    return [name for name in delta.decode("utf-8", "surrogateescape").split("\0")
            if name and runtime_path(name)]


def main(repo=ROOT):
    try:
        version = live_version()
    except (OSError, subprocess.SubprocessError, ValueError):
        print("::notice title=CLI release status::The live release manifest was unavailable or invalid.")
        return

    try:
        count = len(changed_runtime_paths(repo, version))
    except (OSError, subprocess.SubprocessError, ValueError):
        print(f"::notice title=CLI release status::Could not verify {version} as a release tag in this commit's history.")
        return

    if count:
        files = "file differs" if count == 1 else "files differ"
        print(f"::warning title=Unreleased CLI runtime::{count} runtime {files} from live {version}.")
    else:
        print(f"No runtime changes since live {version}.")


if __name__ == "__main__":
    main()
