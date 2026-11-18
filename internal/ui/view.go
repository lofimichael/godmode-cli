package ui

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"unicode/utf8"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"
)

type palette struct{ title, muted, brand, cyan, good, bad, warn, focus, selected lipgloss.Style }

func (m model) palette() palette {
	base := lipgloss.NewStyle()
	p := palette{base, base, base, base, base, base, base, base, base}
	if !m.colors {
		return p
	}
	magenta, cyan, green, red, amber, muted, focus := "#C59BFF", "#78DCE8", "#91DBA3", "#FF8795", "#E8C481", "#949DAA", "#252637"
	if !m.dark {
		magenta, cyan, green, red, amber, muted, focus = "#7949C8", "#006D7A", "#26713B", "#B33144", "#855407", "#626973", "#EDE8F7"
	}
	p.title = base.Bold(true)
	p.muted = base.Foreground(lipgloss.Color(muted))
	p.brand = base.Foreground(lipgloss.Color(magenta)).Bold(true)
	p.cyan = base.Foreground(lipgloss.Color(cyan))
	p.good = base.Foreground(lipgloss.Color(green))
	p.bad = base.Foreground(lipgloss.Color(red))
	p.warn = base.Foreground(lipgloss.Color(amber))
	p.focus = base.Background(lipgloss.Color(focus))
	p.selected = p.focus.Bold(true)
	return p
}

var nfoLogo = []string{
	" ██████╗  ██████╗ ██████╗ ███╗   ███╗ ██████╗ ██████╗ ███████╗",
	"██╔════╝ ██╔═══██╗██╔══██╗████╗ ████║██╔═══██╗██╔══██╗██╔════╝",
	"██║  ███╗██║   ██║██║  ██║██╔████╔██║██║   ██║██║  ██║█████╗",
	"██║   ██║██║   ██║██║  ██║██║╚██╔╝██║██║   ██║██║  ██║██╔══╝",
	"╚██████╔╝╚██████╔╝██████╔╝██║ ╚═╝ ██║╚██████╔╝██████╔╝███████╗",
	" ╚═════╝  ╚═════╝ ╚═════╝ ╚═╝     ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝",
}
var smallLogo = []string{"█▀▀ █▀█ █▀▄ █▀▄▀█ █▀█ █▀▄ █▀▀", "█▄█ █▄█ █▄▀ █ ▀ █ █▄█ █▄▀ ██▄"}

