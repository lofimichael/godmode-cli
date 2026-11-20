package ui

import (
	"fmt"
	"slices"
	"sort"
	"strings"
	"unicode/utf8"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"
)

const (
	homeProviders = iota
	homeProfile
	homeTools
)

type homeItem struct {
	section, index, priority int
	kind, name, status, help string
}

func (m model) providerStatus(pr provider) (string, int) {
	if m.state.StoreError != "" {
		return "Unreadable", 2
	}
	for _, k := range pr.Key {
		switch m.state.States[k.Name] {
		case "malformed", "duplicate":
			return "Needs repair", 2
		}
	}
	if m.providerReady(pr) {
		if pr.ID == "stripe" || pr.ID == "prodigi" {
			var modes []string
			for _, set := range pr.Ready {
				if len(set) != 1 || m.state.States[set[0]] != "set" {
					continue
				}
				for _, k := range pr.Key {
					if k.Name == set[0] {
						mode, _, _ := strings.Cut(k.Label, " ")
						modes = append(modes, strings.ToLower(mode))
					}
				}
			}
			if len(modes) > 0 {
				return "Saved · " + strings.Join(modes, "/"), 0
			}
		}
		return "Saved", 0
	}
	if n := m.providerCount(pr); n > 0 {
		return fmt.Sprintf("%d/%d keys", n, len(pr.Key)), 1
	}
	return "Add key", 3
}

func (m model) agentNoteStatus(compact bool) string {
	if slices.Contains(m.state.Progress.Errors, "agents") {
		return "Unreadable"
	}
	if n := len(m.state.Progress.Agents); n != 0 {
		name := clean(strings.Join(strings.Fields(m.state.Progress.Agents[0]), " "))
		if n > 1 {
			name += fmt.Sprintf(" +%d", n-1)
		}
		if compact {
			return name
		}
		return name + " · " + countLabel(n, "file")
	}
	if m.state.Progress.ByHand {
		return "Marked by hand"
	}
	if compact {
		return "0 files"
	}
	return "0 files with note"
}

func (m model) homeItems() []homeItem {
	items := make([]homeItem, 0, len(m.state.Providers)+len(m.state.Fields)+6)
	known := make(map[string]bool)
	for i, pr := range m.state.Providers {
		status, priority := m.providerStatus(pr)
		items = append(items, homeItem{homeProviders, i, priority, "provider", pr.Name, status, pr.About})
		for _, k := range pr.Key {
			known[k.Name] = true
		}
	}
	var custom []string
	for name, state := range m.state.States {
		if !known[name] && state != "empty" {
			custom = append(custom, name)
		}
	}
	sort.Strings(custom)
	for _, name := range custom {
		status, priority := "Add key · custom", 3
		switch m.state.States[name] {
		case "set":
			status, priority = "Saved · custom", 0
		case "duplicate", "malformed":
			status, priority = "Needs repair · custom", 2
		}
		items = append(items, homeItem{section: homeProviders, priority: priority, kind: "custom", name: name, status: status, help: "Edit this custom key."})
	}
	sort.SliceStable(items, func(i, j int) bool { return items[i].priority < items[j].priority })
	items = append(items, homeItem{section: homeProviders, kind: "name", name: "Add custom key", help: "Save a key for another service."})
	for i, f := range m.state.Fields {
		value := strings.Join(strings.Fields(m.state.Profile[f.Name]), " ")
		if value == "" {
			value = "—"
		}
		if m.state.ProfileError != "" {
			value = "Unreadable"
		}
		help := f.Description
		if value == "—" && f.Example != "" {
			help = "Example: " + f.Example
		}
		items = append(items, homeItem{homeProfile, i, 0, "field", f.Label, value, help})
	}
	return append(items,
		homeItem{section: homeTools, kind: "agents", name: "Agent instructions", status: m.agentNoteStatus(false), help: "Copy instructions for a chat or add them to an agent file."},
		homeItem{section: homeTools, kind: "active", name: "Switch loadout", help: "Choose a key environment and profile."},
		homeItem{section: homeTools, kind: "settings", name: "Settings", help: "Appearance, local file checks and updates."},
		homeItem{section: homeTools, kind: "faq", name: "Help", help: "Quickstart and common questions."},
		homeItem{section: homeTools, kind: "exit", name: "Exit", help: "Return to your terminal."},
	)
}

