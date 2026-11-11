"""Optional-media checks using synthetic files and owned sleeping processes only."""
import contextlib
import hashlib
import io
import os
from pathlib import Path
import shlex
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import godmode_picard as media


class PicardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="godmode-picard-test-", dir="/tmp")
        self.root = Path(self.temp.name).resolve()
        self.state = self.root / "state"
        self.cache = self.state / "picard"

    def tearDown(self):
        self.temp.cleanup()

    def test_link_and_absent_stop_do_not_create_any_state(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(media.picard("link", self.state), 0)
            self.assertEqual(media.picard("stop", self.state), 0)
        self.assertIn(media.PICARD_SOURCE_URL, output.getvalue())
        self.assertFalse(self.state.exists())
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
            media.picard("show", self.state)
        self.assertFalse(self.state.exists())

    def test_cache_hash_permissions_and_symlink_refusal(self):
        media._picard_directory(self.cache, create=True)
        data = b"synthetic audio fixture"
        digest = hashlib.sha256(data).hexdigest()
        fixture = ("https://example.invalid/never-requested", digest, len(data), "excerpt.wav")
        destination = self.cache / "excerpt.wav"
        destination.write_bytes(data)
        destination.chmod(0o600)
        with mock.patch.dict(media.PICARD_MEDIA, {"audio": fixture}):
            self.assertEqual(media._picard_cached(self.cache, "audio"), destination)
            destination.write_bytes(b"corrupt fixture")
            with self.assertRaises(ValueError):
                media._picard_cached(self.cache, "audio")
            destination.write_bytes(data)
            destination.chmod(0o644)
            with self.assertRaises(ValueError):
                media._picard_cached(self.cache, "audio")
            destination.unlink()
            outside = self.root / "outside"
            outside.write_bytes(data)
            outside.chmod(0o600)
            destination.symlink_to(outside)
            with self.assertRaises((OSError, ValueError)):
                media._picard_cached(self.cache, "audio")
            self.assertEqual(outside.read_bytes(), data)

    def test_bad_download_is_not_cached_and_temporary_file_is_removed(self):
        media._picard_directory(self.cache, create=True)
        def synthetic_download(command, *args, **kwargs):
            Path(command[command.index("--output") + 1]).write_bytes(b"not the expected image")
        with mock.patch.object(media, "_picard_run", side_effect=synthetic_download), self.assertRaises(ValueError):
            media._picard_cached(self.cache, "image")
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_bmp_bounds_rgb_and_plain_render(self):
        pixels = b"\x00\x00\xff\x00\xff\x00\x00\x00" + b"\xff\x00\x00\xff\xff\xff\x00\x00"
        bitmap = (struct.pack("<2sIHHI", b"BM", 54 + len(pixels), 0, 0, 54)
                  + struct.pack("<IiiHHIIiiII", 40, 2, -2, 1, 24, 0, len(pixels), 0, 0, 0, 0) + pixels)
        rows = media._picard_bmp(bitmap)
        self.assertEqual(rows, [[(255, 0, 0), (0, 255, 0)], [(0, 0, 255), (255, 255, 255)]])
        with contextlib.redirect_stdout(io.StringIO()) as output:
            media._picard_render(rows, 2, 1, True)
        self.assertTrue(output.getvalue().isascii())
        self.assertNotIn("\x1b", output.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as output:
            media._picard_render(rows, 2, 1, False)
        self.assertIn("38;2;255;0;0", output.getvalue())
        for invalid in [bitmap[:55], b"bad", bitmap[:18] + struct.pack("<i", 10000000) + bitmap[22:]]:
            with self.assertRaises(ValueError):
                media._picard_bmp(invalid)

    def controller(self, download=False):
        media._picard_directory(self.cache, create=True)
        data = b"synthetic audio fixture"
        if not download:
            (self.cache / "excerpt.wav").write_bytes(data)
            (self.cache / "excerpt.wav").chmod(0o600)
        executable = self.root / ("fake-curl" if download else "fake-player")
        pid_file = self.root / "owned-child-pid"
        executable.write_text("#!/bin/sh\nprintf '%s' \"$$\" > " + shlex.quote(str(pid_file)) + "\nexec /bin/sleep 60\n")
        executable.chmod(0o700)
        fixture = ("https://example.invalid/never-requested", hashlib.sha256(data).hexdigest(), len(data), "excerpt.wav")
        mapping = {"afplay": str(executable), "curl": str(executable)}
        program = ("import sys; sys.path.insert(0, " + repr(str(Path(media.__file__).parent)) + ")\n"
                   "import godmode_picard as m\n"
                   "m.PICARD_MEDIA['audio'] = " + repr(fixture) + "\n"
                   "m.shutil.which = " + repr(mapping) + ".get\n"
                   "try:\n m.picard('play', " + repr(str(self.state)) + ")\n"
                   "except KeyboardInterrupt:\n sys.exit(130)\n")
        child = subprocess.Popen([sys.executable, "-c", program], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env={"PATH": "/usr/bin:/bin", "HOME": str(self.root)})
        deadline = time.monotonic() + 5
        # The stub's shell creates the file before printf fills it; wait for the digits.
        while not (pid_file.exists() and pid_file.read_text().strip()):
            if child.poll() is not None or time.monotonic() > deadline:
                child.kill()
                _, error = child.communicate()
                self.fail("Synthetic Picard controller did not start its owned child: " + error.decode())
            time.sleep(0.02)
        return child, int(pid_file.read_text())

    def stop_controller(self, controller, pid, signal_stop=False):
        try:
            if signal_stop:
                controller.terminate()
            else:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(media.picard("stop", self.state), 0)
            self.assertEqual(controller.wait(timeout=5), 130 if signal_stop else 0)
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)
            self.assertFalse((self.cache / "p.sock").exists())
        finally:
            if controller.poll() is None:
                controller.kill()
                controller.wait()
            controller.stdout.close()
            controller.stderr.close()

    def test_external_stop_reaps_only_the_owned_player(self):
        unrelated = subprocess.Popen(["/bin/sleep", "60"], env={"PATH": "/usr/bin:/bin"})
        try:
            controller, pid = self.controller()
            self.stop_controller(controller, pid)
            self.assertIsNone(unrelated.poll())
        finally:
            unrelated.terminate()
            unrelated.wait()

    def test_stop_cancels_owned_download_before_playback(self):
        controller, pid = self.controller(download=True)
        self.stop_controller(controller, pid)
        self.assertFalse((self.cache / "excerpt.wav").exists())
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_sigterm_reaps_owned_player_and_removes_socket(self):
        controller, pid = self.controller()
        self.stop_controller(controller, pid, signal_stop=True)


if __name__ == "__main__":
    unittest.main()
