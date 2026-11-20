package ui

import (
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"slices"
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

func (m model) keyHints(hint string) []string {
	p := m.palette()
	var rows []string
	for _, line := range strings.Split(hint, "\n") {
		row := ""
		for _, item := range strings.Split(line, "·") {
			binding, action, _ := strings.Cut(strings.TrimSpace(item), " ")
			chip := p.cyan.Render(binding) + p.muted.Render(" "+action)
			if row != "" && ansi.StringWidth(row+" · "+chip) > m.innerWidth() {
				rows, row = append(rows, row), ""
			}
			if row != "" {
				row += p.muted.Render(" · ")
			}
			row += chip
		}
		rows = append(rows, strings.Split(ansi.Wrap(row, m.innerWidth(), ""), "\n")...)
	}
	return rows
}
func (m model) title(title, detail string) []string {
	p := m.palette()
	rows := m.styledWrap(title, p.title)
	if detail != "" {
		last := len(rows) - 1
		if ansi.StringWidth(rows[last]+"  "+detail) <= m.innerWidth() {
			rows[last] += "  " + p.muted.Render(detail)
		} else {
			rows = append(rows, p.muted.Render(detail))
		}
	}
	if m.height >= 22 {
		rows = append(rows, "")
	}
	return rows
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

// One line of feedback keeps a short receipt from moving the controls.
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
	return m.styledWrap(text, style)
}

func pad(s string, n int) string { return s + strings.Repeat(" ", max(0, n-ansi.StringWidth(s))) }
func (m model) choice(name, status string, selected bool, width int) string {
	name = clean(name)
	var row string
	if status != "" {
		status = ansi.Truncate(status, max(4, width/2-2), "…")
		room := max(4, min(28, width-ansi.StringWidth(status)-3))
		name = ansi.Truncate(name, room, "…")
		row = pad(name, room+1) + status
	} else {
		row = ansi.Truncate(name, max(1, width-2), "…")
	}
	return m.menuLine(row, selected, width)
}

func (m model) menuLine(row string, selected bool, width int) string {
	if selected {
		style := m.palette().selected
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
		return style.Render(pad("❯ "+ansi.Strip(row), width))
	}
	return "  " + row
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
		return m.title("Recent loadouts", "keys / profile")
	case "recent_details":
		return m.title("Use this loadout", "")
	case "active":
		rows := m.title("Switch loadout", "")
		if m.height >= 18 {
			rows = append(rows, m.wrap("Pair a key environment with a profile for new commands.")...)
			rows = append(rows, "")
		}
		return rows
	case "business":
		rows := m.title("Profile", "")
		if m.state.Context == "" && m.height >= 20 {
			rows = append(rows, m.wrap("Automatic uses the profile saved with this key environment.")...)
		}
		return rows
	case "contexts":
		return m.title("Switch profile", "")
	case "environments":
		return m.title("Key environments", "")
	case "environment_new":
		return append(m.title("New environment", ""), m.wrap("Choose its starting values.")...)
	case "scope_name":
		if m.scopeKind == "environment" {
			return m.title("New environment", "")
		}
		return m.title("New profile", "")
	case "scope_details":
		if m.scopeReturn == "contexts" {
			return m.title("Profile", "")
		}
		return m.title("Environment details", "")
	case "doctor":
		return m.title("Check local files", "local files only")
	case "profile":
		title := "Profile"
		rows := m.title(title, fmt.Sprintf("%d/%d optional fields", len(m.state.Progress.Fields), len(m.state.Fields)))
		blurb := m.state.ProfileBlurb
		if blurb == "" {
			blurb = "Give your agent the names and contact details to use on your site, receipts and policies."
		}
		if m.height >= 22 {
			rows = append(rows, m.wrap(blurb)...)
			rows = append(rows, "")
		}
		return rows
	case "providers":
		rows := m.title("Provider keys", countLabel(m.state.KeyCount, "key")+" saved")
		if m.filtering || m.query != "" {
			rows = append(rows, p.cyan.Render("/ "+clean(m.query)), "")
		}
		return rows
	case "provider_keys":
		if m.selectedProvider != nil {
			return m.title(m.selectedProvider.Name, countLabel(m.providerCount(*m.selectedProvider), "field")+" saved")
		}
	case "profile_field":
		f := m.state.Fields[m.fieldAt]
		rows := m.title(f.Label, "Profile · "+m.profileIdentity())
		return append(rows, m.styledWrap(f.Description, p.muted)...)
	case "key":
		return m.title(m.key.Title, "")
	case "name":
		return m.title("Custom key", "")
	case "agent_targets":
		return m.title("Choose an agent", "")
	case "agent_home":
		return m.title("Agent instructions", "")
	case "agent_copy":
		return m.title("Copy instructions for chat", "")

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
		descriptions := []string{"Animate the intro and selection highlights.", "Check installation and local files. Provider access is not tested.", "Download the latest release. Saved keys and profile stay in place.", "Replay the GODMODE intro.", "Return to the previous screen."}
		rows = append(rows, m.styledWrap(descriptions[min(max(0, m.selected), len(descriptions)-1)], p.muted)...)
	case "update":
		rows = append(rows, m.wrap("Download and install the latest Godmode release.")...)
		rows = append(rows, "")
		rows = append(rows, m.wrap("Your saved keys and profile stay in place. The updater keeps the previous executable.")...)
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
			if f.Group != "" && (i == 0 || f.Group != m.state.Fields[i-1].Group) {
				rows = append(rows, p.brand.Render(clean(f.Group)))
			}
			value := clean(strings.ReplaceAll(m.state.Profile[f.Name], "\n", " ↵ "))
			if value == "" {
				value = p.muted.Render("—")
			}
			labelWidth := max(1, min(28, w/2-1))
			row := pad(ansi.Truncate(clean(f.Label), labelWidth-1, "…"), labelWidth)
			row += ansi.Truncate(value, max(1, w-labelWidth-2), "…")
			rows = append(rows, m.menuLine(row, i == m.selected, w))
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
			if w >= 60 {
				name := pad(clean(pr.Name), 14)
				desc := ansi.Truncate(clean(pr.About), w-19-ansi.StringWidth(status), "…")
				line := name + p.muted.Render(desc)
				if status != "" {
					line = pad(line, w-3-ansi.StringWidth(status)) + status
				}
				rows = append(rows, m.menuLine(line, j == m.selected, w))
			} else {
				rows = append(rows, m.choice(pr.Name, status, j == m.selected, w))
				if j == m.selected && m.height >= 16 {
					rows = append(rows, m.styledWrap(pr.About, p.muted)...)
				}
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
			if m.selectedProvider.Benefit != "" {
				rows = append(rows, m.wrap(m.selectedProvider.Benefit)...)
				rows = append(rows, "")
			}
			guide := "Choose the credential your task needs."
			if len(m.selectedProvider.Ready) == 0 {
				guide = "Save each field to use this provider."
			}
			rows = append(rows, m.styledWrap(guide, p.muted)...)
			for i, k := range m.selectedProvider.Key {
				label := k.Label
				if label == "" {
					label = k.Name
				}
				status := ""
				if m.state.States[k.Name] == "set" {
					status = p.good.Render("saved")
				} else if len(m.selectedProvider.Ready) > 0 {
					used := slices.ContainsFunc(m.selectedProvider.Ready, func(group []string) bool {
						return slices.Contains(group, k.Name)
					})
					if !used {
						status = "optional"
					}
				}
				const labelWidth = 23
				if labelWidth+ansi.StringWidth(k.Name)+12 <= w {
					line := pad(ansi.Truncate(clean(label), labelWidth-1, "…"), labelWidth) + p.muted.Render(clean(k.Name))
					if status != "" {
						line = pad(line, w-3-ansi.StringWidth(status)) + status
					}
					rows = append(rows, m.menuLine(line, i == m.selected, w))
				} else {
					rows = append(rows, m.choice(label, status, i == m.selected, w))
					if i == m.selected {
						rows = append(rows, m.styledWrap("  "+k.Name, p.muted)...)
					}
				}
			}
			rows = append(rows, "", m.choice("Back", "", m.selected == len(m.selectedProvider.Key), w))
		}
	case "profile_field":
		if f := m.state.Fields[m.fieldAt]; m.text == "" && f.Example != "" && m.state.Profile[f.Name] == "" {
			rows = append(rows, m.styledWrap("Example: "+f.Example, p.muted)...)
		}
		rows = append(rows, strings.Split(p.cyan.Render("› ")+m.profileInput(), "\n")...)
	case "key":
		if m.details {
			if m.key.Page != "" {
				rows = append(rows, m.styledWrap(m.key.Page, p.cyan)...)
				rows = append(rows, "")
			}
			if len(m.check.Command) > 0 {
				rows = append(rows, m.wrap("$ "+strings.Join(m.check.Command, " "))...)
			} else {
				rows = append(rows, m.wrap("Save destination: "+m.path(m.key.Path))...)
			}
			if m.key.Guide != "" {
				rows = append(rows, "")
				rows = append(rows, m.styledWrap("$ "+m.key.Guide, p.cyan)...)
			}
			if m.key.Access != "" {
				rows = append(rows, "", p.title.Render("Access"))
				rows = append(rows, m.wrap(m.key.Access)...)
			}
		} else {
			compact := m.height < 22
			if m.key.Benefit != "" && !compact {
				rows = append(rows, m.wrap(m.key.Benefit)...)
				rows = append(rows, "")
			}
			if m.key.Visit != "" && m.key.Visit != m.key.Title && (!compact || m.key.Page == "") {
				rows = append(rows, m.styledWrap(m.key.Visit, p.title)...)
			}
			if m.key.Page != "" {
				link := m.key.Page
				if ansi.StringWidth(link) > w {
					if parsed, err := url.Parse(link); err == nil && parsed.Host != "" {
						link = parsed.Host
					}
				}
				rows = append(rows, p.cyan.Render(ansi.Truncate(clean(link), w, "…")))
			}
			if !compact && len(m.key.Steps) > 0 && len(rows) > 0 {
				rows = append(rows, "")
			}
			for i, step := range m.key.Steps {
				rows = append(rows, m.numberedStep(i+1, step)...)
			}
			if m.key.Note != "" {
				rows = append(rows, "")
				rows = append(rows, m.styledWrap(m.key.Note, p.muted)...)
			}
			if m.key.Benefit != "" && compact {
				rows = append(rows, "")
				rows = append(rows, m.wrap(m.key.Benefit)...)
			}
		}
	case "name":
		rows = append(rows, m.wrap("Key name, such as ACME_TOKEN.")...)
		rows = append(rows, "", p.cyan.Render("› ")+clean(m.text)+"▏")
	case "agent_targets":
		if len(m.agents.Targets) == 0 {
			rows = append(rows, m.wrap("No installed agent folders found. You can still copy the instructions into a chat.")...)
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
		rows = append(rows, m.wrap("Copy the instructions into your agent chat, or append them to an agent file.")...)
		rows = append(rows, "", m.choice("Copy instructions for chat", "", m.selected == 0, w))
		rows = append(rows, m.choice("Add to agent files", countLabel(len(m.agents.Targets), "agent")+" found", m.selected == 1, w))
		rows = append(rows, m.choice("Back", "", m.selected == 2, w), "")
		if m.selected == 0 {
			rows = append(rows, m.styledWrap(m.chatExample(), p.muted)...)
		}
		if m.selected == 1 {
			rows = append(rows, m.styledWrap("Review the files before appending. Existing instructions stay intact.", p.muted)...)
		}
	case "agent_copy":
		rows = append(rows, m.wrap("Paste the instructions into your agent chat.")...)
		rows = append(rows, m.styledWrap(m.chatExample(), p.muted)...)
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
func (m model) chatExample() string {
	if m.state.StoreError == "" {
		for _, pr := range m.state.Providers {
			if !m.providerReady(pr) {
				continue
			}
			switch pr.ID {
			case "github":
				return "Then ask: Which GitHub account does my key belong to?"
			case "cloudflare":
				return "Then ask: Which Cloudflare zones can my token read?"
			case "vercel":
				return "Then ask: Which Vercel projects can my token see?"
			case "supabase":
				return "Then ask: Which Supabase projects can my token see?"
			case "stripe":
				return "Then ask: Which Stripe account does my saved key belong to?"
			case "posthog":
				return "Then ask: Which PostHog projects can my key read?"
			case "notion":
				return "Then ask: Which Notion pages are shared with my integration?"
			case "gmail":
				return "Then ask: Which Gmail address is in my loadout?"
			case "google":
				return "Then ask: Which Google tools do I have keys for?"
			default:
				return "Then ask: Which " + clean(pr.Name) + " keys are saved in my loadout?"
			}
		}
	}
	return "Then ask: Which providers and profile details are in my loadout?"
}

func (m model) numberedStep(number int, s string) []string {
	// Catalog emphasis is static reviewed copy, never user input or executable code.
	p := m.palette()
	parts := strings.Split(clean(s), "**")
	for i := range parts {
		if i%2 == 1 {
			parts[i] = p.title.Render(parts[i])
		}
	}
	rows := strings.Split(ansi.Wrap(strings.Join(parts, ""), max(1, m.innerWidth()-3), ""), "\n")
	for i := range rows {
		if i == 0 {
			rows[i] = p.cyan.Render(fmt.Sprintf("%d. ", number)) + rows[i]
		} else {
			rows[i] = "   " + rows[i]
		}
	}
	return rows
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
	if m.text != "" {
		rows = append(rows, m.styledWrap(m.path(path), p.muted)...)
	}
	assignment := m.check.Assignment
	operation := m.check.Operation
	if assignment == "" {
		assignment = m.key.Name
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
	if m.text == "" && m.key.Example != "" {
		rows = append(rows, m.styledWrap("Example: "+m.key.Example, p.muted)...)
	} else if m.text != "" || m.height >= 22 {
		rows = append(rows, "")
	}
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

	hint := "↑↓ move · Enter choose · Esc back · ? keys"
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
		hint = "↑↓ move · Enter choose · Esc back"
		if (m.page == "contexts" && m.selected < len(m.contexts)) ||
			(m.page == "environments" && m.selected < len(m.environments)) {
			hint = "↑↓ move · Enter select · Tab details · Esc back"
		}
	case "scope_details":
		hint = "↑↓ scroll  ·  Enter select  ·  Esc back"
	case "profile_field":
		hint = "Enter save · Ctrl-U erase input · /clear remove saved value · Esc back"
	case "key":
		hint = "Enter save · Tab details · Ctrl-U clear · Esc back"
		if m.details {
			hint = "Enter save · Tab guide · Ctrl-U clear · Esc back"
		}
		if m.key.Page != "" {
			hint = "Ctrl-O open link · " + hint
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
			hint = "↑↓ scroll · c copy task note · Esc back"
		} else {
			hint = "↑↓ scroll · c copy task note · Esc back"
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
		case "actions":
			hint = "Type to find · ↑↓ Enter · Esc back"
		case "agent_copy":
			hint = "Enter copy · ↑↓ scroll · Esc back"
		}
	}

	if m.page == "providers" && m.query != "" {
		hint = "↑↓ move · Enter open · Esc clear search"
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
	if len(m.trail) == 0 && m.initialRoute != "home" && m.query == "" && !m.filtering && !m.details {
		switch m.page {
		case "providers", "agent_home", "profile", "settings", "faq":
			hint = strings.Replace(hint, "Esc back", "Esc quit", 1)
		case "key":
			if m.keyReturn == "exit" {
				hint = strings.Replace(hint, "Esc back", "Esc cancel", 1)
			}
		}
	}

	if m.busyValidation {
		hint = "Checking · edits retained · Esc back"
	} else if m.busyVisible {
		hint = "Ctrl-C exit"
	}
	rows = append(rows, m.keyHints(hint)...)
	if m.page != "profile_field" && m.page != "scope_name" && m.page != "name" {
		total := len(m.body())
		available := max(1, m.height-len(m.header())-len(rows)-2)
		if total > available {
			room := max(1, available-1)
			start := m.listScroll(m.body(), room)
			end := min(total, start+room)
			position := fmt.Sprintf("Lines %d–%d of %d", start+1, end, total)
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
		rows = append(rows, m.wrap("You can paste the instructions into any agent chat.")...)
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
	rows = append(rows, m.styledWrap("Start a new agent session to load saved instructions, or paste them into your current chat.", p.muted)...)

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
	if len(body) > 0 && (m.page == "key" || strings.TrimSpace(ansi.Strip(foot[0])) != "") {
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
	if m.height > 12 && (m.page != "home" || m.height >= 22) {
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
