"""Opt-in Music Pack lifecycle with isolated companion fixtures and no audio."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import godmode_music_pack as pack


class MusicPackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gm-pack-", dir="/tmp")
        self.folder = Path(self.temp.name).resolve()
        self.home = self.folder / "home"
        self.log = self.folder / "events.jsonl"
        self.source = self.fixture("companion-v1", "1.2.3")
        self.digest = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, name, version, protocol=1, stop_code=0):
        system, arch, _ = pack._pack_target()
        info = {"kind": "godmode-music-pack", "protocol": protocol, "platform": system, "arch": arch, "version": version}
        path = self.folder / name
        path.write_text("#!" + sys.executable + "\n" +
            "import json,os,pathlib,sys,time\n" +
            "args=sys.argv[1:]\n" +
            "home=pathlib.Path(os.environ.get('GODMODE_HOME','.'))\n" +
            "inherited=False\n" +
            "for fd in range(3,256):\n" +
            " try:\n" +
            "  actual=os.fstat(fd);expected=(home/'packs/.music.lock').stat()\n" +
            "  inherited=inherited or (actual.st_ino,actual.st_dev)==(expected.st_ino,expected.st_dev)\n" +
            " except OSError:pass\n" +
            "with pathlib.Path(" + repr(str(self.log)) + ").open('a') as log:\n" +
            " log.write(json.dumps({'args':args,'binary':str(pathlib.Path(sys.argv[0])),'env_keys':sorted(os.environ),'home':str(home),'cache_existed':(home/'state/music/cache').exists(),'lease_inherited':inherited})+'\\n')\n" +
            "if args==['__pack_info']:\n print(json.dumps(" + repr(info) + "));sys.exit(0)\n" +
            "if args[:1]==['--home']:args=args[2:]\n" +
            "if args==['music','stop']:sys.exit(" + str(stop_code) + ")\n" +
            "if args==['music','hold']:\n" +
            " pathlib.Path(" + repr(str(self.folder / "ready")) + ").touch()\n" +
            " while not pathlib.Path(" + repr(str(self.folder / "release")) + ").exists():time.sleep(.02)\n" +
            "print(json.dumps({'forwarded':args,'home':str(home)}))\n")
        path.chmod(0o700)
        return path

    def invoke(self, args, command="music"):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = pack.music_pack_main(args, self.home, command=command)
        return result, output.getvalue()

    def install(self, source=None, digest=None):
        source = source or self.source
        digest = digest or hashlib.sha256(source.read_bytes()).hexdigest()
        self.assertEqual(self.invoke(["install", "--file", str(source), "--sha256", digest])[0], 0)
        return self.home / "packs/music/godmode-music"

    def events(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def state(self, songs=None, config=True):
        state = self.home / "state/music"
        state.mkdir(parents=True, mode=0o700)
        if songs is None:
            songs = self.folder / "songs"
            songs.mkdir(exist_ok=True)
        if config:
            (state / "config.json").write_text(json.dumps({"version": 1, "songs": str(songs), "backend": "/unused"}))
        for name in ("cache", "runtime", "session"):
            (state / name).mkdir(mode=0o700)
            (state / name / "owned.txt").write_text(name)
        (state / "session.json").write_text('{"state":"stopped"}')
        (state / ".lock").touch(mode=0o600)
        return state, songs

    def test_absent_status_stop_help_and_remove_are_read_only(self):
        for args in ([], ["status"], ["status", "--json"], ["stop"], ["remove"]):
            with self.subTest(args=args):
                self.assertEqual(self.invoke(args)[0], 0)
                self.assertFalse(self.home.exists())
        with self.assertRaisesRegex(ValueError, "not installed"):
            self.invoke(["play"], command="jingle")
        self.assertFalse(self.home.exists())

    def test_absent_pack_can_be_inspected_under_read_only_existing_home(self):
        self.home.mkdir(mode=0o500)
        try:
            for args in ([], ["status", "--json"], ["stop"], ["remove"]):
                with self.subTest(args=args):
                    self.assertEqual(self.invoke(args)[0], 0)
                    self.assertEqual(list(self.home.iterdir()), [])
        finally:
            self.home.chmod(0o700)

    def test_install_probes_private_candidate_pins_bytes_and_filters_environment(self):
        with mock.patch.dict(os.environ, {"GH_TOKEN": "synthetic", "OPENAI_API_KEY": "synthetic",
                                         "GODMODE_ENV": "bad-selection", "GODMODE_CONTEXT": "bad-business",
                                         "PYTHONPATH": "/untrusted", "LD_PRELOAD": "/untrusted",
                                         "GODMODE_EXECUTABLE": "/untrusted"}):
            installed = self.install()
        self.assertEqual(installed.read_bytes(), self.source.read_bytes())
        self.assertEqual(installed.stat().st_mode & 0o777, 0o700)
        receipt = json.loads((installed.parent / "receipt.json").read_text())
        self.assertEqual(receipt["sha256"], self.digest)
        self.assertEqual((installed.parent / "receipt.json").stat().st_mode & 0o777, 0o600)
        probe = self.events()[0]
        self.assertEqual(probe["args"], ["__pack_info"])
        self.assertEqual(probe["home"], str(self.home))
        for key in ("GH_TOKEN", "OPENAI_API_KEY", "GODMODE_ENV", "GODMODE_CONTEXT", "PYTHONPATH", "LD_PRELOAD", "GODMODE_EXECUTABLE"):
            self.assertNotIn(key, probe["env_keys"])

    def test_hash_mismatch_or_incompatible_candidate_preserves_installed_pack(self):
        installed = self.install()
        before = {path.name: path.read_bytes() for path in installed.parent.iterdir()}
        bad = self.fixture("bad-companion", "2.0.0", protocol=999)
        for args in (["install", "--file", str(bad), "--sha256", "0" * 64],
                     ["install", "--file", str(bad), "--sha256", hashlib.sha256(bad.read_bytes()).hexdigest()]):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.invoke(args)
            self.assertEqual({path.name: path.read_bytes() for path in installed.parent.iterdir()}, before)
        self.assertFalse(list((self.home / "packs").glob(".music-install-*")))

    def test_failed_atomic_swap_restores_previous_pack_and_reinstall_source(self):
        installed = self.install()
        directory = installed.parent
        original_files = {path.name: path.read_bytes() for path in directory.iterdir()}
        source_file = self.home / "music-pack-source.json"
        original_source = source_file.read_bytes()
        candidate = self.fixture("companion-v2", "2.0.0")
        replace = pack.os.replace
        def fail_adoption(source, target):
            if Path(source).is_dir() and Path(source).name.startswith(".music-install-") and Path(target) == directory:
                raise OSError("simulated directory adoption failure")
            return replace(source, target)
        with mock.patch.object(pack.os, "replace", side_effect=fail_adoption), self.assertRaises(OSError):
            self.install(candidate)
        self.assertEqual({path.name: path.read_bytes() for path in directory.iterdir()}, original_files)
        self.assertEqual(source_file.read_bytes(), original_source)
        self.assertFalse(list(directory.parent.glob(".music-rollback-*")))

    def test_failed_source_record_write_rolls_back_adopted_pack(self):
        installed = self.install()
        original = installed.read_bytes()
        source_file = self.home / "music-pack-source.json"
        source_bytes = source_file.read_bytes()
        candidate = self.fixture("companion-v2", "2.0.0")
        write = pack._pack_write
        def fail_record(path, data, mode=0o600):
            if path == source_file:
                raise OSError("simulated source metadata failure")
            return write(path, data, mode)
        with mock.patch.object(pack, "_pack_write", side_effect=fail_record), self.assertRaises(OSError):
            self.install(candidate)
        self.assertEqual(installed.read_bytes(), original)
        self.assertEqual(source_file.read_bytes(), source_bytes)
        self.assertEqual(pack._pack_installed(self.home)[1]["sha256"], self.digest)
        self.assertFalse(list(installed.parent.parent.glob(".music-*-*")))

    def corrupt_installed(self, installed):
        marker = self.folder / "altered-binary-executed"
        installed.write_text("#!" + sys.executable + "\nfrom pathlib import Path\nPath(" +
                             repr(str(marker)) + ").write_text('must never run')\n")
        installed.chmod(0o700)
        return marker

    def test_explicit_repair_uses_validated_candidate_and_preserves_sources_and_config(self):
        installed = self.install()
        state, songs = self.state()
        song = songs / "Keep.ootrs"
        song.write_bytes(b"original external song")
        note = state / "personal.txt"
        note.write_text("unrelated state")
        config = state / "config.json"
        config_bytes, song_stat = config.read_bytes(), song.stat()
        marker = self.corrupt_installed(installed)
        with self.assertRaises(pack._PackNeedsRepair):
            pack._pack_installed(self.home)
        candidate = self.fixture("repair-companion", "2.0.0")
        before = len(self.events())
        self.install(candidate)
        events = self.events()[before:]
        stops = [item for item in events if item['args'][-2:] == ['music', 'stop']]
        self.assertEqual(len(stops), 1)
        self.assertIn('.music-install-', stops[0]['binary'])
        self.assertNotEqual(stops[0]['binary'], str(installed))
        self.assertFalse(marker.exists(), "Repair executed the altered installed binary")
        self.assertEqual(installed.read_bytes(), candidate.read_bytes())
        self.assertEqual(pack._pack_installed(self.home)[1]['version'], '2.0.0')
        self.assertEqual(config.read_bytes(), config_bytes)
        self.assertEqual(song.read_bytes(), b"original external song")
        self.assertEqual((song.stat().st_ino, song.stat().st_mtime_ns),
                         (song_stat.st_ino, song_stat.st_mtime_ns))
        self.assertEqual(note.read_text(), "unrelated state")
        self.assertFalse(list(installed.parent.parent.glob('.music-install-*')))
        self.assertFalse(list(installed.parent.parent.glob('.music-rollback-*')))

    def test_plain_repair_reuses_pinned_remembered_artifact_without_network(self):
        installed = self.install()
        marker = self.corrupt_installed(installed)
        original_source_record = (self.home / "music-pack-source.json").read_bytes()
        with mock.patch.object(pack, '_pack_download', side_effect=AssertionError('network requested')):
            self.assertEqual(self.invoke(['install'])[0], 0)
        self.assertFalse(marker.exists())
        self.assertEqual(installed.read_bytes(), self.source.read_bytes())
        self.assertEqual((self.home / "music-pack-source.json").read_bytes(), original_source_record)

    def test_repairable_incomplete_receipt_and_mode_failures(self):
        installed = self.install()
        receipt = installed.parent / 'receipt.json'
        for problem in ('missing-receipt', 'missing-binary', 'invalid-json', 'invalid-utf8', 'wrong-shape', 'nonexec'):
            if problem == 'missing-receipt':
                receipt.unlink()
            elif problem == 'missing-binary':
                installed.unlink()
            elif problem == 'invalid-json':
                receipt.write_text('{broken')
            elif problem == 'invalid-utf8':
                receipt.write_bytes(b'\xff')
            elif problem == 'wrong-shape':
                receipt.write_text(json.dumps({'schema': True, 'sha256': self.digest}))
            else:
                installed.chmod(0o600)
            with self.subTest(problem=problem):
                with self.assertRaises(pack._PackNeedsRepair):
                    pack._pack_installed(self.home)
                self.assertEqual(self.invoke(['install'])[0], 0)
                self.assertEqual(pack._pack_installed(self.home)[1]['sha256'], self.digest)
                self.assertTrue(os.access(installed, os.X_OK))

    def test_failed_replacement_stop_preserves_broken_pack_source_and_config(self):
        installed = self.install()
        state, _ = self.state()
        marker = self.corrupt_installed(installed)
        source_record = self.home / 'music-pack-source.json'
        before = {p: p.read_bytes() for p in (installed, installed.parent / 'receipt.json',
                                             source_record, state / 'config.json')}
        candidate = self.fixture('repair-cannot-stop', '2.0.0', stop_code=1)
        with self.assertRaisesRegex(ValueError, 'stop music with the replacement'):
            self.install(candidate)
        self.assertFalse(marker.exists())
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertFalse(list(installed.parent.parent.glob('.music-install-*')))
        self.assertFalse(list(installed.parent.parent.glob('.music-rollback-*')))

    def test_failed_repair_swap_restores_broken_pack_and_source_record(self):
        installed = self.install()
        marker = self.corrupt_installed(installed)
        directory = installed.parent
        source_record = self.home / 'music-pack-source.json'
        original = {p: p.read_bytes() for p in (installed, directory / 'receipt.json', source_record)}
        candidate = self.fixture('repair-swap-fails', '2.0.0')
        replace = pack.os.replace
        def fail_adoption(source, target):
            if Path(source).is_dir() and Path(source).name.startswith('.music-install-') and Path(target) == directory:
                raise OSError('simulated repair adoption failure')
            return replace(source, target)
        with mock.patch.object(pack.os, 'replace', side_effect=fail_adoption), self.assertRaises(OSError):
            self.install(candidate)
        self.assertFalse(marker.exists())
        for path, data in original.items():
            self.assertEqual(path.read_bytes(), data)
        with self.assertRaises(pack._PackNeedsRepair):
            pack._pack_installed(self.home)
        self.assertFalse(list(directory.parent.glob('.music-rollback-*')))
        self.assertFalse(list(directory.parent.glob('.music-install-*')))

    def test_repair_does_not_hide_unsafe_files_behind_malformed_receipt(self):
        installed = self.install()
        receipt = installed.parent / 'receipt.json'
        outside = self.folder / 'outside-pack'
        outside.write_bytes(installed.read_bytes())
        outside.chmod(0o700)
        for problem in ('symlink', 'hardlink', 'shared-writable'):
            installed.unlink()
            if problem == 'symlink':
                installed.symlink_to(outside)
            elif problem == 'hardlink':
                os.link(outside, installed)
            else:
                installed.write_bytes(outside.read_bytes())
                installed.chmod(0o666)
            receipt.write_text('{broken')
            with self.subTest(problem=problem), mock.patch.object(pack, '_pack_run') as run:
                try:
                    self.install()
                except (ValueError, OSError) as error:
                    self.assertNotIsInstance(error, pack._PackNeedsRepair)
                else:
                    self.fail('Unsafe installed file was silently repaired')
                run.assert_not_called()
                self.assertEqual(receipt.read_text(), '{broken')
            installed.unlink()
            installed.write_bytes(outside.read_bytes())
            installed.chmod(0o700)

    def test_repair_refuses_unknown_pack_files_and_changed_remembered_source(self):
        installed = self.install()
        marker = self.corrupt_installed(installed)
        broken = installed.read_bytes()
        unknown = installed.parent / 'personal-note.txt'
        unknown.write_text('keep this file')
        with self.assertRaisesRegex(ValueError, 'other files'):
            self.install()
        with mock.patch.object(pack, '_pack_download') as download, self.assertRaisesRegex(ValueError, 'other files'):
            self.invoke(['install'])
        download.assert_not_called()
        self.assertEqual(unknown.read_text(), 'keep this file')
        self.assertEqual(installed.read_bytes(), broken)
        self.assertFalse(marker.exists())
        unknown.unlink()
        self.source.write_text(self.source.read_text() + '\n# changed artifact\n')
        with mock.patch.object(pack, '_pack_download', side_effect=AssertionError('network requested')), \
                self.assertRaisesRegex(ValueError, 'artifact changed'):
            self.invoke(['install'])
        self.assertEqual(installed.read_bytes(), broken)
        self.assertFalse(marker.exists())

    def test_managed_artifact_sources_are_refused_without_changes(self):
        installed = self.install()
        source_file = self.home / "music-pack-source.json"
        original = source_file.read_bytes()
        state, _ = self.state()
        managed = state / "cache/companion"
        managed.write_bytes(self.source.read_bytes())
        alias = self.folder / "state-alias"
        alias.symlink_to(state)
        for source in (installed, managed, alias / "cache/companion"):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "outside Godmode"):
                self.invoke(["install", "--file", str(source)])
            self.assertEqual(installed.read_bytes(), self.source.read_bytes())
            self.assertEqual(source_file.read_bytes(), original)

    def test_symlink_hardlink_and_foreign_source_files_are_refused(self):
        linked = self.folder / "linked"
        linked.symlink_to(self.source)
        with self.assertRaises((OSError, ValueError)):
            self.invoke(["install", "--file", str(linked)])
        linked.unlink()
        os.link(self.source, linked)
        with self.assertRaises(ValueError):
            self.invoke(["install", "--file", str(linked)])
        linked.unlink()
        original = os.stat(self.source)
        changed = list(original)
        changed[4] = os.geteuid() + 1
        with mock.patch.object(pack.os, "fstat", return_value=os.stat_result(changed)), self.assertRaises(ValueError):
            pack._pack_read(self.source)
        self.assertFalse(self.home.exists())

    def test_symlinked_pack_directory_is_never_followed(self):
        self.home.mkdir()
        (self.home / "packs").mkdir()
        destination = self.folder / "outside"
        destination.mkdir()
        (self.home / "packs/music").symlink_to(destination)
        with self.assertRaisesRegex(ValueError, "symlinks"):
            self.invoke(["install", "--file", str(self.source), "--sha256", self.digest])
        self.assertEqual(list(destination.iterdir()), [])

    def test_forwarding_uses_pack_command_home_and_no_selection_or_key_reads(self):
        installed = self.install()
        for name in ("active.json", "profile.json", ".env.godmode", "ui.json"):
            (self.home / name).write_text("invalid and must not be read")
        allowed = {installed, installed.parent / "receipt.json"}
        original = pack._pack_read
        def checked(path, limit=65536):
            self.assertIn(Path(path), allowed)
            return original(path, limit)
        with mock.patch.object(pack, "_pack_read", side_effect=checked), mock.patch.object(pack, "_pack_run", return_value=0) as forward:
            self.assertEqual(self.invoke(["play", "success"], command="jingle")[0], 0)
        forward.assert_called_once_with(installed, self.home, ["jingle", "play", "success"])
        result = pack._pack_run(installed, self.home, ["music", "status", "--json"], capture=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {"forwarded": ["music", "status", "--json"], "home": str(self.home)})

    def test_foreground_lease_prevents_remove_and_install_without_child_inheritance(self):
        installed = self.install()
        state, _ = self.state()
        code = ("import sys;sys.path.insert(0,sys.argv[1]);import godmode_music_pack as p;"
                "sys.exit(p.music_pack_main(['hold'],sys.argv[2]))")
        foreground = subprocess.Popen([sys.executable, "-c", code, str(ROOT / "lib"), str(self.home)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while not (self.folder / "ready").exists() and foreground.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue((self.folder / "ready").exists(), "forwarded process did not start")
            for args in (["remove"], ["install", "--file", str(self.source)]):
                with self.subTest(args=args), self.assertRaisesRegex(ValueError, "Close Music Pack views"):
                    self.invoke(args)
                self.assertTrue(installed.exists())
                self.assertTrue((state / "cache/owned.txt").exists())
            with mock.patch.object(pack, "_pack_run", return_value=0) as forward:
                self.assertEqual(self.invoke(["status"])[0], 0)
                forward.assert_called_once()
            event = next(item for item in self.events() if item["args"][-2:] == ["music", "hold"])
            self.assertFalse(event["lease_inherited"])
        finally:
            (self.folder / "release").touch()
            try:
                stdout, stderr = foreground.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                foreground.kill()
                foreground.communicate()
                self.fail("forwarded process did not exit")
        self.assertEqual(foreground.returncode, 0, stderr)
        self.assertEqual(self.invoke(["remove"])[0], 0)

    def test_exclusive_lease_blocks_forwarding_and_unsafe_lock_is_refused(self):
        self.install()
        with pack._pack_lock(self.home), mock.patch.object(pack, "_pack_run") as forward:
            with self.assertRaisesRegex(ValueError, "installation or removal"):
                self.invoke(["status"])
            forward.assert_not_called()
        lock = self.home / "packs/.music.lock"
        lock.chmod(0o660)
        try:
            with self.assertRaisesRegex(ValueError, "Unsafe Music Pack lock"):
                self.invoke(["remove"])
        finally:
            lock.chmod(0o600)

    def test_forwarding_rechecks_installation_under_shared_lease(self):
        installed = self.install()
        result = (installed, {})
        with mock.patch.object(pack, "_pack_installed", side_effect=[result, None]) as inspect, \
                mock.patch.object(pack, "_pack_run") as forward:
            code, output = self.invoke(["status", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["installed"], False)
        self.assertEqual(inspect.call_count, 2)
        forward.assert_not_called()

    def test_remove_stops_first_removes_owned_runtime_cache_and_preserves_songs(self):
        installed = self.install()
        state, songs = self.state()
        source = songs / "Keep.ootrs"
        source.write_bytes(b"my music")
        before = source.stat()
        (state / "unrelated.txt").write_text("keep other state")
        self.assertEqual(self.invoke(["remove"])[0], 0)
        self.assertFalse(installed.parent.exists())
        for name in ("runtime", "cache", "session", "config.json", "session.json", ".lock"):
            self.assertFalse((state / name).exists())
        self.assertEqual((state / "unrelated.txt").read_text(), "keep other state")
        self.assertEqual(source.read_bytes(), b"my music")
        self.assertEqual((source.stat().st_ino, source.stat().st_mtime_ns), (before.st_ino, before.st_mtime_ns))
        stop = [event for event in self.events() if event["args"][-2:] == ["music", "stop"]][-1]
        self.assertTrue(stop["cache_existed"])
        self.assertTrue((self.home / "music-pack-source.json").exists())

    def test_remove_refuses_invalid_config_or_source_songs_in_managed_state(self):
        installed = self.install()
        state, _ = self.state()
        config = state / "config.json"
        for data in ("invalid json", json.dumps({"songs": str(state / "runtime/songs")})):
            config.write_text(data)
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.invoke(["remove"])
            self.assertTrue(installed.exists())
            self.assertTrue((state / "cache/owned.txt").exists())
            self.assertEqual(config.read_text(), data)

    def test_remove_resolves_source_alias_before_deleting_managed_tree(self):
        installed = self.install()
        state, _ = self.state()
        songs = state / "runtime/source-songs"
        songs.mkdir()
        source = songs / "Keep.ootrs"
        source.write_bytes(b"source must survive")
        alias = self.folder / "source-alias"
        alias.symlink_to(songs, target_is_directory=True)
        (state / "config.json").write_text(json.dumps({"songs": str(alias)}))
        with self.assertRaises(ValueError):
            self.invoke(["remove"])
        self.assertTrue(installed.exists())
        self.assertEqual(source.read_bytes(), b"source must survive")

    def test_unknown_pack_files_or_source_inside_pack_are_not_removed(self):
        installed = self.install()
        personal = installed.parent / "personal.txt"
        personal.write_text("keep")
        with self.assertRaises(ValueError):
            self.invoke(["remove"])
        self.assertEqual(personal.read_text(), "keep")
        self.assertTrue(installed.exists())
        personal.unlink()
        songs = installed.parent / "songs"
        songs.mkdir()
        (songs / "Keep.ootrs").write_bytes(b"keep")
        self.state(songs=songs)
        with self.assertRaises(ValueError):
            self.invoke(["remove"])
        self.assertEqual((songs / "Keep.ootrs").read_bytes(), b"keep")

    def test_remove_failure_does_not_delete_pack_or_managed_state(self):
        badstop = self.fixture("cannot-stop", "1.2.3", stop_code=1)
        installed = self.install(badstop)
        state, _ = self.state()
        with self.assertRaisesRegex(ValueError, "stop"):
            self.invoke(["remove"])
        self.assertTrue(installed.exists())
        self.assertTrue((state / "runtime/owned.txt").exists())

    def test_remove_refuses_linked_or_shared_writable_managed_files(self):
        installed = self.install()
        state, _ = self.state()
        external = self.folder / "outside.txt"
        external.write_text("keep")
        suspect = state / "cache/suspect"
        for kind in ("symlink", "hardlink", "writable"):
            if kind == "symlink":
                suspect.symlink_to(external)
            elif kind == "hardlink":
                os.link(external, suspect)
            else:
                suspect.write_text("keep writable file")
                suspect.chmod(0o666)
            try:
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    self.invoke(["remove"])
                self.assertTrue(installed.exists())
                self.assertTrue((state / "runtime/owned.txt").exists())
                self.assertEqual(external.read_text(), "keep")
            finally:
                suspect.unlink()

    def test_remove_and_reinstall_reuses_registered_local_artifact_without_network(self):
        self.install()
        self.invoke(["remove"])
        with mock.patch.object(pack, "_pack_download", side_effect=AssertionError("network requested")):
            self.assertEqual(self.invoke(["install"])[0], 0)
        self.assertEqual(pack._pack_installed(self.home)[1]["sha256"], self.digest)
        self.invoke(["remove"])
        self.source.write_text(self.source.read_text() + "\n# changed\n")
        with mock.patch.object(pack, "_pack_download", side_effect=AssertionError("network requested")), \
                self.assertRaisesRegex(ValueError, "changed"):
            self.invoke(["install"])
        self.assertIsNone(pack._pack_installed(self.home))

    def test_invalid_registered_source_never_falls_back_to_network(self):
        self.home.mkdir()
        for source in (None, [], {"kind": "local", "file": ""}, {"kind": "unknown"}):
            (self.home / "music-pack-source.json").write_text(json.dumps(source))
            with self.subTest(source=source), mock.patch.object(pack, "_pack_download") as download, self.assertRaises(ValueError):
                self.invoke(["install"])
            download.assert_not_called()
            self.assertFalse((self.home / "packs").exists())

    def test_manager_protocol_bounds_read_and_stops_after_oversize(self):
        class BoundedInput(io.BytesIO):
            def readline(self, limit=-1):
                if limit != 65537:
                    raise AssertionError("manager must bound every read")
                return super().readline(limit)
        stream = BoundedInput(b"x" * 1000000 + b'\n{"action":"state"}\n')
        with mock.patch.object(pack.sys, "stdin", mock.Mock(buffer=stream)):
            code, output = self.invoke(["__manager"])
        self.assertEqual(code, 1)
        self.assertEqual(len(output.splitlines()), 1)
        self.assertFalse(json.loads(output)["ok"])
        self.assertEqual(stream.tell(), 65537)
        self.assertFalse(self.home.exists())

    def download_fixture(self, manifest, data):
        class Response(io.BytesIO):
            pass
        opener = mock.Mock()
        opener.open.side_effect = [Response(json.dumps(manifest).encode()), Response(data)]
        return opener

    def test_https_release_download_uses_exact_platform_artifact_and_checksum(self):
        _, _, target = pack._pack_target()
        artifact = "godmode-music-v1.2.3-" + target
        data = self.source.read_bytes()
        manifest = {"schema": 1, "version": "1.2.3", "artifacts": [
            {"platform": target, "file": artifact, "sha256": self.digest, "size": len(data)}]}
        opener = self.download_fixture(manifest, data)
        with mock.patch.object(pack.urllib.request, "build_opener", return_value=opener) as build:
            received, digest, source = pack._pack_download()
        self.assertEqual(received, data)
        self.assertEqual(digest, self.digest)
        self.assertEqual(source, {"kind": "release", "version": "1.2.3"})
        self.assertIsInstance(build.call_args.args[0], pack._PackNoRedirect)
        self.assertEqual([call.args[0] for call in opener.open.call_args_list],
                         [pack.PACK_RELEASE_ROOT + "/latest.json", pack.PACK_RELEASE_ROOT + "/1.2.3/" + artifact])
        self.assertTrue(all(call.args[0].startswith("https://") for call in opener.open.call_args_list))
        corrupted = self.download_fixture(manifest, b"x" * len(data))
        with mock.patch.object(pack.urllib.request, "build_opener", return_value=corrupted), \
                self.assertRaisesRegex(ValueError, "checksum"):
            pack._pack_download()

    def test_invalid_remote_manifest_shapes_raise_clean_errors_without_install(self):
        for manifest in ([], None, {"schema": 1, "version": None, "artifacts": []},
                         {"schema": 1, "version": "../escape", "artifacts": []}):
            opener = self.download_fixture(manifest, b"")
            with self.subTest(manifest=manifest), mock.patch.object(pack.urllib.request, "build_opener", return_value=opener), \
                    self.assertRaises(ValueError):
                pack._pack_download()
        self.assertFalse(self.home.exists())

    def test_default_core_bundle_is_light_and_contains_no_music_implementation_assets(self):
        script = self.folder / "godmode-core"
        result = subprocess.run([sys.executable, str(ROOT / "scripts/build.py"), "--output", str(script)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        source = script.read_text()
        self.assertLess(script.stat().st_size, 1024 * 1024)
        self.assertIn("def music_pack_main", source)
        for marker in ("class _MusicSession", "class _MusicMPV", "MUSIC_RUNTIME_BUNDLE", "def music_setup", "def jingle_main"):
            self.assertNotIn(marker, source)

    @unittest.skipUnless((ROOT / "target/godmode-music-pack").is_file(), "native companion not built")
    def test_real_companion_installs_forwards_read_only_commands_and_removes(self):
        artifact = ROOT / "target/godmode-music-pack"
        installed = self.install(artifact)
        self.assertEqual(pack._pack_info(installed, self.home)["kind"], "godmode-music-pack")
        with mock.patch.dict(os.environ, {"GODMODE_ENV": "invalid-selection", "GODMODE_CONTEXT": "invalid-context"}):
            status = pack._pack_run(installed, self.home, ["music", "status", "--json"], capture=True)
            jingles = pack._pack_run(installed, self.home, ["jingle", "list", "--json"], capture=True)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(json.loads(status.stdout)["state"], "stopped")
        self.assertEqual(jingles.returncode, 0, jingles.stderr)
        self.assertEqual(json.loads(jingles.stdout)["jingles"], ["ready", "success", "attention"])
        self.assertFalse((self.home / "state").exists())
        self.assertEqual(self.invoke(["remove"])[0], 0)
        self.assertFalse(installed.parent.exists())


if __name__ == "__main__":
    unittest.main()
