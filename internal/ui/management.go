package ui

import (
	"fmt"
	"path/filepath"
	"strings"
	"unicode/utf8"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"
)

var homeNames = []string{"Business", "Providers", "Agents", "Environments", "Doctor", "Update", "Help / FAQ", "Music", "Done"}

type businessContext struct {
	Name        string
	ProfilePath string `json:"profile_path"`
}
type environment struct {
	Name, Path string
	Keys       int
}
type doctorCheck struct{ Name, Status, Detail, Action string }
type doctorReport struct {
	OK     bool `json:"ok"`
	Checks []doctorCheck
}
type doctorMsg struct {
	request int
	report  doctorReport
	err     error
}

func scopeName(name string) string {
	if name == "" {
		return "default"
	}
	return clean(name)
}

func businessName(name string) string {
	if name == "" {
		return "Automatic"
	}
	return clean(name)
}

func countLabel(n int, name string) string {
	if n != 1 {
		name += "s"
	}
	return fmt.Sprintf("%d %s", n, name)
}

func shellArgument(value string) string {
	if value != "" && strings.IndexFunc(value, func(r rune) bool {
		return !(r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' || r >= '0' && r <= '9' || strings.ContainsRune("_./:-", r))
	}) < 0 {
		return value
	}
	return "'" + strings.ReplaceAll(value, "'", "'\\''") + "'"
}

func (m model) command(action ...string) string {
	words := []string{"godmode"}
	if m.opts.Home != "" {
		words = append(words, "--home", m.opts.Home)
	}
	if m.state.Context != "" {
		words = append(words, "--context", m.state.Context)
	}
	if m.state.Environment != "" && m.state.Environment != "default" {
		words = append(words, "--env", m.state.Environment)
	}
	words = append(words, action...)
	for i, word := range words {
		words[i] = shellArgument(word)
	}
	return clean(strings.Join(words, " "))
}

func (m model) scopeLines() []string {
	p := m.palette()
	business, keys := "Business: "+businessName(m.state.Context), "Keys: "+scopeName(m.state.Environment)
	if ansi.StringWidth(business+" · "+keys) <= m.innerWidth() {
		return []string{p.muted.Render(business + " · " + keys)}
	}
	return []string{p.muted.Render(ansi.Truncate(business, m.innerWidth(), "…")), p.muted.Render(ansi.Truncate(keys, m.innerWidth(), "…"))}
}

func (m *model) external(command error) tea.Cmd {
	m.outcome = &CommandExit{Command: command, Context: m.state.Context, Environment: m.state.Environment}
	m.quitting = true
	return tea.Quit
}

func (m *model) loadContexts() {
	var reply struct {
		Contexts []businessContext
		Selected string
	}
	if m.call("context_list", nil, &reply) {
		m.contexts = reply.Contexts
		m.page, m.selected, m.scroll = "contexts", 0, 0
		for i, c := range m.contexts {
			if c.Name == reply.Selected {
				m.selected = i
			}
		}
	}
}

func (m *model) loadEnvironments() {
	var reply struct {
		Environments []environment
		Selected     string
	}
	if m.call("environment_list", nil, &reply) {
		m.environments = reply.Environments
		m.page, m.selected, m.scroll = "environments", 0, 0
		for i, e := range m.environments {
			if scopeName(e.Name) == scopeName(reply.Selected) {
				m.selected = i
			}
		}
	}
}

func (m *model) loadDoctor() tea.Cmd {
	m.page, m.scroll = "doctor", 0
	m.doctor, m.doctorLoading = doctorReport{}, true
	m.doctorRequest++
	request, backend := m.doctorRequest, m.backend
	return func() tea.Msg {
		data, err := backend.Call("doctor", nil)
		result := doctorMsg{request: request, err: err}
		if err == nil {
			result.err = decode(data, &result.report)
		}
		return result
	}
}

func (m *model) startScopeName(kind, copy string) {
	m.resetInput()
	m.scopeKind, m.scopeCopy = kind, copy
	m.page = "scope_name"
}

func (m *model) openScopeDetails() {
	if (m.page == "contexts" && m.selected < len(m.contexts)) ||
		(m.page == "environments" && m.selected < len(m.environments)) {
		m.scopeReturn, m.page, m.scroll = m.page, "scope_details", 0
	}
}

func (m *model) selectScope(action, name string) bool {
	var next snapshot
	if !m.call(action, map[string]any{"name": name}, &next) {
		return false
	}
	m.state = next
	if m.state.Profile == nil {
		m.state.Profile = map[string]string{}
	}
	if m.state.States == nil {
		m.state.States = map[string]string{}
	}
	return true
}

func (m *model) enterManagement() tea.Cmd {
	switch m.page {
	case "business":
		switch m.selected {
		case 0:
			m.profileReturn = "business"
			m.page, m.selected = "profile", min(m.fieldAt, len(m.state.Fields))
		case 1:
			m.loadContexts()
		case 2:
			m.startScopeName("context", "")
		case 3:
			return m.back()
		}
	case "contexts":
		if m.selected < len(m.contexts) {
			name := m.contexts[m.selected].Name
			if m.selectScope("context_select", name) {
				m.notice = "Business: " + businessName(name)
				m.page, m.selected = "business", 0
			}
		} else if m.selected == len(m.contexts) {
			m.startScopeName("context", "")
		} else {
			return m.back()
		}
	case "environments":
		if m.selected < len(m.environments) {
			name := m.environments[m.selected].Name
			if m.selectScope("environment_select", name) {
				m.notice = "Keys: " + scopeName(name)
				return m.back()
			}
		} else if m.selected == len(m.environments) {
			m.page, m.selected = "environment_new", 0
		} else {
			return m.back()
		}
	case "environment_new":
		switch m.selected {
		case 0:
			m.startScopeName("environment", "")
		case 1:
			if !m.state.StoreExists {
				m.error = "Current environment has no saved file."
				return nil
			}
			m.startScopeName("environment", scopeName(m.state.Environment))
		case 2:
			return m.back()
		}
	}
	return nil
}

func (m *model) editScope(msg tea.KeyPressMsg) (tea.Model, tea.Cmd) {
	key := msg.String()
	if key == "enter" {
		if !m.inputFits() {
			m.error = "Enlarge the terminal to review the new file."
			return *m, nil
		}
		if strings.TrimSpace(m.text) == "" {
			m.error = "Enter a name."
			return *m, nil
		}
		args := map[string]any{"name": m.text}
		if m.scopeCopy != "" {
			args["copy"] = m.scopeCopy
		}
		var next snapshot
		if m.call(m.scopeKind+"_create", args, &next) {
			m.state = next
			m.notice = "Created " + clean(m.text) + "."
			m.resetInput()
			if m.scopeKind == "environment" {
				m.loadEnvironments()
			} else {
				m.page, m.selected = "business", 0
			}
		}
		return *m, nil
	}
	runes := []rune(m.text)
	m.cursor = min(max(0, m.cursor), len(runes))
	switch key {
	case "ctrl+u":
		m.text, m.cursor = "", 0
	case "backspace":
		if m.cursor > 0 {
			m.text = string(append(runes[:m.cursor-1], runes[m.cursor:]...))
			m.cursor--
		}
	case "delete":
		if m.cursor < len(runes) {
			m.text = string(append(runes[:m.cursor], runes[m.cursor+1:]...))
		}
	case "left":
		m.cursor = max(0, m.cursor-1)
	case "right":
		m.cursor = min(len(runes), m.cursor+1)
	case "home", "ctrl+a":
		m.cursor = 0
	case "end", "ctrl+e":
		m.cursor = len(runes)
	default:
		add := printable(msg.Text)
		limit := 48
		if m.scopeKind == "environment" {
			limit = 96
		}
		if add != "" && utf8.RuneCountInString(m.text+add) <= limit {
			m.text = string(runes[:m.cursor]) + add + string(runes[m.cursor:])
			m.cursor += utf8.RuneCountInString(add)
		}
	}
	m.error = ""
	return *m, nil
}

func (m model) managementNames() []string {
	switch m.page {
	case "business":
		return []string{"Edit profile", "Switch business", "New business", "Back"}
	case "environment_new":
		return []string{"Empty", "Copy current", "Back"}
	case "contexts":
		names := []string{}
		for _, c := range m.contexts {
			names = append(names, businessName(c.Name))
		}
		return append(names, "New business", "Back")
	case "environments":
		names := []string{}
		for _, e := range m.environments {
			names = append(names, scopeName(e.Name))
		}
		return append(names, "New environment", "Back")
	}
	return nil
}

func (m model) managementBody() []string {
	p, w := m.palette(), m.innerWidth()
	rows := []string{}
	if m.page == "scope_details" {
		name, path := "", ""
		if m.scopeReturn == "contexts" && m.selected < len(m.contexts) {
			name, path = businessName(m.contexts[m.selected].Name), m.contexts[m.selected].ProfilePath
		}
		if m.scopeReturn == "environments" && m.selected < len(m.environments) {
			e := m.environments[m.selected]
			name, path = scopeName(e.Name), e.Path
			rows = append(rows, countLabel(e.Keys, "key")+" stored", "")
		}
		rows = append(rows, m.styledWrap(name, p.title)...)
		rows = append(rows, "")
		return append(rows, m.wrap(m.path(path))...)
	}
	if m.page == "scope_name" {
		rows = append(rows, "Name")
		rows = append(rows, strings.Split(p.cyan.Render("› ")+m.profileInput(), "\n")...)
		rows = append(rows, "")
		name := m.text
		if name == "" {
			name = "NAME"
		}
		if m.scopeKind == "environment" {
			rows = append(rows, m.wrap(m.path(filepath.Join(m.state.Home, ".env.godmode."+name)))...)
			if m.scopeCopy != "" {
				rows = append(rows, "")
				rows = append(rows, m.wrap("Copy of "+m.path(m.state.EnvPath))...)
				rows = append(rows, m.wrap("Copies saved values. Later edits stay separate.")...)
			} else {
				rows = append(rows, "Starts empty.")
			}
		} else {
			rows = append(rows, m.wrap(m.path(filepath.Join(m.state.Home, "contexts", name, "context.json")))...)
			rows = append(rows, "Business settings. Profile starts empty.")
		}
		return rows
	}
	if m.page == "doctor" {
		if m.doctorLoading {
			return []string{"Checking local files…"}
		}
		if len(m.doctor.Checks) == 0 {
			return []string{"No check results."}
		}
		for i, check := range m.doctor.Checks {
			if i > 0 {
				rows = append(rows, "")
			}
			status, style := "OK", p.good
			if check.Status == "warn" {
				status, style = "WARN", p.warn
			}
			if check.Status == "error" {
				status, style = "ERROR", p.bad
			}
			rows = append(rows, m.styledWrap(status+"  "+check.Name, style)...)
			rows = append(rows, m.wrap(check.Detail)...)
			if check.Action != "" {
				rows = append(rows, m.styledWrap(check.Action, p.cyan)...)
			}
		}
		return rows
	}
	for i, name := range m.managementNames() {
		status := ""
		switch m.page {
		case "business":
			if i == 0 {
				status = countLabel(len(m.state.Progress.Fields), "field")
			}
		case "environment_new":
			if i == 1 && !m.state.StoreExists {
				status = "not saved"
			}
		case "contexts":
			if i < len(m.contexts) && m.contexts[i].Name == m.state.Context {
				status = "selected"
			}
		case "environments":
			if i < len(m.environments) {
				status = countLabel(m.environments[i].Keys, "key")
				if scopeName(name) == scopeName(m.state.Environment) {
					status += " · selected"
				}
			}
		}
		rows = append(rows, m.choice(name, status, i == m.selected, w))
		if i == m.selected && m.height >= 20 {
			path := ""
			if m.page == "business" && i == 0 {
				path = m.state.ProfilePath
			}
			if m.page == "environments" && i < len(m.environments) {
				path = m.environments[i].Path
			}
			if m.page == "contexts" && i < len(m.contexts) {
				path = m.contexts[i].ProfilePath
			}
			if path != "" {
				rows = append(rows, "  "+p.muted.Render(ansi.Truncate(m.path(path), max(1, w-2), "…")))
			}
		}
	}
	return rows
}
