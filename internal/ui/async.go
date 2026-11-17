package ui

import (
	"time"

	tea "charm.land/bubbletea/v2"
)

// Disk, clipboard and browser work never hold Bubble Tea's input/render loop.
// Operations are serial: a second Enter cannot duplicate a write. The worker
// owns its model copy; only presentation events can change the live model.
type operationMsg struct {
	id   int
	next model
	cmd  tea.Cmd
}
type busyMsg struct{ id int }
type pulseMsg struct{ id int }

func introTick() tea.Cmd {
	return tea.Tick(40*time.Millisecond, func(t time.Time) tea.Msg { return tickMsg(t) })
}

func (m model) workLabel(message tea.Msg) string {
	if m.validationInput(message) {
		return "Checking pasted key"
	}
	key, ok := message.(tea.KeyPressMsg)
	if !ok {
		return ""
	}
	k := key.String()
	if k == "esc" && m.page == "environment_new" {
		return "Reading environments"
	}
	if m.page == "agents" && (k == "c" || k == "m" || k == "enter") {
		return "Updating agent instructions"
	}
	if k != "enter" {
		return ""
	}
	switch m.page {
	case "intro":
		if m.introStage == 1 && m.introFits() {
			return "Opening Godmode"
		}
	case "home":
		if m.selected == 2 {
			return "Reading agent instructions"
		}
		if m.selected == 6 {
			return "Opening help"
		}
	case "active":
		if m.selected < 2 {
			return "Reading saved setups"
		}
	case "business":
		if m.selected == 1 {
			return "Reading businesses"
		}
	case "environment_new":
		if m.selected == 2 {
			return "Reading environments"
		}
	case "contexts", "environments", "scope_details":
		return "Selecting active setup"
	case "scope_name":
		return "Creating setup"
	case "providers":
		matches := m.providerMatches()
		if m.selected >= 0 && m.selected < len(matches) {
			if len(m.state.Providers[matches[m.selected]].Key) == 1 {
				return "Opening provider"
			}
		} else if m.selected == len(matches)+1 {
			return "Opening browser"
		}
	case "provider_keys", "name":
		return "Opening key"
	case "key":
		if m.text == "" {
			return "Opening browser"
		}
		return "Saving key"
	case "profile_field":
		return "Saving business details"
	}
	return ""
}

func (m model) validationInput(message tea.Msg) bool {
	if m.page != "key" {
		return false
	}
	switch msg := message.(type) {
	case tea.PasteMsg:
		return len(msg.Content) > 4096 && len(msg.Content) <= 1024*1024
	case tea.KeyPressMsg:
		// Editing a large value has the same cost as its original paste.
		if len(m.text)+len(msg.Text) <= 4096 {
			return false
		}
		return msg.String() == "backspace" || msg.String() == "delete" || msg.String() == "ctrl+u" || printable(msg.Text) != ""
	}
	return false
}

func (m model) beginWork(label string, validation bool, action func(model) (tea.Model, tea.Cmd)) (tea.Model, tea.Cmd) {
	m.operationID++
	m.busy, m.busyVisible, m.busyLabel, m.busyFrame = true, false, label, 0
	m.busyValidation, m.pendingInput, m.pulseFrame = validation, nil, 0
	id, snapshot := m.operationID, m
	// Review/fit checks describe the submitted screen, not its temporary busy
	// footer. The live model alone owns pending presentation.
	snapshot.busy, snapshot.busyVisible, snapshot.busyValidation = false, false, false
	work := func() tea.Msg {
		result, cmd := action(snapshot)
		return operationMsg{id: id, next: result.(model), cmd: cmd}
	}
	delayed := tea.Tick(80*time.Millisecond, func(time.Time) tea.Msg { return busyMsg{id} })
	return m, tea.Batch(work, delayed)
}