func (m model) homeSelection() (homeItem, bool) {
	items := m.homeItems()
	if m.selected < 0 || m.selected >= len(items) {
		return homeItem{}, false
	}
	return items[m.selected], true
}

func (m *model) editProfileField(index int) {
	if m.state.ProfileError != "" {
		m.error = clean(m.state.ProfileError)
		return
	}
	m.fieldAt, m.page = index, "profile_field"
	m.resetInput()
	m.text = m.state.Profile[m.state.Fields[index].Name]
	m.cursor = utf8.RuneCountInString(m.text)
}

func (m *model) enterHome() tea.Cmd {
	item, ok := m.homeSelection()
	if !ok {
		return nil
	}
	m.homeAt = m.selected
	switch item.kind {
	case "provider":
		m.openProvider(item.index)
	case "custom":
		m.keyReturn = "home"
		m.openKey(item.name)
	case "name":
		m.page = "name"
		m.resetInput()
	case "field":
		m.editProfileField(item.index)
	case "agents":
		m.loadAgents()
	case "active":
		m.startActive()
	case "settings":
		m.page, m.selected = "settings", 0
	case "faq":
		m.loadFAQ()
	case "exit":
		m.quitting = true
		return tea.Quit
	}
	return nil
}

// The narrow layout shows one section at a time. Logical focus is independent
// of terminal size, so resizing never changes what Enter opens.
func (m *model) moveHomeSection(key string) bool {
	direction := 0
	switch key {
	case "tab", "right":
		direction = 1
	case "shift+tab", "left":
		direction = -1
	default:
		return false
	}
	items := m.homeItems()
	if m.selected >= 0 && m.selected < len(items) {
		section := items[m.selected].section
		if m.innerWidth() >= 68 && (key == "left" || key == "right") {
			fromLeft := section == homeProviders
			if fromLeft != (key == "right") {
				return true
			}
			// The Actions heading occupies a non-selectable row on the right.
			providers := 0
			for providers < len(items) && items[providers].section == homeProviders {
				providers++
			}
			fields := len(m.state.Fields)
			if fromLeft {
				row := m.selected
				if row > fields {
					row--
				}
				m.selected = min(providers+row, len(items)-1)
			} else {
				row := m.selected - providers
				if section == homeTools {
					row++
				}
				m.selected = min(row, providers-1)
			}
			return true
		}
		for step := 1; step <= 3; step++ {
			want := (section + direction*step + 3) % 3
			for i, item := range items {
				if item.section == want {
					m.selected = i
					return true
				}
			}
		}
	}
	return true
}

func (m model) homeRow(item homeItem, selected bool, width int) string {
	p := m.palette()
	name, value := clean(item.name), clean(item.status)
	body := width - 2
	if item.kind == "agents" && width < 34 {
		value = ""
	}
	if value != "" {
		valueWidth := min(ansi.StringWidth(value), max(1, body-min(ansi.StringWidth(name), body/2)-1))
		if item.kind == "field" {
			valueWidth = max(1, body-min(15, body/2)-1)
		}
		value = ansi.Truncate(value, valueWidth, "…")
		name = ansi.Truncate(name, max(1, body-valueWidth-1), "…")
		prefix := pad(name, max(1, body-valueWidth))
		if item.kind == "field" {
			prefix = p.muted.Render(prefix)
		} else if item.kind == "agents" {
			value = p.muted.Render(value)
		} else if strings.HasPrefix(value, "Saved") {
			value = p.good.Render(value)
		} else if value == "Add key" {
			value = p.muted.Render(value)
		} else {
			value = p.warn.Render(value)
		}
		name = prefix + value
	} else {
		name = ansi.Truncate(name, max(1, body), "…")
	}
	if selected {
		row := pad("❯ "+ansi.Strip(name), width)
		if m.colors {
			style := lipgloss.NewStyle().Foreground(lipgloss.Color("#171717")).Background(lipgloss.Color("#F2F0E7")).Bold(true)
			if !m.dark {
				style = style.Foreground(lipgloss.Color("#FFFFFF")).Background(lipgloss.Color("#35352F"))
			}
			return style.Render(row)
		}
		return row
	}
	return "  " + name
}