func (m model) logo(large bool) []string {
	p := m.palette()
	art := smallLogo
	if large && m.innerWidth() >= 63 {
		art = nfoLogo
	}
	if m.innerWidth() < 31 {
		return []string{p.brand.Render("G O D M O D E")}
	}
	out := []string{}
	for i, row := range art {
		if i == len(art)-1 {
			out = append(out, p.cyan.Render(row))
		} else {
			out = append(out, p.brand.Render(row))
		}
	}
	return out
}
func (m model) innerWidth() int { return max(1, min(104, m.width-2*m.margin())) }
func (m model) margin() int {
	if m.width < 16 {
		return 0
	}
	if m.width < 52 {
		return 1
	}
	return 2
}
func (m model) wrap(s string) []string {
	return strings.Split(ansi.Wrap(clean(s), m.innerWidth(), ""), "\n")
}
func (m model) styledWrap(s string, style lipgloss.Style) []string {
	out := m.wrap(s)
	for i, row := range out {
		out[i] = style.Render(row)
	}
	return out
}
func (m model) title(title, detail string) []string {
	p := m.palette()
	row := p.title.Render(title)
	if detail != "" {
		row += "  " + p.muted.Render(detail)
	}
	if m.height < 22 {
		return []string{row}
	}
	return []string{row, ""}
}
func (m model) path(path string) string {
	home, e := os.UserHomeDir()
	if e == nil && strings.HasPrefix(path, home+string(filepath.Separator)) {
		return "~/" + clean(strings.TrimPrefix(path, home+string(filepath.Separator)))
	}
	return clean(path)
}
func (m model) introLines() []string { return m.cinematicIntroLines() }
func (m model) introFits() bool      { return m.cinematicIntroFits() }
func (m model) introView() []string  { return m.cinematicIntroView() }
func (m model) homeView() []string {
	p, w := m.palette(), m.innerWidth()
	rows := []string{}
	if m.height >= 24 {
		rows = append(rows, m.logo(false)...)
		rows = append(rows, "")
	} else {
		rows = append(rows, p.brand.Render("GODMODE"))
	}
	rows = append(rows, m.scopeLines()...)
	rows = append(rows, "")
	if m.height >= 16 {
		next := "Ask your agent for the result you want."
		if m.state.KeyCount == 0 {
			next = "Add a provider key, then connect your agent."
		} else if m.state.Progress.Agent == 0 && len(m.state.Progress.Agents) == 0 {
			next = "Connect your agent to use your saved keys."
		}
		if w < 45 {
			if m.state.KeyCount == 0 {
				next = "Add keys, then connect your agent."
			} else if m.state.Progress.Agent == 0 && len(m.state.Progress.Agents) == 0 {
				next = "Keys saved. Connect your agent."
			} else {
				next = "Ask your agent for what you want."
			}
		}
		rows = append(rows, m.wrap(next)...)
		rows = append(rows, "")
	}
	statuses := []string{countLabel(m.state.KeyCount, "key") + " saved", countLabel(max(len(m.state.Progress.Agents), m.state.Progress.Agent), "note") + " added", "optional", "", "", "", "optional", ""}
	if m.state.StoreError != "" {
		statuses[0] = "needs attention"
	}
	if m.state.ProfileError != "" {
		statuses[2] = "needs attention"
	}
	if !m.state.MusicIncluded {
		statuses[6] = "not included"
	}
	choices := []string{}
	for i, name := range homeNames {
		if w < 45 {
			if i == 0 {
				statuses[i] = fmt.Sprintf("%d saved", m.state.KeyCount)
			}
			if i == 1 {
				statuses[i] = fmt.Sprintf("%d added", max(len(m.state.Progress.Agents), m.state.Progress.Agent))
			}
		}
		if w < 34 {
			statuses[i] = ""
		}
		if (i == 3 || i == 6) && m.height >= 24 {
			choices = append(choices, "")
		}
		choices = append(choices, m.choice(name, statuses[i], i == m.selected, w))
	}
	foot := []string{}
	if m.height >= 20 {
		help := m.styledWrap(m.homeDescription(), p.muted)
		foot = append(foot, help...)
		for len(foot) < 2 {
			foot = append(foot, "")
		}
	}
	foot = append(foot, m.statusLines()...)
	hint := "↑↓ move · Enter open · / find · s switch · ? keys · Esc quit"
	if w < 60 {
		hint = "↑↓ Enter · / find · ? keys · Esc quit"
	}
	if w < 38 {
		hint = "↑↓ Enter · / find\nEsc quit · ? keys"
	}
	foot = append(foot, m.styledWrap(hint, p.muted)...)
	leading := 0
	if m.height > 12 {
		leading = 1
	}
	room := max(1, m.height-leading-len(rows)-len(foot))
	start := m.listScroll(choices, room)
	rows = append(rows, choices[start:min(len(choices), start+room)]...)
	for len(rows)+len(foot) < m.height-leading {
		rows = append(rows, "")
	}
	return append(rows, foot...)
}

// Reserve feedback space before a write starts so copy/save/loading never move
// the controls or silently change how much of an append preview was reviewed.
func (m model) statusLines() []string {
	p := m.palette()
	text, style := "", p.good
	if m.busyVisible {
		text, style = m.loadingText(), p.cyan
	} else if m.error != "" {
		text, style = m.error, p.bad
	} else if m.page == "key" && m.check.Error != "" {
		text, style = m.check.Error, p.warn
	} else {
		text = m.notice
	}
	rows := m.styledWrap(text, style)
	reserve := 2
	if m.height < 22 {
		reserve = 1
	}
	for len(rows) < reserve {
		rows = append(rows, "")
	}
	return rows
}

