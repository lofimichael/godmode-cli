#!/usr/bin/env python3
"""Record actual native intro and active-setup screens in disposable PTYs.

Uses scripts/demo-requirements.txt. Only synthetic keys enter the fixture home.
No ordinary Godmode files, provider accounts, desktop or audio are accessed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import time
from datetime import date

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("native_record", REPO / "scripts/record-native.py")
NATIVE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NATIVE)

SYNTHETIC = "synthetic_V019_NOT_A_PROVIDER_KEY_173920"


class CaptureStream(NATIVE.NativeStream):
    """Ignore xterm keyboard negotiation, which pyte mistakes for SGR 4.

    This filters only nonvisual CSI > ... m controls. Ordinary styling reaches
    the emulator unchanged, including genuine underline and reset sequences.
    """

    pending = ""

    def feed(self, text):
        text = self.pending + text
        self.pending = ""
        partial = re.search(r"\x1b(?:\[(?:>[0-9;]*)?)?$", text)
        if partial:
            self.pending, text = partial.group(), text[:partial.start()]
        super().feed(re.sub(r"\x1b\[>[0-9;]*m", "", text))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=REPO / "target/godmode-native")
    parser.add_argument("--output", type=Path, default=REPO / "target/v019-ui")
    parser.add_argument("--font", type=Path)
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    binary, output = args.binary.resolve(), args.output.resolve()
    if not binary.is_file():
        parser.error("Build the native candidate first.")
    output.mkdir(parents=True, exist_ok=True)
    font = NATIVE.DEMO.font_path(args.font)
    evidence = {"binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "screens": [], "checks": []}
    warning_cells = None

    def fixed_cells(capture):
        # Only these decorative connector cells change. Logo letters, layout
        # and every word must stay at the same actual terminal coordinates.
        return tuple(row.replace("▪", "─").replace("◆", "─").replace("▶", "─")
                     for row in capture.screen.display)

    def environment(root, theme="dark", motion=False, colors=True):
        env = {"HOME": str(root), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
               "TERM": "xterm-256color", "COLORTERM": "truecolor", "PYTHONUTF8": "1",
               "COLORFGBG": "0;15" if theme == "light" else "15;0",
               "CODEX_HOME": str(root / ".codex"), "COPILOT_HOME": str(root / ".copilot")}
        if not motion:
            env["GODMODE_NO_MOTION"] = "1"
        if not colors:
            env["NO_COLOR"] = "1"
        return env

    def recorder(env, words, cols, rows, theme):
        terminal = NATIVE.NativeTerminal([str(binary), *words], env, cols=cols, rows=rows)
        capture = NATIVE.Recorder(terminal, cols, rows, font, theme=theme,
                                  caption="Godmode CLI · " + args.date)
        capture.stream = CaptureStream(capture.screen)
        return terminal, capture

    def no_secret(terminal):
        assert SYNTHETIC.encode() not in terminal.capture, "synthetic key reached terminal output"
        assert b"V019_NOT_A_PROVIDER" not in terminal.capture, "synthetic key middle reached terminal output"

    def shot(capture, name, cols, rows, theme):
        capture.capture(500)
        no_secret(capture.terminal)
        capture.frames[-1].save(output / (name + ".png"))
        evidence["screens"].append({"file": name + ".png", "columns": cols, "rows": rows,
                                    "theme": theme, "reduced_motion": True})

    for cols, rows, theme, colors in ((80, 24, "dark", True), (40, 18, "dark", True), (110, 36, "dark", True),
                                      (80, 24, "light", True), (80, 24, "dark", False)):
        with tempfile.TemporaryDirectory(prefix="godmode-v019-intro-") as temp:
            root = Path(temp).resolve()
            env = environment(root, theme, colors=colors)
            terminal, capture = recorder(env, ["intro"], cols, rows, theme)
            suffix = f"{cols}x{rows}-{theme}" + ("-no-color" if not colors else "")
            try:
                capture.wait_for("Enter I understand")
                assert not (root / ".godmode").exists(), "intro created files before acknowledgement"
                shot(capture, "intro-warning-" + suffix, cols, rows, theme)
                if (cols, rows, theme, colors) == (80, 24, "dark", True):
                    warning_cells = fixed_cells(capture)
                if not colors:
                    assert not re.search(rb"\x1b\[[0-9:;]*m", bytes(terminal.capture)), "NO_COLOR emitted styled text"
                    assert not any(cell.underscore for row in capture.screen.buffer.values()
                                   for cell in row.values()), "terminal model invented underline"
                terminal.send(b"\r")
                capture.wait_for("Enter finish")
                assert not (root / ".godmode/intro.seen").exists(), "first card marked intro complete"
                shot(capture, "intro-power-" + suffix, cols, rows, theme)
                terminal.send(b"\r")
                terminal.done()
                assert sorted(p.name for p in (root / ".godmode").iterdir()) == ["intro.seen"]
                evidence["checks"].append("two-stage intro and terminal restoration: " + suffix)
            finally:
                terminal.close()

    with tempfile.TemporaryDirectory(prefix="godmode-v019-first-run-") as temp:
        root = Path(temp).resolve()
        terminal, capture = recorder(environment(root), [], 80, 24, "dark")
        try:
            capture.wait_for("Enter I understand")
            assert not (root / ".godmode").exists()
            terminal.send(b"\r")
            capture.wait_for("Enter open Godmode")
            assert not (root / ".godmode/intro.seen").exists()
            terminal.send(b"\r")
            capture.wait_for("Active setup")
            capture.wait_for("Esc quit")
            assert (root / ".godmode/intro.seen").is_file()
            terminal.send(b"\x03")
            terminal.done(130)
            evidence["checks"].append("first-run intro opens management only after both cards")
        finally:
            terminal.close()

    with tempfile.TemporaryDirectory(prefix="godmode-v019-motion-") as temp:
        env = environment(Path(temp).resolve(), motion=True)
        terminal, capture = recorder(env, ["intro"], 80, 24, "dark")
        # Capture real in-flight terminal frames; the default recorder waits
        # until output settles, which is appropriate only for stills.
        next_frame = time.monotonic()

        def live_frame():
            nonlocal next_frame
            next_frame += .040
            while time.monotonic() < next_frame:
                terminal.drain(max(0, min(.010, next_frame - time.monotonic())))
            capture.sync()

        capture.settle = live_frame
        try:
            capture.wait_for("Enter I understand")
            for stage in range(2):
                next_frame = time.monotonic()
                for frame in range(96):
                    capture.capture(40)
                if stage == 0:
                    terminal.send(b"\r")
                    capture.wait_for("Enter finish")
            terminal.send(b"\r")
            terminal.done()
            capture.write(output / "intro.gif")
            evidence["checks"].append("7.68-second motion recording from actual PTY frames")
        finally:
            terminal.close()

    with tempfile.TemporaryDirectory(prefix="godmode-v019-loop-") as temp:
        root = Path(temp).resolve()
        terminal, capture = recorder(environment(root, motion=True), ["intro"], 80, 24, "dark")
        try:
            capture.wait_for("Enter I understand")
            started = time.monotonic()
            later_styles = set()
            while time.monotonic() - started < 9:
                terminal.drain(.040)
                capture.sync()
                assert fixed_cells(capture) == warning_cells, "looping intro left misplaced glyphs"
                if time.monotonic() - started > 7.68:
                    later_styles.add(tuple((capture.screen.buffer[y][x].fg,
                                            capture.screen.buffer[y][x].bg,
                                            capture.screen.buffer[y][x].bold)
                                           for y in range(24) for x in range(80)))
            assert len(later_styles) >= 3, "intro stopped changing after two cycles"
            assert not (root / ".godmode/intro.seen").exists(), "loop acknowledged itself"
            terminal.send(b"\x1b")
            terminal.done()
            evidence["checks"].append("motion continues after two cycles with unchanged terminal cell layout")
        finally:
            terminal.close()

    for cols, rows, theme in ((80, 24, "dark"), (40, 18, "dark"), (80, 24, "light")):
        with tempfile.TemporaryDirectory(prefix="godmode-v019-management-") as temp:
            root = Path(temp).resolve()
            env = environment(root, theme)
            home = root / ".godmode"
            home.mkdir(mode=0o700)
            (home / "intro.seen").touch(mode=0o600)

            def command(*words, data=None):
                return subprocess.run([str(binary), *words], env=env, input=data, text=True,
                                      capture_output=True, check=True, timeout=15)

            command("env", "create", "studio-test")
            command("--env", "studio-test", "set", "CLOUDFLARE_API_TOKEN", "--stdin", data=SYNTHETIC)
            command("context", "create", "studio")
            command("--context", "studio", "profile", "set", "business_name", "--stdin", data="Example Studio")
            command("use", "--env", "studio-test", "--context", "studio")
            terminal, capture = recorder(env, [], cols, rows, theme)
            suffix = f"{cols}x{rows}-{theme}"
            try:
                capture.wait_for("Esc quit")
                capture.wait_for("Business: studio")
                shot(capture, "home-" + suffix, cols, rows, theme)
                terminal.send(b"\r")
                capture.wait_for("Key environment")
                shot(capture, "active-setup-" + suffix, cols, rows, theme)
                terminal.send(b"\r")
                capture.wait_for("New environment")
                shot(capture, "environments-" + suffix, cols, rows, theme)
                terminal.send(b"\x1b")
                capture.wait_for("Business profile")
                terminal.send(b"\x1b[B\r")
                capture.wait_for("New business")
                shot(capture, "businesses-" + suffix, cols, rows, theme)
                terminal.send(b"\x03")
                terminal.done(130)
                no_secret(terminal)
                evidence["checks"].append("persisted active pair visible in native management: " + suffix)
            finally:
                terminal.close()

    (output / "verification.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({"screens": len(evidence["screens"]), "checks": len(evidence["checks"]), "output": str(output)}))


if __name__ == "__main__":
    main()
