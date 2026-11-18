package musicui

import (
	"fmt"
	"math"
	"strings"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"
)

type palette struct{ ink, dim, violet, cyan, lime, amber, selected, faint lipgloss.Style }

func (m model) palette() palette {
	b := lipgloss.NewStyle()
	p := palette{b, b, b, b, b, b, b, b}
	if m.opts.Plain {
		return p
	}
	ink, dim, violet, cyan, lime, amber, bg, faint := "#ECEAF7", "#9593AB", "#BA9CFF", "#6FE4E5", "#C4E88D", "#F3B76B", "#29213F", "#514760"
	if m.opts.Light {
		ink, dim, violet, cyan, lime, amber, bg, faint = "#292338", "#72687E", "#7540AC", "#006B75", "#396D20", "#8A4D00", "#E8DEF5", "#C8BCD4"
	}
	p.ink = b.Foreground(lipgloss.Color(ink))
	p.dim = b.Foreground(lipgloss.Color(dim))
	p.violet = b.Foreground(lipgloss.Color(violet)).Bold(true)
	p.cyan = b.Foreground(lipgloss.Color(cyan))
	p.lime = b.Foreground(lipgloss.Color(lime))
	p.amber = b.Foreground(lipgloss.Color(amber))
	p.selected = p.ink.Background(lipgloss.Color(bg)).Bold(true)
	p.faint = b.Foreground(lipgloss.Color(faint))
	return p
}

var logo = []string{
	" ██████╗  ██████╗ ██████╗ ███╗   ███╗ ██████╗ ██████╗ ███████╗",
	"██╔════╝ ██╔═══██╗██╔══██╗████╗ ████║██╔═══██╗██╔══██╗██╔════╝",
	"██║  ███╗██║   ██║██║  ██║██╔████╔██║██║   ██║██║  ██║█████╗  ",
	"██║   ██║██║   ██║██║  ██║██║╚██╔╝██║██║   ██║██║  ██║██╔══╝  ",
	"╚██████╔╝╚██████╔╝██████╔╝██║ ╚═╝ ██║╚██████╔╝██████╔╝███████╗",
	" ╚═════╝  ╚═════╝ ╚═════╝ ╚═╝     ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝",
}

