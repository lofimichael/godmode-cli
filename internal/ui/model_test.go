package ui

import (
	"errors"
	"fmt"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"
)

type fakeBackend struct {
	calls     []string
	saved     string
	state     map[string]any
	longAgent bool
	requests  []map[string]any
}

func fake() *fakeBackend {
	fields := []any{}
	for _, name := range []string{"name", "business", "legal", "website", "email", "address"} {
		fields = append(fields, map[string]any{"name": name, "label": strings.ToUpper(name[:1]) + name[1:], "description": "A public profile fact."})
	}
	return &fakeBackend{state: map[string]any{
		"version": "test", "home": "/tmp/godmode-test", "env_path": "/tmp/godmode-test/.env.godmode", "intro_seen": true, "music_included": true,
		"profile": map[string]string{}, "fields": fields, "states": map[string]string{}, "progress": map[string]any{"fields": []string{}, "providers": 0, "agents": []string{}, "agent": 0, "points": 0, "percent": 0},
		"providers": []any{map[string]any{"id": "example", "name": "Example", "about": "Example provider", "key": []any{map[string]any{"name": "EXAMPLE_TOKEN", "label": "API token"}}}},
		"issue_url": "https://example.test/issues/new",
	}}
}
func (f *fakeBackend) Call(action string, args map[string]any) (map[string]any, error) {
	f.calls = append(f.calls, action)
	f.requests = append(f.requests, args)
	switch action {
	case "state":
		return f.state, nil
	case "context_list":
		return map[string]any{"selected": f.state["context"], "contexts": []any{
			map[string]any{"name": "", "profile_path": "/tmp/godmode-test/profile.json"},
			map[string]any{"name": "default", "profile_path": "/tmp/godmode-test/contexts/default/profile.json"},
			map[string]any{"name": "acme", "profile_path": "/tmp/godmode-test/contexts/acme/profile.json"}}}, nil
	case "context_select", "context_create":
		f.state["context"] = args["name"]
		return f.state, nil
	case "environment_list":
		environments := []any{map[string]any{"name": "default", "path": "/tmp/godmode-test/.env.godmode", "keys": 0},
			map[string]any{"name": "acme-test", "path": "/tmp/godmode-test/.env.godmode.acme-test", "keys": 2}}
		if name, ok := f.state["environment"].(string); ok && name != "" && name != "default" && name != "acme-test" {
			environments = append(environments, map[string]any{"name": name, "path": f.state["env_path"], "keys": 0})
		}
		return map[string]any{"selected": f.state["environment"], "environments": environments}, nil
	case "environment_select", "environment_create":
		f.state["environment"] = args["name"]
		f.state["env_path"] = "/tmp/godmode-test/.env.godmode." + args["name"].(string)
		return f.state, nil
	case "doctor":
		return map[string]any{"ok": false, "checks": []any{map[string]any{"name": "Synthetic file", "status": "warn", "detail": "Missing example", "action": "godmode setup example"}}}, nil
	case "key_plan":
		return map[string]any{"id": "key-1", "name": args["name"], "title": "Example · API token", "visit": "Visit Example's token page", "page": "https://example.test/token", "steps": []string{"Make a token with **full scope**. Choose an expiration date."}, "prompt": "Paste your token:", "path": "/tmp/godmode-test/.env.godmode", "sealed": true, "saved": true, "lines": []int{4}}, nil
	case "key_check":
		v, _ := args["value"].(string)
		return map[string]any{"valid": v != "", "masked": "syn•••••key", "assignment": "EXAMPLE_TOKEN=sealed(syn•••••key)", "operation": "Replace", "path": "/tmp/godmode-test/.env.godmode", "notes": []string{}, "command": []string{"printf", "%s", "EXAMPLE_TOKEN=sealed(syn•••••key)"}}, nil
	case "key_save":
		f.saved = args["value"].(string)
		return map[string]any{"receipt": "Saved EXAMPLE_TOKEN=sealed(syn•••••key)"}, nil
	case "agents_plan":
		block := "<!-- godmode:start -->\nUse godmode help.\n<!-- godmode:end -->\n"
		if f.longAgent {
			block = strings.Repeat("One added instruction.\n", 80)
		}
		return map[string]any{"id": "agent-1", "block": block, "targets": []any{map[string]any{"name": "Example Agent", "path": "~/.example/AGENTS.md", "created": false, "added": false, "addition": "\n" + block}}}, nil
	case "agents_apply":
		return map[string]any{"added": []string{"~/.example/AGENTS.md"}}, nil
	case "faq":
		return map[string]any{"entries": []any{map[string]any{"title": "What is sealed(...)?", "paragraphs": []string{"Keys go straight to commands."}}}}, nil
	}
	return map[string]any{}, nil
}
func key(code rune, text string) tea.KeyPressMsg {
	return tea.KeyPressMsg(tea.Key{Code: code, Text: text})
}
func send(m model, msg tea.Msg) model { result, _ := m.Update(msg); return result.(model) }
func enter(m model) model             { return send(m, key(tea.KeyEnter, "")) }
func escape(m model) model            { return send(m, key(tea.KeyEscape, "")) }
func count(calls []string, name string) int {
	n := 0
	for _, call := range calls {
		if call == name {
			n++
		}
	}
	return n
}
func create(t *testing.T, backend *fakeBackend, route, arg string) model {
	t.Helper()
	m, e := newModel(backend, route, arg, Options{NoMotion: true})
	if e != nil {
		t.Fatal(e)
	}
	return m
}

