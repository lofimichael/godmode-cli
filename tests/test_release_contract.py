"""Exercise release identity and removal guarantees across source and native CLI.

These checks reuse the candidates built by scripts/check.py. All command execution
uses a disposable home and an allowlisted environment; no installed account is read.
"""
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(os.environ.get("GODMODE_TEST_NATIVE_BINARY", ROOT / "target/godmode-native"))
REMOVED_COMMANDS = (("music",), ("music", "install"), ("music", "remove"),
                    ("music", "play"), ("music", "stop"), ("jingle", "play"),
                    ("picard", "play"), ("picard", "stop"))


class ReleaseFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="godmode-release-contract-")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name).resolve()
        self.home = self.folder / ".godmode"
        self.env = {"HOME": str(self.folder), "GODMODE_HOME": str(self.home),
                    "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"),
                    "TERM": "dumb",
                    "PYTHONDONTWRITEBYTECODE": "1", "NO_COLOR": "1"}
        self.version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

    def command(self, executable, *arguments, env=None):
        return subprocess.run([str(part) for part in [*executable, *arguments]],
                              cwd=self.folder, env=self.env if env is None else env,
                              stdin=subprocess.DEVNULL, capture_output=True, timeout=15)

    def successful(self, executable, *arguments, env=None):
        result = self.command(executable, *arguments, env=env)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(result.stderr, b"")
        return result.stdout

    def malformed_state(self):
        self.home.mkdir(mode=0o700)
        for name in ("active.json", "profile.json", "license.json", ".env.godmode", "seal.key"):
            path = self.home / name
            path.write_bytes(b"synthetic-release-contract-unreadable-state\n")
            path.chmod(0o600)
        return self.snapshot()

    def snapshot(self):
        return {str(path.relative_to(self.home)): (path.read_bytes() if path.is_file() else None,
                                                   path.stat().st_mode, path.stat().st_ino,
                                                   path.stat().st_mtime_ns)
                for path in self.home.rglob("*")}

    def assert_removed_commands_preserve_legacy_state(self, executable):
        # Old optional content remains the user's data after upgrading. Removed
        # verbs must not run it, remove it, or treat it as a new installation.
        self.home.mkdir(mode=0o700, exist_ok=True)
        for name in ("packs/godmode-music/legacy.py", "state/music/config.json",
                     "state/picard/cached-media", "profile.json"):
            path = self.home / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n" if name == "profile.json" else "synthetic legacy data\n")
            path.chmod(0o600)
        before = self.snapshot()
        for arguments in REMOVED_COMMANDS:
            with self.subTest(arguments=arguments):
                result = self.command(executable, *arguments)
                self.assertEqual(result.returncode, 2, result.stderr.decode("utf-8", "replace"))
                self.assertIn(b"unknown command", result.stderr)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(self.snapshot(), before)