func pad(s string, n int) string { return s + strings.Repeat(" ", max(0, n-ansi.StringWidth(s))) }
func (m model) choice(name, status string, selected bool, width int) string {
	p := m.palette()
	pointer := "  "
	name = clean(name)
	if selected {
		pointer = p.cyan.Render("❯ ")
		name = p.title.Render(name)
	}
	var row string
	if status != "" {
		status = ansi.Truncate(status, max(4, width/2-2), "…")
		room := max(4, min(28, width-ansi.StringWidth(status)-3))
		name = ansi.Truncate(name, room, "…")
		row = pointer + pad(name, room+1) + status
	} else {
		row = pointer + ansi.Truncate(name, max(1, width-2), "…")
	}
	if selected {
		style := p.selected
		if m.colors {
			if m.dark {
				style = style.Foreground(lipgloss.Color("#EAE5FF"))
			} else {
				style = style.Foreground(lipgloss.Color("#352552"))
			}
		}
		if m.pulseFrame > 0 && m.colors && !m.opts.NoMotion {
			if m.dark {
				style = style.Background(lipgloss.Color("#34304D"))
			} else {
				style = style.Background(lipgloss.Color("#DDD3EF"))
			}
		}
		// Nested ANSI resets from the pointer/status would clear the row's
		// background. One style owns the complete selected row.
		return style.Render(pad(ansi.Strip(row), width))
	}
	return row
}
func (m model) header() []string {
	rows := m.scopeLines()
	if m.height >= 22 {
		rows = append(rows, "")
	}
	return append(rows, m.pageHeader()...)
}
func (m model) pageHeader() []string {
	p := m.palette()
	switch m.page {
	case "settings":
		return m.title("Settings", "")
	case "update":
		return m.title("Update Godmode", "")
	case "shortcuts":
		return m.title("Keyboard shortcuts", "")
	case "actions":
		return append(m.title("Find an action", ""), p.cyan.Render("/ "+clean(m.query)+"▏"), "")
	case "recent_setups":
		return m.title("Recent setups", "keys / business")
	case "recent_details":
		return m.title("Use this setup", "")
	case "active":
		rows := m.title("Switch setup", "")
		if m.height >= 18 {
			rows = append(rows, m.wrap("Choose both before switching.")...)
			rows = append(rows, "")
		}
		return rows
	case "business":
		rows := m.title("Business details", "")
		if m.state.Context == "" && m.height >= 20 {
			rows = append(rows, m.wrap("Automatic uses the business details saved with this key environment.")...)
		}
		return rows
	case "contexts":
		return m.title("Switch business", "")
	case "environments":
		return m.title("Key environments", "")
	case "environment_new":
		return append(m.title("New environment", ""), m.wrap("Choose its starting values.")...)
	case "scope_name":
		if m.scopeKind == "environment" {
			return m.title("New environment", "")
		}
		return m.title("New business", "")
	case "scope_details":
		if m.scopeReturn == "contexts" {
			return m.title("Business details", "")
		}
		return m.title("Environment details", "")
	case "doctor":
		return m.title("Check setup", "local files only")
	case "profile":
		title := "Business details"
		rows := m.title(title, fmt.Sprintf("%d/%d optional fields", len(m.state.Progress.Fields), len(m.state.Fields)))
		blurb := m.state.ProfileBlurb
		if blurb == "" {
			blurb = "Full sites that take payments usually require a business profile, terms of service and a privacy policy. Agents use these details to fill them in."
		}
		if m.height >= 22 {
			rows = append(rows, m.wrap(blurb)...)
			rows = append(rows, "")
		}
		return rows
	case "providers":
		rows := m.title("Provider keys", countLabel(m.state.KeyCount, "key")+" saved")
		if m.height >= 22 {
			rows = append(rows, m.wrap("Save only the keys your task needs. / searches providers.")...)
			rows = append(rows, "")
		}
		if m.filtering || m.query != "" {
			rows = append(rows, p.cyan.Render("/ "+clean(m.query)), "")
		}
		return rows
	case "provider_keys":
		if m.selectedProvider != nil {
			return m.title(m.selectedProvider.Name, fmt.Sprintf("%d/%d keys saved", m.providerCount(*m.selectedProvider), len(m.selectedProvider.Key)))
		}
	case "profile_field":
		f := m.state.Fields[m.fieldAt]
		rows := m.title(f.Label, "")
		return append(rows, m.styledWrap(f.Description, p.muted)...)
	case "key":
		return m.title(m.key.Title, "")
	case "name":
		return m.title("Custom key", "")
	case "agent_targets":
		return m.title("Choose an agent", "")
	case "agent_home":
		return m.title("Connect agent", "")
	case "agent_copy":
		return m.title("Copy for this task", "")

	case "agents":
		count := 0
		added := 0
		for _, t := range m.reviewTargets() {
			if t.Added {
				added++
			}
			if !t.Added && t.Issue == "" {
				count += strings.Count(t.Addition, "\n")
			}
		}
		rows := m.title("Agent files", p.good.Render(fmt.Sprintf("+%d", count))+" "+p.bad.Render("−0"))
		if count == 0 {
			rows = m.title("Agent files", countLabel(added, "note")+" added")
		}

		return rows
	case "faq":
		return m.title("Help", "")
	case "faq_text":
		if m.faqAt < len(m.faq) {
			return m.title(m.faq[m.faqAt].Title, "")
		}
	}
	return nil
}
func (m model) body() []string {
	p := m.palette()
	w := m.innerWidth()
	rows := []string{}
	switch m.page {
	case "settings":
		if m.state.PreferencesError != "" {
			rows = append(rows, m.styledWrap(m.state.PreferencesError, p.warn)...)
			rows = append(rows, "")
		}
		if m.state.HistoryError != "" && m.state.HistoryError != m.state.PreferencesError {
			rows = append(rows, m.styledWrap(m.state.HistoryError, p.warn)...)
			rows = append(rows, "")
		}
		for i, name := range settingsNames {
			status := ""
			if i == 0 {
				status = "on"
				if m.opts.NoMotion || !m.colors {
					status = "off"
				}
				if m.motionForced {
					status += " · command flag"
				}
			}
			rows = append(rows, m.choice(name, status, i == m.selected, w))
		}
		rows = append(rows, "")
		descriptions := []string{"Animate the intro and selection highlights.", "Check installation and local files. Provider access is not tested.", "Download the latest release. Saved keys and business details stay in place.", "Replay the GODMODE intro.", "Return to the previous screen."}
		rows = append(rows, m.styledWrap(descriptions[min(max(0, m.selected), len(descriptions)-1)], p.muted)...)
	case "update":
		rows = append(rows, m.wrap("Download and install the latest Godmode release.")...)
		rows = append(rows, "")
		rows = append(rows, m.wrap("Your saved keys and business details stay in place. The updater keeps the previous executable.")...)
		rows = append(rows, "", m.choice("Update Godmode", "", m.selected == 0, w), m.choice("Back", "", m.selected == 1, w))
	case "shortcuts":
		for _, line := range m.shortcuts() {
			rows = append(rows, m.wrap(line)...)
		}
	case "actions":
		matches := m.matchActions()
		if len(matches) == 0 {
			rows = append(rows, m.wrap("No actions match. Try a provider name or a task.")...)
		}
		for i, a := range matches {
			rows = append(rows, m.choice(a.title, "", i == m.selected, w))
			if i == m.selected {
				rows = append(rows, m.styledWrap("  "+a.detail, p.muted)...)
			}
		}
	case "active", "recent_setups", "recent_details", "business", "contexts", "environments", "environment_new", "scope_name", "scope_details", "doctor":
		return m.managementBody()
	case "profile":
		if m.state.ProfileError != "" {
			return m.styledWrap(m.state.ProfileError, p.warn)
		}
		for i, f := range m.state.Fields {
			value := clean(strings.ReplaceAll(m.state.Profile[f.Name], "\n", " ↵ "))
			if value == "" {
				value = p.muted.Render("—")
			}
			rows = append(rows, m.choice(f.Label, ansi.Truncate(value, max(8, w/2), "…"), i == m.selected, w))
			if m.height >= 26 {
				rows = append(rows, "")
			}
		}
		rows = append(rows, "", m.choice("Back", "", m.selected == len(m.state.Fields), w))
	case "providers":
		if m.state.StoreError != "" {
			rows = append(rows, m.styledWrap(m.state.StoreError, p.warn)...)
			rows = append(rows, "")
		}
		for j, i := range m.providerMatches() {
			pr := m.state.Providers[i]
			count := m.providerCount(pr)
			status := ""
			if count > 0 {
				status = fmt.Sprintf("%d/%d", count, len(pr.Key))
				if m.providerReady(pr) {
					status = p.good.Render("saved")
				}
			}
			rows = append(rows, m.choice(pr.Name, status, j == m.selected, w))
			if j == m.selected && m.height >= 20 {
				rows = append(rows, "  "+p.muted.Render(ansi.Truncate(clean(pr.About), max(1, w-2), "…")))
			}
		}
		matches := len(m.providerMatches())
		if matches == 0 {
			rows = append(rows, m.styledWrap("No providers match. Esc clears search.", p.muted)...)
		}
		rows = append(rows, "")
		rows = append(rows, m.styledWrap("Missing a provider? Save a custom key or request a guide.", p.muted)...)
		rows = append(rows, m.choice("Custom key", "", m.selected == matches, w), m.choice("Open a GitHub issue", "", m.selected == matches+1, w), m.choice("Back", "", m.selected == matches+2, w))
	case "provider_keys":
		if m.selectedProvider != nil {
			for i, k := range m.selectedProvider.Key {
				label := k.Label
				if label == "" {
					label = k.Name
				}
				status := ""
				if m.state.States[k.Name] == "set" {
					status = p.good.Render("saved")
				}
				rows = append(rows, m.choice(label, status, i == m.selected, w))
				if i == m.selected {
					rows = append(rows, "  "+p.muted.Render(k.Name))
				}
			}
			rows = append(rows, "", m.choice("Back", "", m.selected == len(m.selectedProvider.Key), w))
		}
	case "profile_field":
		current := m.state.Profile[m.state.Fields[m.fieldAt].Name]
		if current != "" {
			rows = append(rows, p.muted.Render("Saved"))
			rows = append(rows, m.wrap(current)...)
			rows = append(rows, "")
		}
		rows = append(rows, strings.Split(p.cyan.Render("› ")+m.profileInput(), "\n")...)
	case "key":
		if m.details {
			if len(m.check.Command) > 0 {
				rows = append(rows, m.wrap("$ "+strings.Join(m.check.Command, " "))...)
			}
			if len(rows) == 0 {
				if m.key.Page != "" {
					rows = append(rows, m.styledWrap(m.key.Page, p.cyan)...)
					rows = append(rows, "")
				}
				rows = append(rows, m.wrap("Save destination: "+m.path(m.key.Path))...)
				rows = append(rows, "", p.muted.Render("Paste a key to review its exact edit."))
			}
		} else {
			if m.check.Valid {
				return nil
			}
			if m.key.Visit != "" {
				rows = append(rows, m.styledWrap(m.key.Visit, p.title)...)
			}
			if m.key.Page != "" {
				rows = append(rows, p.cyan.Render(ansi.Truncate(clean(m.key.Page), w, "…")))
			}
			if len(m.key.Steps) > 0 {
				rows = append(rows, "")
			}
			for i, step := range m.key.Steps {
				if i > 0 {
					rows = append(rows, "")
				}
				rows = append(rows, m.markdownBullet(step)...)
			}
			if m.key.Note != "" {
				rows = append(rows, "")
				rows = append(rows, m.styledWrap(m.key.Note, p.muted)...)
			}
		}
	case "name":
		rows = append(rows, m.wrap("Key name, such as ACME_TOKEN.")...)
		rows = append(rows, "", p.cyan.Render("› ")+clean(m.text)+"▏")
	case "agent_targets":
		if len(m.agents.Targets) == 0 {
			rows = append(rows, m.wrap("No installed agent folders found. Copy for this task works with any agent chat.")...)
			rows = append(rows, "", m.choice("Back", "", true, w))
			return rows
		}
		for i, t := range m.agents.Targets {
			status := ""
			if t.Added {
				status = "already added"
			}
			if t.Issue != "" {
				status = "needs attention"
			}
			rows = append(rows, m.choice(t.Name, status, i == m.selected, w))
			if i == m.selected {
				rows = append(rows, m.styledWrap("  "+t.Path, p.muted)...)
			}
		}
		rows = append(rows, "", m.choice("All detected agents", "", m.selected == len(m.agents.Targets), w), m.choice("Back", "", m.selected == len(m.agents.Targets)+1, w))
	case "agent_home":
		rows = append(rows, m.wrap("Your agent uses these instructions to find keys and business details.")...)
		rows = append(rows, "", m.choice("Copy for this task", "", m.selected == 0, w))
		rows = append(rows, m.choice("Add to agent files", countLabel(len(m.agents.Targets), "agent")+" found", m.selected == 1, w))
		rows = append(rows, m.choice("Back", "", m.selected == 2, w), "")
		if m.selected == 0 {
			rows = append(rows, m.styledWrap("Paste into your current agent chat, then ask for the result you want.", p.muted)...)
		}
		if m.selected == 1 {
			rows = append(rows, m.styledWrap("Review the files before appending. Existing instructions stay intact.", p.muted)...)
		}
	case "agent_copy":
		rows = append(rows, m.wrap("Paste into your current agent chat.")...)
		rows = append(rows, "")
		block := m.agents.CopyBlock
		if block == "" {
			block = m.agents.Block
		}
		for _, line := range strings.Split(strings.TrimSuffix(block, "\n"), "\n") {
			rows = append(rows, m.wrap(line)...)
		}

	case "agents":
		return m.agentLines()
	case "faq":
		for i, e := range m.faq {
			rows = append(rows, m.choice(e.Title, "", i == m.selected, w))
			if m.height >= 27 {
				rows = append(rows, "")
			}
		}
		rows = append(rows, "", m.choice("Back", "", m.selected == len(m.faq), w))
	case "faq_text":
		if m.faqAt < len(m.faq) {
			for i, para := range m.faq[m.faqAt].Paragraphs {
				if i > 0 {
					rows = append(rows, "")
				}
				sty := lipgloss.NewStyle()
				if strings.HasPrefix(para, "https://") {
					sty = p.cyan
				}
				rows = append(rows, m.styledWrap(para, sty)...)
			}
		}
	}
	return rows
}
func (m model) markdownBullet(s string) []string {
	// Catalog emphasis is static reviewed copy, never user input or executable code.
	p := m.palette()
	parts := strings.Split(clean(s), "**")
	for i := range parts {
		if i%2 == 1 {
			parts[i] = p.title.Render(parts[i])
		}
	}
	return strings.Split(ansi.Wrap("• "+strings.Join(parts, ""), m.innerWidth(), ""), "\n")
}
func (m model) profileInput() string {
	runes := []rune(m.text)
	at := min(max(0, m.cursor), len(runes))
	text := clean(string(runes[:at])) + "▏" + clean(string(runes[at:]))
	return ansi.Wrap(text, max(1, m.innerWidth()-2), "")
}
func (m model) keyFooter() []string {
	p := m.palette()
	rows := []string{}
	path := m.key.Path
	if m.check.Path != "" {
		path = m.check.Path
	}
	rows = append(rows, m.styledWrap(m.path(path), p.muted)...)
	assignment := m.check.Assignment
	operation := m.check.Operation
	if assignment == "" {
		assignment = m.key.Name + "=sealed(…)"
		operation = "Add"
		if m.key.Saved {
			operation = "Replace"
		}
	}
	sign := "+ "
	if operation == "Replace" {
		sign = "± "
	}
	rows = append(rows, m.styledWrap(sign+operation+" "+assignment, p.good)...)
	for _, note := range m.check.Notes {
		rows = append(rows, m.styledWrap(note, p.warn)...)
	}
	rows = append(rows, "")
	masked := m.check.Masked
	if m.text != "" && masked == "" {
		masked = strings.Repeat("•", min(24, utf8.RuneCountInString(m.text)))
	}
	prompt := m.key.Prompt
	if prompt == "" {
		prompt = "Paste your token:"
	}
	rows = append(rows, p.title.Render(clean(prompt))+" "+p.cyan.Render(ansi.Truncate(masked, max(4, m.innerWidth()-ansi.StringWidth(prompt)-2), "…"))+"▏")
	return rows
}
func (m model) footer() []string {
	p := m.palette()
	rows := []string{}
	if m.page == "key" {
		rows = append(rows, m.keyFooter()...)
	}
	rows = append(rows, m.statusLines()...)

	hint := "↑↓ move · Enter open · Esc back · ? keys"
	switch m.page {
	case "providers":
		hint = "↑↓ move · / search · Enter open · Esc back · ? keys"
	case "actions":
		hint = "Type to find · ↑↓ move · Enter open · Esc back"
	case "shortcuts":
		hint = "↑↓ / PgDn scroll · Esc back"
	case "doctor":
		hint = "↑↓ scroll · r check again · Esc back"
	case "scope_name":
		hint = "Enter create  ·  Esc back"
	case "contexts", "environments":
		hint = "↑↓ move  ·  Enter select  ·  Tab details  ·  Esc back"
	case "scope_details":
		hint = "↑↓ scroll  ·  Enter select  ·  Esc back"
	case "profile_field":
		hint = "Enter save  ·  Ctrl-U clear  ·  /clear remove  ·  Esc back"
	case "key":
		if m.text == "" {
			hint = "Tab details  ·  Esc back"
			if m.key.Page != "" {
				hint = "Enter open link  ·  " + hint
			}
		} else {
			hint = "Enter save  ·  Tab details  ·  Ctrl-U clear  ·  Esc back"
		}
	case "name":
		hint = "Enter continue  ·  Esc back"
	case "agent_copy":
		hint = "Enter / c copy · ↑↓ scroll · Esc back"

	case "agents":
		pending := false
		for _, t := range m.reviewTargets() {
			pending = pending || (!t.Added && t.Issue == "")
		}
		if pending {
			if m.reviewedUntil < len(m.agentLines()) {
				hint = "PgDn review changes · Esc back"
			} else {
				hint = "Enter append · ↑↓ scroll · Esc back"
			}
		} else if len(m.agents.Targets) == 0 {
			hint = "↑↓ scroll · c copy for this task · Esc back"
		} else {
			hint = "↑↓ scroll · c copy for this task · Esc back"
		}
	case "faq_text":
		hint = "↑↓ / PgDn scroll  ·  Esc back"
	}
	if m.innerWidth() < 48 {
		switch m.page {
		case "providers":
			hint = "↑↓ Enter · / search · Esc back"
		case "profile", "business", "active", "agent_targets", "agent_home", "settings", "update", "faq":
			hint = "↑↓ Enter · Esc back · ? keys"
		case "key":
			hint = "Tab details · Esc back"
			if m.text != "" {
				hint = "Enter save · Ctrl-U clear\nTab details · Esc back"
			} else if m.key.Page != "" {
				hint = "Enter open link · Tab details\nEsc back"
			}
		case "actions":
			hint = "Type to find · ↑↓ Enter · Esc back"
		case "agent_copy":
			hint = "Enter copy · ↑↓ scroll · Esc back"
		}
	}

	if m.innerWidth() < 48 {
		switch m.page {
		case "contexts", "environments":
			hint = "↑↓ Enter · Tab details · Esc back"
		case "scope_details":
			hint = "↑↓ scroll · Enter select · Esc back"
		}
	}
	if m.innerWidth() < 36 {
		switch m.page {
		case "contexts", "environments":
			hint = "↑↓ Enter · Tab details\nEsc back"
		case "scope_details":
			hint = "↑↓ · Enter select\nEsc back"
		}
	}
	if m.page == "providers" && m.query != "" {
		hint = "↑↓ Enter · / search · Esc clear search"
	}

	if m.page == "active" && len(m.state.RecentSetups) > 0 {
		hint = "↑↓ Enter · r recent · Esc back"
	}
	if m.page == "recent_setups" {
		hint = "↑↓ move · Enter review · Esc back"
	}
	if m.page == "recent_details" {
		hint = "Enter use · ↑↓ scroll · Esc back"
	}

	if m.busyValidation {
		hint = "Checking · edits retained · Esc back"
	} else if m.busyVisible {
		hint = "Ctrl-C exit"
	}
	if m.height >= 22 {
		rows = append(rows, "")
	}
	rows = append(rows, m.styledWrap(hint, p.muted)...)
	if m.page != "profile_field" && m.page != "scope_name" && m.page != "name" {
		total := len(m.body())
		available := max(1, m.height-len(m.header())-len(rows)-2)
		if total > available {
			room := max(1, available-1)
			start := m.listScroll(m.body(), room)
			end := min(total, start+room)
			position := fmt.Sprintf("%d–%d of %d", start+1, end, total)
			if end < total {
				position += "  ·  ↓ more"
			}
			rows = append(rows, p.muted.Render(position))
		}
	}
	return rows
}
func (m model) bodyRoom() int { return max(1, m.height-len(m.header())-len(m.footer())-2) }
func (m model) inputFits() bool {
	if m.width < 28 || m.height < 10 {
		return false
	}
	if m.page == "key" {
		return len(m.header())+len(m.footer())+3 <= m.height
	}
	if m.page == "profile_field" || m.page == "scope_name" {
		return len(m.header())+len(m.body())+len(m.footer())+2 <= m.height
	}
	return true
}
func (m model) agentLines() []string {
	p := m.palette()
	rows := []string{}
	if len(m.reviewTargets()) == 0 {
		rows = append(rows, m.wrap("No installed agent folders found.")...)
		rows = append(rows, "")
		rows = append(rows, m.wrap("Open your agent once, then reopen Godmode to find its instruction files.")...)
		rows = append(rows, "")
		rows = append(rows, m.wrap("Copy for this task works with any agent chat.")...)
		return rows
	}

	pending := 0
	for _, created := range []bool{true, false} {
		group := []target{}
		for _, t := range m.reviewTargets() {
			if !t.Added && t.Issue == "" && t.Created == created {
				group = append(group, t)
			}
		}
		if len(group) == 0 {
			continue
		}
		heading := "These files will be modified:"
		if created {
			heading = "These files will be created:"
		}
		rows = append(rows, m.styledWrap(heading, p.title)...)
		for _, t := range group {
			pending++
			// Every target receives the same note. Its separator can add blank lines;
			// each path's count includes those exact bytes without repeating the note.
			rows = append(rows, strings.Split(ansi.Wrap(clean(t.Path)+"  "+p.good.Render(fmt.Sprintf("+%d", strings.Count(t.Addition, "\n")))+" "+p.bad.Render("−0"), m.innerWidth(), ""), "\n")...)
			if t.Real != "" && t.Real != t.Path {
				rows = append(rows, m.styledWrap("→ "+t.Real, p.muted)...)
			}
		}
		rows = append(rows, "")
	}
	for _, t := range m.reviewTargets() {
		if t.Issue != "" {
			rows = append(rows, m.styledWrap(t.Path+": "+t.Issue, p.warn)...)
		}
		if t.Added {
			rows = append(rows, m.styledWrap("✓ "+t.Path+"  ·  already added", p.good)...)
		}
	}
	rows = append(rows, "", p.title.Render("Godmode note:"))
	for _, row := range strings.Split(strings.TrimSuffix(m.agents.Block, "\n"), "\n") {
		if pending > 0 {
			rows = append(rows, m.styledWrap("+ "+row, p.good)...)
		} else {
			rows = append(rows, m.wrap(row)...)
		}
	}
	rows = append(rows, "")
	rows = append(rows, m.styledWrap("Already added means either marker or \"godmode help\" was found. Existing wording is kept.", p.muted)...)
	rows = append(rows, "")
	rows = append(rows, m.styledWrap("Start a new agent session to load saved instructions. Copy for this task works in a running session.", p.muted)...)

	return rows
}

