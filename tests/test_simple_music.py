"""Local optional music: synthetic PCM and isolated process/cache checks."""
import contextlib
import fcntl
import hashlib
import io
import json
import math
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import godmode_music as music
import godmode_terminal as terminal
from pty_support import Terminal, plain


class MusicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="godmode-music-test-", dir="/tmp")
        self.home = Path(self.temp.name).resolve()
        self.root = music._music_root(self.home)
        self.backend = self.home / "darunia"
        self.songs = self.home / "songs"
        self.backend.mkdir()
        self.songs.mkdir()
        self.script = self.backend / "synthesize.py"
        self.script.write_text("# synthetic local backend\n")
        for name in ("tools/render_synth", "tools/seq64/build/seq64_console", "tools/florestan-subset.sf2", "oot-instruments.json"):
            path = self.backend / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic fixture")
        (self.songs / "Quiet.ootrs").write_bytes(b"fixture")

    def tearDown(self):
        self.temp.cleanup()

    def init(self):
        with mock.patch.object(music.shutil, "which", return_value="/never/executed"), contextlib.redirect_stdout(io.StringIO()):
            music._music_init(self.root, self.backend, self.songs)
        return music._music_config(self.root)

    def wav(self, path, frequency=440, seconds=0.25):
        rate = 44100
        with wave.open(str(path), "wb") as audio:
            audio.setparams((2, 2, rate, 0, "NONE", "not compressed"))
            samples = b"".join(struct.pack("<hh", *(int(12000 * math.sin(2 * math.pi * frequency * n / rate)),) * 2)
                               for n in range(int(rate * seconds)))
            audio.writeframes(samples)

    def test_uninitialized_status_does_not_create_files(self):
        self.assertFalse(music.music_available(self.home))
        with self.assertRaisesRegex(ValueError, "music init"):
            music.music_main(["status"], self.home)
        self.assertFalse(self.root.exists())

    def test_explicit_init_pins_local_script_and_ignores_network_player(self):
        config = self.init()
        self.assertEqual(config["sha256"], hashlib.sha256(self.script.read_bytes()).hexdigest())
        self.assertTrue(music.music_available(self.home))
        self.assertEqual((self.root / "config.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        self.script.write_text("# changed backend\n")
        with self.assertRaisesRegex(ValueError, "synth changed"):
            music._music_config(self.root)
        self.assertFalse(music.music_available(self.home))

    def test_missing_tools_never_installs_or_initializes(self):
        with mock.patch.object(music.shutil, "which", return_value=None), self.assertRaisesRegex(ValueError, "tools are missing"):
            music._music_init(self.root, self.backend, self.songs)
        self.assertFalse(self.root.exists())

    def test_init_refuses_linked_scripts_and_dirs(self):
        original = self.backend / "original.py"
        self.script.rename(original)
        self.script.symlink_to(original)
        with self.assertRaises((ValueError, OSError)):
            music._music_init(self.root, self.backend, self.songs)
        self.assertFalse(self.root.exists())
        alias = self.home / "alias"
        alias.symlink_to(self.songs, target_is_directory=True)
        with self.assertRaises(ValueError):
            music._music_directory(alias)

    def test_song_scan_stays_inside_tree_and_search_is_exact_first(self):
        outside = self.home / "outside"
        outside.mkdir()
        (outside / "secret.ootrs").write_text("not music")
        (self.songs / "linked-dir").symlink_to(outside, target_is_directory=True)
        (self.songs / "linked.ootrs").symlink_to(outside / "secret.ootrs")
        (self.songs / "Quiet again.ootrs").write_text("fixture")
        self.assertEqual(len(music._music_songs(self.songs)), 2)
        self.assertEqual(music._music_select(self.songs, "Quiet.ootrs"), self.songs / "Quiet.ootrs")
        with self.assertRaisesRegex(ValueError, "2 tracks match"):
            music._music_select(self.songs, "Quiet")

    def test_local_list_cannot_inject_terminal_controls(self):
        self.init()
        (self.songs / "evil\x1b[2J.ootrs").write_text("fixture")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            music.music_main(["list"], self.home)
        self.assertNotIn("\x1b", output.getvalue())

    def test_clear_removes_only_cache_and_retains_config_source_and_other_state(self):
        self.init()
        cache = self.root / "cache" / ("a" * 64)
        cache.mkdir(parents=True)
        (cache / "render.wav").write_bytes(b"synthetic")
        other = self.root.parent / "unrelated.txt"
        other.write_text("preserve")
        config = (self.root / "config.json").read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            music.music_main(["clear"], self.home)
        self.assertFalse((self.root / "cache").exists())
        self.assertEqual((self.root / "config.json").read_bytes(), config)
        self.assertEqual(other.read_text(), "preserve")
        self.assertTrue(self.script.exists())
        self.assertTrue((self.songs / "Quiet.ootrs").exists())

    def test_clear_refuses_symlinks_hardlinks_and_running_session(self):
        self.init()
        cache = self.root / "cache"
        cache.mkdir()
        outside = self.home / "outside"
        outside.write_text("preserve")
        linked = cache / "linked"
        linked.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "Unsafe music cache"):
            music._music_clear(self.root)
        linked.unlink()
        os.link(outside, linked)
        with self.assertRaisesRegex(ValueError, "Unsafe music cache"):
            music._music_clear(self.root)
        linked.unlink()
        with music._music_lock(self.root), self.assertRaisesRegex(ValueError, "Music is running"):
            music._music_clear(self.root)
        self.assertEqual(outside.read_text(), "preserve")

    def test_clear_absent_and_forget_leave_other_paths(self):
        with contextlib.redirect_stdout(io.StringIO()):
            music.music_main(["clear"], self.home)
        self.assertFalse(self.root.exists())
        self.init()
        with contextlib.redirect_stdout(io.StringIO()):
            music.music_main(["forget"], self.home)
        self.assertFalse(music.music_available(self.home))
        self.assertTrue(self.script.exists())

    def test_pcm_spectrum_follows_frequency_not_animation_time(self):
        path = self.home / "tone.wav"
        self.wav(path, frequency=440)
        with wave.open(str(path), "rb") as audio:
            low = music._music_levels(audio, 0)
            repeat = music._music_levels(audio, 0)
            empty = music._music_levels(audio, 1)
        self.wav(path, frequency=2000)
        with wave.open(str(path), "rb") as audio:
            high = music._music_levels(audio, 0)
        self.assertEqual(low, repeat)
        self.assertEqual(empty, [0.0] * 24)
        self.assertLess(low.index(max(low)), high.index(max(high)))
        self.assertGreater(max(low), 0.5)

    def test_plain_frames_and_child_environment_do_not_expose_keys(self):
        with mock.patch.dict(os.environ, {"GODMODE_PLAIN": "1", "GH_TOKEN": "synthetic-never-propagated"}):
            self.assertNotIn("GH_TOKEN", music._music_env())
            self.assertFalse(music._music_animated())
            rows = music.music_visual_rows([0, 0.5, 1], 12, 180)
            self.assertNotIn("\x1b", "\n".join(rows))

    def test_invalid_duration_and_action_arguments_do_not_touch_disk(self):
        for args in (["play", "--seconds", "nan"], ["play", "--seconds", "0"], ["clear", "extra"], ["status", "--songs", "/tmp"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                music.music_main(args, self.home)
        self.assertFalse(self.root.exists())

    def test_child_errors_are_bounded_and_not_printed(self):
        with self.assertRaises(ValueError) as error:
            music._music_run([sys.executable, "-c", "import sys; print('synthetic-secret'); sys.exit(1)"])
        self.assertNotIn("synthetic-secret", str(error.exception))

    def test_cancellation_kills_owned_process_group_not_unrelated_child(self):
        pidfile = self.home / "child.pid"
        grandchild = ("import os,pathlib,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                      "pathlib.Path(" + repr(str(pidfile)) + ").write_text(str(os.getpid())); time.sleep(60)")
        script = ("import subprocess,time,pathlib,sys\n"
                  "child=subprocess.Popen([sys.executable,'-c'," + repr(grandchild) + "])\n"
                  "time.sleep(60)\n")
        unrelated = subprocess.Popen(["/bin/sleep", "60"])
        def cancel_when_ready(active):
            return pidfile.exists()
        try:
            with mock.patch.object(music, "_music_quit", side_effect=cancel_when_ready), self.assertRaises(KeyboardInterrupt):
                music._music_run([sys.executable, "-c", script], active=True)
            self.assertIsNone(unrelated.poll())
            pid = int(pidfile.read_text())
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.02)
            else:
                self.fail("owned synth descendant survived cancellation")
        finally:
            unrelated.terminate()
            unrelated.wait()

    def test_render_uses_local_script_private_cache_and_verifies_wav(self):
        config = self.init()
        def synth(command, frame=None, active=False, timeout=180, **kwargs):
            self.assertEqual(command[1], str(self.script))
            self.assertNotIn("joy.py", command)
            cache = Path(command[command.index("--cache-dir") + 1])
            folder = cache / ("f" * 64)
            folder.mkdir()
            self.wav(folder / "render.wav")
            details = {"cache_key": "f" * 64, "wav_sha256": music._music_sha(folder / "render.wav"), "mode": "piano"}
            export = Path(command[command.index("--output") + 1])
            export.with_suffix(".synthesis.json").write_text(json.dumps(details))
            return "Cache hit: 0.1s"
        with mock.patch.object(music, "_music_run", side_effect=synth), contextlib.redirect_stdout(io.StringIO()):
            path, details, hit = music._music_render(self.root, config, self.songs / "Quiet.ootrs", 15)
        self.assertTrue(hit)
        self.assertEqual(path.parent.name, "f" * 64)
        self.assertFalse(list(self.root.glob(".render-*")))

    def test_cancelled_render_removes_only_new_empty_backend_lock(self):
        config = self.init()
        cache = self.root / "cache"
        cache.mkdir()
        old = cache / ("a" * 64 + ".lock")
        old.mkdir()
        new = cache / ("b" * 64 + ".lock")
        def cancel(*args, **kwargs):
            new.mkdir()
            raise KeyboardInterrupt()
        with mock.patch.object(music, "_music_run", side_effect=cancel), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(KeyboardInterrupt):
            music._music_render(self.root, config, self.songs / "Quiet.ootrs", 15)
        self.assertTrue(old.exists())
        self.assertFalse(new.exists())

    def pty_player(self):
        self.init()
        path = self.home / "fixture.wav"
        self.wav(path, seconds=2)
        bindir = self.home / "bin"
        bindir.mkdir()
        player = bindir / "afplay"
        player.write_text("#!/bin/sh\nexec /bin/sleep 60\n")
        player.chmod(0o700)
        program = ("import sys;sys.path.insert(0," + repr(str(Path(music.__file__).parent)) + ")\n"
                   "import godmode_music as m\n"
                   "from pathlib import Path\n"
                   "m._music_render=lambda *a,**k:(Path(" + repr(str(path)) + "),{'title':'Fixture','mode':'piano'},True)\n"
                   "sys.exit(m.music_main(['play','Quiet','--seconds','60']," + repr(str(self.home)) + "))\n")
        env = {"PATH": str(bindir) + ":/usr/bin:/bin", "HOME": str(self.home), "TERM": "xterm-256color"}
        return Terminal([sys.executable, "-c", program], env, cols=80, rows=24)

    def test_pty_long_fragmented_paste_never_quits_echoes_or_reaches_shell(self):
        player = self.pty_player()
        try:
            player.seen("q stop")
            secret = b"qSECRET_MUSIC_FIXTURE_" * 1000 + b"\necho NEVER_RUN\n"
            before = len(player.capture)
            player.send(b"\x1b[200~" + secret[:9000])
            player.settle(0.2)
            self.assertIsNone(player.process.poll())
            # The animation keeps running while the paste is incomplete.
            self.assertGreater(len(player.capture), before)
            player.send(secret[9000:] + b"\x1b[201~")
            player.settle(0.2)
            self.assertIsNone(player.process.poll())
            self.assertNotIn(b"SECRET_MUSIC_FIXTURE", player.capture)
            self.assertNotIn(b"NEVER_RUN", player.capture)
            player.send(b"q" + b"DO_NOT_ECHO" * 200)
            player.done(130)
            self.assertTrue(b"DO_NOT_ECHO" not in player.capture, "post-quit input was echoed")
        finally:
            player.close()

    def test_pty_resize_clears_old_frame_and_recomputes_rows(self):
        player = self.pty_player()
        try:
            player.seen("q stop")
            for cols, rows in ((32, 12), (10, 8), (80, 24)):
                mark = len(player.capture)
                fcntl.ioctl(player.slave, terminal.termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
                os.killpg(player.process.pid, signal.SIGWINCH)
                player.settle(0.35)
                output = bytes(player.capture[mark:])
                self.assertIn(b"\x1b[J", output)
                complete = [plain(chunk) for chunk in output.split(b"\x1b[J")[1:] if "q stop" in plain(chunk)]
                self.assertTrue(complete, "resize did not finish a frame")
                last = complete[-1].split("q stop")[0] + "q stop"
                self.assertLessEqual(len(last.splitlines()), rows - 1)
                for line in last.splitlines():
                    self.assertLessEqual(terminal.cells(line), cols - 1)
            player.send(b"\x03")
            player.done(130)
        finally:
            player.close()


class KeyboardPollTests(unittest.TestCase):
    def setUp(self):
        self.read, self.write = os.pipe()
        self.wake, self.wake_write = os.pipe()
        self.keyboard = terminal._Keyboard()
        self.keyboard.fd, self.keyboard.wake = self.read, self.wake
        self.keyboard.pending, self.keyboard.events = bytearray(), []
        self.keyboard.paste, self.keyboard.rejected = None, False

    def tearDown(self):
        for fd in (self.read, self.write, self.wake, self.wake_write):
            os.close(fd)

    def test_poll_buffers_fragmented_paste_without_blocking_or_key_events(self):
        os.write(self.write, b"\x1b[200~qprivate\n")
        started = time.monotonic()
        self.assertIsNone(self.keyboard.poll())
        self.assertLess(time.monotonic() - started, 0.1)
        os.write(self.write, b"data\x1b[20")
        self.assertIsNone(self.keyboard.poll())
        os.write(self.write, b"1~")
        self.assertEqual(self.keyboard.poll(), ("paste", b"qprivate\ndata"))
        self.assertIsNone(self.keyboard.poll())

    def test_poll_distinguishes_isolated_escape_and_arrow_fragments(self):
        os.write(self.write, b"\x1b")
        self.assertIsNone(self.keyboard.poll())
        os.write(self.write, b"[A")
        self.assertEqual(self.keyboard.poll(), ("key", "up"))
        os.write(self.write, b"\x1b")
        self.assertIsNone(self.keyboard.poll())
        self.assertEqual(self.keyboard.poll(0.12), ("key", "esc"))


if __name__ == "__main__":
    unittest.main()
