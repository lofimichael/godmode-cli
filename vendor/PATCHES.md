# Local vendor patches

## Ultraviolet fullscreen cursor movement

- Dependency: `github.com/charmbracelet/ultraviolet` at
  `v0.0.0-20261008173134-6b8d4baf91b4`, used by Bubble Tea `v2.1.1`.
- File: `github.com/charmbracelet/ultraviolet/terminal_renderer.go`,
  `relativeCursorMove`.
- Change: fullscreen downward cursor movement uses its existing CSI movement
  sequence instead of choosing a shorter bare line feed. Inline movement and
  intentional scrolling retain their original behavior.

The native intro's color animation exposed a transport mismatch. The renderer
assumes a bare LF keeps the current column after its input TTY enters raw mode.
A host PTY with output processing enabled, or a terminal in newline mode, can
instead map LF to CRLF. The next logo fragment is then painted at column zero,
leaving persistent fragments beside the centered logo. Restoring `OPOST|ONLCR`
in a disposable real PTY reproduced the reported screenshot's exact pattern.

CSI cursor movement preserves the column regardless of LF mapping. Fullscreen
targets are within the viewport, so this does not depend on newline scrolling.
The patch adds no redraw timer, whole-screen clearing, output rewriting, or
repeated termios changes. It costs a few additional bytes for short downward
moves.

Regression tests in `terminal_renderer_godmode_test.go` exercise both newline
mapping settings, changing styled logo-tail rows through the real renderer,
and unchanged inline scrolling. Run them explicitly because Go excludes vendor
tests from `./...`:

```sh
go test -mod=vendor ./vendor/github.com/charmbracelet/ultraviolet -run TestGodmode
```

The original regression failed before this patch. Native regressions use only a
temporary HOME and public intro content. They enable PTY output processing or
emulated terminal newline mode after the first complete frame, then compare exact
logo cells after 8.2 seconds (more than two 3.84-second animation cycles). With
`scripts/demo-requirements.txt` installed in the demo environment, run:

```sh
GODMODE_TEST_NATIVE_BINARY="$PWD/target/godmode-native" target/demo-venv/bin/python -m unittest discover -s tests -p test_native_renderer.py -v
```

The shared capture emulator also implements CSI Z backward tabs. Without this
valid renderer operation, stock pyte invented unrelated right-edge duplicates;
a focused terminal-model assertion covers the added parser behavior.

When updating or regenerating `vendor`, retain this patch and its tests until an
upstream equivalent passes the ONLCR reproduction. This is separate from Bubble
Tea's [stale resize frame fix](https://github.com/charmbracelet/bubbletea/pull/1856)
and [tab-stop refresh proposal](https://github.com/charmbracelet/bubbletea/pull/1847);
neither addresses LF mapping in ordinary animation frames.
