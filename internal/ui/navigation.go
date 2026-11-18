package ui

import (
	"strings"

	tea "charm.land/bubbletea/v2"
)

// History stores navigation identifiers, never input, key plans or credential previews.
type location struct {
	page                                string
	selected, scroll                    int
	query                               string
	filtering                           bool
	providerID                          string
	providerAt, providerKeyAt, faqAt    int
	scopeReturn, profileReturn          string
	scopeItem                           string
	hasScopeItem                        bool
	agentOnly, agentPlanID, agentTarget string
	agentScope                          setupPair
	agentAll                            bool
	recentPair                          setupPair
	hasRecentPair                       bool
}

func agentPage(page string) bool {
	return page == "agent_home" || page == "agent_targets" || page == "agents" || page == "agent_copy"
}

func (m model) location() location {
	l := location{page: m.page, selected: m.selected, scroll: m.scroll, query: m.query, filtering: m.filtering,
		providerAt: m.providerAt, providerKeyAt: m.providerKeyAt, faqAt: m.faqAt,
		scopeReturn: m.scopeReturn, profileReturn: m.profileReturn}
	if m.selectedProvider != nil {
		l.providerID = m.selectedProvider.ID
	}
	scopePage := m.page
	if scopePage == "scope_details" {
		scopePage = m.scopeReturn
	}
	if scopePage == "contexts" && m.selected >= 0 && m.selected < len(m.contexts) {
		l.scopeItem, l.hasScopeItem = m.contexts[m.selected].Name, true
	}
	if scopePage == "environments" && m.selected >= 0 && m.selected < len(m.environments) {
		l.scopeItem, l.hasScopeItem = m.environments[m.selected].Name, true
	}
	if agentPage(m.page) {
		l.agentOnly, l.agentPlanID = m.agentOnly, m.agents.ID
		l.agentScope = setupPair{scopeName(m.state.Environment), m.state.Context}
		if m.page == "agent_targets" {
			if m.selected >= 0 && m.selected < len(m.agents.Targets) {
				l.agentTarget = m.agents.Targets[m.selected].Path
			}
			l.agentAll = m.selected == len(m.agents.Targets)
		}
	}
	recent := m.selected
	if m.page == "recent_details" {
		recent = m.recentAt
	}
	if (m.page == "recent_details" || m.page == "recent_setups") && recent >= 0 && recent < len(m.state.RecentSetups) {
		l.recentPair, l.hasRecentPair = m.state.RecentSetups[recent], true
	}
	return l
}

func (m model) needsAgentReload(l location) bool {
	// Scope operations invalidate backend plans even when the pair is unchanged.
	// A non-agent detour may also have opened a replacement plan.
	return agentPage(l.page) && (!agentPage(m.page) || l.agentPlanID == "" || l.agentPlanID != m.agents.ID ||
		l.agentScope != (setupPair{scopeName(m.state.Environment), m.state.Context}))
}

func (m model) backNeedsAgentReload() bool {
	return len(m.trail) > 0 && m.needsAgentReload(m.trail[len(m.trail)-1])
}

func (m *model) restore(l location) {
	reloadAgent := m.needsAgentReload(l)
	m.page, m.selected, m.scroll = l.page, l.selected, l.scroll
	m.query, m.filtering = l.query, l.filtering
	m.providerAt, m.providerKeyAt, m.faqAt = l.providerAt, l.providerKeyAt, l.faqAt
	m.scopeReturn, m.profileReturn = l.scopeReturn, l.profileReturn
	m.selectedProvider = nil
	for i, p := range m.state.Providers {
		if p.ID == l.providerID {
			m.providerAt, m.selectedProvider = i, &p
			break
		}
	}
	if l.page == "provider_keys" && m.selectedProvider == nil {
		m.page, m.selected = "providers", 0
	}
	if l.hasScopeItem {
		scopePage := l.page
		if scopePage == "scope_details" {
			scopePage = l.scopeReturn
		}
		found := false
		if scopePage == "contexts" {
			for i, item := range m.contexts {
				if item.Name == l.scopeItem {
					m.selected, found = i, true
					break
				}
			}
		} else if scopePage == "environments" {
			for i, item := range m.environments {
				if item.Name == l.scopeItem {
					m.selected, found = i, true
					break
				}
			}
		}
		if !found {
			m.page, m.selected, m.scroll = scopePage, 0, 0
		}
	}
	if l.hasRecentPair {
		found := false
		for i, pair := range m.state.RecentSetups {
			if pair == l.recentPair {
				m.selected, m.recentAt, found = i, i, true
				break
			}
		}
		if !found {
			m.page, m.selected, m.scroll = "recent_setups", 0, 0
		}
	}
	if agentPage(l.page) {
		m.restoreAgent(l, reloadAgent)
	}
}

