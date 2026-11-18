// Package musicui is the optional GODMODE BEATZ terminal player. It knows only
// the music protocol: no profile, credential, filesystem, or synthesis access.
package musicui

import (
	"encoding/json"
	"fmt"
	"os"
	"path"
	"sort"
	"strings"
	"time"
	"unicode"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"
)

type Backend interface {
	Call(string, map[string]any) (map[string]any, error)
}
type Options struct{ NoMotion, Plain, Light bool }
type track struct {
	ID         string `json:"id"`
	Title      string `json:"title"`
	Collection string `json:"collection"`
}
type library struct {
	Configured      bool    `json:"configured"`
	Error           string  `json:"error"`
	Tracks          []track `json:"tracks"`
	PlayerAvailable bool    `json:"player_available"`
	NoMotion        bool    `json:"no_motion"`
}
type status struct {
	State    string    `json:"state"`
	Track    *track    `json:"track"`
	Queue    []track   `json:"queue"`
	Index    int       `json:"index"`
	Position float64   `json:"position"`
	Duration float64   `json:"duration"`
	Volume   float64   `json:"volume"`
	Repeat   string    `json:"repeat"`
	Shuffle  bool      `json:"shuffle"`
	Levels   []float64 `json:"levels"`
	Message  string    `json:"message"`
}
type entry struct {
	title, collection string
	container         bool
	tracks            []track
	track             track
	queueIndex        int
}
type location struct {
	path     string
	selected int
}
type action struct {
	name string
	args map[string]any
}
type loadedMsg struct {
	epoch   int
	library library
	status  status
	err     error
}
type resultMsg struct {
	id, epoch int
	status    status
	err       error
}
type pollMsg struct{ token int }
type noticeExpiredMsg struct{ token int }
type statusMsg struct {
	epoch, token int
	status       status
	err          error
}

type model struct {
	backend                              Backend
	opts                                 Options
	library                              library
	status                               status
	width, height                        int
	loaded, closing, help, searching     bool
	query, collection, view              string
	selected, libraryAt, queueAt, helpAt int
	trail                                []location
	searchReturn                         location
	searchView                           string
	searchActive                         bool
	searchLibraryAt                      int
	info                                 bool
	setupAt                              int
	collectionReturns                    []browserState
	infoAt                               int
	notice, failure                      string
	noticeToken                          int
	busy                                 bool
	busyAction                           string
	serial, epoch, pollToken             int
	pending                              []action
}

