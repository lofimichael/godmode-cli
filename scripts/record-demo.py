#!/usr/bin/env python3
"""Record the real onboarding UI into a short GIF using synthetic credentials.

The PTY transcript stays in memory. Nothing reads the normal Godmode config,
opens a browser, contacts a provider, or captures the desktop.
"""
from __future__ import annotations

import argparse
import codecs
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time

from PIL import Image, ImageDraw, ImageFont
import pyte

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
from pty_support import Terminal  # noqa: E402

SYNTHETIC = "cf_DEMO_ONLY_NOT_A_REAL_CREDENTIAL_6d8f"
THEMES = {
    # ANSI colors belong to the terminal. These two representative themes let
    # reviewers inspect the same actual output on both light and dark surfaces.
    "dark": {
        "bg": "#161b22", "fg": "#d8dee9", "caption": "#a7afba", "border": "#58616c",
        "palette": {
            "black": "#161b22", "red": "#e78b83", "green": "#91c49b",
            "brown": "#d7ba7d", "blue": "#8cb4e8", "magenta": "#bd9dd5",
            "cyan": "#82c3cb", "white": "#d8dee9", "brightblack": "#a7afba",
            "brightred": "#f2a29b", "brightgreen": "#aad7b2", "brightbrown": "#e7cd9c",
            "brightblue": "#accbf3", "brightmagenta": "#d2b8e4", "brightcyan": "#a0d5dc",
            "brightwhite": "#ffffff",
        },
    },
    "light": {
        "bg": "#ffffff", "fg": "#24292f", "caption": "#57606a", "border": "#8c959f",
        "palette": {
            "black": "#24292f", "red": "#b42318", "green": "#1a7f37",
            "brown": "#806000", "blue": "#0550ae", "magenta": "#8250df",
            "cyan": "#006b75", "white": "#6e7781", "brightblack": "#57606a",
            "brightred": "#a40e26", "brightgreen": "#116329", "brightbrown": "#633c01",
            "brightblue": "#0969da", "brightmagenta": "#6639ba", "brightcyan": "#075b63",
            "brightwhite": "#24292f",
        },
    },
}


def color(value: str, default: str, palette: dict[str, str]) -> str:
    if value == "default":
        return default
    if re.fullmatch(r"[0-9a-fA-F]{6}", value):
        return "#" + value
    return palette.get(value, default)


def font_path(explicit: Path | None) -> Path:
    if explicit:
        if not explicit.is_file():
            raise RuntimeError("The requested font file does not exist")
        return explicit
    for candidate in [
        "/System/Library/Fonts/Menlo.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
    ]:
        path = Path(candidate)
        if path.is_file():
            return path
    raise RuntimeError("Pass --font with a local monospace TrueType font")


