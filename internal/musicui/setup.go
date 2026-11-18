package musicui

import (
	"github.com/charmbracelet/x/ansi"
	"strings"
)

// Setup remains a readable, scrollable guide; the backend owns preparation.
func (m model) setupLines() []string {
	guide := []string{
		"Play a cue: godmode jingle play",
		"Only mpv needed; no track library.",
		"",
		"Music uses your local .ootrs tracks.",
		"godmode music setup --songs DIR",
		"Replace DIR with your folder's path.",
		"Press R here after setup.",
		"",

		"Godmode turns local .ootrs sequences into audio. Setup builds the included synth once, offline.",
		"",
		"EXAMPLE FOLDER",
		`godmode music setup --songs "$HOME/Music/Sequences"`,
		"Use the folder containing your .ootrs files. Subfolders become collections.",
		"Quote paths containing spaces.",
		"",
		"REQUIRED TOOLS (macOS)",
		"brew install mpv ffmpeg cmake",
		"Also requires Python 3.9+, a C/C++ compiler.",
		"If the compiler is missing, install Apple's command line tools:",
		"xcode-select --install",
		"Setup validates the folder and tools, builds the included synth, then links the library after success.",
		"",
		"AFTER SETUP",
		"Press R to reload this screen, then browse collections or search with /.",
		"Enter opens a collection. Choose a track to begin playback.",
	}

	rows := []string{}
	for _, line := range guide {
		rows = append(rows, strings.Split(ansi.Wrap(line, m.innerWidth(), ""), "\n")...)
	}
	return rows
}
