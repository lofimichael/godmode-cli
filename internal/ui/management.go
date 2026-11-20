package ui

import (
	"fmt"
	"path/filepath"
	"strings"
	"unicode/utf8"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"
)

var settingsNames = []string{"Motion", "Check local files", "Update Godmode", "Replay intro", "Back"}

type setupPair struct{ Environment, Context string }

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
	context := m.state.Context
	if context == "" {
		context = "-"
	}
	words = append(words, "--context", context, "--env", scopeName(m.state.Environment))
	words = append(words, action...)
	for i, word := range words {
		words[i] = shellArgument(word)
	}
	return clean(strings.Join(words, " "))
}

// An unnamed profile follows its environment. The editor shows the resolved
// identity, while the switcher retains "Automatic" as an explicit choice.
func (m model) profileScope() string {
	if m.state.Context != "" {
		return clean(m.state.Context)
	}
	return scopeName(m.state.Environment)
}

func (m model) profileBrand() string {
	return clean(strings.Join(strings.Fields(m.state.Profile["business_name"]), " "))
}

func (m model) profileIdentity() string {
	brand, scope := m.profileBrand(), m.profileScope()
	if brand == "" || brand == scope {
		return scope
	}
	if m.state.Context == "" {
		return brand
	}
	return scope + " · " + brand
}