class Recorder:
    def __init__(self, terminal: Terminal, cols: int, rows: int, font: Path, theme: str = "dark",
                 caption: str = "Interactive setup · synthetic credentials"):
        self.terminal = terminal
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.Stream(self.screen)
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.read_at = 0
        self.cols, self.rows = cols, rows
        self.font = ImageFont.truetype(str(font), 14)
        self.cell_width = math.ceil(self.font.getlength("M"))
        self.cell_height = 18
        self.caption_height = 28
        self.frames: list[Image.Image] = []
        self.durations: list[int] = []
        self.text_colors: set[str] = set()
        self.theme = THEMES[theme]
        self.caption = caption

    def sync(self) -> None:
        # After godmode exits, the test wrapper reports the terminal flags; that line is not Godmode's.
        end = self.terminal.capture.find(b"__PTY_FLAGS=")
        end = len(self.terminal.capture) if end < 0 else end
        # pyte has no faint attribute; draw SGR 2 as the palette's grey so dim text reads as dim.
        chunk = bytes(self.terminal.capture[self.read_at:end]).replace(b"\x1b[2m", b"\x1b[90m")
        self.read_at = max(self.read_at, end)
        self.stream.feed(self.decoder.decode(chunk))

    def wait_for(self, text: str, timeout: float = 8) -> None:
        deadline = time.monotonic() + timeout
        while True:
            self.terminal.drain(0.05)
            self.sync()
            if text in "\n".join(self.screen.display):
                return
            if self.terminal.process.poll() is not None:
                raise RuntimeError("CLI exited before the expected demo state")
            if time.monotonic() > deadline:
                raise RuntimeError(f"Timed out waiting for demo state: {text}")

    def settle(self) -> None:
        # Finish an incremental terminal write before taking a screen snapshot.
        quiet_since = time.monotonic()
        deadline = quiet_since + 3
        while time.monotonic() < deadline:
            previous = len(self.terminal.capture)
            self.terminal.drain(0.03)
            self.sync()
            if len(self.terminal.capture) != previous:
                quiet_since = time.monotonic()
            elif time.monotonic() - quiet_since >= 0.06:
                return
        raise RuntimeError("Terminal output did not settle before a demo frame")

    def capture(self, duration: int) -> None:
        self.settle()
        text = "\n".join(self.screen.display)
        if SYNTHETIC in text or "DEMO_ONLY_NOT_A_REAL" in text:
            raise RuntimeError("Credential input unexpectedly appeared in a frame")
        image = Image.new("RGB", (self.cols * self.cell_width,
                                   self.rows * self.cell_height + self.caption_height), self.theme["bg"])
        draw = ImageDraw.Draw(image)
        draw.text((9, 5), self.caption, font=self.font, fill=self.theme["caption"])
        draw.line((0, self.caption_height - 2, image.width, self.caption_height - 2), fill=self.theme["border"])
        for y in range(self.rows):
            for x in range(self.cols):
                char = self.screen.buffer[y][x]
                foreground = color(char.fg, self.theme["fg"], self.theme["palette"])
                background = color(char.bg, self.theme["bg"], self.theme["palette"])
                if char.reverse:
                    foreground, background = background, foreground
                px, py = x * self.cell_width, y * self.cell_height + self.caption_height
                draw.rectangle((px, py, px + self.cell_width - 1, py + self.cell_height - 1), fill=background)
                if char.data and char.data != " ":
                    self.text_colors.add(foreground)
                    draw.text((px, py - 1), char.data, font=self.font, fill=foreground,
                              stroke_width=0.25 if char.bold else 0)
                if char.underscore:
                    draw.line((px, py + 15, px + self.cell_width - 1, py + 15), fill=foreground)
        if not self.screen.cursor.hidden:
            x, y = self.screen.cursor.x, self.screen.cursor.y
            if x < self.cols and y < self.rows:
                px, py = x * self.cell_width, y * self.cell_height + self.caption_height
                draw.line((px, py + 16, px + self.cell_width - 1, py + 16), fill=self.theme["fg"], width=2)
        self.frames.append(image)
        self.durations.append(duration)

    def write(self, destination: Path) -> None:
        if not self.frames or sum(self.durations) > 10_000:
            raise RuntimeError("The demo must contain frames and last at most ten seconds")
        if len(self.text_colors) < 3:
            raise RuntimeError("The setup recording did not retain its terminal text colors")
        # Derive the GIF palette from full-resolution cells. Downsampling thin
        # colored glyphs first averages them into the background and dims the
        # ANSI colors even though the actual terminal output retains them.
        width, height = self.frames[0].size
        sample = Image.new("RGB", (width, height * len(self.frames)), self.theme["bg"])
        for i, frame in enumerate(self.frames):
            sample.paste(frame, (0, i * height))
        palette = sample.quantize(colors=256, dither=Image.Dither.NONE)
        frames = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in self.frames]
        destination.parent.mkdir(parents=True, exist_ok=True)
        frames[0].save(destination, save_all=True, append_images=frames[1:],
                       duration=self.durations, loop=0, disposal=2, optimize=True)
        with Image.open(destination) as check:
            elapsed = 0
            for frame in range(check.n_frames):
                check.seek(frame)
                elapsed += check.info.get("duration", 0)
            if elapsed != sum(self.durations) or check.info.get("loop") != 0:
                raise RuntimeError("GIF timing or looping verification failed")
            print(f"Recorded {check.n_frames} frames, {elapsed / 1000:.1f}s, "
                  f"{check.width}x{check.height}, {destination.stat().st_size:,} bytes")


