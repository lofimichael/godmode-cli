package musicui

import (
	tea "charm.land/bubbletea/v2"
	"strings"
)

// A collection opened from a result or queue has a real back destination. Audio
// state is deliberately absent: restoring navigation can never restore playback.
type browserState struct {
	view, collection, query      string
	selected, libraryAt, queueAt int
	trail                        []location
	searchActive, searching      bool
	searchReturn                 location
	searchView                   string
	searchLibraryAt              int
	info                         bool
	infoAt                       int
}

func (m model) browserSnapshot() browserState {
	return browserState{view: m.view, collection: m.collection, query: m.query, selected: m.selected, libraryAt: m.libraryAt, queueAt: m.queueAt, trail: append([]location(nil), m.trail...), searchActive: m.searchActive, searching: m.searching, searchReturn: m.searchReturn, searchView: m.searchView, searchLibraryAt: m.searchLibraryAt, info: m.info, infoAt: m.infoAt}
}
func (m *model) restoreBrowser(s browserState) {
	m.view = s.view
	m.collection = s.collection
	m.query = s.query
	m.selected = s.selected
	m.libraryAt = s.libraryAt
	m.queueAt = s.queueAt
	m.trail = s.trail
	m.searchActive = s.searchActive
	m.searching = s.searching
	m.searchReturn = s.searchReturn
	m.searchView = s.searchView
	m.searchLibraryAt = s.searchLibraryAt
	m.info = s.info
	m.infoAt = s.infoAt
	m.clampSelection()
}
func collectionPath(s string) string {
	s = strings.Trim(s, "/")
	if s == "." {
		return ""
	}
	return s
}
func (m model) openCollection() (tea.Model, tea.Cmd) {
	entries := m.entries()
	if len(entries) == 0 {
		return m, nil
	}
	m.clampSelection()
	e := entries[m.selected]
	if e.container {
		m.info = false
		return m.activate()
	}
	destination := collectionPath(e.track.Collection)
	if m.view == "library" && m.collection == destination && !m.searchActive && m.query == "" && !m.info {
		return m, nil
	}
	if m.view == "queue" {
		m.queueAt = m.selected
	} else {
		m.libraryAt = m.selected
	}
	m.collectionReturns = append(m.collectionReturns, m.browserSnapshot())
	m.view = "library"
	m.collection = destination
	m.query = ""
	m.searchActive = false
	m.searching = false
	m.info = false
	m.trail = nil
	m.selected = 0
	for i, row := range m.entries() {
		if !row.container && row.track.ID == e.track.ID {
			m.selected = i
			break
		}
	}
	m.libraryAt = m.selected
	return m, nil
}
func (m model) enqueueCollection() (tea.Model, tea.Cmd) {
	entries := m.entries()
	if len(entries) == 0 {
		return m, nil
	}
	m.clampSelection()
	e := entries[m.selected]
	tracks := e.tracks
	if !e.container {
		collection := collectionPath(e.track.Collection)
		for _, t := range m.library.Tracks {
			c := collectionPath(t.Collection)
			if c == collection || (collection != "" && strings.HasPrefix(c, collection+"/")) {
				tracks = append(tracks, t)
			}
		}
	}
	if len(tracks) == 0 {
		return m, nil
	}
	return m.mutate("enqueue", map[string]any{"ids": ids(tracks)})
}
func (m model) selectedTrack() bool {
	entries := m.entries()
	return len(entries) > 0 && !entries[min(m.selected, len(entries)-1)].container
}
func (m model) setupPage() bool { return m.loaded && !m.library.Configured && !m.help && !m.info }