func (m model) scopeLines() []string {
	p := m.palette()
	profile := p.muted.Render("Profile: ") + p.cyan.Render(m.profileIdentity())
	keys := p.muted.Render("Keys: ") + p.title.Render(scopeName(m.state.Environment))
	if m.innerWidth() < 52 {
		profile = p.muted.Render("Profile ") + p.cyan.Render(m.profileIdentity())
		keys = p.muted.Render("Keys ") + p.title.Render(scopeName(m.state.Environment))
	}
	var rows []string
	if ansi.StringWidth(keys+" · "+profile) <= m.innerWidth() {
		rows = []string{keys + p.muted.Render(" · ") + profile}
	} else {
		rows = []string{ansi.Truncate(keys, m.innerWidth(), "…"), ansi.Truncate(profile, m.innerWidth(), "…")}
	}
	if m.state.ShellOverride {
		rows = append(rows, m.styledWrap("Shell settings override the saved default.", p.warn)...)
	}
	return rows
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
	args := map[string]any{}
	if m.draftOpen {
		args["environment"] = m.draftEnvironment
	}
	if m.call("context_list", args, &reply) {
		m.contexts = reply.Contexts
		m.page, m.selected, m.scroll = "contexts", 0, 0
		for i, c := range m.contexts {
			selected := reply.Selected
			if m.draftOpen {
				selected = m.draftContext
			}
			if c.Name == selected {
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
			selected := reply.Selected
			if m.draftOpen {
				selected = m.draftEnvironment
			}
			if scopeName(e.Name) == scopeName(selected) {
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
	case "active":
		switch m.selected {
		case 0:
			m.loadEnvironments()
		case 1:
			m.loadContexts()
		case 2:
			return m.applySetup(m.draftEnvironment, m.draftContext)
		case 3:
			if len(m.state.RecentSetups) > 0 {
				m.openRecent()
			} else {
				return m.back()
			}
		case 4:
			return m.back()
		}
	case "recent_setups":
		if m.selected >= len(m.state.RecentSetups) {
			return m.back()
		}
		m.recentAt = m.selected
		m.page, m.scroll = "recent_details", 0

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
			if m.draftOpen {
				m.draftContext = name
				return m.back()
			}
			if m.selectScope("context_select", name) {
				m.notice = "Profile selected: " + businessName(name)
				return m.back()
			}
		} else if m.selected == len(m.contexts) {
			m.startScopeName("context", "")
		} else {
			return m.back()
		}
	case "environments":
		if m.selected < len(m.environments) {
			name := m.environments[m.selected].Name
			if m.draftOpen {
				m.draftEnvironment = scopeName(name)
				return m.back()
			}
			if m.selectScope("environment_select", name) {
				m.notice = "Environment selected: " + scopeName(name)
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
		if m.draftOpen {
			args["select"] = false
		}
		if m.scopeCopy != "" {
			args["copy"] = m.scopeCopy
		}
		var next snapshot
		if m.call(m.scopeKind+"_create", args, &next) {
			m.state = next
			if m.draftOpen {
				if m.scopeKind == "environment" {
					m.draftEnvironment = m.text
				} else {
					m.draftContext = m.text
				}
			}
			m.notice = "Created and selected " + clean(m.text) + "."
			if m.draftOpen {
				m.notice = "Created " + clean(m.text) + ". Use this loadout to make it active."
			}
			m.resetInput()
			if m.scopeKind == "environment" {
				for len(m.trail) > 0 && m.trail[len(m.trail)-1].page != "environments" {
					m.trail = m.trail[:len(m.trail)-1]
				}
				if len(m.trail) > 0 {
					m.trail = m.trail[:len(m.trail)-1]
				}
				m.loadEnvironments()
			} else {
				m.back()
				if m.page == "contexts" {
					m.loadContexts()
				} else {
					m.page, m.selected = "business", 0
				}
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
	case "active":
		if len(m.state.RecentSetups) > 0 {
			return []string{"Key environment", "Profile", "Use this loadout", "Recent loadouts", "Back"}
		}
		return []string{"Key environment", "Profile", "Use this loadout", "Back"}
	case "recent_setups":
		names := []string{}
		for _, pair := range m.state.RecentSetups {
			names = append(names, scopeName(pair.Environment)+" / "+businessName(pair.Context))
		}
		return append(names, "Back")
	case "business":
		return []string{"Edit profile", "Switch profile", "New profile", "Back"}
	case "environment_new":
		return []string{"Empty", "Copy current", "Back"}
	case "contexts":
		names := []string{}
		for _, c := range m.contexts {
			names = append(names, businessName(c.Name))
		}
		return append(names, "New profile", "Back")
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
	if m.page == "recent_details" {
		if m.recentAt >= len(m.state.RecentSetups) {
			return []string{"This loadout is no longer in recent history. Esc goes back."}
		}
		pair := m.state.RecentSetups[m.recentAt]
		rows = append(rows, p.muted.Render("Key environment"))
		rows = append(rows, m.styledWrap(scopeName(pair.Environment), p.title)...)
		rows = append(rows, "", p.muted.Render("Profile"))
		rows = append(rows, m.styledWrap(businessName(pair.Context), p.title)...)
		rows = append(rows, "")
		rows = append(rows, m.wrap("New commands use this pair. Paste new task instructions to switch a running agent.")...)
		return rows
	}

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
			rows = append(rows, "Profile starts empty.")
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
		case "active":
			if i == 0 {
				status = p.cyan.Render(scopeName(m.draftEnvironment))
			} else if i == 1 {
				status = p.cyan.Render(businessName(m.draftContext))
			}
		case "recent_setups":
			if i < len(m.state.RecentSetups) && m.state.RecentSetups[i].Environment == scopeName(m.state.Environment) && m.state.RecentSetups[i].Context == m.state.Context {
				status = "active"
			}
		case "business":
			if i == 0 {
				status = countLabel(len(m.state.Progress.Fields), "field")
			}
		case "environment_new":
			if i == 1 {
				status = scopeName(m.state.Environment)
				if !m.state.StoreExists {
					status = "not saved"
				}
			}
		case "contexts":
			if i < len(m.contexts) {
				if m.contexts[i].Name == m.state.Context {
					status = p.good.Render("active")
				}
				if m.draftOpen && m.contexts[i].Name == m.draftContext && m.draftContext != m.state.Context {
					status = "chosen"
				}
			}
		case "environments":
			if i < len(m.environments) {
				status = countLabel(m.environments[i].Keys, "key")
				if scopeName(name) == scopeName(m.state.Environment) {
					status += " · active"
				}
				if m.draftOpen && scopeName(name) == m.draftEnvironment && m.draftEnvironment != scopeName(m.state.Environment) {
					status += " · chosen"
				}
			}
		}
		rows = append(rows, m.choice(name, status, i == m.selected, w))
		if m.page == "active" && i == 1 && m.draftContext == "" {
			rows = append(rows, m.styledWrap("  Uses the profile stored with "+scopeName(m.draftEnvironment)+".", p.muted)...)
		}
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
	if m.page == "active" && m.selected == 2 {
		rows = append(rows, "")
		rows = append(rows, m.styledWrap("New commands use this pair. Open Godmode sessions keep their selection.", p.muted)...)
		rows = append(rows, m.styledWrap("Paste new task instructions to switch a running agent.", p.muted)...)
	}

	return rows
}

func (m *model) applySetup(environment, context string) tea.Cmd {
	var next snapshot
	if !m.call("selection_save", map[string]any{"environment": environment, "context": context}, &next) {
		return nil
	}
	m.state = next
	m.draftEnvironment, m.draftContext = scopeName(next.Environment), next.Context
	m.notice = "Using " + scopeName(m.state.Environment) + " · " + businessName(m.state.Context) + "."
	cmd := m.back()
	if m.page == "recent_setups" {
		m.selected = 0
		for i, pair := range m.state.RecentSetups {
			if pair.Environment == scopeName(m.state.Environment) && pair.Context == m.state.Context {
				m.selected = i
				break
			}
		}
	}
	if next.HistoryError != "" {
		m.error = next.HistoryError
	}
	return cmd
}
func (m *model) openRecent() {
	m.page, m.selected, m.scroll = "recent_setups", 0, 0
	for i, pair := range m.state.RecentSetups {
		if pair.Environment != scopeName(m.state.Environment) || pair.Context != m.state.Context {
			m.selected = i
			break
		}
	}
}
func (m *model) useRecent() tea.Cmd {
	if m.recentAt >= len(m.state.RecentSetups) {
		return nil
	}
	pair := m.state.RecentSetups[m.recentAt]
	// Apply only the reviewed complete pair. The history picker itself never writes.
	return m.applySetup(pair.Environment, pair.Context)
}
