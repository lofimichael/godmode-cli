"""Owned optional runtime: integrity, private staging, failure/cancel preservation."""
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import godmode_music as music
import godmode_music_runtime as runtime


class MusicRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gm-runtime-", dir="/tmp")
        self.folder = Path(self.temp.name).resolve()
        self.home = self.folder / "home"
        self.songs = self.folder / "songs"
        self.songs.mkdir()
        self.root = music._music_root(self.home)

    def tearDown(self):
        self.temp.cleanup()

    def tiny_manifest(self, name="synthesize.py", data=b"# fixture\n"):
        return {"version": 1, "files": {name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}}}

    def zipped(self, name="synthesize.py", data=b"# fixture\n", copies=1, mode=0o100600):
        target = io.BytesIO()
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for _ in range(copies):
                entry = zipfile.ZipInfo(name)
                entry.external_attr = mode << 16
                archive.writestr(entry, data)
        return base64.b64encode(target.getvalue()).decode()

    def test_selected_sources_and_only_four_required_fonts_match_manifest(self):
        manifest, digest = runtime._music_runtime_manifest()
        self.assertEqual(len(digest), 64)
        fonts = {name for name in manifest["files"] if name.endswith(".sf2")}
        self.assertEqual(fonts, {"tools/florestan-subset.sf2", "tools/oot-soundfonts/03 Main Orchestra.sf2",
                                "tools/oot-soundfonts/20 Battle 2.sf2", "tools/oot-soundfonts/22 Ending Orchestra 2.sf2"})
        self.assertIn("vendor/seq64/LICENSE.txt", manifest["files"])
        self.assertIn("vendor/juce/LICENSE.md", manifest["files"])
        self.assertFalse(any(name.endswith((".ootrs", ".zip")) or "/.git/" in name for name in manifest["files"]))
        self.assertNotIn("tools/seq64/build/seq64_console", manifest["files"])
        self.assertEqual(len(list(runtime._music_runtime_files(manifest))), len(manifest["files"]))

    def test_missing_tools_and_bad_song_path_do_not_write_state(self):
        with mock.patch.object(runtime.shutil, "which", return_value=None), self.assertRaisesRegex(ValueError, "No files changed"):
            runtime.music_setup(self.home, self.songs)
        self.assertFalse(self.home.exists())
        with self.assertRaisesRegex(ValueError, "does not exist"):
            runtime.music_setup(self.home, self.folder / "missing")
        self.assertFalse(self.home.exists())

    def test_embedded_payload_validates_hash_paths_duplicates_and_links(self):
        manifest = self.tiny_manifest()
        with mock.patch.object(runtime, "MUSIC_RUNTIME_BUNDLE", self.zipped()):
            self.assertEqual(list(runtime._music_runtime_files(manifest)), [("synthesize.py", b"# fixture\n")])
        for payload in (self.zipped(data=b"# changed\n"), self.zipped(name="../outside"),
                        self.zipped(mode=0o120777)):
            with mock.patch.object(runtime, "MUSIC_RUNTIME_BUNDLE", payload), self.assertRaises(ValueError):
                list(runtime._music_runtime_files(manifest))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            duplicate = self.zipped(copies=2)
        with mock.patch.object(runtime, "MUSIC_RUNTIME_BUNDLE", duplicate), self.assertRaisesRegex(ValueError, "duplicate"):
            list(runtime._music_runtime_files(manifest))
        with mock.patch.object(runtime, "MUSIC_RUNTIME_MANIFEST", self.tiny_manifest("../outside")), self.assertRaisesRegex(ValueError, "Unsafe path"):
            runtime._music_runtime_manifest()
        with mock.patch.object(runtime, "MUSIC_RUNTIME_MANIFEST", []), self.assertRaises(ValueError):
            runtime._music_runtime_manifest()

    def test_source_checksum_failure_happens_before_state_creation(self):
        with mock.patch.object(runtime, "_music_runtime_files", side_effect=ValueError("checksum failed")), \
                mock.patch.object(runtime.shutil, "which", return_value="/fixture"), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "checksum"):
            runtime.music_setup(self.home, self.songs)
        self.assertFalse(self.home.exists())

    def test_failed_or_cancelled_build_preserves_config_and_removes_only_stage(self):
        music._music_directory(self.root, True)
        config = self.root / "config.json"
        original = b'{"version":1,"existing":"preserve"}\n'
        config.write_bytes(original)
        config.chmod(0o600)
        other = self.root / "unrelated.txt"
        other.write_text("preserve")
        manifest = self.tiny_manifest()
        for failure in (ValueError("compiler failed"), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__), \
                    mock.patch.object(runtime, "_music_runtime_manifest", return_value=(manifest, "a" * 64)), \
                    mock.patch.object(runtime, "_music_runtime_files", return_value=iter([("synthesize.py", b"# fixture\n")])), \
                    mock.patch.object(runtime, "_music_setup_run", side_effect=failure), \
                    mock.patch.object(runtime.shutil, "which", return_value="/fixture"), \
                    contextlib.redirect_stdout(io.StringIO()), self.assertRaises(type(failure)):
                runtime.music_setup(self.home, self.songs)
            self.assertEqual(config.read_bytes(), original)
            self.assertEqual(other.read_text(), "preserve")
            self.assertFalse(list((self.root / "runtime").glob(".setup-*")))
            self.assertFalse(list((self.root / "runtime").iterdir()))

    def test_runtime_output_refuses_existing_files_and_symlink_parent(self):
        stage = self.folder / "stage"
        music._music_directory(stage, True)
        target = runtime._music_runtime_output(stage, "tools/a.txt", b"owned")
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            runtime._music_runtime_output(stage, "tools/a.txt", b"replace")
        (stage / "linked").symlink_to(self.songs)
        with self.assertRaises(ValueError):
            runtime._music_runtime_output(stage, "linked/outside", b"bad")
        self.assertEqual(list(self.songs.iterdir()), [])

    def test_actual_setup_interrupt_reaps_compiler_descendants_and_preserves_config(self):
        music._music_directory(self.root, True)
        config = self.root / "config.json"
        original = b'{"version":1,"existing":"keep"}\n'
        config.write_bytes(original)
        config.chmod(0o600)
        bindir = self.folder / "bin"
        bindir.mkdir()
        pidfile = self.folder / "compiler-child.pid"
        descendant = ("import os,pathlib,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                      "pathlib.Path(" + repr(str(pidfile)) + ").write_text(str(os.getpid()));time.sleep(30)")
        compiler = bindir / "cmake"
        compiler.write_text("#!" + sys.executable + "\nimport subprocess,sys,time\n"
                            "subprocess.Popen([sys.executable,'-c'," + repr(descendant) + "])\ntime.sleep(30)\n")
        compiler.chmod(0o700)
        ffmpeg = bindir / "ffmpeg"
        ffmpeg.write_text("#!/bin/sh\nexit 0\n")
        ffmpeg.chmod(0o700)
        code = ("import sys;sys.path.insert(0," + repr(str(ROOT / "lib")) + ");"
                "from godmode_music_runtime import music_setup\n"
                "try: music_setup(" + repr(str(self.home)) + "," + repr(str(self.songs)) + ")\n"
                "except KeyboardInterrupt: sys.exit(130)\n")
        env = {"PATH": str(bindir) + ":/usr/bin:/bin", "HOME": str(self.folder)}
        owner = subprocess.Popen([sys.executable, "-c", code], env=env, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
        unrelated = subprocess.Popen(["/bin/sleep", "30"])
        try:
            deadline = time.monotonic() + 5
            while not pidfile.exists() and time.monotonic() < deadline and owner.poll() is None:
                time.sleep(.03)
            self.assertTrue(pidfile.exists(), "compiler probe never started")
            os.kill(owner.pid, signal.SIGINT)
            self.assertEqual(owner.wait(timeout=5), 130)
            self.assertEqual(config.read_bytes(), original)
            self.assertFalse(list((self.root / "runtime").glob(".setup-*")))
            self.assertIsNone(unrelated.poll())
            pid = int(pidfile.read_text())
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(.02)
            else:
                self.fail("compiler descendant survived setup cancellation")
        finally:
            if owner.poll() is None:
                music._music_end(owner)
            unrelated.terminate()
            unrelated.wait()

    def test_without_music_build_omits_runtime_source_and_asset_literals(self):
        output = self.folder / "godmode-minimal"
        process = subprocess.run([sys.executable, str(ROOT / "scripts/build.py"), "--without-music", "--output", str(output)],
                                 capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        source = output.read_text()
        for marker in ("MUSIC_RUNTIME_BUNDLE", "def music_setup", "florestan-subset.sf2", "juce_data_structures"):
            self.assertNotIn(marker, source)

    def test_music_only_bundle_has_no_credentials_and_normal_commands_extract_nothing(self):
        output = self.folder / "music-pack.py"
        process = subprocess.run([sys.executable, str(ROOT / "scripts/build-music.py"), "--output", str(output)],
                                 capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        source = output.read_text()
        for marker in ("# --- godmode_store.py", "# --- godmode_profile.py", "class Store:", "PROVIDERS ="):
            self.assertNotIn(marker, source)
        self.assertIn("MUSIC_RUNTIME_BUNDLE", source)
        env = {"PATH": os.environ["PATH"], "HOME": str(self.folder), "GODMODE_HOME": str(self.home),
               "GODMODE_ENV": "broken-selection", "GODMODE_CONTEXT": "broken-business", "TERM": "dumb"}
        for arguments, data in ((["--version"], None), (["music"], None),
                                (["music", "__bridge"], '{"action":"status"}\n')):
            process = subprocess.run([sys.executable, str(output)] + arguments, cwd=self.folder, env=env,
                                     input=data, capture_output=True, text=True, timeout=10)
            self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["data"]["state"], "stopped")
        self.assertFalse(self.home.exists())

    def test_global_home_and_plain_flags_work_in_music_only_bundle(self):
        output = self.folder / "music-pack.py"
        process = subprocess.run([sys.executable, str(ROOT / "scripts/build-music.py"), "--output", str(output)],
                                 capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        process = subprocess.run([sys.executable, str(output), "--home", str(self.home), "--plain", "music", "status", "--json"],
                                 cwd=self.folder, capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["state"], "stopped")
        self.assertFalse(self.home.exists())


if __name__ == "__main__":
    unittest.main()
