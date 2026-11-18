package musicui

import (
	"github.com/charmbracelet/x/ansi"
	"strings"
)

var helpText = []string{
	"LIBRARY & QUEUE",
	"↑ / ↓     Choose a row",
	"Enter      Open collection / play track",
	"Esc        Clear search / go back",
	"/          Search the whole library",
	"Enter/Tab  Finish search; focus results",
	"Tab        Switch library and queue",
	"a          Append track or collection",
	"i          Full title and collection details",
	"c          Open selected track's collection",
	"A          Append its whole collection",
	"Ctrl+U     Clear text while searching",
	"d / Delete Remove selected queue entry",
	"",
	"PLAYBACK",
	"Space      Pause / resume",
	"n / p      Next / previous track",
	"< / >      Seek back / forward 5 sec",
	"+ / -      Volume in 5% steps",
	"r          Repeat: off → all → one",
	"s          Toggle shuffle",
	"x          Stop playback; keep queue",
	"",
	"CLOSE THE VIEW",
	"q / Ctrl+C Close; playback stays alive",
	"godmode music stop  Stops from any shell",
	"",
	"JINGLES",
	"godmode jingle play  Play a cue; only mpv needed",
	"No track library or synth setup needed for jingles.",
	"",
	"R          Reload library and setup",
	"Enter replaces queue with visible tracks",
	"at the selected position. a appends.",
}

// Wrap descriptions with a hanging indent so every word survives small screens.
// Scroll offsets refer to the wrapped rows, not the original document lines.
func helpLines(width int) []string {
	width = max(1, width)
	rows := []string{}
	for _, line := range helpText {
		split := strings.Index(line, "  ")
		if split < 0 {
			rows = append(rows, strings.Split(ansi.Wrap(line, width, ""), "\n")...)
			continue
		}
		key, description := strings.TrimSpace(line[:split]), strings.TrimSpace(line[split:])
		indent := max(11, ansi.StringWidth(key)+2)
		if width-indent < 10 {
			rows = append(rows, strings.Split(ansi.Wrap(key, width, ""), "\n")...)
			for _, part := range strings.Split(ansi.Wrap(description, max(1, width-2), ""), "\n") {
				rows = append(rows, strings.Repeat(" ", min(2, width-1))+part)
			}
			continue
		}
		parts := strings.Split(ansi.Wrap(description, width-indent, ""), "\n")
		for i, part := range parts {
			prefix := strings.Repeat(" ", indent)
			if i == 0 {
				prefix = pad(key, indent)
			}
			rows = append(rows, prefix+part)
		}
	}
	return rows
}