func TestSectionExitFocusAndMenuState(t *testing.T) {
	m := create(t, fake(), "home", "")
	for _, test := range []struct {
		at   int
		page string
	}{{0, "business"}, {1, "providers"}, {2, "agents"}, {3, "environments"}, {6, "faq"}} {
		m.selected = test.at
		m = enter(m)
		if m.page != test.page {
			t.Fatalf("Enter opened %s, want %s", m.page, test.page)
		}
		m = escape(m)
		if m.page != "home" || m.selected != test.at {
			t.Fatal("section did not preserve home selection")
		}
	}
}
func TestPasteNeverSubmitsAndNeverAppearsUnmasked(t *testing.T) {
	f := fake()
	m := create(t, f, "set", "EXAMPLE_TOKEN")
	secret := "synthetic_private_credential_12345"
	m = send(m, tea.PasteMsg{Content: secret + "\r\n"})
	if count(f.calls, "key_save") != 0 {
		t.Fatal("paste saved a credential")
	}
	if strings.Contains(m.View().Content, secret) {
		t.Fatal("credential appeared in the view")
	}
	if !m.check.Valid || m.key.ID == "" {
		t.Fatal("key did not validate")
	}
	m = enter(m)
	if count(f.calls, "key_save") != 1 || f.saved != secret+"\r\n" {
		t.Fatal("explicit Enter did not save exact pending input")
	}
	if !m.quitting {
		t.Fatal("direct set should finish")
	}
}
func TestPastesDoNotEnterSearchNamesOrMenus(t *testing.T) {
	f := fake()
	m := create(t, f, "setup", "")
	secret := "synthetic_private_paste"
	m = send(m, tea.PasteMsg{Content: secret})
	if m.query != "" || m.text != "" || m.selected != 0 {
		t.Fatal("menu consumed paste")
	}
	m = send(m, key('/', "/"))
	m = send(m, tea.PasteMsg{Content: secret})
	if m.query != "" {
		t.Fatal("search consumed paste")
	}
	m.page = "name"
	m = send(m, tea.PasteMsg{Content: secret})
	if m.text != "" {
		t.Fatal("key name consumed paste")
	}
	if strings.Contains(m.View().Content, secret) {
		t.Fatal("paste was rendered")
	}
}
func TestTinyWindowCannotSaveKeyOrAcceptIntro(t *testing.T) {
	f := fake()
	m := create(t, f, "set", "EXAMPLE_TOKEN")
	m = send(m, tea.PasteMsg{Content: "synthetic_key"})
	m = send(m, tea.WindowSizeMsg{Width: 12, Height: 5})
	m = enter(m)
	if count(f.calls, "key_save") != 0 {
		t.Fatal("invisible key edit saved")
	}
	f.state["intro_seen"] = false
	m = create(t, f, "home", "")
	m = send(m, tea.WindowSizeMsg{Width: 20, Height: 5})
	m = enter(m)
	if count(f.calls, "accept_intro") != 0 {
		t.Fatal("hidden consequences accepted")
	}
}
func TestAgentAppendRequiresEveryPreviewLine(t *testing.T) {
	f := fake()
	f.longAgent = true
	m := create(t, f, "agents", "")
	m = send(m, tea.WindowSizeMsg{Width: 80, Height: 24})
	m = enter(m)
	if count(f.calls, "agents_apply") != 0 {
		t.Fatal("unreviewed append ran")
	}
	m = send(m, key(tea.KeyEnd, ""))
	m = enter(m)
	if count(f.calls, "agents_apply") != 0 {
		t.Fatal("jumping past unviewed lines unlocked append")
	}
	m = send(m, key(tea.KeyHome, ""))
	for i := 0; i < 30; i++ {
		m = send(m, key(tea.KeyPgDown, ""))
	}
	if m.reviewedUntil < len(m.agentLines()) {
		t.Fatalf("continuous paging did not review all lines: %d/%d", m.reviewedUntil, len(m.agentLines()))
	}
	m = enter(m)
	if count(f.calls, "agents_apply") != 1 {
		t.Fatal("reviewed append did not run")
	}
}
func TestViewsFitTerminalAndEscapeControlText(t *testing.T) {
	f := fake()
	f.state["profile"] = map[string]string{"name": "Alex\x1b]0;bad\a"}
	routes := []string{"home", "intro", "profile", "setup", "agents", "faq", "set"}
	for _, route := range routes {
		for _, size := range [][2]int{{8, 5}, {28, 12}, {40, 18}, {80, 24}, {110, 36}} {
			for _, dark := range []bool{false, true} {
				t.Run(fmt.Sprintf("%s-%dx%d-%v", route, size[0], size[1], dark), func(t *testing.T) {
					m := create(t, f, route, "EXAMPLE_TOKEN")
					m.dark = dark
					m = send(m, tea.WindowSizeMsg{Width: size[0], Height: size[1]})
					v := m.View().Content
					if strings.Contains(v, "\x1b]0;bad") {
						t.Fatal("control input reached terminal")
					}
					lines := strings.Split(v, "\n")
					if len(lines) > size[1] {
						t.Fatal("view exceeds height")
					}
					for _, line := range lines {
						if ansi.StringWidth(line) > size[0] {
							t.Fatalf("view exceeds width: %d", ansi.StringWidth(line))
						}
					}
				})
			}
		}
	}
}
func TestNoColorKeepsReadableWords(t *testing.T) {
	m := create(t, fake(), "home", "")
	m.colors = false
	v := m.View().Content
	if strings.Contains(v, "\x1b[") {
		t.Fatal("NO_COLOR view contains ANSI styles")
	}
	for _, word := range homeNames {
		if !strings.Contains(v, word) {
			t.Fatal("missing " + word)
		}
	}
}
func TestRemovedMusicDoesNotLaunch(t *testing.T) {
	f := fake()
	f.state["music_included"] = false
	m := create(t, f, "home", "")
	m.selected = 7
	m = enter(m)
	if errors.Is(m.outcome, ErrMusic) {
		t.Fatal("removed music launched")
	}
	if m.error == "" {
		t.Fatal("missing disabled music explanation")
	}
}

