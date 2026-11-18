// Package musicpackui is the core application's lightweight opt-in card. It
// contains no music engine, synth assets, installer, backend, or credential code.
package musicpackui

import (
	"errors"
	"os"
	"strings"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"
)

type model struct {
	width, height                  int
	plain, light, closing, install bool
}

// Run asks only for the user's install choice. The caller performs installation
// after this function returns and Bubble Tea has restored the terminal.
func Run() (bool, error) {
	m := newModel()
	m.plain = os.Getenv("NO_COLOR") != "" || os.Getenv("CLICOLOR") == "0"
	bg := os.Getenv("COLORFGBG")
	m.light = strings.HasSuffix(bg, ";15") || strings.HasSuffix(bg, ";7")
	final, err := tea.NewProgram(m).Run()
	if err != nil {
		return false, err
	}
	result, ok := final.(model)
	if !ok {
		return false, errors.New("Music pack card returned an invalid state")
	}
	return result.install, nil
}
func newModel() model         { return model{width: 80, height: 24} }
func (m model) Init() tea.Cmd { return nil }
func (m model) Update(message tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := message.(type) {
	case tea.WindowSizeMsg:
		m.width = max(1, msg.Width)
		m.height = max(1, msg.Height)
	case tea.KeyPressMsg:
		switch msg.String() {
		case "enter":
			m.install = true
			m.closing = true
			return m, tea.Quit
		case "esc", "q", "ctrl+c":
			m.install = false
			m.closing = true
			return m, tea.Quit
		}
	}
	return m, nil
}
func clipped(text string, width int) string { return ansi.Truncate(text, max(1, width), "…") }
func (m model) View() tea.View {
	if m.closing {
		v := tea.NewView("")
		v.AltScreen = true
		return v
	}
	width := max(1, min(64, m.width-2))
	if m.width < 3 {
		width = m.width
	}
	margin := max(0, (m.width-width)/2)
	base := lipgloss.NewStyle()
	ink, dim, brand, cyan := base, base, base, base
	if !m.plain {
		a, b, c, d := "#ECEAF7", "#9593AB", "#BA9CFF", "#6FE4E5"
		if m.light {
			a, b, c, d = "#292338", "#72687E", "#7540AC", "#006B75"
		}
		ink = base.Foreground(lipgloss.Color(a))
		dim = base.Foreground(lipgloss.Color(b))
		brand = base.Foreground(lipgloss.Color(c)).Bold(true)
		cyan = base.Foreground(lipgloss.Color(d))
	}
	rows := []string{}
	if m.width >= 70 && m.height >= 22 {
		rows = append(rows, brand.Render("█▀▀ █▀█ █▀▄ █▀▄▀█ █▀█ █▀▄ █▀▀"), brand.Render("█▄█ █▄█ █▄▀ █ ▀ █ █▄█ █▄▀ ██▄"), cyan.Render("B E A T Z   /   OPTIONAL MUSIC PACK"), "")
	} else {
		rows = append(rows, brand.Render("GODMODE // BEATZ"), dim.Render("OPTIONAL MUSIC PACK"))
	}
	rows = append(rows, dim.Render(strings.Repeat("─", width)), ink.Bold(true).Render("Install the music pack?"), "")
	paragraphs := []string{"Player, library and queue", "Local synth and instruments", "Original jingles", "", "Music uses your local .ootrs tracks.", "Jingles only need mpv."}
	for _, line := range paragraphs {
		for _, wrapped := range strings.Split(ansi.Wrap(line, width, ""), "\n") {
			rows = append(rows, ink.Render(wrapped))
		}
	}
	rows = append(rows, "", dim.Render("Optional. Remove it at any time."))
	footer := []string{dim.Render(strings.Repeat("─", width)), cyan.Render("Enter install · Esc back")}
	// Keep the decision visible even when a terminal is resized below the
	// supported 40x18 layout; full copy is retained at the supported sizes.
	available := max(0, m.height-len(footer))
	if len(rows) > available {
		rows = rows[:available]
	}
	rows = append(rows, footer...)
	if len(rows) > m.height {
		rows = rows[len(rows)-m.height:]
	}
	top := max(0, (m.height-len(rows))/2)
	out := make([]string, 0, m.height)
	for i := 0; i < top; i++ {
		out = append(out, "")
	}
	for _, row := range rows {
		if m.plain {
			row = ansi.Strip(row)
		}
		out = append(out, strings.Repeat(" ", margin)+clipped(row, width))
	}
	for len(out) < m.height {
		out = append(out, "")
	}
	v := tea.NewView(strings.Join(out, "\n"))
	v.AltScreen = true
	return v
}
