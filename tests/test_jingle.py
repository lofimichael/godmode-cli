"""Jingles generate original bounded audio and never share the music session."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import godmode_jingle as jingle


class JingleTests(unittest.TestCase):
    def test_all_cues_are_short_nonzero_unclipped_pcm_with_silent_edges(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in jingle.JINGLE_TONES:
                with self.subTest(name=name):
                    path = Path(directory) / (name + ".wav")
                    duration = jingle._jingle_wave(path, name)
                    with wave.open(str(path)) as audio:
                        self.assertEqual((audio.getnchannels(), audio.getsampwidth()), (1, 2))
                        samples = struct.unpack("<" + "h" * audio.getnframes(), audio.readframes(audio.getnframes()))
                        self.assertEqual(audio.getnframes() / audio.getframerate(), duration)
                    self.assertGreater(duration, .2)
                    self.assertLessEqual(duration, 2)
                    self.assertGreater(max(map(abs, samples)), 1000)
                    self.assertLess(max(map(abs, samples)), 32767)
                    self.assertEqual(samples[0], 0)
                    self.assertTrue(all(sample == 0 for sample in samples[-100:]))

    def test_player_ignores_config_and_credentials_and_cleans_temporary_file(self):
        child = mock.Mock()
        child.wait.return_value = child.poll.return_value = 0
        observed = {}
        def start(command, **options):
            observed.update(command=command, options=options)
            self.assertTrue(Path(command[-1]).is_file())
            return child
        with mock.patch.object(jingle.shutil, "which", return_value="/fixture/mpv"), \
                mock.patch.dict(os.environ, {"SYNTHETIC_SECRET": "must-not-inherit", "MPV_HOME": "/untrusted"}):
            result = jingle._jingle_play("ready", 19, popen=start)
        for flag in ("--no-config", "--load-scripts=no", "--input-media-keys=no", "--audio-device=auto", "--volume=19"):
            self.assertIn(flag, observed["command"])
        self.assertNotIn("--ao=null", observed["command"])
        self.assertTrue(observed["options"]["start_new_session"])
        self.assertTrue(observed["options"]["close_fds"])
        self.assertNotIn("SYNTHETIC_SECRET", observed["options"]["env"])
        self.assertNotIn("MPV_HOME", observed["options"]["env"])
        self.assertFalse(Path(observed["command"][-1]).exists())
        self.assertEqual(result["state"], "played")

    def test_timeout_and_interrupt_reap_only_own_child_and_restore_handlers(self):
        before = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
        for failure in (subprocess.TimeoutExpired("mpv", 4), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                child = mock.Mock()
                child.wait.side_effect = failure
                child.poll.return_value = None
                with mock.patch.object(jingle.shutil, "which", return_value="/fixture/mpv"), \
                        mock.patch.object(jingle, "_music_end") as stop:
                    with self.assertRaises((ValueError, KeyboardInterrupt)):
                        jingle._jingle_play("ready", 35, popen=lambda *a, **kw: child)
                    stop.assert_called_once_with(child)
                self.assertEqual(before, {sig: signal.getsignal(sig) for sig in before})

    def test_termination_cleans_real_child_and_temporary_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "player.json"
            script = """import json,pathlib,subprocess,sys
sys.path.insert(0, sys.argv[1])
import godmode_jingle as j
original = subprocess.Popen
def player(command, **options):
    child = original([sys.executable, '-c', 'import time; time.sleep(60)'], **options)
    pathlib.Path(sys.argv[2]).write_text(json.dumps({'pid': child.pid, 'wav': command[-1]}))
    return child
j.shutil.which = lambda _: sys.executable
j.subprocess.Popen = player
sys.exit(j.jingle_main(['play']))
"""
            owner = subprocess.Popen([sys.executable, "-c", script, str(ROOT / "lib"), str(marker)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
            try:
                deadline = time.monotonic() + 3
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(marker.exists(), "player did not start")
                data = json.loads(marker.read_text())
                owner.send_signal(signal.SIGTERM)
                output, errors = owner.communicate(timeout=4)
                self.assertEqual(owner.returncode, 130, errors)
                self.assertEqual(output, "")
                self.assertIn("Jingle stopped", errors)
                self.assertFalse(Path(data["wav"]).exists())
                with self.assertRaises(ProcessLookupError):
                    os.kill(data["pid"], 0)
            finally:
                if owner.poll() is None:
                    owner.kill()
                owner.communicate()

    def test_jingle_does_not_read_or_change_home_queue_or_volume(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            root = home / "state/music"
            root.mkdir(parents=True)
            saved = root / "session.json"
            saved.write_text('{"queue":["track"],"volume":73}')
            before = saved.stat()
            output = io.StringIO()
            with mock.patch.object(jingle, "_jingle_play", return_value={"state": "played", "name": "ready"}) as play, \
                    mock.patch.object(Path, "read_bytes", side_effect=AssertionError("read state")), \
                    mock.patch.object(Path, "read_text", side_effect=AssertionError("read state")), \
                    contextlib.redirect_stdout(output):
                self.assertEqual(jingle.jingle_main(["play"], home=home), 0)
            play.assert_called_once_with("ready", 35)
            self.assertEqual(output.getvalue(), "Ready jingle played.\n")
            after = saved.stat()
            self.assertEqual((before.st_ino, before.st_mtime_ns, before.st_size),
                             (after.st_ino, after.st_mtime_ns, after.st_size))
            self.assertEqual(list(root.iterdir()), [saved])

    def test_list_needs_no_player_and_failed_play_never_claims_success(self):
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(jingle.shutil, "which", return_value=None), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(jingle.jingle_main(["list", "--json"]), 0)
            self.assertEqual(json.loads(output.getvalue())["jingles"], ["ready", "success", "attention"])
            output.seek(0)
            output.truncate()
            self.assertEqual(jingle.jingle_main(["play"]), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("Install mpv", errors.getvalue())

    def test_player_failure_does_not_report_played(self):
        child = mock.Mock()
        child.wait.return_value = child.poll.return_value = 2
        with mock.patch.object(jingle.shutil, "which", return_value="/fixture/mpv"), \
                self.assertRaisesRegex(ValueError, "playback failed"):
            jingle._jingle_play("success", 35, popen=lambda *a, **kw: child)

    def test_invalid_names_volume_and_player_flags_are_rejected(self):
        for arguments in (["play", "unknown"], ["play", "--volume", "-1"], ["play", "--volume", "101"],
                          ["play", "--volume", "nan"], ["play", "--ao=null"], ["list", "ready"]):
            with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()), \
                    mock.patch.object(jingle, "_jingle_play") as play, self.assertRaises(SystemExit):
                jingle.jingle_main(arguments)
            play.assert_not_called()

    @unittest.skipUnless(shutil.which("mpv"), "mpv unavailable")
    def test_real_mpv_with_explicit_null_audio(self):
        result = jingle._jingle_play("attention", 0, null_output=True)
        self.assertEqual(result["state"], "played")


if __name__ == "__main__":
    unittest.main()