func (m *model) restoreAgent(l location, reloaded bool) {
	if reloaded {
		m.loadAgents()
		if m.agents.ID == "" {
			m.page, m.selected = "agent_home", 0
			return
		}
		m.page, m.selected, m.scroll = l.page, l.selected, 0
	}
	m.agentOnly = l.agentOnly
	// A resumed diff must be reviewed again. Other detours may have changed the
	// selected plan, target set, viewport or review progress while it was hidden.
	if l.page == "agents" {
		m.scroll, m.reviewedUntil = 0, 0
		if l.agentOnly == "" && reloaded {
			// All referred to the old plan. Ask again rather than adding new targets.
			m.page, m.selected = "agent_home", 1
			return
		}
		if l.agentOnly != "" && len(m.reviewTargets()) == 0 {
			m.page, m.selected, m.agentOnly = "agent_home", 1, ""
			return
		}
		m.noteReview()
	}
	if l.page == "agent_targets" {
		m.selected = len(m.agents.Targets) + 1 // Preserve Back unless a target was selected.
		if l.agentAll {
			m.selected = len(m.agents.Targets)
		} else if l.agentTarget != "" {
			for i, target := range m.agents.Targets {
				if target.Path == l.agentTarget {
					m.selected = i
					return
				}
			}
			m.page, m.selected, m.agentOnly = "agent_home", 1, ""
		}
	}
}
func (m *model) remember(l location) {
	// Models in flight may share a backing array. Publish a fresh history.
	m.trail = append(append([]location{}, m.trail...), l)
}
func (m *model) visit(page string) {
	if m.page == page {
		return
	}
	m.remember(m.location())
	m.page, m.selected, m.scroll, m.query, m.filtering = page, 0, 0, "", false
	m.error, m.notice = "", ""
	if page == "active" {
		m.startActive()
	}
}
func (m *model) enter() tea.Cmd {
	previous, depth := m.location(), len(m.trail)
	m.returning = false
	cmd := m.enterAction()
	if m.page != previous.page && !m.returning && !m.quitting && len(m.trail) == depth {
		m.remember(previous)
	}
	return cmd
}

type action struct{ title, detail, keywords, route, arg string }