func (m model) homeHeading(title, summary string, width int) string {
	p := m.palette()
	line := p.title.Render(title)
	if summary != "" {
		line += p.muted.Render("  " + summary)
	}
	if n := width - ansi.StringWidth(line) - 1; n > 1 {
		line += p.muted.Render(" " + strings.Repeat("─", n))
	}
	return ansi.Truncate(line, width, "…")
}

type homeLine struct {
	text     string
	selected bool
}

func homeWindow(lines []homeLine, room int) []homeLine {
	if len(lines) <= room {
		return lines
	}
	at := 0
	for i, line := range lines {
		if line.selected {
			at = i
			break
		}
	}
	start := min(max(0, at-room/2), len(lines)-room)
	return lines[start : start+room]
}

func (m model) homeView() []string {
	p, w := m.palette(), m.innerWidth()
	items := m.homeItems()
	at := min(max(0, m.selected), len(items)-1)
	current := items[at]
	wide := w >= 68
	brand := m.profileBrand()
	scope := "Keys " + scopeName(m.state.Environment) + " · Profile " + m.profileIdentity()
	title := "Loadout"
	if brand != "" && m.state.Context != "" {
		// Put a named profile's brand on the first line; both identities stay
		// visible in a narrow viewport without repeating the brand.
		title += " · " + brand
		scope = "Keys " + scopeName(m.state.Environment) + " · Profile " + m.profileScope()
	}
	rows := []string{p.title.Render(ansi.Truncate("GODMODE  /  "+title, w, "…")), ansi.Truncate(p.muted.Render(scope), w, "…")}
	if wide && m.height >= 22 {
		logo := smallLogo
		labelWidth := max(1, w-ansi.StringWidth(logo[0])-4)
		rows = []string{
			p.brand.Render(logo[0]) + "    " + p.title.Render(ansi.Truncate(title, labelWidth, "…")),
			p.cyan.Render(logo[1]) + "    " + p.muted.Render(ansi.Truncate(scope, labelWidth, "…")),
			"",
		}
	}
	if m.state.ShellOverride {
		rows = append(rows, p.warn.Render("Shell overrides the saved loadout."))
	}
	sectionNames := []string{"Providers", "Profile", "Actions"}
	if !wide {
		tabs := make([]string, len(sectionNames))
		for i, label := range sectionNames {
			tabs[i] = p.muted.Render(label)
			if i == current.section {
				tabs[i] = p.title.Render("[" + label + "]")
			}
		}
		count, position := 0, 0
		for i, item := range items {
			if item.section == current.section {
				count++
				if i == at {
					position = count
				}
			}
		}
		tabLine := strings.Join(tabs, "  ")
		index := fmt.Sprintf("row %d/%d", position, count)
		if ansi.StringWidth(tabLine)+len(index)+1 <= w {
			tabLine = pad(tabLine, w-len(index)) + p.muted.Render(index)
		}
		rows = append(rows, tabLine)
	}

	hints := "↑↓ move · Tab section · Enter open · / find · s switch · Esc quit"
	if !wide {
		hints = "↑↓ move · Tab section · Enter open"
	}
	foot := m.keyHints(hints)
	if !wide {
		notes := m.agentNoteStatus(true)
		foot = append(foot, m.keyHints("Notes "+notes+" · / find · Esc quit")...)
	}
	firstStep := m.state.KeyCount == 0 && m.state.StoreError == ""
	for _, state := range m.state.States {
		if state == "set" {
			firstStep = false
			break
		}
	}
	if firstStep && current.section == homeProviders {
		message := "Add a key, then paste the note in chat"
		if wide {
			message = "Add a provider key, then paste Agent instructions into your agent chat."
		}
		if m.state.Progress.ByHand || len(m.state.Progress.Agents) > 0 {
			message = "Choose a provider to add your first key."
		}
		rows = append(rows, p.cyan.Render(ansi.Truncate(message, w, "…")))
	}
	if m.error != "" || m.notice != "" || m.busyVisible {
		status := m.statusLines()
		foot = append([]string{ansi.Truncate(strings.Join(status, " "), w, "…")}, foot...)
	} else if m.height >= 21 {
		help := clean(current.help)
		if current.kind == "provider" || current.kind == "custom" {
			help = current.name + " · " + help
		}
		foot = append([]string{ansi.Truncate(p.muted.Render(help), w, "…")}, foot...)
	}
	room := max(1, m.height-len(rows)-len(foot))
	if m.height >= 22 {
		room--
	}
	room = max(1, room)
	if wide {
		left := (w - 3) * 46 / 100
		right := w - left - 3
		saved, custom, fields := 0, 0, 0
		for _, item := range items {
			if item.kind == "provider" && item.priority == 0 {
				saved++
			}
			if item.kind == "custom" && item.priority == 0 {
				custom++
			}
			if item.kind == "field" && m.state.Profile[m.state.Fields[item.index].Name] != "" {
				fields++
			}
		}
		providerSummary := fmt.Sprintf("%d/%d saved", saved, len(m.state.Providers))
		if custom > 0 {
			providerSummary = fmt.Sprintf("%d/%d + %d custom", saved, len(m.state.Providers), custom)
		}
		if m.state.StoreError != "" {
			providerSummary = "Unreadable"
		}
		profileSummary := fmt.Sprintf("%d/%d fields", fields, len(m.state.Fields))
		if m.state.ProfileError != "" {
			profileSummary = "Unreadable"
		}
		rows = append(rows, pad(m.homeHeading("Providers", providerSummary, left), left)+"   "+m.homeHeading("Profile", profileSummary, right))
		// Taller terminals can fit a single plain-language description for each
		// entry while keeping every catalog provider in view.
		expanded := room >= len(m.state.Providers)*2+3 && m.height >= 32
		var providers, details []homeLine
		for i, item := range items {
			switch item.section {
			case homeProviders:
				providers = append(providers, homeLine{m.homeRow(item, i == at, left), i == at})
				if expanded && item.kind == "provider" {
					providers = append(providers, homeLine{text: "  " + p.muted.Render(ansi.Truncate(clean(item.help), left-2, "…"))})
				}
			default:
				if item.kind == "agents" {
					details = append(details, homeLine{m.homeHeading("Actions", "", right), false})
				}
				details = append(details, homeLine{m.homeRow(item, i == at, right), i == at})
				if expanded {
					details = append(details, homeLine{text: "  " + p.muted.Render(ansi.Truncate(clean(item.help), right-2, "…"))})
				}
			}
		}
		providers, details = homeWindow(providers, max(1, room-1)), homeWindow(details, max(1, room-1))
		for i := 0; i < max(len(providers), len(details)); i++ {
			l, r := "", ""
			if i < len(providers) {
				l = providers[i].text
			}
			if i < len(details) {
				r = details[i].text
			}
			rows = append(rows, pad(l, left)+p.muted.Render(" │ ")+r)
		}
	} else {
		var lines []homeLine
		for i, item := range items {
			if item.section == current.section {
				lines = append(lines, homeLine{m.homeRow(item, i == at, w), i == at})
			}
		}
		for _, line := range homeWindow(lines, room) {
			rows = append(rows, line.text)
		}
	}
	if wide && len(rows)+len(foot)+2 <= m.height {
		rows = append(rows, "")
	}
	return append(rows, foot...)
}