// Run owns the terminal only. Closing this view never stops the player.
func Run(backend Backend, opts Options) error {
	opts.Plain = opts.Plain || os.Getenv("NO_COLOR") != "" || os.Getenv("CLICOLOR") == "0"
	opts.Light = opts.Light || strings.HasSuffix(os.Getenv("COLORFGBG"), ";15") || strings.HasSuffix(os.Getenv("COLORFGBG"), ";7")
	m := newModel(backend, opts)
	final, err := tea.NewProgram(m).Run()
	if err != nil {
		return err
	}
	if result, ok := final.(model); ok {
		switch result.status.State {
		case "playing", "preparing":
			fmt.Fprintln(os.Stdout, "Music keeps playing. Stop it with: godmode music stop")
		case "paused":
			fmt.Fprintln(os.Stdout, "Music stays paused. Stop it with: godmode music stop")
		}
	}
	return nil
}
func newModel(backend Backend, opts Options) model {
	return model{backend: backend, opts: opts, width: 80, height: 24, view: "library", status: status{State: "stopped", Repeat: "off", Volume: 35, Index: -1}}
}
func decode[T any](value map[string]any) (T, error) {
	var result T
	data, err := json.Marshal(value)
	if err == nil {
		err = json.Unmarshal(data, &result)
	}
	return result, err
}
func fetchStatus(backend Backend, name string, args map[string]any) (status, error) {
	raw, err := backend.Call(name, args)
	if err != nil {
		return status{}, err
	}
	return decode[status](raw)
}
func (m model) Init() tea.Cmd {
	return func() tea.Msg {
		raw, err := m.backend.Call("library", nil)
		if err != nil {
			return loadedMsg{epoch: m.epoch, err: err}
		}
		lib, err := decode[library](raw)
		if err != nil {
			return loadedMsg{epoch: m.epoch, err: err}
		}
		s, err := fetchStatus(m.backend, "status", nil)
		return loadedMsg{epoch: m.epoch, library: lib, status: s, err: err}
	}
}
func (m model) interval() time.Duration {
	if m.status.State == "playing" || m.status.State == "preparing" {
		if m.opts.NoMotion {
			return time.Second
		}
		return 100 * time.Millisecond
	}
	return 2 * time.Second
}
func (m *model) schedule() tea.Cmd {
	m.pollToken++
	token := m.pollToken
	return tea.Tick(m.interval(), func(time.Time) tea.Msg { return pollMsg{token} })
}
func (m *model) start(a action) tea.Cmd {
	if a.name == "volume" {
		if delta, ok := a.args["delta"].(float64); ok {
			a.args = map[string]any{"value": max(0, min(100, m.status.Volume+delta))}
		}
	}
	if a.name == "repeat" && a.args["cycle"] == true {
		next := map[string]string{"off": "all", "all": "one", "one": "off"}[m.status.Repeat]
		if next == "" {
			next = "all"
		}
		a.args = map[string]any{"value": next}
	}
	if a.name == "shuffle" && a.args["toggle"] == true {
		a.args = map[string]any{"value": !m.status.Shuffle}
	}
	m.busy = true
	m.busyAction = a.name
	m.serial++
	id, epoch, backend := m.serial, m.epoch, m.backend
	return func() tea.Msg {
		s, err := fetchStatus(backend, a.name, a.args)
		return resultMsg{id: id, epoch: epoch, status: s, err: err}
	}
}
func (m *model) clearNotice() { m.notice = ""; m.noticeToken++ }
func (m model) mutate(name string, args map[string]any) (tea.Model, tea.Cmd) {
	m.epoch++
	m.pollToken++
	m.failure = ""
	m.clearNotice()
	a := action{name, args}
	if name == "stop" {
		m.pending = nil
	}
	if m.busy {
		if len(m.pending) < 32 {
			m.pending = append(m.pending, a)
		}
		return m, nil
	}
	return m, m.start(a)
}
func (m model) quit() (tea.Model, tea.Cmd) {
	m.closing = true
	m.pending = nil
	m.pollToken++
	if m.busy {
		return m, nil
	}
	return m, tea.Quit
}
func (m model) Update(message tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := message.(type) {
	case noticeExpiredMsg:
		if msg.token == m.noticeToken {
			m.notice = ""
		}
		return m, nil
	case tea.WindowSizeMsg:
		m.width = max(1, msg.Width)
		m.height = max(1, msg.Height)
		return m, nil
	case loadedMsg:
		m.loaded = true
		m.library = msg.library
		m.opts.NoMotion = m.opts.NoMotion || msg.library.NoMotion
		if msg.epoch == m.epoch && !m.busy {
			if msg.err != nil {
				m.failure = msg.err.Error()
			} else {
				m.status = msg.status
				m.failure = ""
			}
		}
		if m.status.State == "" {
			m.status.State = "stopped"
		}
		return m, m.schedule()
	case pollMsg:
		if msg.token != m.pollToken || m.closing || m.busy {
			return m, nil
		}
		backend, epoch, token := m.backend, m.epoch, m.pollToken
		return m, func() tea.Msg { s, err := fetchStatus(backend, "status", nil); return statusMsg{epoch, token, s, err} }
	case statusMsg:
		if msg.epoch != m.epoch || msg.token != m.pollToken || m.busy || m.closing {
			return m, nil
		}
		if msg.err != nil {
			m.failure = msg.err.Error()
		} else {
			m.status = msg.status
			m.failure = ""
		}
		m.clampSelection()
		return m, m.schedule()
	case resultMsg:
		if !m.busy || msg.id != m.serial {
			return m, nil
		}
		m.busy = false
		var noticeCmd tea.Cmd
		if msg.err != nil {
			m.failure = msg.err.Error()
			m.pending = nil
		} else {
			m.status = msg.status
			m.notice = receipt(m.busyAction)
			m.noticeToken++
			if m.notice != "" {
				token := m.noticeToken
				noticeCmd = tea.Tick(2*time.Second, func(time.Time) tea.Msg { return noticeExpiredMsg{token} })
			}
		}
		m.busyAction = ""
		m.clampSelection()
		if m.closing {
			return m, tea.Quit
		}
		if len(m.pending) > 0 {
			a := m.pending[0]
			m.pending = m.pending[1:]
			next := m.start(a)
			if noticeCmd != nil {
				return m, tea.Batch(next, noticeCmd)
			}
			return m, next
		}
		next := m.schedule()
		if noticeCmd != nil {
			return m, tea.Batch(next, noticeCmd)
		}
		return m, next
	case tea.PasteMsg:
		if m.searching {
			m.clearNotice()
			m.query += clean(msg.Content)
			m.query = limitRunes(m.query, 200)
			m.selected = 0
		}
		return m, nil
	case tea.KeyPressMsg:
		k := msg.String()
		switch k {
		case "up", "down", "left", "right", "home", "end", "pgup", "pgdown", "j", "k", "tab", "esc", "backspace", "enter", "/", "i", "?", "c":
			m.clearNotice()
		}
		if k == "ctrl+c" {
			return m.quit()
		}
		if m.closing {
			return m, nil
		}
		if m.setupPage() {
			switch k {
			case "up", "k":
				m.setupAt = max(0, m.setupAt-1)
				return m, nil
			case "down", "j":
				m.setupAt = min(m.setupAt+1, max(0, len(m.setupLines())-m.bodyRows()))
				return m, nil
			case "pgdown", "space":
				m.setupAt = min(m.setupAt+max(1, m.bodyRows()-1), max(0, len(m.setupLines())-m.bodyRows()))
				return m, nil
			case "pgup":
				m.setupAt = max(0, m.setupAt-max(1, m.bodyRows()-1))
				return m, nil
			case "home":
				m.setupAt = 0
				return m, nil
			case "end":
				m.setupAt = max(0, len(m.setupLines())-m.bodyRows())
				return m, nil
			}
		}
		if m.info {
			switch k {
			case "i", "esc":
				m.info = false
			case "tab":
				// The enqueue receipt promises queue inspection from details.
				// Opening it preserves the library query/cursor; queue details
				// simply close onto their existing queue row.
				m.info = false
				if m.view != "queue" {
					m.libraryAt = m.selected
					m.view = "queue"
					m.selected = m.queueAt
				}
				m.clampSelection()
				return m, nil
			case "c":
				return m.openCollection()
			case "A":
				return m.enqueueCollection()
			case "a":
				return m.enqueueSelected()
			case "enter":
				entries := m.entries()
				if len(entries) > 0 && entries[min(m.selected, len(entries)-1)].container {
					m.info = false
				}
				return m.activate()
			case "q":
				return m.quit()
			case "up", "k":
				m.infoAt = max(0, m.infoAt-1)
			case "down", "j":
				m.infoAt++
			case "pgdown", "space":
				m.infoAt += 5
			case "pgup":
				m.infoAt = max(0, m.infoAt-5)
			}
			return m, nil
		}
		if m.help {
			end := max(0, len(helpLines(m.innerWidth()))-m.bodyRows())
			page := max(1, m.bodyRows()-1)
			switch k {
			case "?", "esc":
				m.help = false
			case "q":
				return m.quit()
			case "up", "k":
				m.helpAt = max(0, min(end, m.helpAt)-1)
			case "down", "j":
				m.helpAt = min(end, m.helpAt+1)
			case "pgdown", "space":
				m.helpAt = min(end, m.helpAt+page)
			case "pgup":
				m.helpAt = max(0, min(end, m.helpAt)-page)
			case "home":
				m.helpAt = 0
			case "end":
				m.helpAt = end
			}
			return m, nil
		}

		if m.searching {
			switch k {
			case "esc":
				m.clearSearch()
				return m, nil
			case "tab", "enter":
				// Submitting a query only transfers focus. Playback needs a
				// separate Enter from the results, where its queue effect is shown.
				m.searching = false
				return m, nil
			case "up", "down", "pgup", "pgdown", "home", "end":
				return m.navigate(k)
			case "backspace":
				r := []rune(m.query)
				if len(r) > 0 {
					m.query = string(r[:len(r)-1])
				}
				m.selected = 0
			case "ctrl+u":
				m.query = ""
				m.selected = 0
			default:
				if msg.Text != "" {
					m.query = limitRunes(m.query+clean(msg.Text), 200)
					m.selected = 0
				}
			}
			return m, nil
		}
		switch k {
		case "q":
			return m.quit()
		case "i":
			m.info = true
			m.infoAt = 0
			return m, nil
		case "?":
			m.help = true
			m.helpAt = 0
			return m, nil
		case "esc", "left", "backspace":
			if m.view == "library" && (m.searchActive || m.query != "") {
				m.clearSearch()
			} else if m.view == "queue" {
				m.queueAt = m.selected
				m.view = "library"
				m.selected = m.libraryAt
			} else if len(m.trail) > 0 {
				l := m.trail[len(m.trail)-1]
				m.trail = m.trail[:len(m.trail)-1]
				m.collection = l.path
				m.selected = l.selected
			} else if len(m.collectionReturns) > 0 {
				previous := m.collectionReturns[len(m.collectionReturns)-1]
				m.collectionReturns = m.collectionReturns[:len(m.collectionReturns)-1]
				m.restoreBrowser(previous)
			} else {
				m.notice = "Library root · q closes view; x stops music"
			}
			return m, nil
		case "/":
			if !m.searchActive {
				m.searchReturn = location{m.collection, m.selected}
				m.searchView = m.view
				m.searchLibraryAt = m.libraryAt
				if m.view == "library" {
					m.searchLibraryAt = m.selected
				}
			}
			if m.view == "queue" {
				m.queueAt = m.selected
			}
			m.searchActive = true
			m.view = "library"
			m.searching = true
			m.selected = 0
			return m, nil
		case "tab":
			if m.view == "queue" {
				m.queueAt = m.selected
				m.view = "library"
				m.selected = m.libraryAt
			} else {
				m.libraryAt = m.selected
				m.view = "queue"
				m.selected = m.queueAt
			}
			m.clampSelection()
			return m, nil
		case "up", "down", "pgup", "pgdown", "home", "end", "j", "k":
			return m.navigate(k)
		case "enter", "right":
			return m.activate()
		case "c":
			return m.openCollection()
		case "A":
			return m.enqueueCollection()
		case "a":
			return m.enqueueSelected()
		case "space":
			return m.mutate("toggle", nil)
		case "x":
			return m.mutate("stop", nil)
		case "n":
			return m.mutate("next", nil)
		case "p":
			return m.mutate("previous", nil)
		case "<", ",":
			return m.mutate("seek", map[string]any{"seconds": -5})
		case ">", ".":
			return m.mutate("seek", map[string]any{"seconds": 5})
		case "+", "=":
			return m.mutate("volume", map[string]any{"delta": float64(5)})
		case "-":
			return m.mutate("volume", map[string]any{"delta": float64(-5)})
		case "r":
			return m.mutate("repeat", map[string]any{"cycle": true})
		case "s":
			return m.mutate("shuffle", map[string]any{"toggle": true})
		case "delete", "d":
			if m.view == "queue" && len(m.status.Queue) > 0 {
				return m.mutate("remove", map[string]any{"index": m.selected})
			}
		case "R":
			m.epoch++
			m.pollToken++
			return m, m.Init()
		}
	}
	return m, nil
}
func (m *model) clearSearch() {
	m.query = ""
	m.searching = false
	m.searchActive = false
	m.libraryAt = m.searchLibraryAt
	m.collection = m.searchReturn.path
	m.view = m.searchView
	if m.view == "" {
		m.view = "library"
	}
	m.selected = m.searchReturn.selected
	if m.view == "queue" {
		m.queueAt = m.selected
	} else {
		m.libraryAt = m.selected
	}
	m.clampSelection()
}
func (m model) navigate(k string) (tea.Model, tea.Cmd) {
	n := len(m.entries())
	step := max(1, m.bodyRows()-2)
	switch k {
	case "up", "k":
		m.selected--
	case "down", "j":
		m.selected++
	case "pgup":
		m.selected -= step
	case "pgdown":
		m.selected += step
	case "home":
		m.selected = 0
	case "end":
		m.selected = n - 1
	}
	m.clampSelection()
	return m, nil
}
func (m *model) clampSelection() { m.selected = max(0, min(m.selected, len(m.entries())-1)) }
func (m model) enqueueSelected() (tea.Model, tea.Cmd) {
	entries := m.entries()
	if len(entries) == 0 {
		return m, nil
	}
	m.clampSelection()
	e := entries[m.selected]
	tracks := e.tracks
	if !e.container {
		tracks = []track{e.track}
	}
	return m.mutate("enqueue", map[string]any{"ids": ids(tracks)})
}
func (m model) activate() (tea.Model, tea.Cmd) {
	entries := m.entries()
	if len(entries) == 0 {
		return m, nil
	}
	m.clampSelection()
	e := entries[m.selected]
	if e.container {
		m.trail = append(m.trail, location{m.collection, m.selected})
		m.collection = e.collection
		m.selected = 0
		return m, nil
	}
	if !m.library.PlayerAvailable {
		m.failure = "Playback needs mpv. Run: brew install mpv"
		return m, nil
	}
	var tracks []track
	at := 0
	for _, row := range entries {
		if !row.container {
			if row.track.ID == e.track.ID && len(tracks) == m.selected {
				at = len(tracks)
			}
			tracks = append(tracks, row.track)
		}
	}
	// Queue rows may repeat an ID; use the visible index rather than ID matching.
	if m.view == "queue" {
		at = m.selected
	} else {
		for i, t := range tracks {
			if t.ID == e.track.ID {
				at = i
				break
			}
		}
	}
	return m.mutate("play", map[string]any{"ids": ids(tracks), "index": at})
}
func ids(tracks []track) []string {
	out := make([]string, 0, len(tracks))
	for _, t := range tracks {
		out = append(out, t.ID)
	}
	return out
}
func (m model) entries() []entry {
	if m.view == "queue" {
		out := make([]entry, 0, len(m.status.Queue))
		for i, t := range m.status.Queue {
			out = append(out, entry{title: t.Title, track: t, queueIndex: i})
		}
		return out
	}
	if m.searchActive || m.query != "" || m.searching {
		q := strings.ToLower(m.query)
		out := []entry{}
		for _, t := range m.library.Tracks {
			if strings.Contains(strings.ToLower(t.Title+" "+t.Collection), q) {
				out = append(out, entry{title: t.Title, track: t})
			}
		}
		return out
	}
	if m.collection == "*" {
		out := []entry{}
		for _, t := range m.library.Tracks {
			out = append(out, entry{title: t.Title, track: t})
		}
		return out
	}
	groups := map[string][]track{}
	out := []entry{}
	for _, t := range m.library.Tracks {
		c := strings.Trim(t.Collection, "/")
		if c == "." {
			c = ""
		}
		if c == m.collection {
			out = append(out, entry{title: t.Title, track: t})
			continue
		}
		prefix := m.collection
		if prefix != "" {
			prefix += "/"
		}
		if !strings.HasPrefix(c, prefix) {
			continue
		}
		rest := strings.TrimPrefix(c, prefix)
		if rest == "" {
			continue
		}
		child := prefix + strings.SplitN(rest, "/", 2)[0]
		groups[child] = append(groups[child], t)
	}
	containers := []entry{}
	for c, tracks := range groups {
		containers = append(containers, entry{title: path.Base(c), collection: c, container: true, tracks: tracks})
	}
	sort.Slice(containers, func(i, j int) bool {
		return strings.ToLower(containers[i].title) < strings.ToLower(containers[j].title)
	})
	sort.SliceStable(out, func(i, j int) bool { return strings.ToLower(out[i].title) < strings.ToLower(out[j].title) })
	if m.collection == "" && len(groups) > 0 {
		containers = append([]entry{{title: "All tracks", collection: "*", container: true, tracks: m.library.Tracks}}, containers...)
	}
	return append(containers, out...)
}
func clean(s string) string {
	return strings.Map(func(r rune) rune {
		if unicode.IsControl(r) || unicode.In(r, unicode.Cf) {
			return -1
		}
		return r
	}, ansi.Strip(s))
}
func limitRunes(s string, n int) string {
	r := []rune(s)
	if len(r) > n {
		return string(r[:n])
	}
	return s
}
func receipt(name string) string {
	switch name {
	case "enqueue":
		return "Added to queue · Tab to inspect"
	case "stop":
		return "Stopped · queue kept"
	case "remove":
		return "Removed from queue"
	}
	return ""
}