func TestNoMatchEnterDoesNotOpenCustomKey(t *testing.T) {
	f := fake()
	m := create(t, f, "setup", "")
	m = send(m, key('/', "/"))
	m = send(m, key('z', "zzz-no-provider"))
	m = enter(m)
	if m.page != "providers" || !m.filtering {
		t.Fatal("no-match Enter opened another action")
	}
	if count(f.calls, "key_plan") != 0 || count(f.calls, "open_url") != 0 {
		t.Fatal("no-match Enter called an operation")
	}
}
func TestCtrlDLeavesWithoutSaving(t *testing.T) {
	f := fake()
	m := create(t, f, "set", "EXAMPLE_TOKEN")
	m = send(m, tea.PasteMsg{Content: "synthetic_pending"})
	m = send(m, tea.KeyPressMsg(tea.Key{Code: 'd', Mod: tea.ModCtrl}))
	if m.outcome != ErrCancelled || !m.quitting || m.text != "" {
		t.Fatal("Ctrl-D did not cancel")
	}
	if count(f.calls, "key_save") != 0 {
		t.Fatal("Ctrl-D saved a credential")
	}
}
func TestSecondPasteReplacesTheExactCandidate(t *testing.T) {
	f := fake()
	m := create(t, f, "set", "EXAMPLE_TOKEN")
	m = send(m, tea.PasteMsg{Content: "synthetic_first"})
	m = send(m, tea.PasteMsg{Content: "synthetic_second"})
	m = enter(m)
	if f.saved != "synthetic_second" {
		t.Fatal("saved a stale or combined paste")
	}
}
func TestUnreadableProfileIsShownAndCannotWrite(t *testing.T) {
	f := fake()
	f.state["profile_error"] = "profile.json cannot be read."
	m := create(t, f, "profile", "")
	if !strings.Contains(ansi.Strip(m.View().Content), "profile.json cannot be read.") {
		t.Fatal("missing profile error")
	}
	m = enter(m)
	if m.page != "profile" || count(f.calls, "profile_save") != 0 {
		t.Fatal("unreadable profile entered a blank edit")
	}
}

