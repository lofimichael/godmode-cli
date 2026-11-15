package ui

import (
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
)

func TestSecretPasteNeverSubmitsOrDisplaysItsContents(t *testing.T) {
	m := secretModel{prompt: "License key:"}
	updated, cmd := m.Update(tea.PasteMsg{Content: "synthetic-private-value\n"})
	m = updated.(secretModel)
	if cmd != nil || m.done {
		t.Fatal("paste submitted")
	}
	if strings.Contains(m.View().Content, "synthetic") {
		t.Fatal("paste exposed")
	}
	updated, _ = m.Update(tea.KeyPressMsg{Code: tea.KeyEnter})
	if !updated.(secretModel).done {
		t.Fatal("explicit Enter did not submit")
	}
}
