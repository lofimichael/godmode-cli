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
	return []string{row, ""}
}
func (m model) path(path string) string {
	home, e := os.UserHomeDir()
	if e == nil && strings.HasPrefix(path, home+string(filepath.Separator)) {
		return "~/" + clean(strings.TrimPrefix(path, home+string(filepath.Separator)))
	}
	return clean(path)
}
func (m model) introLines() []string {
	p := m.palette()
	rows := m.logo(m.height >= 20)
	rows = append(rows, "")
	rows = append(rows, m.styledWrap("GODMODE gives your agents the goddamn keys.", p.title)...)
	rows = append(rows, "")
	rows = append(rows, m.wrap("Your profile and keys are stored in files on this machine.")...)
	rows = append(rows, "")
	rows = append(rows, m.styledWrap("Agents use these keys as you. They can spend money, change live systems and delete data.", p.warn)...)
	return rows
}
func (m model) introFits() bool { return m.width >= 28 && len(m.introLines())+4 <= m.height }
func (m model) introView() []string {
	p := m.palette()
	if !m.introFits() {
		return append(m.styledWrap("Enlarge the terminal to read the account-access statement.", p.warn), "", p.muted.Render("Esc exits"))
	}
	rows := m.introLines()
	if !m.opts.NoMotion && m.colors && m.tick < 6 {
		artRows := len(m.logo(m.height >= 20))
		for i := m.tick; i < min(artRows, 6); i++ {
			rows[i] = ""
		}
	}
	action := "Enter accept and set up"
	if m.initialRoute == "intro" {
		action = "Enter accept"
	}
	if m.error != "" {
		rows = append(rows, m.styledWrap(m.error, p.bad)...)
	}
	rows = append(rows, "", p.muted.Render(action+"  ·  Esc exit"))
	return rows
}
func (m model) homeView() []string {
	p, w := m.palette(), m.innerWidth()
	rows := []string{}
	if m.height >= 22 {
		rows = append(rows, m.logo(m.height >= 31 && w >= 63)...)
		rows = append(rows, "")
	} else {
		rows = append(rows, p.brand.Render("GODMODE"))
	}
	rows = append(rows, m.scopeLines()...)
	if m.height >= 18 {
		rows = append(rows, "")
	}
	statuses := []string{
		countLabel(len(m.state.Progress.Fields), "field"),
		countLabel(m.state.KeyCount, "key") + " stored",
		countLabel(max(len(m.state.Progress.Agents), m.state.Progress.Agent), "note") + " added",
		"Key files", "Check local setup", "Install latest", "", "", "",
	}
	if m.state.ProfileError != "" {
		statuses[0] = "cannot read"
	}
	if m.state.StoreError != "" {
		statuses[1] = "cannot read"
	}
	if !m.state.MusicIncluded {
		statuses[7] = "not installed"
	}
	if w < 45 {
		statuses[4], statuses[5] = "", ""
	}
	if w < 40 && m.state.StoreError == "" {
		statuses[1] = countLabel(m.state.KeyCount, "key")
	}
	choices := []string{}
	for i, name := range homeNames {
		choices = append(choices, m.choice(name, statuses[i], i == m.selected, w))
	}
	foot := []string{}
	if m.error != "" {
		foot = append(foot, m.styledWrap(m.error, p.bad)...)
	} else if m.notice != "" {
		foot = append(foot, m.styledWrap(m.notice, p.good)...)
	}
	hint := "↑↓ move  ·  Enter open  ·  Esc quit"
	if w < 36 {
		hint = "↑↓ Enter · Esc quit"
	}
	foot = append(foot, p.muted.Render(hint))
	leading := 0
	if m.height > 12 {
		leading = 1
	}
	room := max(1, m.height-leading-len(rows)-len(foot))
	start := min(max(0, m.selected-room/2), max(0, len(choices)-room))
	rows = append(rows, choices[start:min(len(choices), start+room)]...)
	for len(rows)+len(foot) < m.height-leading {
		rows = append(rows, "")
	}
	return append(rows, foot...)
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
	if status != "" {
		room := max(4, width-ansi.StringWidth(status)-3)
		name = ansi.Truncate(name, room, "…")
		return pointer + pad(name, room+1) + status
	}
	return pointer + ansi.Truncate(name, max(1, width-2), "…")
}
func (m model) header() []string {
	rows := m.scopeLines()
	if m.height >= 18 {
		rows = append(rows, "")
	}
	return append(rows, m.pageHeader()...)
}
func (m model) pageHeader() []string {
	p := m.palette()
	switch m.page {
	case "business":
		rows := m.title("Business", "")
		if m.state.Context == "" && m.height >= 20 {
			rows = append(rows, m.wrap("Automatic uses the selected environment's profile.")...)
		}
		return rows
	case "contexts":
		return m.title("Switch business", "")
	case "environments":
		return m.title("Environments", "")
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
		return m.title("Doctor", "Read-only checks")
	case "profile":
		title := "Profile"
		if m.state.Context != "" {
			title += " · " + m.state.Context
		}
		rows := m.title(title, fmt.Sprintf("%d/%d optional fields", len(m.state.Progress.Fields), len(m.state.Fields)))
		blurb := m.state.ProfileBlurb
		if blurb == "" {
			blurb = "Full sites that take payments usually require a business profile, terms of service and a privacy policy. Agents use these details to fill them in."
		}
		if m.height >= 18 {
			rows = append(rows, m.wrap(blurb)...)
			rows = append(rows, "")
		}
		return rows
	case "providers":
		rows := m.title("Providers", countLabel(m.state.KeyCount, "key")+" stored")
		if m.height >= 17 {
			rows = append(rows, m.wrap("Add or replace keys in this environment.")...)
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
		if m.text == "" && !m.details {
			return nil
		}
		return m.title(m.key.Title, "")
	case "name":
		return m.title("Another key", "")
	case "agents":
		count := 0
		added := 0
		for _, t := range m.agents.Targets {
			if t.Added {
				added++
			}
			if !t.Added && t.Issue == "" {
				count += strings.Count(t.Addition, "\n")
			}
		}
		rows := m.title("Agents", p.good.Render(fmt.Sprintf("+%d", count))+" "+p.bad.Render("−0"))
		if count == 0 {
			rows = m.title("Agents", countLabel(added, "note")+" added")
		}
		command := m.styledWrap(m.command("agents", "--print"), p.muted)
		if len(command) <= m.height-len(m.scopeLines())-len(rows)-10 {
			rows = append(rows, command...)
		}
		return rows
	case "faq":
		return m.title("Help / FAQ", "")
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
	case "business", "contexts", "environments", "environment_new", "scope_name", "scope_details", "doctor":
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
			rows = append(rows, p.muted.Render("No providers match."))
		}
		rows = append(rows, "")
		rows = append(rows, m.wrap("Don't see a provider you want? Open a GitHub issue! We'll get on it.")...)
		rows = append(rows, m.choice("Another key", "", m.selected == matches, w), m.choice("Open a GitHub issue", "", m.selected == matches+1, w), m.choice("Back", "", m.selected == matches+2, w))
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
				rows = append(rows, p.muted.Render("Paste a key to see its exact edit."))
			}
		} else {
			if m.check.Valid {
				return nil
			}
			if m.key.Visit != "" {
				rows = append(rows, m.styledWrap(m.key.Visit, p.title)...)
			}
			if m.key.Page != "" {
				rows = append(rows, m.styledWrap(m.key.Page, p.cyan)...)
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
	if m.error != "" {
		rows = append(rows, m.styledWrap(m.error, p.bad)...)
	} else if m.page == "key" && m.check.Error != "" {
		rows = append(rows, m.styledWrap(m.check.Error, p.warn)...)
	} else if m.notice != "" {
		rows = append(rows, m.styledWrap(m.notice, p.good)...)
	}
	hint := "↑↓ move  ·  Enter open  ·  Esc back"
	switch m.page {
	case "providers":
		hint = "↑↓ move  ·  / search  ·  Enter open  ·  Esc back"
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
	case "agents":
		pending := false
		for _, t := range m.agents.Targets {
			pending = pending || (!t.Added && t.Issue == "")
		}
		if pending {
			hint = "↑↓ / PgDn scroll  ·  Enter append  ·  c copy  ·  Esc back"
		} else if len(m.agents.Targets) == 0 {
			hint = "↑↓ scroll  ·  c copy  ·  m mark as added  ·  Esc back"
		} else {
			hint = "↑↓ scroll  ·  c copy  ·  Esc back"
		}
	case "faq_text", "doctor":
		hint = "↑↓ / PgDn scroll  ·  Esc back"
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
	rows = append(rows, "")
	rows = append(rows, m.styledWrap(hint, p.muted)...)
	if m.page == "agents" || m.page == "faq_text" || m.page == "doctor" || m.page == "scope_details" || m.page == "key" {
		total := len(m.body())
		available := max(1, m.height-len(m.header())-len(rows)-2)
		if total > available {
			room := max(1, available-1)
			start := min(max(0, m.scroll), max(0, total-room))
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
	copyBlock := m.agents.CopyBlock
	if copyBlock == "" {
		copyBlock = m.agents.Block
	}
	if len(m.agents.Targets) == 0 {
		rows = append(rows, m.wrap("No agent folders found. Add this note to your agent's instructions.")...)
		rows = append(rows, "")
		for _, row := range strings.Split(strings.TrimSuffix(copyBlock, "\n"), "\n") {
			rows = append(rows, m.wrap(row)...)
		}
		return rows
	}
	pending := 0
	for _, created := range []bool{true, false} {
		group := []target{}
		for _, t := range m.agents.Targets {
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
	for _, t := range m.agents.Targets {
		if t.Issue != "" {
			rows = append(rows, m.styledWrap(t.Path+": "+t.Issue, p.warn)...)
		}
		if t.Added {
			rows = append(rows, m.styledWrap("✓ "+t.Path+"  ·  already added", p.good)...)
		}
	}
	if pending > 0 {
		for _, row := range strings.Split(strings.TrimSuffix(m.agents.Block, "\n"), "\n") {
			rows = append(rows, m.styledWrap("+ "+row, p.good)...)
		}
	}
	rows = append(rows, "", p.title.Render("Copy for this task"))
	for _, row := range strings.Split(strings.TrimSuffix(copyBlock, "\n"), "\n") {
		rows = append(rows, m.wrap(row)...)
	}
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
	if m.page == "agents" || m.page == "faq_text" || m.page == "doctor" || m.page == "scope_details" || m.page == "key" || m.page == "profile_field" || m.page == "scope_name" {
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