func fit(s string, w int) string {
	if w <= 0 {
		return ""
	}
	return ansi.Truncate(s, w, "…")
}
func pad(s string, w int) string {
	return fit(s, w) + strings.Repeat(" ", max(0, w-ansi.StringWidth(s)))
}
func splitLine(left, right string, w int) string {
	if ansi.StringWidth(right)+2 > w {
		return fit(left, w)
	}
	room := w - ansi.StringWidth(right) - 1
	return pad(left, room) + " " + right
}
func (m model) margin() int {
	if m.width < 30 {
		return 0
	}
	return 1
}
func (m model) innerWidth() int { return max(1, m.width-2*m.margin()) }
func (m model) header() []string {
	p, w := m.palette(), m.innerWidth()
	if m.width >= 100 && m.height >= 30 {
		stamp := []string{"╔════════════════════════╗", "║  B E A T Z   /   0 1   ║", "║  LOCAL SEQUENCE RADIO  ║", "║  LIBRARY → QUEUE → PLAY║", "╚════════════════════════╝", "      [ GODMODE / MUSIC ]"}
		rows := []string{}
		for i, line := range logo {
			style := p.violet
			if i == len(logo)-1 {
				style = p.cyan
			}
			rows = append(rows, splitLine(style.Render(line), p.cyan.Render(stamp[i]), w))
		}
		return rows
	}
	if m.width >= 70 && m.height >= 23 {
		return []string{splitLine(p.violet.Render("█▀▀ █▀█ █▀▄ █▀▄▀█ █▀█ █▀▄ █▀▀"), p.cyan.Bold(true).Render("B E A T Z   /   0 1"), w), splitLine(p.violet.Render("█▄█ █▄█ █▄▀ █ ▀ █ █▄█ █▄▀ ██▄"), p.dim.Render("LOCAL SEQUENCE RADIO"), w)}
	}
	return []string{splitLine(p.violet.Render("GODMODE")+p.cyan.Render(" // BEATZ"), p.dim.Render("LOCAL"), w)}
}
func (m model) footer() []string {
	p := m.palette()
	if m.searching {
		return []string{p.cyan.Render("Type query · Ctrl+U clears text"), p.dim.Render("Enter/Tab results · Esc clear")}
	}
	if m.info {
		return []string{p.dim.Render("c collection  A add collection"), p.cyan.Render("↑↓ scroll  i/Esc back  q close")}
	}
	if m.setupPage() {
		return []string{p.dim.Render("↑↓ scroll  PgUp/PgDn page"), p.cyan.Render("R reloads after setup  q close")}
	}
	if m.help {
		return []string{p.dim.Render("↑↓ scroll  ? / Esc return"), p.cyan.Render("q close view · playback continues")}
	}
	if m.width < 60 {
		if m.view == "queue" {
			return []string{p.dim.Render("↑↓ Enter play c collection / search"), p.dim.Render("Tab library  d remove  i info  ? keys"), p.cyan.Render("Space pause x stop Esc back q close")}
		}
		if m.selectedTrack() {
			first := "↑↓ Enter play / search c collection"
			if m.collection != "" && m.collection != "*" && !m.searchActive && m.query == "" {
				first = "↑↓ Enter play  A add collection"
			}
			return []string{p.dim.Render(first), p.dim.Render("Tab queue a add i info ? keys Esc back"), p.cyan.Render("Space pause  x stop  q close view")}
		}
		return []string{p.dim.Render("↑↓ browse  Enter open/play  / search"), p.dim.Render("Tab queue a add i info ? keys Esc back"), p.cyan.Render("Space pause  x stop  q close view")}
	}
	if m.selectedTrack() {
		first := "↑↓ Enter play  a add  c collection  A add collection  / search"
		second := "Space pause  x stop  Tab queue  i info  ? keys  Esc back  q close"
		if m.view == "queue" {
			first = "↑↓ Enter play  a add  d remove  c collection  A add collection"
			second = "Space pause x stop Tab library / search i info ? keys Esc back q close"
		}
		return []string{p.dim.Render(first), p.cyan.Render(second)}
	}
	first := "↑↓ browse  Enter open/play  a add  / search  Tab queue  i info  ? keys"
	if m.view == "queue" {
		first = "↑↓ choose  Enter play  d remove  Tab library  / search  i info  ? keys"
	}
	return []string{p.dim.Render(first), p.cyan.Render("Space pause  n/p skip  x stop  Esc back  q close view")}
}
func (m model) transportRows() int {
	if m.width < 60 || m.height < 22 {
		return 4
	}
	return 5
}
func (m model) bodyRows() int {
	return max(1, m.height-len(m.header())-3-m.transportRows()-len(m.footer())-1)
}
func (m model) nav() []string {
	p, w := m.palette(), m.innerWidth()
	libraryTab, queueTab := p.dim.Render("LIBRARY"), p.dim.Render(fmt.Sprintf("QUEUE %d", len(m.status.Queue)))
	if m.view == "queue" {
		queueTab = p.cyan.Bold(true).Render(fmt.Sprintf("[ QUEUE %d ]", len(m.status.Queue)))
	} else {
		libraryTab = p.cyan.Bold(true).Render("[ LIBRARY ]")
	}
	tabs := libraryTab + "   " + queueTab
	count := fmt.Sprintf("%d tracks", len(m.library.Tracks))
	if !m.loaded {
		count = "loading"
	}
	crumb := "Collections"
	if m.collection == "*" {
		crumb = "Library / All tracks"
	} else if m.collection != "" {
		crumb = "Library / " + clean(strings.ReplaceAll(m.collection, "/", " / "))
	}
	if m.view == "queue" {
		crumb = "Enter plays this queued track"
	}
	if m.view == "library" && (m.searchActive || m.query != "" || m.searching) {
		crumb = "/ " + clean(m.query)
		if m.searching {
			crumb += "▏"
		}
		crumb = splitLine(p.ink.Render(crumb), p.dim.Render(fmt.Sprintf("%d found", len(m.entries()))), w)
	} else {
		crumb = p.ink.Render(crumb)
	}
	if m.help {
		crumb = p.ink.Bold(true).Render("PLAYER KEYS · ↑↓ to scroll")
	}
	if m.info {
		crumb = p.ink.Bold(true).Render("SELECTED DETAILS · ↑↓ to scroll")
	}
	if m.setupPage() {
		crumb = p.ink.Bold(true).Render("SETUP GUIDE · ↑↓ to scroll")
	}
	if !m.help && !m.info && !m.setupPage() && !m.searching && (m.view == "queue" || (!m.searchActive && m.query == "")) {
		n := len(m.entries())
		if n > 0 {
			crumb = splitLine(crumb, p.dim.Render(fmt.Sprintf("%d / %d", m.selected+1, n)), w)
		}
	}
	return []string{splitLine(tabs, p.dim.Render(count), w), crumb, p.faint.Render(strings.Repeat("─", w))}
}
func (m model) View() tea.View {
	if m.closing && !m.busy {
		v := tea.NewView("")
		v.AltScreen = true
		return v
	}
	w := m.innerWidth()
	rows := append([]string{}, m.header()...)
	rows = append(rows, m.nav()...)
	body := m.body(m.bodyRows(), w)
	rows = append(rows, body...)
	p := m.palette()
	message := ""
	if !m.library.PlayerAvailable && m.loaded && m.library.Configured {
		message = "Playback needs mpv · brew install mpv"
	}
	if m.status.Message != "" {
		message = clean(m.status.Message)
	}

	if m.view == "library" && m.library.Configured && !m.help && !m.searching && m.library.PlayerAvailable && m.status.State != "preparing" && m.status.State != "error" {
		entries := m.entries()
		if len(entries) > 0 {
			e := entries[min(m.selected, len(entries)-1)]
			if e.container {
				message = "Enter opens collection · a appends"
			} else if m.width < 60 {
				message = "Enter replaces queue · a appends"
			} else {
				message = "Enter plays from here · replaces queue · a appends"
			}
		}
	}
	if m.searching && m.status.State != "preparing" && m.status.State != "error" {
		message = "Enter / Tab focuses search results"
	}
	if m.view == "queue" && m.width < 60 && m.status.State != "preparing" && m.status.State != "error" {
		entries := m.entries()
		if len(entries) > 0 {
			message = "Selected · " + clean(entries[min(m.selected, len(entries)-1)].track.Collection)
		}
	}
	if m.notice != "" && m.status.State != "preparing" && m.status.State != "error" {
		message = clean(m.notice)
	}
	if m.busy {
		message = "Working · " + m.busyAction
		if len(m.pending) > 0 {
			message += fmt.Sprintf(" · %d queued controls", len(m.pending))
		}
	}
	if m.failure != "" {
		message = clean(m.failure)
	}
	if m.closing {
		message = "Closing view after the current control…"
	}
	rows = append(rows, p.amber.Render(message))
	rows = append(rows, m.transport(w)...)
	rows = append(rows, m.footer()...)
	// A bounded cell canvas prevents a wrapped last row from scrolling the player.
	if len(rows) > m.height {
		rows = rows[:m.height]
	}
	for len(rows) < m.height {
		rows = append(rows, "")
	}
	margin := strings.Repeat(" ", m.margin())
	for i := range rows {
		rows[i] = margin + pad(fit(rows[i], w), w)
		if m.opts.Plain {
			rows[i] = ansi.Strip(rows[i])
		}
	}
	v := tea.NewView(strings.Join(rows, "\n"))
	v.AltScreen = true
	return v
}
func (m model) body(height, width int) []string {
	p := m.palette()
	rows := []string{}
	if m.info {
		entries := m.entries()
		lines := []string{"No row selected."}
		if len(entries) > 0 {
			e := entries[min(m.selected, len(entries)-1)]
			lines = []string{clean(e.title), ""}
			if e.container {
				lines = append(lines, clean(e.collection), fmt.Sprintf("%d local tracks", len(e.tracks)), "", "Enter opens this collection.", "a appends its tracks to the queue.")
			} else {
				intent := "Enter replaces queue; plays from here."
				if m.view == "queue" {
					intent = "Enter plays this queued track."
				}
				lines = append(lines, clean(e.track.Collection), "", intent, "a appends it to the queue.", "c opens its collection.", "A appends the whole collection.")
			}
		}
		var wrapped []string
		for _, line := range lines {
			wrapped = append(wrapped, strings.Split(ansi.Wrap(line, width, ""), "\n")...)
		}
		start := min(m.infoAt, max(0, len(wrapped)-height))
		for _, line := range wrapped[start:min(len(wrapped), start+height)] {
			rows = append(rows, p.ink.Render(line))
		}
	} else if m.help {
		lines := helpLines(width)
		start := min(m.helpAt, max(0, len(lines)-height))
		for _, s := range lines[start:min(len(lines), start+height)] {
			rows = append(rows, p.ink.Render(s))
		}
	} else if !m.loaded {
		rows = []string{p.cyan.Render("Reading your local music library…"), p.dim.Render("q closes this view")}
	}
	if m.setupPage() {
		lines := m.setupLines()
		start := min(m.setupAt, max(0, len(lines)-height))
		rows = append(rows, lines[start:min(len(lines), start+height)]...)
	}

	if len(rows) > 0 {
		for len(rows) < height {
			rows = append(rows, "")
		}
		return rows[:height]
	}
	entries := m.entries()
	if len(entries) == 0 {
		title := "This collection has no tracks."
		detail := "Esc returns to the library."
		if m.view == "queue" {
			title = "Your queue is empty."
			detail = "Tab to browse · a adds a track or collection."
		} else if m.searchActive || m.query != "" || m.searching {
			title = "No tracks match your search."
			detail = "Edit the query above, or Esc to clear."
		}
		rows = []string{p.ink.Render(title), p.dim.Render(detail)}
		for len(rows) < height {
			rows = append(rows, "")
		}
		return rows[:height]
	}
	listWidth := width
	sideWidth := 0
	if width >= 98 && !m.searching {
		sideWidth = 32
		listWidth = width - sideWidth - 3
	}
	start := max(0, min(m.selected-height/2, len(entries)-height))
	end := min(len(entries), start+height)
	side := m.sidebar(height, sideWidth)
	for i := start; i < end; i++ {
		e := entries[i]
		prefix := "  "
		if i == m.selected {
			prefix = "› "
		}
		label := clean(e.title)
		suffix := ""
		if e.container {
			label = "▸ " + label
			suffix = fmt.Sprintf("%d", len(e.tracks))
		} else if m.view == "queue" {
			if listWidth >= 58 {
				suffix = clean(e.track.Collection)
			}
			prefix += fmt.Sprintf("%02d ", i+1)
			if i == m.selected {
				prefix = "› " + fmt.Sprintf("%02d ", i+1)
			}
			if i == m.status.Index && m.status.State != "stopped" {
				marker := "▶"
				if m.status.State == "paused" {
					marker = "Ⅱ"
				} else if m.status.State == "preparing" {
					marker = "…"
				}
				if suffix != "" {
					suffix += " "
				}
				suffix += marker
			}
		} else if listWidth >= 64 {
			suffix = clean(e.track.Collection)
		}
		line := splitLine(prefix+label, suffix, listWidth)
		if i == m.selected {
			line = p.selected.Render(pad(line, listWidth))
		} else if e.container {
			line = p.violet.Render(line)
		} else {
			line = p.ink.Render(line)
		}
		if sideWidth > 0 {
			at := i - start
			line = pad(line, listWidth) + p.faint.Render(" │ ") + pad(side[at], sideWidth)
		}
		rows = append(rows, line)
	}
	for len(rows) < height {
		line := ""
		if sideWidth > 0 {
			line = strings.Repeat(" ", listWidth) + p.faint.Render(" │ ") + pad(side[len(rows)], sideWidth)
		}
		rows = append(rows, line)
	}
	return rows
}
func (m model) sidebar(height, width int) []string {
	rows := make([]string, height)
	if width <= 0 {
		return rows
	}
	p := m.palette()
	entries := m.entries()
	if len(entries) == 0 {
		return rows
	}
	at := min(m.selected, len(entries)-1)
	e := entries[at]
	lines := []string{p.dim.Render("SELECTED"), p.violet.Render(clean(e.title)), ""}
	if e.container {
		lines = append(lines, p.ink.Render(fmt.Sprintf("%d local tracks", len(e.tracks))), p.dim.Render("Enter opens collection"), p.dim.Render("a appends the collection"))
	} else {
		lines = append(lines, p.dim.Render(clean(e.track.Collection)), p.ink.Render("Enter plays from this track"), p.dim.Render("a appends to the queue"))
	}
	lines = append(lines, "", p.dim.Render(fmt.Sprintf("ROW %d / %d", at+1, len(entries))), p.dim.Render("Selection does not change audio."))
	if height >= 14 {
		lines = append(lines, "", p.cyan.Render("PCM / PLAYER CLOCK"))
		bars := m.signal(width, 3)
		lines = append(lines, bars...)
	}
	for i := 0; i < min(height, len(lines)); i++ {
		rows[i] = fit(lines[i], width)
	}
	return rows
}
func (m model) signal(width, height int) []string {
	p := m.palette()
	rows := make([]string, height)
	if m.opts.NoMotion || len(m.status.Levels) == 0 || m.status.State != "playing" {
		label := "No signal"
		if m.opts.NoMotion {
			label = "Motion reduced"
		}
		for i := range rows {
			rows[i] = p.faint.Render(strings.Repeat("·", max(0, width)))
		}
		if height > 0 {
			rows[height-1] = p.dim.Render(label)
		}
		return rows
	}
	for y := 0; y < height; y++ {
		var b strings.Builder
		for x := 0; x < max(1, width/2); x++ {
			level := m.status.Levels[x*len(m.status.Levels)/max(1, width/2)]
			if math.IsNaN(level) || math.IsInf(level, 0) {
				level = 0
			}
			if level*float64(height) > float64(height-y-1) {
				b.WriteString("█ ")
			} else {
				b.WriteString("  ")
			}
		}
		rows[y] = p.cyan.Render(b.String())
	}
	return rows
}
func clock(seconds float64) string {
	if math.IsNaN(seconds) || math.IsInf(seconds, 0) || seconds < 0 {
		return "0:00"
	}
	n := int(seconds)
	return fmt.Sprintf("%d:%02d", n/60, n%60)
}
func (m model) transport(w int) []string {
	p := m.palette()
	state := strings.ToUpper(clean(m.status.State))
	if state == "" {
		state = "STOPPED"
	}
	label := p.cyan.Bold(true).Render("NOW PLAYING") + " / " + p.lime.Render(state)
	border := p.faint.Render(strings.Repeat("─", max(0, w-ansi.StringWidth(label)-1)))
	rows := []string{label + " " + border}
	title := "Choose a track to begin"
	collection := ""
	if m.status.Track != nil {
		title = clean(m.status.Track.Title)
		collection = clean(m.status.Track.Collection)
	}
	title = p.ink.Bold(true).Render(title)
	if w >= 70 {
		title = splitLine(title, p.dim.Render(collection), w)
	}
	rows = append(rows, title)
	position, duration := m.status.Position, m.status.Duration
	played := clock(position)
	total := "–:––"
	if duration > 0 {
		total = clock(duration)
	}
	timing := played + " / " + total
	vol := fmt.Sprintf("%d%%", int(max(0, min(100, m.status.Volume))))
	meterW := max(2, w-ansi.StringWidth(timing)-ansi.StringWidth(vol)-4)
	filled := 0
	if duration > 0 && !math.IsNaN(position) && !math.IsNaN(duration) {
		filled = int(float64(meterW) * max(0, min(1, position/duration)))
	}
	meter := p.cyan.Render(strings.Repeat("━", filled)) + p.faint.Render(strings.Repeat("─", meterW-filled))
	rows = append(rows, p.dim.Render(timing)+" "+meter+" "+p.dim.Render(vol))
	repeat := m.status.Repeat
	if repeat == "" {
		repeat = "off"
	}
	shuffle := "off"
	if m.status.Shuffle {
		shuffle = "on"
	}
	queue := "Queue empty"
	if len(m.status.Queue) > 0 {
		queue = fmt.Sprintf("%d queued", len(m.status.Queue))
		if m.status.Index >= 0 && m.status.Track != nil {
			queue = fmt.Sprintf("Queue %d/%d", m.status.Index+1, len(m.status.Queue))
		}
	}
	rows = append(rows, splitLine(p.dim.Render("Repeat "+repeat+" · Shuffle "+shuffle), p.cyan.Render(queue), w))
	if m.transportRows() == 5 {
		rows = append(rows, m.pcmStrip(w))
	}
	return rows
}
func (m model) pcmStrip(w int) string {
	p := m.palette()
	label := "PCM / player clock  "
	if m.opts.NoMotion {
		return p.dim.Render(label + "motion reduced")
	}
	if m.status.State != "playing" || len(m.status.Levels) == 0 {
		return p.faint.Render(label + "waiting for audio")
	}
	glyphs := []rune("▁▂▃▄▅▆▇█")
	var b strings.Builder
	n := max(1, w-len(label))
	for i := 0; i < n; i++ {
		level := m.status.Levels[i*len(m.status.Levels)/n]
		if math.IsNaN(level) || math.IsInf(level, 0) {
			level = 0
		}
		at := int(max(0, min(1, level)) * float64(len(glyphs)-1))
		b.WriteRune(glyphs[at])
	}
	return p.dim.Render(label) + p.cyan.Render(b.String())
}