func (m model) actions() []action {
	items := []action{
		{"Provider keys", "Add or replace a key", "setup providers accounts credentials tokens", "providers", ""},
		{"Connect agent", "Copy instructions or add them to an agent", "agents codex claude gemini copilot opencode instructions", "agents", ""},
		{"Business details", "Name, contact details and address", "business profile terms privacy email address", "profile", ""},
		{"Switch setup", "Choose a business and key environment", "active context environment profile switch", "active", ""},
		{"Key environments", "Switch or create an independent set of keys", "env copy duplicate new create account sandbox", "environments", ""},
		{"Business profiles", "Switch or create a business", "context new create client", "contexts", ""},
		{"Settings", "Appearance, checks and updates", "preferences motion animation", "settings", ""},
		{"Check setup", "Check local files and installation", "doctor diagnose repair troubleshoot errors", "doctor", ""},
		{"Update Godmode", "Install the latest release", "upgrade version updater", "update", ""},
		{"Help", "Quickstart and common questions", "faq guide how help sealed sealing source files tokens network privacy", "faq", ""},
		{"Keyboard shortcuts", "Navigation and editing keys", "keys controls back cancel quit search", "shortcuts", ""},
	}
	if len(m.state.RecentSetups) > 0 {
		items = append(items, action{"Recent setups", "Reuse a business and key environment", "history switch pair", "recent_setups", ""})
	}
	if m.state.MusicIncluded {
		items = append(items, action{"Music", "Optional Music Pack", "songs audio synthesizer", "music", ""})
	}
	for _, p := range m.state.Providers {
		items = append(items, action{p.Name, "Provider · " + p.About, providerSearchText(p) + " setup token key", "provider", p.ID})
	}
	return items
}
func (m model) matchActions() []action {
	items := []action{}
	for _, a := range m.actions() {
		haystack := strings.ToLower(a.title + " " + a.detail + " " + a.keywords)
		match := true
		for _, word := range strings.Fields(strings.TrimPrefix(strings.ToLower(strings.TrimSpace(m.query)), "godmode ")) {
			match = match && strings.Contains(haystack, word)
		}
		if match {
			items = append(items, a)
		}
	}
	return items
}
func (m *model) chooseAction() tea.Cmd {
	matches := m.matchActions()
	if m.selected < 0 || m.selected >= len(matches) {
		return nil
	}
	a := matches[m.selected]
	m.query, m.filtering, m.selected, m.scroll = "", false, 0, 0
	switch a.route {
	case "provider":
		for i, p := range m.state.Providers {
			if p.ID == a.arg {
				m.openProvider(i)
				break
			}
		}
	case "agents":
		m.loadAgents()
	case "faq":
		m.loadFAQ()
	case "recent_setups":
		m.openRecent()
	case "contexts":
		m.loadContexts()
	case "environments":
		m.loadEnvironments()
	case "doctor":
		return m.loadDoctor()
	case "music":
		return m.external(ErrMusic)
	case "active":
		m.startActive()
	default:
		m.page = a.route
	}
	return nil
}
func (m model) searchAction(msg tea.KeyPressMsg) (tea.Model, tea.Cmd) {
	key := msg.String()
	count := len(m.matchActions())
	switch key {
	case "down", "ctrl+n", "tab":
		if count > 0 {
			m.selected = (m.selected + 1) % count
		}
	case "up", "ctrl+p", "shift+tab":
		if count > 0 {
			m.selected = (m.selected + count - 1) % count
		}
	case "enter":
		cmd := m.enter()
		return m, cmd
	case "backspace":
		m.query = dropLast(m.query)
		m.selected = 0
	case "ctrl+u":
		m.query, m.selected = "", 0
	default:
		m.query += printable(msg.Text)
		m.selected = 0
	}
	return m, nil
}

func (m model) homeDescription() string {
	text := []string{
		"Give your agent access to the services you use.",
		"Copy instructions into a task or save them for future sessions.",
		"Business and contact details for terms, privacy and payments. Optional.",
		"Choose the business and key environment for new commands.",
		"Appearance, local checks and updates.",
		"Quickstart, keyboard controls and common questions.",
		"Install the optional Music Pack, or open its player.",
		"Return to your terminal. Saved changes stay saved.",
	}
	if m.selected >= 0 && m.selected < len(text) {
		return text[m.selected]
	}
	return ""
}

func (m model) shortcuts() []string {
	return []string{
		"Navigation", "↑ / ↓ or j / k    Move through a list", "Enter              Open the selected item", "Esc                Go back; cancel an unsaved edit", "q                  Quit from a menu", "Ctrl-C             Exit from any screen", "",
		"Find", "/                  Search providers or find an action", "Ctrl-K             Find an action from any menu", "s                  Switch business and key environment", "?                  Show these shortcuts", "",
		"Editing", "Enter              Save the reviewed value", "Ctrl-U             Clear the input", "Tab                Inspect a key's save details", "Esc                Leave without saving", "",
		"Reading", "↑ / ↓              Scroll one line", "PgUp / PgDn        Scroll one page", "Home / End         Go to the start or end", "",
		"godmode --plain uses the text interface.", "godmode --no-motion disables animation.", "NO_COLOR=1 disables color.",
	}
}

func (m *model) startActive() {
	m.page, m.selected = "active", 0
	m.draftEnvironment, m.draftContext, m.draftOpen = scopeName(m.state.Environment), m.state.Context, true
}
func (m model) stagedScope() bool {
	return m.draftOpen && len(m.trail) > 0 && (m.trail[len(m.trail)-1].page == "active" || m.trail[len(m.trail)-1].page == "contexts" || m.trail[len(m.trail)-1].page == "environment_new" || m.trail[len(m.trail)-1].page == "environments")
}

func (m model) reviewTargets() []target {
	if m.agentOnly == "" {
		return m.agents.Targets
	}
	for _, t := range m.agents.Targets {
		if t.Path == m.agentOnly {
			return []target{t}
		}
	}
	return nil
}

func providerSearchText(p provider) string {
	text := p.Name + " " + p.ID + " " + p.About
	for _, k := range p.Key {
		text += " " + k.Name + " " + k.Label
	}
	return text
}
