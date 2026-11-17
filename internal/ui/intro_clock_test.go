package ui

import (
	"testing"
	"time"

	tea "charm.land/bubbletea/v2"
)

func TestIntroClockWrapsWithoutDuplicatingOnEnter(t *testing.T) {
	m := create(t, fake(), "intro", "")
	m.colors, m.opts.NoMotion = true, false
	m.tick = introCycleFrames - 1
	next, cmd := m.Update(tickMsg(time.Now()))
	m = next.(model)
	if m.tick != 0 || cmd == nil {
		t.Fatal("intro clock did not schedule its next cycle")
	}
	next, cmd = m.Update(tea.KeyPressMsg{Code: tea.KeyEnter})
	m = next.(model)
	if m.introStage != 1 || cmd != nil {
		t.Fatal("stage transition duplicated the active clock")
	}
	next, cmd = m.Update(tickMsg(time.Now()))
	m = next.(model)
	if m.tick != 1 || cmd == nil {
		t.Fatal("the existing clock did not continue in the second scene")
	}
	m.page = "home"
	next, cmd = m.Update(tickMsg(time.Now()))
	if next.(model).tick != 1 || cmd != nil {
		t.Fatal("intro clock continued outside the intro")
	}
}
