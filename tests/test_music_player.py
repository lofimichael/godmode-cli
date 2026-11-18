"""Music session contracts: real mpv null output, bounded IPC, cancellation, ownership."""
import contextlib
import io
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import godmode_music as music
import godmode_music_player as player


class MusicPlayerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gm-player-", dir="/tmp")
        self.home = Path(self.temp.name).resolve()
        self.root = music._music_root(self.home)
        self.backend, self.songs = self.home / "synth", self.home / "songs"
        self.backend.mkdir()
        self.songs.mkdir()
        for name in ("First", "Second", "Third"):
            (self.songs / (name + ".ootrs")).write_bytes(b"fixture " + name.encode())
        self.wav = self.home / "audio.wav"
        with wave.open(str(self.wav), "wb") as audio:
            audio.setparams((1, 2, 44100, 0, "NONE", "not compressed"))
            audio.writeframes(b"\0\0" * 44100 * 4)
        script = '''import argparse,hashlib,json,pathlib,wave
p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--seconds',type=float);p.add_argument('--cache-dir');p.add_argument('--output');a=p.parse_args()
key=hashlib.sha256((a.source+str(a.seconds)).encode()).hexdigest();target=pathlib.Path(a.cache_dir)/key;target.mkdir(exist_ok=True)
wav=target/'render.wav'
with wave.open(str(wav),'wb') as w:
 w.setparams((1,2,44100,0,'NONE','not compressed'));w.writeframes(b'\\0\\0'*int(44100*a.seconds))
pathlib.Path(a.output).with_suffix('.synthesis.json').write_text(json.dumps({'cache_key':key,'wav_sha256':hashlib.sha256(wav.read_bytes()).hexdigest(),'mode':'piano'}))
'''
        (self.backend / "synthesize.py").write_text(script)
        for name in ("tools/render_synth", "tools/seq64/build/seq64_console", "tools/florestan-subset.sf2", "oot-instruments.json"):
            path = self.backend / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture")
        with mock.patch.object(music.shutil, "which", return_value="/fixture"), contextlib.redirect_stdout(io.StringIO()):
            music._music_init(self.root, self.backend, self.songs)
        self.wrapper = self.home / "godmode-fixture"
        self.wrapper.write_text("#!" + sys.executable + "\n" +
            "import sys;sys.path.insert(0," + repr(str(ROOT / "lib")) + ")\n" +
            "import godmode_music_player as p\n" +
            "original=p._MusicSession\n" +
            "p._MusicSession=lambda root:original(root,player_factory=lambda events:p._MusicMPV(events,audio_output='null'))\n" +
            "sys.exit(p.music_session_serve())\n")
        self.wrapper.chmod(0o700)

    def tearDown(self):
        with contextlib.suppress(Exception):
            player.music_request({"action": "stop"}, self.home)
        self.temp.cleanup()

    def request(self, action, **fields):
        with mock.patch.dict(os.environ, {"GODMODE_EXECUTABLE": str(self.wrapper)}):
            return player.music_request(dict(action=action, **fields), self.home)

    def wait_state(self, state, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = self.request("status")
            if data["state"] == state:
                return data
            time.sleep(0.03)
        self.fail("state never became " + state + ": " + repr(data))

    def test_invalid_requests_are_bounded_before_daemon_start(self):
        requests = [{"action": "arbitrary"}, {"action": "status", "command": ["run", "anything"]},
                    {"action": "play", "ids": []}, {"action": "play", "ids": ["First.ootrs"] * 10001},
                    {"action": "play", "ids": ["First.ootrs"], "index": True},
                    {"action": "volume", "value": float("nan")}, {"action": "shuffle", "value": 1},
                    {"action": "play", "ids": ["x" * (player.MUSIC_PROTOCOL_LIMIT + 1)]}]
        for request in requests:
            with self.subTest(request=str(request)[:80]), self.assertRaises((ValueError, TypeError)):
                player.music_request(request, self.home)
        self.assertFalse((self.root / "session").exists())

    def test_protocol_rejects_nonobjects_trailing_commands_and_oversize(self):
        for payload in (b"[]\n", b"{}\n{}\n", b"broken\n"):
            first, second = socket.socketpair()
            with first, second:
                second.sendall(payload)
                with self.assertRaises(ValueError):
                    player._music_json_line(first)
        first, second = socket.socketpair()
        with first, second, mock.patch.object(player, "MUSIC_PROTOCOL_LIMIT", 8):
            second.sendall(b"x" * 9)
            with self.assertRaises(ValueError):
                player._music_json_line(first)

    def test_long_home_endpoint_is_private_hashed_and_not_symlink_followed(self):
        root = music._music_root(self.home / ("long-" * 30))
        path = player._music_session_path(root, True)
        self.assertLess(len(os.fsencode(path)), 104)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        path.symlink_to(self.wav)
        with self.assertRaisesRegex(ValueError, "Unsafe music session"):
            player._music_session_path(root)
        path.unlink()
        path.parent.rmdir()

    def test_stop_absent_ignores_invalid_config_and_does_not_touch_other_files(self):
        (self.root / "config.json").write_text("invalid")
        before = (self.root / "config.json").read_bytes()
        self.assertEqual(self.request("stop")["state"], "stopped")
        self.assertEqual((self.root / "config.json").read_bytes(), before)
        self.assertFalse((self.root / "session").exists())

    def test_queue_shuffle_history_remove_and_saved_stopped_restore(self):
        session = player._MusicSession(self.root)
        ids = ["First.ootrs", "Second.ootrs", "Third.ootrs"]
        try:
            session.handle({"action": "play", "ids": ids, "index": 0})
            session.handle({"action": "shuffle", "value": True})
            session.remaining = [2, 1]
            self.assertEqual(session.handle({"action": "next"})["index"], 1)
            self.assertEqual(session.handle({"action": "previous"})["index"], 0)
            session.handle({"action": "volume", "value": 18})
            session.handle({"action": "repeat", "value": "all"})
            stopped = session.handle({"action": "stop"})
            self.assertEqual(len(stopped["queue"]), 3)
        finally:
            session.close()
        restored = player._MusicSession(self.root)
        try:
            self.assertEqual(restored.data["state"], "stopped")
            self.assertEqual(restored.data["volume"], 18)
            self.assertEqual(restored.data["repeat"], "all")
            self.assertTrue(restored.data["shuffle"])
            restored.handle({"action": "remove", "index": 2})
            self.assertEqual(len(restored.data["queue"]), 2)
            restored.handle({"action": "clear_queue"})
            self.assertEqual(restored.data["queue"], [])
            self.assertIsNone(restored.player)
        finally:
            restored.close()
        self.assertEqual((self.root / "session.json").stat().st_mode & 0o777, 0o600)

    def test_remove_current_stopped_or_error_track_never_starts_playback(self):
        for state in ("stopped", "error"):
            with self.subTest(state=state):
                session = player._MusicSession(self.root)
                try:
                    session.data.update(queue=session._resolve(["First.ootrs", "Second.ootrs"]),
                                        index=0, state=state)
                    session.data["track"] = session.data["queue"][0]
                    with mock.patch.object(session, "_start", side_effect=AssertionError("started playback")), \
                            mock.patch.object(player, "_music_render", side_effect=AssertionError("rendered audio")), \
                            mock.patch.object(player, "_MusicMPV", side_effect=AssertionError("created player")):
                        result = session.handle({"action": "remove", "index": 0})
                        session.tick()
                    self.assertEqual(result["state"], "stopped")
                    self.assertEqual(result["track"]["id"], "Second.ootrs")
                    self.assertEqual(result["index"], 0)
                    self.assertIsNone(session.pending)
                    self.assertIsNone(session.worker)
                    self.assertIsNone(session.player)
                    restored, _ = player._music_saved(self.root)
                    self.assertEqual(restored["track"]["id"], "Second.ootrs")
                finally:
                    session.close()

    def test_remove_after_stop_edits_saved_queue_without_daemon_or_config(self):
        session = player._MusicSession(self.root)
        session.handle({"action": "play", "ids": ["First.ootrs", "Second.ootrs"]})
        session.handle({"action": "stop"})
        session.close()
        (self.root / "config.json").write_text("invalid config must not be read")
        with mock.patch.object(player, "_music_launch", side_effect=AssertionError("launched owner")), \
                mock.patch.object(player, "_music_render", side_effect=AssertionError("rendered audio")):
            result = self.request("remove", index=0)
        self.assertEqual(result["state"], "stopped")
        self.assertEqual(result["track"]["id"], "Second.ootrs")
        self.assertFalse(player._music_session_path(self.root).exists())

    def test_remove_paused_current_track_preserves_pause_intent(self):
        session = player._MusicSession(self.root)
        try:
            session.handle({"action": "play", "ids": ["First.ootrs", "Second.ootrs"]})
            session.data["state"] = "paused"
            session.want_pause = True
            result = session.handle({"action": "remove", "index": 0})
            self.assertEqual(result["track"]["id"], "Second.ootrs")
            self.assertEqual(result["state"], "preparing")
            self.assertTrue(session.want_pause)
            session.loaded_path = str(self.wav)
            session.awaiting_start = False
            session._process_event({"event": "property-change", "name": "audio-pts", "data": 0.0})
            self.assertEqual(session.data["state"], "paused")
        finally:
            session.close()

    def test_late_cancelled_render_cannot_replace_new_selection(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def render(root, config, source, seconds, **options):
            calls.append(source.name)
            entered.set()
            if source.name == "First.ootrs":
                release.wait(2)
                self.assertTrue(options["cancel"].is_set())
            return self.wav, {}, True
        class FakePlayer:
            def __init__(self, events):
                self.commands = []
            def command(self, *command):
                self.commands.append(command)
            def close(self):
                pass
        session = player._MusicSession(self.root, FakePlayer)
        with mock.patch.object(player, "_music_render", side_effect=render):
            try:
                session.handle({"action": "play", "ids": ["First.ootrs", "Second.ootrs"]})
                session.tick()
                self.assertTrue(entered.wait(1))
                started = time.monotonic()
                session.handle({"action": "next"})
                self.assertLess(time.monotonic() - started, .3)
                self.assertEqual(session.snapshot()["track"]["id"], "Second.ootrs")
                release.set()
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and session.player is None:
                    session.tick()
                    time.sleep(.01)
                self.assertEqual(calls, ["First.ootrs", "Second.ootrs"])
                self.assertEqual([cmd[0] for cmd in session.player.commands].count("loadfile"), 1)
            finally:
                release.set()
                session.close()

    def test_clock_is_reported_not_wall_time_and_stale_analysis_clears(self):
        session = player._MusicSession(self.root)
        try:
            session.loaded_path = str(self.wav)
            session.awaiting_start = False
            session.data["duration"] = 4
            session.audio = wave.open(str(self.wav), "rb")
            session._process_event({"event": "property-change", "name": "audio-pts", "data": 1.25})
            self.assertEqual(session.snapshot()["position"], 1.25)
            time.sleep(.05)
            self.assertEqual(session.snapshot()["position"], 1.25)
            self.assertEqual(session.data["clock_source"], "mpv:audio-pts")
            session.clock_at -= 3
            self.assertEqual(session.snapshot()["levels"], [])
            self.assertEqual(session.data["message"], "Waiting for audio clock")
        finally:
            session.close()

    def test_prospective_queue_byte_limit_rejects_without_mutation(self):
        session = player._MusicSession(self.root)
        try:
            session.handle({"action": "enqueue", "ids": ["First.ootrs"]})
            before = (self.root / "session.json").read_bytes()
            # Below 10,000 entries but above the serialized protocol limit.
            tracks = [{"id": str(index) + "a" * 200 + ".ootrs", "title": "x" * 200, "collection": "Library"}
                      for index in range(9000)]
            with mock.patch.object(session, "_resolve", return_value=tracks), self.assertRaisesRegex(ValueError, "too large"):
                session.handle({"action": "enqueue", "ids": ["First.ootrs"]})
            self.assertEqual(len(session.data["queue"]), 1)
            self.assertEqual((self.root / "session.json").read_bytes(), before)
            self.assertIsNone(session.player)
        finally:
            session.close()

    def test_one_next_prefetch_reuses_prepared_audio_and_invalidates_source_change(self):
        calls = []
        def render(root, config, source, seconds, **options):
            calls.append(source.name)
            return self.wav, {}, True
        def signature(config, source, details, verify=False):
            return (str(source), source.stat().st_ctime_ns)
        class FakePlayer:
            def __init__(self, events):
                self.events, self.serial = events, 0
            def command(self, *command):
                if command[0] == "loadfile":
                    self.serial += 1
                    self.events.put({"event": "start-file", "playlist_entry_id": self.serial})
                    self.events.put({"event": "property-change", "name": "audio-pts", "data": .1})
            def close(self):
                pass
        session = player._MusicSession(self.root, FakePlayer)
        def settle(check):
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                session.tick()
                if check():
                    return
                time.sleep(.01)
            self.fail("prepared audio did not settle")
        with mock.patch.object(player, "_music_render", side_effect=render), \
                mock.patch.object(player, "_music_prepared_signature", side_effect=signature):
            try:
                session.handle({"action": "play", "ids": ["First.ootrs", "Second.ootrs"]})
                settle(lambda: len(session.prepared) == 2 and session.worker is None)
                self.assertEqual(calls, ["First.ootrs", "Second.ootrs"])
                session.handle({"action": "next"})
                settle(lambda: session.data["state"] == "playing" and session.worker is None)
                session.handle({"action": "previous"})
                settle(lambda: session.data["state"] == "playing" and session.worker is None)
                self.assertEqual(calls, ["First.ootrs", "Second.ootrs"])
                (self.songs / "First.ootrs").write_bytes(b"changed source")
                session.handle({"action": "play", "ids": ["First.ootrs"]})
                settle(lambda: session.data["state"] == "playing" and session.worker is None)
                self.assertEqual(calls, ["First.ootrs", "Second.ootrs", "First.ootrs"])
            finally:
                session.close()

    def test_natural_eof_repeat_modes_and_stale_entry_event(self):
        session = player._MusicSession(self.root)
        try:
            session.handle({"action": "play", "ids": ["First.ootrs", "Second.ootrs"]})
            def eof(entry=4):
                session.loaded_path = str(self.wav)
                session.awaiting_start = False
                session.entry_id = 4
                session.data["state"] = "playing"
                session._process_event({"event": "end-file", "reason": "eof", "playlist_entry_id": entry})
            eof(entry=3)
            self.assertEqual(session.data["index"], 0)
            session.handle({"action": "repeat", "value": "one"})
            eof()
            self.assertEqual(session.data["index"], 0)
            session.handle({"action": "repeat", "value": "all"})
            eof()
            self.assertEqual(session.data["index"], 1)
            eof()
            self.assertEqual(session.data["index"], 0)
            session.handle({"action": "repeat", "value": "off"})
            eof()
            eof()
            self.assertEqual(session.data["state"], "stopped")
        finally:
            session.close()

    @unittest.skipUnless(shutil.which("mpv"), "mpv optional runtime is absent")
    def test_real_mpv_null_output_pause_seek_volume_clock_and_eof(self):
        events = queue.Queue()
        transport = player._MusicMPV(events, audio_output="null")
        try:
            transport.command("loadfile", str(self.wav), "replace")
            time.sleep(.25)
            before = transport.command("get_property", "audio-pts")
            self.assertGreater(before, 0)
            transport.command("set_property", "pause", True)
            paused = transport.command("get_property", "time-pos")
            time.sleep(.2)
            self.assertAlmostEqual(transport.command("get_property", "time-pos"), paused, delta=.03)
            transport.command("seek", 2.0, "absolute+exact")
            time.sleep(.08)
            # Audio-master reporting includes output buffering; it is a player
            # clock, not a sample-exact seek receipt while the output is paused.
            self.assertAlmostEqual(transport.command("get_property", "time-pos"), 2.0, delta=.25)
            transport.command("set_property", "volume", 22)
            self.assertEqual(transport.command("get_property", "volume"), 22)
            transport.command("set_property", "pause", False)
            transport.command("seek", 3.9, "absolute+exact")
            deadline = time.monotonic() + 2
            eof = False
            while time.monotonic() < deadline:
                try:
                    event = events.get(timeout=.1)
                except queue.Empty:
                    continue
                if event.get("event") == "end-file" and event.get("reason") == "eof":
                    eof = True
                    break
            self.assertTrue(eof)
        finally:
            transport.close()
        self.assertIsNotNone(transport.child.poll())

    @unittest.skipUnless(shutil.which("mpv"), "mpv optional runtime is absent")
    def test_detached_singleton_survives_clients_and_stop_reaps_owned_player(self):
        unrelated = subprocess.Popen(["/bin/sleep", "30"])
        try:
            status = self.request("play", ids=["First.ootrs", "Second.ootrs"], seconds=4)
            session_id = status["session_id"]
            playing = self.wait_state("playing")
            self.assertEqual(playing["session_id"], session_id)
            time.sleep(.15)
            self.assertGreater(self.request("status")["position"], playing["position"])
            self.assertEqual(self.request("pause")["state"], "paused")
            paused = self.request("status")["position"]
            time.sleep(.2)
            self.assertAlmostEqual(self.request("status")["position"], paused, delta=.06)
            self.request("remove", index=0)
            replacement = self.wait_state("paused")
            self.assertEqual(replacement["track"]["id"], "Second.ootrs")
            time.sleep(.2)
            self.assertEqual(self.request("status")["state"], "paused")
            self.assertAlmostEqual(self.request("status")["position"], replacement["position"], delta=.06)
            # A new launch races the existing owner and must not replace it.
            with mock.patch.dict(os.environ, {"GODMODE_EXECUTABLE": str(self.wrapper)}):
                player._music_launch(self.root)
            self.assertEqual(self.request("status")["session_id"], session_id)
            with self.assertRaisesRegex(ValueError, "Music is running"):
                music._music_clear(self.root)
            self.request("stop")
            self.assertIsNone(unrelated.poll())
            self.assertFalse(player._music_session_path(self.root).exists())
            restored = self.request("status")
            self.assertEqual(restored["state"], "stopped")
            self.assertEqual(len(restored["queue"]), 1)
            self.assertNotIn("session_id", restored)
        finally:
            self.request("stop")
            unrelated.terminate()
            unrelated.wait()

    @unittest.skipUnless(shutil.which("mpv"), "mpv optional runtime is absent")
    def test_stale_socket_is_replaced_only_under_owner_lock(self):
        path = player._music_session_path(self.root, True)
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(path))
        os.chmod(path, 0o600)
        stale.close()
        self.assertIsNone(player._music_contact(self.root, {"action": "status"}))
        self.request("play", ids=["First.ootrs"], seconds=1)
        self.assertIn(self.request("status")["state"], ("preparing", "playing"))


if __name__ == "__main__":
    unittest.main()
