package musicpackui

import (
	"os/exec"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"
)

func TestInstallRequiresEnterAndCancelNeverInstalls(t *testing.T) {
	cases := []struct {
		key  tea.KeyPressMsg
		want bool
	}{
		{tea.KeyPressMsg{Code: tea.KeyEnter}, true},
		{tea.KeyPressMsg{Code: tea.KeyEscape}, false},
		{tea.KeyPressMsg{Code: 'q', Text: "q"}, false},
		{tea.KeyPressMsg{Code: 'c', Mod: tea.ModCtrl}, false},
	}
	for _, c := range cases {
		m := newModel()
		if m.Init() != nil {
			t.Fatal("card performed startup work")
		}
		next, cmd := m.Update(c.key)
		got := next.(model)
		if got.install != c.want || !got.closing || cmd == nil {
			t.Fatal("decision did not match key")
		}
		if _, ok := cmd().(tea.QuitMsg); !ok {
			t.Fatal("decision did not restore terminal before caller proceeds")
		}
	}
	m := newModel()
	next, cmd := m.Update(tea.KeyPressMsg{Code: 'a', Text: "a"})
	if cmd != nil || next.(model).install || next.(model).closing {
		t.Fatal("unrelated key accepted installation")
	}
}
func TestCardFitsAndExplainsOptionalPack(t *testing.T) {
	for _, size := range [][2]int{{40, 18}, {80, 24}, {120, 36}} {
		m := newModel()
		m.width, m.height = size[0], size[1]
		m.plain = true
		v := m.View()
		lines := strings.Split(v.Content, "\n")
		if len(lines) != size[1] {
			t.Fatalf("%v wrong height", size)
		}
		for _, line := range lines {
			if ansi.StringWidth(line) > size[0] {
				t.Fatalf("%v clipped decision card", size)
			}
		}
		for _, text := range []string{"OPTIONAL MUSIC PACK", "Player, library and queue", "Local synth and instruments", "Original jingles", "local .ootrs tracks", "Jingles only need mpv", "Enter install · Esc back"} {
			if !strings.Contains(v.Content, text) {
				t.Fatalf("%v missing %q\n%s", size, text, v.Content)
			}
		}
		if !strings.Contains(v.Content, "BEATZ") && !strings.Contains(v.Content, "B E A T Z") {
			t.Fatal("card omitted music identity")
		}
		if strings.Contains(v.Content, "\x1b") {
			t.Fatal("plain card emitted styling")
		}
	}
}
func TestResizeKeepsChoiceWithoutSideEffects(t *testing.T) {
	m := newModel()
	next, cmd := m.Update(tea.WindowSizeMsg{Width: 40, Height: 18})
	if cmd != nil || next.(model).install {
		t.Fatal("resize did work")
	}
	if !strings.Contains(next.(model).View().Content, "Enter install") {
		t.Fatal("resize hid choice")
	}
}
func TestCardDoesNotImportMusicAssetsOrBackends(t *testing.T) {
	raw, err := exec.Command("go", "list", "-deps", ".").Output()
	if err != nil {
		t.Fatal(err)
	}
	for _, dep := range strings.Split(strings.TrimSpace(string(raw)), "\n") {
		if strings.HasPrefix(dep, "github.com/lofimichael/godmode-cli/internal/") && dep != "github.com/lofimichael/godmode-cli/internal/musicpackui" {
			t.Fatalf("light card imported backend or assets: %s", dep)
		}
	}
}
