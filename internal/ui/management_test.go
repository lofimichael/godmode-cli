package ui

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"
)

func TestHomeShortKeepsEveryFocusedActionAndExitVisible(t *testing.T) {
	for _, size := range [][2]int{{28, 12}, {40, 18}, {80, 24}, {110, 36}} {
		for at, name := range homeNames {
			m := create(t, fake(), "home", "")
			m = send(m, tea.WindowSizeMsg{Width: size[0], Height: size[1]})
			m.selected = at
			view := ansi.Strip(m.View().Content)
			if !strings.Contains(view, "❯ "+name) || !strings.Contains(view, "Esc quit") {
				t.Fatalf("%dx%d hides %s or exit: %s", size[0], size[1], name, view)
			}
			if strings.Contains(view, "Setup ") || strings.Contains(view, "%") {
				t.Fatal("management screen still scores optional setup")
			}
		}
	}
}

func TestBusinessProfileReturnsToItsParent(t *testing.T) {
	m := create(t, fake(), "home", "")
	m = enter(enter(m))
	if m.page != "profile" {
		t.Fatal("Business did not open profile")
	}
	m = escape(m)
	if m.page != "business" || m.selected != 0 {
		t.Fatal("profile lost Business parent")
	}
	m = escape(m)
	if m.page != "home" || m.selected != 0 {
		t.Fatal("Business lost home focus")
	}
}

func TestScopeSelectionDistinguishesAutomaticAndNamedDefault(t *testing.T) {
	f := fake()
	m := create(t, f, "home", "")
	m = enter(m)
	m.selected = 1
	m = enter(m)
	if !strings.Contains(ansi.Strip(m.View().Content), "Automatic") {
		t.Fatal("missing automatic business choice")
	}
	m.selected = 1
	m = enter(m)
	if m.state.Context != "default" || !strings.Contains(m.command("help"), "--context default") {
		t.Fatal("explicit business named default was treated as automatic")
	}
	m.selected = 1
	m = enter(m)
	m.selected = 0
	m = enter(m)
	if m.state.Context != "" {
		t.Fatal("automatic selection did not clear explicit context")
	}
	if f.requests[len(f.requests)-1]["name"] != "" {
		t.Fatal("automatic selection sent a named context")
	}

	m = escape(m)
	m.selected = 3
	m = enter(m)
	m.selected = 1
	m = enter(m)
	if m.state.Environment != "acme-test" || m.state.Context != "" || m.page != "home" || m.selected != 3 {
		t.Fatal("environment selection changed business or lost home position")
	}
	if !strings.Contains(m.View().Content, "acme-test") {
		t.Fatal("selected environment is invisible")
	}
}

func TestEnvironmentCopyShowsSnapshotAndWaitsForReview(t *testing.T) {
	f := fake()
	f.state["store_exists"] = true
	m := create(t, f, "home", "")
	m.selected = 3
	m = enter(m)
	m.selected = len(m.environments)
	m = enter(m)
	m.selected = 1
	m = enter(m)
	m = send(m, key('a', "acme-stage"))
	view := ansi.Strip(m.View().Content)
	for _, want := range []string{".env.godmode.acme-stage", "Copies saved values", "Later edits stay separate"} {
		if !strings.Contains(view, want) {
			t.Fatalf("copy preview missing %q", want)
		}
	}
	if count(f.calls, "environment_create") != 0 {
		t.Fatal("typing created an environment")
	}
	m = send(m, tea.WindowSizeMsg{Width: 28, Height: 10})
	m = enter(m)
	if count(f.calls, "environment_create") != 0 {
		t.Fatal("hidden preview created an environment")
	}
	m = send(m, tea.WindowSizeMsg{Width: 80, Height: 24})
	m = enter(m)
	if m.state.Environment != "acme-stage" || count(f.calls, "environment_create") != 1 {
		t.Fatal("reviewed copy did not select new environment")
	}
	for i, call := range f.calls {
		if call == "environment_create" && f.requests[i]["copy"] != "default" {
			t.Fatal("copy source was not explicit")
		}
	}
}

func TestDoctorLoadsAsCommandAndIgnoresLateResults(t *testing.T) {
	f := fake()
	m := create(t, f, "home", "")
	m.selected = 4
	result, cmd := m.Update(key(tea.KeyEnter, ""))
	m = result.(model)
	if cmd == nil || !m.doctorLoading || count(f.calls, "doctor") != 0 {
		t.Fatal("Doctor did not expose loading before its command")
	}
	message := cmd()
	m = send(m, message)
	if m.doctorLoading || !strings.Contains(m.View().Content, "Missing example") || !strings.Contains(m.View().Content, "godmode setup example") {
		t.Fatal("Doctor did not render result and recovery action")
	}
	m = escape(m)
	m = send(m, message)
	if m.page != "home" || m.selected != 4 {
		t.Fatal("late Doctor result replaced the current screen")
	}
}

func TestUpdateRestoresTerminalBeforeScopedExternalCommand(t *testing.T) {
	m := create(t, fake(), "home", "")
	m.state.Context, m.state.Environment = "acme", "acme-test"
	m.selected = 5
	m = enter(m)
	var external *CommandExit
	if !m.quitting || !errors.Is(m.outcome, ErrUpdate) || !errors.As(m.outcome, &external) {
		t.Fatal("Update did not yield an external action")
	}
	if external.Context != "acme" || external.Environment != "acme-test" {
		t.Fatal("Update lost current UI selection")
	}
	if m.View().Content != "" {
		t.Fatal("Update retained the TUI")
	}
}