func TestFailedBrowserOpenDoesNotClaimSuccess(t *testing.T) {
	f := fake()
	m := create(t, f, "set", "EXAMPLE_TOKEN")
	m = enter(m)
	if m.notice != "Open the link above." {
		t.Fatalf("wrong browser receipt: %q", m.notice)
	}
	if count(f.calls, "key_save") != 0 {
		t.Fatal("empty key saved")
	}
}

func TestEditedPasteKeepsOriginUntilCleared(t *testing.T) {
	m := create(t, fake(), "set", "EXAMPLE_TOKEN")
	m = send(m, tea.PasteMsg{Content: "synthetic_value"})
	m = send(m, key(tea.KeyBackspace, ""))
	if !m.fromPaste || m.pasted {
		t.Fatal("edited paste lost its privacy state")
	}
	m.text = "x"
	m.cursor = 1
	m = send(m, key(tea.KeyBackspace, ""))
	if m.fromPaste {
		t.Fatal("empty field retained paste state")
	}
}
func TestNoSearchResultsAllowExplicitRecovery(t *testing.T) {
	m := create(t, fake(), "setup", "")
	m = send(m, key('/', "/"))
	m = send(m, key('z', "zzzz"))
	m = enter(m)
	if m.page != "providers" {
		t.Fatal("failed search implicitly selected an action")
	}
	m = send(m, key(tea.KeyDown, ""))
	m = enter(m)
	if m.page != "name" {
		t.Fatal("Another key recovery is unreachable")
	}
}
func TestLinklessKeyHasNoOpenLinkHint(t *testing.T) {
	m := create(t, fake(), "set", "EXAMPLE_TOKEN")
	m.key.Page = ""
	if strings.Contains(strings.Join(m.footer(), "\n"), "open link") {
		t.Fatal("linkless field promises a link")
	}
}
func TestClippedPreviewShowsPosition(t *testing.T) {
	f := fake()
	f.longAgent = true
	m := create(t, f, "agents", "")
	if !strings.Contains(m.View().Content, "↓ more") {
		t.Fatal("hidden note has no scroll indicator")
	}
}

func TestFilteredProviderReturnKeepsSelection(t *testing.T) {
	m := create(t, fake(), "setup", "")
	extra := m.state.Providers[0]
	extra.ID = "another"
	extra.Name = "Another"
	m.state.Providers = append([]provider{extra}, m.state.Providers...)
	m.query = "example"
	m.selected = 0
	m = enter(m)
	m = escape(m)
	if m.page != "providers" || m.selected != 0 || m.query != "example" {
		t.Fatal("filtered provider selection lost")
	}
}
