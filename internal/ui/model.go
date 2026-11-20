// Package ui is Godmode's terminal interface. It owns no files or credentials:
// every read and mutation crosses the small, inspectable Backend interface.
package ui

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"

	tea "charm.land/bubbletea/v2"
)

type Backend interface {
	Call(string, map[string]any) (map[string]any, error)
}
type Options struct {
	Home            string
	Plain, NoMotion bool
}

var ErrUpdate = errors.New("godmode update")
var ErrCancelled = errors.New("cancelled")

// ReceiptExit reports a successful direct edit after the terminal is restored.
type ReceiptExit struct{ Message string }

func (e *ReceiptExit) Error() string { return e.Message }

// CommandExit runs an external command only after Bubble Tea restores the terminal.
type CommandExit struct {
	Command              error
	Context, Environment string
}

func (e *CommandExit) Error() string { return e.Command.Error() }
func (e *CommandExit) Unwrap() error { return e.Command }

type field struct{ Name, Label, Description, Group string }
type providerKey struct {
	Name, Label, Kind string
	Secret            *bool
}
type provider struct {
	ID, Name, About, Benefit string
	Key                      []providerKey
	Ready                    [][]string
}
type progress struct {
	Fields                 []string
	Providers              int
	Agents                 []string
	ByHand                 bool `json:"by_hand"`
	Agent, Points, Percent int
	Errors                 []string
}
type snapshot struct {
	RecentSetups []setupPair `json:"recent_setups"`
	HistoryError string      `json:"history_error"`

	Preferences      struct{ Motion *bool }
	PreferencesError string `json:"preferences_error"`

	StoreError                          string `json:"store_error"`
	ProfileError                        string `json:"profile_error"`
	Version, Home, Context, Environment string
	EnvPath                             string `json:"env_path"`
	ProfilePath                         string `json:"profile_path"`
	KeyCount                            int    `json:"key_count"`
	Profile                             map[string]string
	Fields                              []field
	Providers                           []provider
	States                              map[string]string
	Progress                            progress
	IntroSeen                           bool              `json:"intro_seen"`
	SelectionSource                     string            `json:"selection_source"`
	EnvironmentSource                   string            `json:"environment_source"`
	ContextSource                       string            `json:"context_source"`
	StartupSources                      map[string]string `json:"startup_sources"`
	ShellOverride                       bool              `json:"shell_override"`
	StoreExists                         bool              `json:"store_exists"`
	IssueURL                            string            `json:"issue_url"`
	ProfileBlurb                        string            `json:"profile_blurb"`
	ProvidersBlurb                      string            `json:"providers_blurb"`
}
type keyPlan struct {
	ID, Name, Title, Benefit, Visit, Page, Note, Prompt, Path string
	Access, Guide                                             string
	Steps                                                     []string
	Sealed, Saved                                             bool
	Lines                                                     []int
}
type keyCheck struct {
	Valid                                      bool
	Error, Masked, Assignment, Operation, Path string
	Notes, Command                             []string
}
type target struct {
	Name, Path, Real, Addition, Issue string
	Added, Created                    bool
}
type agentPlan struct {
	ID, Block string
	CopyBlock string `json:"copy_block"`
	Targets   []target
}
type faqEntry struct {
	Title      string
	Paragraphs []string
}
type tickMsg time.Time

type model struct {
	recentAt int

	agentOnly string

	draftEnvironment, draftContext string
	draftOpen                      bool

	trail         []location
	returning     bool
	motionForced  bool
	providerKeyAt int

	backend                               Backend
	opts                                  Options
	state                                 snapshot
	page, initialRoute, arg               string
	width, height                         int
	dark, colors, quitting                bool
	selected, homeAt, providerAt, fieldAt int
	selectedProvider                      *provider
	text                                  string
	cursor                                int
	pasted, fromPaste, filtering, details bool
	query                                 string
	scroll                                int
	error, notice                         string
	key                                   keyPlan
	check                                 keyCheck
	keyReturn                             string
	agents                                agentPlan
	reviewedUntil                         int
	faq                                   []faqEntry
	faqAt                                 int
	tick                                  int
	introStage                            int
	busy, busyVisible                     bool
	busyValidation, deferValidation       bool
	pendingInput                          []tea.Msg
	busyLabel                             string
	operationID, busyFrame                int
	pulseID, pulseFrame                   int
	outcome                               error
	contexts                              []businessContext
	environments                          []environment
	scopeKind, scopeCopy, profileReturn   string
	scopeReturn                           string
	doctor                                doctorReport
	doctorLoading                         bool
	doctorRequest                         int
}