func TestInstalledAgentsKeepTaskInstructionsAndCopyAction(t *testing.T) {
	f := fake()
	m := create(t, f, "agents", "")
	m.state.Context, m.state.Environment = "acme", "acme-test"
	m.agents.CopyBlock = "Use godmode --context acme --env acme-test help."
	for i := range m.agents.Targets {
		m.agents.Targets[i].Added = true
	}
	view := ansi.Strip(m.View().Content)
	for _, want := range []string{"Copy for this task", m.agents.CopyBlock, "c copy", "agents --print"} {
		if !strings.Contains(view, want) {
			t.Fatalf("installed screen hides %q", want)
		}
	}
	m = send(m, key('c', "c"))
	if count(f.calls, "copy_agent") != 1 || !strings.Contains(m.notice, "Clipboard unavailable") {
		t.Fatal("installed screen cannot copy or describe clipboard fallback")
	}
	if !strings.Contains(strings.Join(m.agentLines(), "\n"), m.agents.CopyBlock) {
		t.Fatal("fallback note is not visible")
	}
}

func TestManagementViewsFitWithAndWithoutColor(t *testing.T) {
	for _, page := range []string{"business", "contexts", "environments", "environment_new", "scope_name", "doctor"} {
		for _, size := range [][2]int{{28, 12}, {40, 18}, {80, 24}, {110, 36}} {
			for _, colors := range []bool{false, true} {
				t.Run(fmt.Sprintf("%s-%dx%d-%v", page, size[0], size[1], colors), func(t *testing.T) {
					m := create(t, fake(), "home", "")
					m.loadContexts()
					m.loadEnvironments()
					m.page, m.scopeKind, m.colors = page, "environment", colors
					m = send(m, tea.WindowSizeMsg{Width: size[0], Height: size[1]})
					view := m.View().Content
					if len(strings.Split(view, "\n")) > size[1] {
						t.Fatal("height overflow")
					}
					for _, row := range strings.Split(view, "\n") {
						if ansi.StringWidth(row) > size[0] {
							t.Fatal("width overflow")
						}
					}
					if !colors && view != ansi.Strip(view) {
						t.Fatal("NO_COLOR retained styling")
					}
				})
			}
		}
	}
}

func TestLongScopeDetailsRemainScrollableAndSelectTheInspectedItem(t *testing.T) {
	f := fake()
	m := create(t, f, "home", "")
	m.selected = 3
	m = enter(m)
	longName := "acme-" + strings.Repeat("long-project-", 5) + "staging"
	longPath := "/tmp/" + strings.Repeat("long-directory/", 20) + ".env.godmode." + longName
	m.environments = []environment{{Name: longName, Path: longPath, Keys: 1}}
	m.selected = 0
	m = send(m, tea.WindowSizeMsg{Width: 40, Height: 18})
	m = send(m, key(tea.KeyTab, ""))
	if m.page != "scope_details" || count(f.calls, "environment_select") != 0 {
		t.Fatal("details selected or lost the inspected item")
	}
	all := strings.Join(m.body(), "\n")
	full := strings.ReplaceAll(ansi.Strip(all), "\n", "")
	if !strings.Contains(full, longName) || !strings.Contains(full, longPath) {
		t.Fatal("full environment name or path is unavailable")
	}
	m = send(m, key(tea.KeyEnd, ""))
	if m.scroll == 0 || !strings.Contains(ansi.Strip(m.View().Content), "Esc back") {
		t.Fatal("long path cannot scroll with exit visible")
	}
	m = enter(m)
	if m.state.Environment != longName || m.page != "home" || m.selected != 3 {
		t.Fatal("details selected a different environment")
	}
}

func TestWrappedEnvironmentNameCannotHideAFileCreation(t *testing.T) {
	f := fake()
	m := create(t, f, "home", "")
	m.startScopeName("environment", "default")
	m.text = "a" + strings.Repeat("long-project-", 7)
	m.cursor = len(m.text)
	m = send(m, tea.WindowSizeMsg{Width: 40, Height: 18})
	for _, row := range m.body() {
		if strings.Contains(row, "\n") {
			t.Fatal("wrapped input was not counted as separate display rows")
		}
	}
	if m.inputFits() {
		t.Fatal("long candidate unexpectedly fits short review")
	}
	m = enter(m)
	if count(f.calls, "environment_create") != 0 {
		t.Fatal("partly hidden form created a file")
	}
}

func TestDisplayedCommandQuotesCustomHomeWithoutShellExpansion(t *testing.T) {
	m := create(t, fake(), "home", "")
	marker := filepath.Join(t.TempDir(), "must-not-exist")
	home := "/tmp/client's home $(touch " + marker + ") `touch " + marker + "`"
	m.opts.Home, m.state.Context, m.state.Environment = home, "acme", "acme-test"
	command := m.command("agents", "--print")
	if !strings.Contains(command, "--home '/tmp/client'\\''s home") {
		t.Fatal("custom home is not shell quoted")
	}
	// set -- treats the displayed words as arguments, never as an invoked CLI.
	// The marker detects command substitution if quoting regresses.
	probe := exec.Command("/bin/sh", "-c", "set -- "+command+"; printf '%s\\n' \"$@\"")
	got, err := probe.Output()
	if err != nil {
		t.Fatal(err)
	}
	want := strings.Join([]string{"godmode", "--home", home, "--context", "acme", "--env", "acme-test", "agents", "--print"}, "\n") + "\n"
	if string(got) != want {
		t.Fatal("displayed command does not preserve literal scope arguments")
	}
	if _, err := os.Stat(marker); !os.IsNotExist(err) {
		t.Fatal("displayed path executed shell substitution")
	}
}