class SourceReleaseContract(ReleaseFixture):
    def test_declared_version_matches_every_source_entrypoint_and_nfo(self):
        self.assertRegex(self.version, r"^[0-9]+\.[0-9]+\.[0-9]+$")
        nfo = (ROOT / "READTHIS.NFO").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"^GODMODE ([^\r\n]+)$", nfo, re.MULTILINE), [self.version])
        for script in ("godmode.py", "internal/core/core.py"):
            with self.subTest(script=script):
                output = self.successful([sys.executable, "-S", ROOT / script], "--version")
                self.assertEqual(output, ("godmode " + self.version + "\n").encode())
        self.assertFalse(self.home.exists(), "Version inspection created installation state")

    def test_modular_and_embedded_sources_reject_removed_verbs_without_mutation(self):
        for script in ("godmode.py", "internal/core/core.py"):
            with self.subTest(script=script):
                self.assert_removed_commands_preserve_legacy_state([sys.executable, "-B", "-S", ROOT / script])

    def test_real_release_source_inventory_excludes_removed_media_payloads(self):
        spec = importlib.util.spec_from_file_location("release_contract_package", ROOT / "scripts/package-native.py")
        package = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(package)
        binaries = self.folder / "native"
        for target, (system, cpu) in package.TARGETS.items():
            binary = binaries / target / "godmode"
            binary.parent.mkdir(parents=True)
            header = bytearray(64)
            if system == "darwin":
                header[:4] = b"\xcf\xfa\xed\xfe"
                struct.pack_into("<I", header, 4, 0x0100000c if cpu == "arm64" else 0x01000007)
            else:
                header[:6] = b"\x7fELF\x02\x01"
                struct.pack_into("<H", header, 18, 183 if cpu == "arm64" else 62)
            binary.write_bytes(header)
        output = self.folder / "dist"
        argv = ["package-native.py", "--skip-build", "--binaries-dir", str(binaries),
                "--output-dir", str(output), "--epoch", "1234"]
        # Assembly uses this checkout's real source tree. Synthetic platform
        # headers keep this inventory check fast; real native execution is tested
        # separately. The commit gate has its own packaging regression coverage.
        with mock.patch.object(package, "verify_committed_source"), mock.patch.object(package, "verify_build_identity"), \
                mock.patch("sys.argv", argv), mock.patch("sys.stdout", io.StringIO()):
            package.main()
        archives = sorted(output.glob("*.tar.gz"))
        self.assertEqual(len(archives), 5)
        forbidden = ("music_assets/", "cmd/godmode-music/", "internal/musiccore/", "internal/musicui/",
                     "internal/musicpackui/", "lib/godmode_music", "lib/godmode_jingle", "lib/godmode_picard",
                     "scripts/build-music", "docs/music.md", "docs/picard.md", ".sf2", ".ootrs")
        for path in archives:
            with self.subTest(archive=path.name), tarfile.open(path) as archive:
                names = archive.getnames()
                self.assertFalse([name for name in names if any(part in name.lower() for part in forbidden)])
                self.assertNotIn("godmode-music", names)
                self.assertNotIn("godmode-music-pack", names)
                if path.name.endswith("-source.tar.gz"):
                    self.assertIn("internal/core/core.py", names)
                    self.assertEqual(archive.extractfile("internal/core/core.py").read(),
                                     (ROOT / "internal/core/core.py").read_bytes())


@unittest.skipUnless(BINARY.is_file(), "Build the native candidate first.")
class NativeReleaseContract(ReleaseFixture):
    def test_native_rejects_removed_verbs_without_mutating_legacy_state(self):
        self.assert_removed_commands_preserve_legacy_state([BINARY])

    def test_native_metadata_attests_to_exact_exported_engine_and_pinned_compiler(self):
        source = self.successful([BINARY], "source")
        self.assertEqual(source, (ROOT / "internal/core/core.py").read_bytes(),
                         "Native candidate embeds stale or different source")
        metadata = self.successful([BINARY], "build-info").decode().splitlines()
        pinned = re.search(r"^go (\S+)$", (ROOT / "go.mod").read_text(), re.MULTILINE).group(1)
        self.assertEqual(metadata[:3], ["Godmode " + self.version,
                                       "Core SHA-256 " + hashlib.sha256(source).hexdigest(),
                                       "Go " + pinned])
        self.assertEqual(self.successful([BINARY], "--version"),
                         ("godmode " + self.version + "\n").encode())
        self.assertFalse(self.home.exists())

    def test_exported_engine_runs_without_repository_imports_or_user_state_mutations(self):
        before = self.malformed_state()
        exported = self.folder / "exported-core.py"
        exported.write_bytes(self.successful([BINARY], "source"))
        # -I -S and the external cwd exclude repository imports and user site hooks.
        for arguments in (("--version",), ("help", "run"), ("help", "provider")):
            with self.subTest(arguments=arguments):
                native = self.successful([BINARY], *arguments)
                standalone = self.successful([sys.executable, "-I", "-S", exported], *arguments)
                self.assertEqual(native, standalone)
                self.assertNotIn(b"synthetic-release-contract-unreadable-state", native)
        self.assertEqual(self.snapshot(), before)

    def test_exported_engine_carries_its_provider_catalog_without_repository_files(self):
        exported = self.folder / "exported-core.py"
        exported.write_bytes(self.successful([BINARY], "source"))
        for arguments in (("provider",), ("provider", "github")):
            with self.subTest(arguments=arguments):
                native = self.successful([BINARY], *arguments)
                standalone = self.successful([sys.executable, "-I", "-S", exported], *arguments)
                self.assertEqual(native, standalone)
                self.assertIn(b"github", native.lower())
        self.assertFalse(self.home.exists())

    def test_native_inspection_works_without_python_or_config_access(self):
        before = self.malformed_state()
        without_python = dict(self.env, PATH="", GODMODE_ENV="missing", GODMODE_CONTEXT="missing")
        for argument in ("source", "build-info"):
            with self.subTest(argument=argument):
                self.assertTrue(self.successful([BINARY], argument, env=without_python))
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