func (m model) Update(message tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := message.(type) {
	case operationMsg:
		if !m.busy || msg.id != m.operationID || m.quitting {
			return m, nil
		}
		next := msg.next
		resized := next.width != m.width || next.height != m.height
		next.width, next.height, next.dark, next.colors = m.width, m.height, m.dark, m.colors
		next.operationID, next.busy, next.busyVisible = m.operationID, false, false
		next.busyLabel, next.busyValidation, next.pendingInput, next.pulseFrame = "", false, nil, 0
		if next.page == m.page && next.introStage == m.introStage {
			next.tick = m.tick
		}
		if m.busyValidation && len(m.pendingInput) > 0 {
			value, pasted, fromPaste := next.text, next.pasted, next.fromPaste
			checked := next.check
			// Replay edits in order, but validate only the final candidate. No
			// queued event can submit, navigate away, or call another backend.
			next.deferValidation = true
			for _, input := range m.pendingInput {
				result, _ := next.updateNow(input)
				next = result.(model)
			}
			next.deferValidation = false
			if next.text != value || next.pasted != pasted || next.fromPaste != fromPaste {
				return next.beginWork("Checking key", true, func(candidate model) (tea.Model, tea.Cmd) {
					candidate.validateKey()
					return candidate, nil
				})
			}
			next.check = checked
		}
		if resized && next.page == "agents" {
			next.reviewedUntil, next.scroll = 0, 0
		}
		next.clampScroll()
		next.noteReview()
		return next, msg.cmd
	case busyMsg:
		if !m.busy || msg.id != m.operationID || m.quitting {
			return m, nil
		}
		m.busyVisible, m.busyFrame = true, m.busyFrame+1
		if m.opts.NoMotion || !m.colors {
			return m, nil
		}
		return m, tea.Tick(80*time.Millisecond, func(time.Time) tea.Msg { return busyMsg{msg.id} })
	case pulseMsg:
		if msg.id != m.pulseID || m.pulseFrame <= 0 || m.busy {
			return m, nil
		}
		m.pulseFrame--
		if m.pulseFrame == 0 {
			return m, nil
		}
		return m, tea.Tick(25*time.Millisecond, func(time.Time) tea.Msg { return pulseMsg{msg.id} })
	}
	if m.busy {
		switch msg := message.(type) {
		case tea.KeyPressMsg:
			if msg.String() == "ctrl+c" || msg.String() == "ctrl+d" {
				m.pendingInput = nil
				return m.updateNow(message)
			}
			if m.busyValidation {
				if msg.String() == "esc" {
					// Validation is read-only. Leaving the field invalidates its
					// pending reply; a dispatched write uses the locked path below.
					m.operationID++
					m.busy, m.busyVisible, m.busyValidation, m.pendingInput = false, false, false, nil
					return m.updateNow(message)
				}
				if msg.String() != "enter" {
					m.pendingInput = append(m.pendingInput, msg)
				}
				return m, nil
			}
			// A committed file change cannot truthfully be cancelled with Escape.
			return m, nil
		case tea.PasteMsg:
			if m.busyValidation {
				m.pendingInput = append(m.pendingInput, msg)
			}
			return m, nil
		case doctorMsg:
			return m, nil
		}
		return m.updateNow(message)
	}
	if label := m.workLabel(message); label != "" {
		if m.validationInput(message) {
			// Accept and mask the candidate immediately; only the expensive
			// validation crosses the command boundary.
			m.deferValidation = true
			result, _ := m.updateNow(message)
			m = result.(model)
			m.deferValidation = false
			return m.beginWork(label, true, func(candidate model) (tea.Model, tea.Cmd) {
				candidate.validateKey()
				return candidate, nil
			})
		}
		return m.beginWork(label, false, func(snapshot model) (tea.Model, tea.Cmd) {
			return snapshot.updateNow(message)
		})
	}
	beforePage, beforeSelection := m.page, m.selected
	result, cmd := m.updateNow(message)
	next := result.(model)
	if !next.opts.NoMotion && next.colors && next.page != "intro" &&
		(beforePage != next.page || beforeSelection != next.selected) {
		next.pulseID++
		next.pulseFrame = 5
		id := next.pulseID
		return next, tea.Batch(cmd, tea.Tick(25*time.Millisecond, func(time.Time) tea.Msg { return pulseMsg{id} }))
	}
	return next, cmd
}

func (m model) loadingText() string {
	if !m.busyVisible {
		return ""
	}
	frames := []string{"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"}
	frame := "…"
	if !m.opts.NoMotion && m.colors {
		frame = frames[m.busyFrame%len(frames)]
	}
	return frame + " " + m.busyLabel
}