def record_intro(binary, config, env, font, args):
    terminal = Terminal([str(binary)], env, cols=80, rows=22)
    recorder = Recorder(terminal, 80, 22, font, args.theme, "Godmode · first-run welcome")
    names = ["welcome", "risk", "profile", "home"]
    try:
        for number in range(1, 4):
            recorder.wait_for("%d / 3" % number)
            recorder.capture(1800)
            terminal.send(b"\r")
        recorder.wait_for("Esc quit")
        recorder.capture(1600)
        terminal.send(b"\x1b")
        terminal.done()
        assert sorted(path.name for path in config.iterdir()) == ["intro.seen"]
        recorder.write(args.output.resolve())
        if args.frames_dir:
            args.frames_dir.mkdir(parents=True, exist_ok=True)
            for name, frame in zip(names, recorder.frames, strict=True):
                frame.save(args.frames_dir / f"{name}.png")
    finally:
        terminal.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=REPO / "target/godmode")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--intro", action="store_true", help="record the three-page welcome and the home screen instead of a first key")
    parser.add_argument("--font", type=Path)
    parser.add_argument("--theme", choices=THEMES, default="dark", help="terminal palette for the recording")
    parser.add_argument("--frames-dir", type=Path, help="also save readable PNGs of the recorded states")
    args = parser.parse_args()
    args.output = args.output or (REPO / "target/intro.gif" if args.intro else REPO / "docs/images/setup.gif")
    binary = args.binary.resolve()
    if not binary.is_file():
        parser.error("Build the readable script first")
    font = font_path(args.font)
    temp_parent = "/private/tmp" if Path("/private/tmp").is_dir() else None
    with tempfile.TemporaryDirectory(prefix="godmode-demo-", dir=temp_parent) as temp:
        root = Path(temp).resolve()
        config = root / ".godmode"
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(root),
               "TERM": "xterm-256color", "COLORTERM": "truecolor"}
        if args.intro:
            record_intro(binary, config, env, font, args)
            return
        # Start where a returning user starts: the welcome was seen, nothing is saved yet.
        # The marker affects only the isolated synthetic home.
        config.mkdir(mode=0o700)
        os.close(os.open(config / "intro.seen", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        terminal = Terminal([str(binary)], env, cols=84, rows=26)
        recorder = Recorder(terminal, 84, 26, font, args.theme)
        try:
            recorder.wait_for("Esc quit")
            recorder.wait_for("0%")
            recorder.capture(1300)
            terminal.send(b"\x1b[B\r")  # Down to Providers, then Enter
            recorder.wait_for("❯ GitHub")
            recorder.capture(1000)
            terminal.send(b"\x1b[B")
            recorder.wait_for("❯ Cloudflare")
            recorder.capture(700)
            terminal.send(b"\r")
            recorder.wait_for("Create a Cloudflare API token")
            recorder.wait_for("CLOUDFLARE_API_TOKEN=sealed(…)")
            recorder.capture(1900)
            terminal.paste(SYNTHETIC)
            recorder.wait_for("CLOUDFLARE_API_TOKEN=sealed(cf_•••••d8f)")
            recorder.wait_for("Paste your token: cf_•••••d8f")
            recorder.capture(1800)
            assert not (config / ".env.godmode").exists() or SYNTHETIC not in (config / ".env.godmode").read_text()
            terminal.send(b"\r")
            recorder.wait_for("Saved CLOUDFLARE_API_TOKEN=sealed(cf_•••••d8f)")
            recorder.wait_for("❯ Vercel")
            recorder.capture(1100)
            terminal.send(b"\x1b")
            recorder.wait_for("11%")
            recorder.capture(1700)
            terminal.send(b"\x1b")
            recorder.wait_for("Next:")
            terminal.done()
            assert SYNTHETIC.encode() not in terminal.capture, "PTY output exposed synthetic input"
            # Prove this was an actual save in a temporary store, not an animated mockup.
            sys.path.insert(0, str(REPO / "lib"))
            from godmode_store import Store  # noqa: E402
            saved = (config / ".env.godmode").read_text()
            assert SYNTHETIC not in saved and "sealed:v1:" in saved, "the saved value is not sealed"
            assert Store(str(config)).values(["CLOUDFLARE_API_TOKEN"]) == {"CLOUDFLARE_API_TOKEN": SYNTHETIC}
            recorder.write(args.output.resolve())
            if args.frames_dir:
                args.frames_dir.mkdir(parents=True, exist_ok=True)
                names = ["home", "providers", "selected", "prompt", "masked", "saved", "home-after"]
                for name, frame in zip(names, recorder.frames, strict=True):
                    frame.save(args.frames_dir / f"{name}.png")
        finally:
            terminal.close()


if __name__ == "__main__":
    main()