// Run starts the native Bubble Tea application. The caller owns backend lifetime.
func Run(client Backend, route, arg string, opts Options) error {
	m, err := newModel(client, route, arg, opts)
	if err != nil {
		return err
	}
	input := &pasteInput{file: os.Stdin}
	defer input.stop()
	final, err := tea.NewProgram(m, tea.WithInput(input), tea.WithFilter(func(_ tea.Model, msg tea.Msg) tea.Msg {
		switch msg.(type) {
		case tea.QuitMsg, tea.InterruptMsg:
			input.stop()
		}
		return msg
	})).Run()
	input.stop()
	if input.parser.err != nil {
		return input.parser.err
	}
	if err != nil {
		return err
	}
	result, ok := final.(model)
	if !ok {
		return errors.New("Godmode UI returned an invalid state")
	}
	return result.outcome
}

func newModel(client Backend, route, arg string, opts Options) (model, error) {
	m := model{backend: client, opts: opts, motionForced: opts.NoMotion, initialRoute: route, arg: arg, width: 80, height: 24, dark: true,
		colors: os.Getenv("NO_COLOR") == "" && os.Getenv("CLICOLOR") != "0", keyReturn: "providers"}
	if bg := os.Getenv("COLORFGBG"); strings.HasSuffix(bg, ";15") || strings.HasSuffix(bg, ";7") {
		m.dark = false
	}
	if err := m.refresh(); err != nil {
		return m, err
	}
	if m.state.Preferences.Motion != nil && !*m.state.Preferences.Motion {
		m.opts.NoMotion = true
	}
	if route == "" {
		route = "home"
		m.initialRoute = route
	}
	if route == "intro" || (!m.state.IntroSeen && (route == "home" || route == "loadout" || route == "setup" || route == "set")) {
		m.page = "intro"
	} else {
		m.openRoute(route, arg)
	}
	return m, nil
}
func decode(data map[string]any, into any) error {
	b, e := json.Marshal(data)
	if e != nil {
		return e
	}
	return json.Unmarshal(b, into)
}
func (m *model) call(action string, args map[string]any, into any) bool {
	data, err := m.backend.Call(action, args)
	if err != nil {
		m.error = clean(err.Error())
		return false
	}
	if into != nil {
		if err = decode(data, into); err != nil {
			m.error = "Godmode received an unreadable response."
			return false
		}
	}
	return true
}
func (m *model) refresh() error {
	data, err := m.backend.Call("state", nil)
	if err != nil {
		return err
	}
	// A command owns a model copy, whose existing maps and slices may still be
	// rendered by the live model. Decode into fresh storage before publishing it.
	var next snapshot
	if err = decode(data, &next); err != nil {
		return err
	}
	if next.Profile == nil {
		next.Profile = map[string]string{}
	}
	if next.States == nil {
		next.States = map[string]string{}
	}
	m.state = next
	return nil
}
func (m model) Init() tea.Cmd {
	if m.opts.NoMotion || !m.colors {
		return tea.RequestBackgroundColor
	}
	if m.page == "intro" {
		return tea.Batch(tea.RequestBackgroundColor, introTick())
	}
	return tea.RequestBackgroundColor
}
func (m *model) openRoute(route, arg string) {
	m.error = ""
	m.scroll = 0
	m.selected = 0
	m.text = ""
	m.query = ""
	m.filtering = false
	switch route {
	case "home":
		m.page = "home"
		m.homeAt = 0
		if m.state.KeyCount > 0 && m.state.Progress.Agent == 0 && len(m.state.Progress.Agents) == 0 {
			m.homeAt = 1
		}
		m.selected = m.homeAt
	case "intro":
		m.page = "intro"
		m.introStage, m.tick = 0, 0
	case "profile":
		m.page = "profile"
	case "settings":
		m.page = "settings"
	case "loadout", "setup":
		m.page = "providers"
		if arg != "" {
			for i, p := range m.state.Providers {
				if p.ID == arg {
					m.providerAt = i
					previous := m.location()
					m.openProvider(i)
					m.remember(previous)
					return
				}
			}
			m.error = "Unknown provider. Choose one below."
		}
	case "agents":
		m.loadAgents()
	case "faq":
		m.loadFAQ()
	case "set":
		m.keyReturn = "exit"
		m.openKey(arg)
	default:
		m.page = "home"
	}
}
func (m *model) resetInput() {
	m.text = ""
	m.cursor = 0
	m.pasted = false
	m.fromPaste = false
	m.scroll = 0
	m.details = false
	m.error = ""
}
func (m *model) openKey(name string) {
	m.resetInput()
	m.key = keyPlan{Name: name, Title: name}
	m.page = "key"
	m.check = keyCheck{}
	if m.call("key_plan", map[string]any{"name": name}, &m.key) {
		m.page = "key"
		if m.key.Name == "" {
			m.key.Name = name
		}
	}
}
func (m *model) validateKey() {
	m.check = keyCheck{}
	if m.deferValidation {
		return
	}
	if m.key.ID == "" {
		m.error = "Open the key again before entering a value."
		return
	}
	m.call("key_check", map[string]any{"id": m.key.ID, "value": m.text, "pasted": m.pasted, "from_paste": m.fromPaste}, &m.check)
}
func (m *model) openProvider(index int) {
	if index < 0 || index >= len(m.state.Providers) {
		return
	}
	m.providerAt = index
	p := m.state.Providers[index]
	m.selectedProvider = &p
	m.scroll = 0
	m.selected = 0
	if len(p.Key) == 1 {
		m.keyReturn = "providers"
		m.openKey(p.Key[0].Name)
	} else {
		m.page = "provider_keys"
		for i, k := range p.Key {
			if m.state.States[k.Name] != "set" {
				m.selected = i
				break
			}
		}
	}
}
func (m *model) loadAgents() {
	m.resetInput()
	m.agents = agentPlan{}
	m.agentOnly = ""
	m.reviewedUntil = 0
	if m.call("agents_plan", nil, &m.agents) {
		m.page, m.selected = "agent_home", 0
	}
}
func (m *model) loadFAQ() {
	m.scroll = 0
	var reply struct{ Entries []faqEntry }
	if m.call("faq", nil, &reply) {
		m.faq = reply.Entries
		m.page = "faq"
		m.selected = 0
	}
}
func (m *model) back() tea.Cmd {
	m.returning = true
	if m.page == "active" {
		m.draftOpen = false
	}
	if len(m.trail) > 0 {
		m.resetInput()
		previous := m.trail[len(m.trail)-1]
		m.trail = m.trail[:len(m.trail)-1]
		m.restore(previous)
		return nil
	}
	m.error = ""
	m.scroll = 0
	m.details = false
	switch m.page {
	case "intro":
		m.quitting = true
		return tea.Quit
	case "home":
		m.quitting = true
		return tea.Quit
	case "profile":
		if m.profileReturn == "business" {
			m.page, m.selected = "business", 0
			return nil
		}
		fallthrough
	case "active", "business", "providers", "agent_targets", "agent_home", "agents", "faq", "doctor", "settings", "update", "shortcuts", "actions", "agent_copy":
		if m.initialRoute != "home" {
			m.quitting = true
			return tea.Quit
		}
		m.page = "home"
		m.selected = m.homeAt
	case "contexts":
		m.page, m.selected = "active", 1
	case "environments":
		m.startActive()
	case "environment_new":
		m.loadEnvironments()
	case "scope_name":
		m.resetInput()
		if m.scopeKind == "environment" {
			m.page, m.selected = "environment_new", 0
		} else {
			m.page, m.selected = "business", 2
		}
	case "scope_details":
		m.page = m.scopeReturn
	case "profile_field":
		m.page = "profile"
		m.selected = m.fieldAt
		m.resetInput()
	case "provider_keys":
		m.page = "providers"
		m.selected = m.providerSelection()
	case "key":
		m.resetInput()
		if m.keyReturn == "exit" {
			m.quitting = true
			return tea.Quit
		}
		m.page = m.keyReturn
		if m.page == "providers" {
			m.selected = m.providerSelection()
		}
	case "name":
		m.page = "providers"
		m.resetInput()
	case "faq_text":
		m.page = "faq"
		m.selected = m.faqAt
	}
	return nil
}
func (m model) updateNow(message tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := message.(type) {
	case doctorMsg:
		if msg.request != m.doctorRequest || m.page != "doctor" {
			return m, nil
		}
		m.doctorLoading = false
		if msg.err != nil {
			m.error = clean(msg.err.Error())
		} else {
			m.doctor = msg.report
		}
		return m, nil
	case tea.WindowSizeMsg:
		if m.page == "agents" && msg.Width != m.width {
			m.reviewedUntil = 0
			m.scroll = 0
		}
		m.width = max(1, msg.Width)
		m.height = max(1, msg.Height)
		m.clampScroll()
		m.noteReview()
		return m, nil
	case tea.BackgroundColorMsg:
		m.dark = msg.IsDark()
		return m, nil
	case tickMsg:
		if m.introMotionActive() {
			m.tick = (m.tick + 1) % introCycleFrames
			return m, introTick()
		}
		return m, nil
	case tea.PasteMsg:
		// Menus, search, and key names ignore pastes. A complete paste never submits.
		if m.page != "key" && m.page != "profile_field" {
			return m, nil
		}
		if len(msg.Content) > 1024*1024 {
			m.error = "Paste exceeds 1 MiB. Nothing was saved."
			return m, nil
		}
		m.text = msg.Content
		m.cursor = utf8.RuneCountInString(m.text)
		m.pasted = true
		m.fromPaste = true
		m.error, m.notice = "", ""
		if m.page == "key" {
			m.validateKey()
		}
		return m, nil
	case tea.KeyPressMsg:
		key := msg.String()
		if key == "ctrl+c" || key == "ctrl+d" {
			m.text = ""
			m.quitting = true
			m.outcome = ErrCancelled
			return m, tea.Quit
		}
		if key == "esc" {
			if m.filtering || (m.page == "providers" && m.query != "") {
				m.filtering = false
				m.query = ""
				m.selected = 0
				return m, nil
			}
			if m.details && m.page == "key" {
				m.details = false
				m.scroll = 0
				return m, nil
			}
			cmd := m.back()
			return m, cmd
		}
		if m.page == "key" || m.page == "profile_field" || m.page == "name" {
			cmd := m.editKey(msg)
			return m, cmd
		}
		if m.page == "scope_name" {
			return m.editScope(msg)
		}
		if m.page != "intro" && !m.filtering {
			if m.page == "actions" {
				return m.searchAction(msg)
			}
			switch key {
			case "q":
				if m.page == "home" {
					m.quitting = true
					return m, tea.Quit
				}
			case "?":
				m.visit("shortcuts")
				return m, nil
			case "ctrl+k":
				m.visit("actions")
				return m, nil
			case "/":
				if m.page != "providers" {
					m.visit("actions")
					return m, nil
				}
			case "s":
				if m.page == "home" {
					m.visit("active")
					return m, nil
				}
			}
		}
		if m.page == "active" && key == "r" && len(m.state.RecentSetups) > 0 {
			previous := m.location()
			m.openRecent()
			m.remember(previous)
			return m, nil
		}

		if key == "tab" && (m.page == "contexts" || m.page == "environments") {
			previous := m.location()
			m.openScopeDetails()
			if m.page != previous.page {
				m.remember(previous)
			}
			return m, nil
		}
		if m.page == "intro" {
			if key == "enter" && m.introFits() {
				if m.introStage == 0 {
					m.introStage, m.tick = 1, 0
					// Init owns the one repeating clock. Its pending tick advances
					// this scene too; starting another would accelerate each loop.
					return m, nil
				}
				if m.call("accept_intro", nil, nil) {
					m.state.IntroSeen = true
					if len(m.trail) > 0 {
						cmd := m.back()
						return m, cmd
					}
					if m.initialRoute == "intro" {
						m.quitting = true
						return m, tea.Quit
					}
					m.openRoute(m.initialRoute, m.arg)
				}
			}
			return m, nil
		}
		if m.page == "agents" || m.page == "agent_copy" || m.page == "faq_text" || m.page == "doctor" || m.page == "scope_details" || m.page == "recent_details" || m.page == "shortcuts" {
			if key != "enter" {
				m.error = ""
			}
			if key == "down" || key == "j" {
				m.scroll++
			}
			if key == "up" || key == "k" {
				m.scroll--
			}
			if key == "pgdown" || key == " " {
				m.scroll += max(1, m.bodyRoom()-1)
			}
			if key == "pgup" {
				m.scroll -= max(1, m.bodyRoom()-1)
			}
			if key == "home" {
				m.scroll = 0
			}
			if key == "end" {
				m.scroll = 1 << 30
			}
			m.clampScroll()
			m.noteReview()
			if m.page == "recent_details" && key == "enter" {
				cmd := m.useRecent()
				return m, cmd
			}
			if m.page == "doctor" && key == "r" {
				cmd := m.loadDoctor()
				return m, cmd
			}
			if m.page == "agents" || m.page == "agent_copy" {
				cmd := m.agentKey(key)
				return m, cmd
			}
			if m.page == "scope_details" && key == "enter" {
				m.back()
				cmd := m.enterManagement()
				return m, cmd
			}
			return m, nil
		}
		if m.page == "providers" && (m.filtering || key == "/") {
			if key == "/" && !m.filtering {
				m.filtering = true
				m.query = ""
				m.selected = 0
				return m, nil
			}
			if key == "backspace" {
				m.query = dropLast(m.query)
				m.selectSearchResult()
				return m, nil
			}
			if key == "enter" {
				if m.selected < 0 {
					return m, nil
				}
				m.filtering = false
				cmd := m.enter()
				return m, cmd
			}
			if msg.Text != "" {
				m.query += printable(msg.Text)
				m.selectSearchResult()
				return m, nil
			}
		}
		count := m.choiceCount()

		switch key {
		case "down", "j", "ctrl+n":
			if count > 0 {
				m.selected = (m.selected + 1) % count
			}
		case "up", "k", "ctrl+p":
			if count > 0 {
				m.selected = (m.selected + count - 1) % count
			}
		case "home":
			m.selected = 0
		case "end":
			m.selected = max(0, count-1)
		case "enter":
			cmd := m.enter()
			return m, cmd
		default:
			if msg.Text != "" {
				m.jump(msg.Text)
			}
		}
	}
	return m, nil
}
func (m *model) editKey(msg tea.KeyPressMsg) tea.Cmd {
	key := msg.String()
	if key == "ctrl+o" && m.page == "key" {
		if m.key.Page != "" {
			m.error, m.notice = "", ""
			var reply struct{ Opened bool }
			if m.call("open_url", map[string]any{"url": m.key.Page}, &reply) {
				if reply.Opened {
					m.notice = "Browser opened."
				} else {
					m.details, m.scroll = true, 0
					m.notice = "Copy the link into your browser."
				}
			}
		}
		return nil
	}
	if key == "tab" && m.page == "key" {
		m.details = !m.details
		m.scroll = 0
		return nil
	}
	if key == "pgdown" || key == "pgup" || key == "up" || key == "down" {
		step := 1
		if strings.HasPrefix(key, "pg") {
			step = max(1, m.bodyRoom()-1)
		}
		if key == "up" || key == "pgup" {
			step = -step
		}
		m.scroll += step
		m.clampScroll()
		return nil
	}
	if key == "enter" {
		if m.page == "name" {
			if m.text != "" {
				m.keyReturn = "providers"
				m.openKey(m.text)
			}
			return nil
		}
		if !m.inputFits() {
			m.error = "Enlarge the terminal to review the full edit."
			return nil
		}
		if m.page == "profile_field" {
			f := m.state.Fields[m.fieldAt]
			var reply struct{ Changed *bool }
			if m.call("profile_save", map[string]any{"field": f.Name, "value": m.text}, &reply) {
				verb := "Saved "
				if reply.Changed != nil && !*reply.Changed {
					verb = "Unchanged "
				} else if m.text == "/clear" {
					verb = "Removed "
				}
				m.notice = verb + f.Label
				m.text = ""
				if e := m.refresh(); e != nil {
					m.error = clean(e.Error())
				}
				m.back()
				m.page = "profile"
				m.selected = min(m.fieldAt+1, len(m.state.Fields))
			}
			return nil
		}
		if m.text == "" {
			m.error = "Enter a value before saving."
			return nil
		}
		m.validateKey()
		if !m.check.Valid {
			if m.check.Error != "" {
				m.error = m.check.Error
			}
			return nil
		}
		var reply struct{ Receipt string }
		if m.call("key_save", map[string]any{"id": m.key.ID, "value": m.text, "pasted": m.pasted, "from_paste": m.fromPaste}, &reply) {
			m.notice = reply.Receipt
			m.text = ""
			m.check = keyCheck{}
			if e := m.refresh(); e != nil {
				m.error = clean(e.Error())
			}
			if m.keyReturn == "exit" {
				m.outcome = &ReceiptExit{Message: "Saved " + m.key.Name + " in environment " + scopeName(m.state.Environment) + "."}
				m.quitting = true
				return tea.Quit
			}
			m.back()
			if m.page == "providers" {
				m.notice = "Saved " + m.key.Name + "."
				if m.state.Progress.Agent == 0 && len(m.state.Progress.Agents) == 0 {
					m.notice = "Key saved. Next: Connect agent."
				}
			}

		}
		return nil
	}
	runes := []rune(m.text)
	m.cursor = min(max(0, m.cursor), len(runes))
	changed := false
	switch key {
	case "ctrl+u":
		m.text = ""
		m.cursor = 0
		changed = true
	case "backspace":
		if m.cursor > 0 {
			m.text = string(append(runes[:m.cursor-1], runes[m.cursor:]...))
			m.cursor--
			changed = true
		}
	case "delete":
		if m.cursor < len(runes) {
			m.text = string(append(runes[:m.cursor], runes[m.cursor+1:]...))
			changed = true
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
		if add != "" && len(m.text)+len(add) <= 1024*1024 {
			m.text = string(runes[:m.cursor]) + add + string(runes[m.cursor:])
			m.cursor += utf8.RuneCountInString(add)
			changed = true
		}
	}
	if changed {
		m.error, m.notice = "", ""
		m.pasted = false
		if m.text == "" {
			m.fromPaste = false
		}
		if m.page == "key" {
			m.validateKey()
		}
	}
	return nil
}
func (m *model) enterAction() tea.Cmd {
	m.error = ""
	m.notice = ""
	m.scroll = 0
	switch m.page {
	case "home":
		m.homeAt = m.selected
		switch m.selected {
		case 0:
			m.page, m.selected = "providers", 0
		case 1:
			m.loadAgents()
		case 2:
			m.profileReturn = ""
			m.page, m.selected = "profile", 0
		case 3:
			m.startActive()
		case 4:
			m.page, m.selected = "settings", 0
		case 5:
			m.loadFAQ()
		case 6:
			m.quitting = true
			return tea.Quit
		}
	case "settings":
		switch m.selected {
		case 0:
			if m.motionForced {
				m.notice = "Motion is off for this command (--no-motion)."
				return nil
			}
			next := !m.opts.NoMotion
			if m.call("preferences_save", map[string]any{"motion": !next}, nil) {
				m.opts.NoMotion = next
				m.notice = "Appearance saved."
			}
		case 1:
			return m.loadDoctor()
		case 2:
			m.page, m.selected = "update", 0
		case 3:
			m.page, m.introStage, m.tick = "intro", 0, 0
			return introTick()
		case 4:
			return m.back()
		}
	case "update":
		if m.selected == 0 {
			return m.external(ErrUpdate)
		}
		return m.back()
	case "actions":
		return m.chooseAction()

	case "active", "recent_setups", "business", "contexts", "environments", "environment_new":
		return m.enterManagement()
	case "agent_home":
		switch m.selected {
		case 0:
			m.page, m.scroll = "agent_copy", 0
		case 1:
			m.page, m.selected = "agent_targets", 0
		case 2:
			return m.back()
		}

	case "agent_targets":
		if len(m.agents.Targets) == 0 {
			return m.back()
		}
		if m.selected >= len(m.agents.Targets)+1 {
			return m.back()
		}
		m.agentOnly = ""
		if m.selected < len(m.agents.Targets) {
			m.agentOnly = m.agents.Targets[m.selected].Path
		}
		m.page, m.scroll, m.reviewedUntil = "agents", 0, 0
		m.noteReview()

	case "profile":
		if m.state.ProfileError != "" {
			return nil
		}
		if m.selected >= len(m.state.Fields) {
			return m.back()
		}
		m.fieldAt = m.selected
		m.page = "profile_field"
		m.resetInput()
		m.text = m.state.Profile[m.state.Fields[m.fieldAt].Name]
		m.cursor = utf8.RuneCountInString(m.text)
	case "providers":
		matches := m.providerMatches()
		if m.selected < 0 {
			return nil
		}
		if m.selected < len(matches) {
			m.openProvider(matches[m.selected])
			return nil
		}
		switch m.selected - len(matches) {
		case 0:
			m.page = "name"
			m.resetInput()
		case 1:
			if m.state.IssueURL != "" {
				m.call("open_url", map[string]any{"url": m.state.IssueURL}, nil)
			}
		case 2:
			return m.back()
		}
	case "provider_keys":
		if m.selectedProvider == nil {
			return m.back()
		}
		if m.selected >= len(m.selectedProvider.Key) {
			return m.back()
		}
		m.keyReturn = "provider_keys"
		m.providerKeyAt = m.selected
		m.openKey(m.selectedProvider.Key[m.selected].Name)
	case "faq":
		if m.selected >= len(m.faq) {
			return m.back()
		}
		m.faqAt = m.selected
		m.page = "faq_text"
		m.scroll = 0
	}
	return nil
}
func (m *model) agentKey(key string) tea.Cmd {
	pending := 0
	for _, t := range m.reviewTargets() {
		if !t.Added && t.Issue == "" {
			pending++
		}
	}
	if key == "c" || (m.page == "agent_copy" && key == "enter") {
		var reply struct{ Copied bool }
		if m.call("copy_agent", map[string]any{"id": m.agents.ID}, &reply) {
			if reply.Copied {
				m.notice = "Copied. Paste into your agent."
			} else {
				m.notice = "Clipboard unavailable. Copy the instructions below."
			}
		}
	}

	if m.page == "agents" && key == "enter" && pending > 0 {
		if m.width < 32 || m.height < 12 {
			m.error = "Enlarge the terminal to review the changes."
			return nil
		}
		if m.reviewedUntil < len(m.agentLines()) {
			m.error = "Scroll through the full diff before adding the note."
			return nil
		}
		var reply struct{ Added []string }
		args := map[string]any{"id": m.agents.ID}
		if m.agentOnly != "" {
			args["targets"] = []string{m.agentOnly}
		}
		if m.call("agents_apply", args, &reply) {
			m.notice = "Added to " + countLabel(len(reply.Added), "file") + ". Start a new agent session, or copy for this task."
			_ = m.refresh()
			for len(m.trail) > 0 && m.trail[len(m.trail)-1].page != "agent_home" {
				m.trail = m.trail[:len(m.trail)-1]
			}
			if len(m.trail) > 0 {
				m.trail = m.trail[:len(m.trail)-1]
			}
			m.loadAgents()
			return nil
		}
	}
	return nil
}
func (m model) providerMatches() []int {
	out := []int{}
	for i, p := range m.state.Providers {
		if strings.Contains(strings.ToLower(providerSearchText(p)), strings.ToLower(m.query)) {
			out = append(out, i)
		}
	}
	return out
}
func (m model) providerReady(p provider) bool {
	sets := p.Ready
	if len(sets) == 0 {
		names := []string{}
		for _, k := range p.Key {
			names = append(names, k.Name)
		}
		sets = [][]string{names}
	}
	for _, set := range sets {
		ok := len(set) > 0
		for _, name := range set {
			ok = ok && m.state.States[name] == "set"
		}
		if ok {
			return true
		}
	}
	return false
}
func (m model) providerCount(p provider) int {
	n := 0
	for _, k := range p.Key {
		if m.state.States[k.Name] == "set" {
			n++
		}
	}
	return n
}
func (m model) choiceCount() int {
	switch m.page {
	case "home":
		return len(homeNames)
	case "agent_targets":
		if len(m.agents.Targets) == 0 {
			return 1
		}
		return len(m.agents.Targets) + 2
	case "agent_home":
		return 3
	case "settings":
		return len(settingsNames)
	case "update":
		return 2
	case "actions":
		return len(m.matchActions())
	case "active":
		return len(m.managementNames())
	case "recent_setups":
		return len(m.state.RecentSetups) + 1
	case "business":
		return 4
	case "contexts":
		return len(m.contexts) + 2
	case "environments":
		return len(m.environments) + 2
	case "environment_new":
		return 3
	case "profile":
		return len(m.state.Fields) + 1
	case "providers":
		return len(m.providerMatches()) + 3
	case "provider_keys":
		if m.selectedProvider != nil {
			return len(m.selectedProvider.Key) + 1
		}
	case "faq":
		return len(m.faq) + 1
	}
	return 0
}
func (m *model) jump(text string) {
	names := m.choiceNames()
	for step := 1; step <= len(names); step++ {
		i := (m.selected + step) % len(names)
		if strings.HasPrefix(strings.ToLower(names[i]), strings.ToLower(text)) {
			m.selected = i
			break
		}
	}
}
func (m model) choiceNames() []string {
	switch m.page {
	case "home":
		return homeNames
	case "agent_targets":
		names := []string{}
		for _, t := range m.agents.Targets {
			names = append(names, t.Name)
		}
		return append(names, "All detected agents", "Back")
	case "agent_home":
		return []string{"Copy for this task", "Add to agent files", "Back"}
	case "settings":
		return settingsNames
	case "update":
		return []string{"Update Godmode", "Back"}
	case "active", "recent_setups", "business", "contexts", "environments", "environment_new":
		return m.managementNames()
	case "profile":
		out := []string{}
		for _, f := range m.state.Fields {
			out = append(out, f.Label)
		}
		return append(out, "Back")
	case "providers":
		out := []string{}
		for _, i := range m.providerMatches() {
			out = append(out, m.state.Providers[i].Name)
		}
		return append(out, "Another key", "Open a GitHub issue", "Back")
	case "provider_keys":
		out := []string{}
		if m.selectedProvider != nil {
			for _, k := range m.selectedProvider.Key {
				label := k.Label
				if label == "" {
					label = k.Name
				}
				out = append(out, label)
			}
		}
		return append(out, "Back")
	case "faq":
		out := []string{}
		for _, e := range m.faq {
			out = append(out, e.Title)
		}
		return append(out, "Back")
	}
	return nil
}
func printable(s string) string {
	return strings.Map(func(r rune) rune {
		if unicode.IsControl(r) || unicode.Is(unicode.Cf, r) {
			return -1
		}
		return r
	}, s)
}
func clean(s string) string {
	var b strings.Builder
	for _, r := range s {
		if r == '\n' || r == '\t' {
			b.WriteRune(r)
		} else if unicode.IsControl(r) || unicode.Is(unicode.Cf, r) || r == 0x1b {
			fmt.Fprintf(&b, "\\u%04x", r)
		} else {
			b.WriteRune(r)
		}
	}
	return b.String()
}
func dropLast(s string) string {
	r := []rune(s)
	if len(r) == 0 {
		return ""
	}
	return string(r[:len(r)-1])
}

// A failed search selects nothing until the user moves to a recovery action.
func (m *model) selectSearchResult() {
	m.selected = 0
	if len(m.providerMatches()) == 0 {
		m.selected = -1
	}
}

func (m model) providerSelection() int {
	for i, index := range m.providerMatches() {
		if index == m.providerAt {
			return i
		}
	}
	return 0
}