func (m *model) noteReview() {
	if m.page != "agents" {
		return
	}
	room := m.bodyRoom()
	if m.scroll <= m.reviewedUntil {
		m.reviewedUntil = max(m.reviewedUntil, min(len(m.agentLines()), m.scroll+room))
	}
}
func (m *model) clampScroll() { m.scroll = min(max(0, m.scroll), max(0, len(m.body())-m.bodyRoom())) }
func (m model) listScroll(lines []string, room int) int {
	if m.page == "agents" || m.page == "agent_copy" || m.page == "faq_text" || m.page == "doctor" || m.page == "shortcuts" || m.page == "recent_details" || m.page == "scope_details" || m.page == "key" || m.page == "profile_field" || m.page == "scope_name" {
		return min(max(0, m.scroll), max(0, len(lines)-room))
	}
	// A selected row stays in the viewport even when a description occupies another row.
	selectedLine := 0
	for i, row := range lines {
		if strings.HasPrefix(ansi.Strip(row), "❯ ") {
			selectedLine = i
			break
		}
	}
	return min(max(0, selectedLine-room/2), max(0, len(lines)-room))
}
func (m model) screenLines() []string {
	if m.page == "intro" {
		return m.introView()
	}
	if m.page == "home" {
		return m.homeView()
	}
	head, body, foot := m.header(), m.body(), m.footer()
	room := m.bodyRoom()
	if (m.page == "key" || m.page == "profile_field" || m.page == "scope_name") && !m.inputFits() {
		return append(m.styledWrap("Enlarge the terminal to review the full edit.", m.palette().warn), "", m.palette().muted.Render("Esc back"))
	}
	top := m.listScroll(body, room)
	end := min(len(body), top+room)
	shown := append([]string{}, body[top:end]...)

	lines := append([]string{}, head...)
	lines = append(lines, shown...)
	for len(lines)+len(foot) < m.height-2 {
		lines = append(lines, "")
	}
	return append(lines, foot...)
}
func (m model) View() tea.View {
	if m.quitting {
		v := tea.NewView("")
		v.AltScreen = true
		return v
	}
	rows := m.screenLines()
	w := m.innerWidth()
	margin := strings.Repeat(" ", m.margin())
	out := []string{}
	if m.height > 12 {
		out = append(out, "")
	}
	for _, row := range rows {
		// Each row has a hard cell bound. Untrusted text cannot become terminal control.
		for _, part := range strings.Split(row, "\n") {
			out = append(out, margin+ansi.Truncate(part, w, "…"))
		}
	}
	if len(out) > m.height {
		out = out[:m.height]
	}
	view := tea.NewView(strings.Join(out, "\n"))
	view.AltScreen = true
	return view
}
