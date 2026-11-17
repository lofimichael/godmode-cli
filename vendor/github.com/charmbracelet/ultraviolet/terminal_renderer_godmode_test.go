package uv

import (
	"bytes"
	"fmt"
	"io"
	"strings"
	"testing"

	"github.com/charmbracelet/colorprofile"
	"github.com/charmbracelet/x/ansi"
)

// ONLCR and terminal LNM may map LF to CRLF even when the renderer's input
// terminal was put in raw mode. A next-row animation update must keep its X.
func TestGodmodeFullscreenDownPreservesColumn(t *testing.T) {
	for _, mapNewline := range []bool{false, true} {
		t.Run(fmt.Sprintf("map-newline-%t", mapNewline), func(t *testing.T) {
			renderer := NewTerminalRenderer(io.Discard, []string{"TERM=xterm-256color"})
			renderer.SetFullscreen(true)
			renderer.SetMapNewline(mapNewline)
			got := relativeCursorMove(renderer, nil, 64, 5, 64, 6, false, false, false)
			if got != ansi.CursorDown(1) {
				t.Fatalf("next-row movement must preserve column independently of LF mapping: %q", got)
			}
		})
	}
}

func TestGodmodeAnimatedFullscreenTransportAvoidsLineFeeds(t *testing.T) {
	var output bytes.Buffer
	renderer := NewTerminalRenderer(&output, []string{"TERM=xterm-256color"})
	renderer.SetColorProfile(colorprofile.TrueColor)
	renderer.SetFullscreen(true)
	renderer.SetRelativeCursor(false)
	renderer.SetTabStops(120)
	renderer.Resize(120, 32)
	screen := NewScreenBuffer(120, 32)
	for frame := 0; frame < 6; frame++ {
		// Adjacent logo-tail rows change color without changing character
		// positions, matching the intro's diagonal highlight.
		text := "\n\n" + strings.Repeat(" ", 64) + fmt.Sprintf("\x1b[38;2;%d;120;100m══╝\x1b[m\n", 150+frame*10) +
			strings.Repeat(" ", 64) + fmt.Sprintf("\x1b[38;2;%d;120;100m██╗\x1b[m", 160+frame*10)
		screen.Clear()
		NewStyledString(text).Draw(screen, screen.Bounds())
		renderer.Render(screen.RenderBuffer)
		if err := renderer.Flush(); err != nil {
			t.Fatal(err)
		}
		if bytes.ContainsAny(output.Bytes(), "\n\v") {
			t.Fatalf("frame %d used a line-feed movement that ONLCR/LNM can relocate to column zero", frame)
		}
		output.Reset()
	}
}

func TestGodmodeInlineMovementKeepsScrollingNewlines(t *testing.T) {
	renderer := NewTerminalRenderer(io.Discard, []string{"TERM=xterm-256color"})
	renderer.SetFullscreen(false)
	renderer.SetRelativeCursor(true)
	got := relativeCursorMove(renderer, nil, 64, 5, 64, 6, false, false, false)
	if got != "\n" {
		t.Fatalf("inline movement must retain its intentional scrolling newline: %q", got)
	}
}
