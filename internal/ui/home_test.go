package ui

import (
	"encoding/json"
	"os"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"
)

func dashboardFixture(t *testing.T) *fakeBackend {
	t.Helper()
	raw, err := os.ReadFile("../../providers.json")
	if err != nil {
		t.Fatal(err)
	}
	var catalog []provider
	if err := json.Unmarshal(raw, &catalog); err != nil {
		t.Fatal(err)
	}
	f := fake()
	f.state["providers"] = catalog
	f.state["context"] = "studio"
	f.state["environment"] = "preview"
	f.state["fields"] = []field{
		{Name: "business_name", Label: "Brand name", Example: "Acme Studio"},
		{Name: "website", Label: "Website", Example: "https://example.com"},
		{Name: "public_email", Label: "Public email"},
		{Name: "legal_name", Label: "Legal name"},
		{Name: "business_mailing_address", Label: "Mailing address"},
		{Name: "operator_name", Label: "Your name"},
	}
	f.state["profile"] = map[string]string{"business_name": "Cedar Studio", "website": "https://cedar.example", "business_mailing_address": "14 Cedar Street\nMadison, WI"}
	f.state["states"] = map[string]string{"STRIPE_TEST_SECRET_KEY": "set", "GMAIL_APP_PASSWORD": "set", "MY_CUSTOM_KEY": "set"}
	return f
}

func TestDashboardUsesRealCatalogAndKeepsIdentityAtEverySize(t *testing.T) {
	m := create(t, dashboardFixture(t), "home", "")
	for _, size := range [][2]int{{40, 18}, {80, 24}, {120, 36}} {
		m = send(m, tea.WindowSizeMsg{Width: size[0], Height: size[1]})
		view := ansi.Strip(m.View().Content)
		for _, want := range []string{"Loadout", "Cedar Studio", "Keys preview", "Profile studio", "Saved · test", "Add key", "Providers", "Profile", "Tab section"} {
			if !strings.Contains(view, want) {
				t.Fatalf("%dx%d lacks %q:\n%s", size[0], size[1], want, view)
			}
		}
		for _, pr := range m.state.Providers {
			if !strings.Contains(view, pr.Name) {
				t.Fatalf("%dx%d hides %s:\n%s", size[0], size[1], pr.Name, view)
			}
		}
		if size[0] >= 80 {
			for _, want := range []string{"Brand name", "Website", "https://cedar.example", "Mailing address", "Agent instructions", "MY_CUSTOM_KEY"} {
				if !strings.Contains(view, want) {
					t.Fatalf("%dx%d hides %s:\n%s", size[0], size[1], want, view)
				}
			}
		} else if !strings.Contains(view, "1/14") {
			t.Fatalf("narrow view hides its longer provider list: %s", view)
		}
		if strings.Contains(view, "STRIPE_TEST_SECRET_KEY") {
			t.Fatal("Home exposed an internal provider field instead of its mode")
		}
	}
}

func TestDashboardSaveRestoresProviderAfterItMoves(t *testing.T) {
	f := dashboardFixture(t)
	m := create(t, f, "home", "")
	start := homeItemIndex(t, m, "Cloudflare")
	m = openHomeItem(t, m, "Cloudflare")
	if m.page != "key" || m.key.Name != "CLOUDFLARE_API_TOKEN" {
		t.Fatalf("Cloudflare opened %s, %s", m.page, m.key.Name)
	}
	m = send(m, tea.PasteMsg{Content: "dummy-dashboard-only"})
	// The real backend returns a fresh state after writing. Reproduce the move
	// from available to saved without accessing any local credentials.
	f.state["states"].(map[string]string)["CLOUDFLARE_API_TOKEN"] = "set"
	m = enter(m)
	item, _ := m.homeSelection()
	if m.page != "home" || item.name != "Cloudflare" || item.status != "Saved" || m.selected == start {
		t.Fatalf("save restored position instead of identity: %s %v", m.page, item)
	}
	if strings.Contains(ansi.Strip(m.View().Content), "dummy-dashboard-only") || strings.Contains(m.notice, "••") {
		t.Fatal("Home rendered a credential or masked preview")
	}
	m = openHomeItem(t, m, "Website")
	m = send(m, tea.PasteMsg{Content: "https://new.example"})
	f.state["profile"].(map[string]string)["website"] = "https://new.example"
	m = enter(m)
	item, _ = m.homeSelection()
	if m.page != "home" || item.name != "Website" || item.status != "https://new.example" {
		t.Fatalf("profile save lost its field: %s %+v", m.page, item)
	}
}

func TestDashboardNarrowSectionsAndCustomKeys(t *testing.T) {
	m := create(t, dashboardFixture(t), "home", "")
	m = send(m, tea.WindowSizeMsg{Width: 40, Height: 18})
	m = send(m, key(tea.KeyTab, ""))
	if view := ansi.Strip(m.View().Content); !strings.Contains(view, "[Profile]") || !strings.Contains(view, "❯ Brand name") {
		t.Fatal(view)
	}
	m = send(m, key(tea.KeyTab, ""))
	if item, _ := m.homeSelection(); item.kind != "agents" {
		t.Fatal(item)
	}
	m = openHomeItem(t, m, "MY_CUSTOM_KEY")
	if m.page != "key" || m.key.Name != "MY_CUSTOM_KEY" {
		t.Fatal("custom key did not open its editor")
	}
	m = escape(m)
	if item, _ := m.homeSelection(); m.page != "home" || item.name != "MY_CUSTOM_KEY" || !strings.Contains(ansi.Strip(m.View().Content), "2/14") {
		t.Fatalf("custom key lost focus: %v", item)
	}
	m = openHomeItem(t, m, "Stripe")
	if m.page != "provider_keys" {
		t.Fatalf("Stripe skipped mode selection: %s", m.page)
	}
	m = escape(m)
	if item, _ := m.homeSelection(); item.name != "Stripe" {
		t.Fatalf("Stripe lost focus: %v", item)
	}
}

func TestDashboardDistinguishesLocalStates(t *testing.T) {
	m := create(t, dashboardFixture(t), "home", "")
	pr := provider{ID: "example", Key: []providerKey{{Name: "A"}, {Name: "B"}}}
	for _, test := range []struct{ a, b, want string }{
		{"", "", "Add key"}, {"blank", "empty", "Add key"}, {"set", "", "1/2 keys"}, {"set", "set", "Saved"}, {"set", "duplicate", "Needs repair"}, {"malformed", "", "Needs repair"},
	} {
		m.state.States = map[string]string{"A": test.a, "B": test.b}
		if got, _ := m.providerStatus(pr); got != test.want {
			t.Errorf("%q, %q produced %q", test.a, test.b, got)
		}
	}
	m.state.StoreError = "unreadable store"
	if got, _ := m.providerStatus(pr); got != "Unreadable" {
		t.Error(got)
	}
}

func TestEditorsIdentifyResolvedProfileAndKeepNamedContext(t *testing.T) {
	m := create(t, dashboardFixture(t), "home", "")
	for _, test := range []struct {
		context, brand, want string
	}{
		{"", "", "Profile: preview"},
		{"", "Cedar Studio", "Profile: Cedar Studio"},
		{"client", "", "Profile: client"},
		{"client", "Cedar Studio", "Profile: client · Cedar Studio"},
	} {
		m.state.Context, m.state.Profile["business_name"] = test.context, test.brand
		view := ansi.Strip(strings.Join(m.scopeLines(), "\n"))
		if !strings.Contains(view, "Keys: preview") || !strings.Contains(view, test.want) {
			t.Fatalf("scope lost its real profile: %s", view)
		}
	}
}

func TestDashboardAgentFileStatusAndFirstKeyInstruction(t *testing.T) {
	f := dashboardFixture(t)
	f.state["states"] = map[string]string{}
	m := create(t, f, "home", "")
	for _, size := range [][2]int{{40, 18}, {80, 24}} {
		m = send(m, tea.WindowSizeMsg{Width: size[0], Height: size[1]})
		view := ansi.Strip(m.View().Content)
		if !strings.Contains(view, "0 files") || !strings.Contains(view, "then paste") {
			t.Fatalf("empty Home lost agent status or its first step: %s", view)
		}
	}
	m.state.Progress.ByHand = true
	if m.agentNoteStatus(false) != "Marked by hand" {
		t.Fatal("a manual marker advertised an installed instruction file")
	}
	m.state.Progress.Agents = []string{"Claude Code"}
	if m.agentNoteStatus(false) != "Claude Code · 1 file" {
		t.Fatal("the agent file with an existing instruction block wasn't counted")
	}
	m.state.Progress.Agents = append(m.state.Progress.Agents, "Codex")
	if m.agentNoteStatus(true) != "Claude Code +1" || m.agentNoteStatus(false) != "Claude Code +1 · 2 files" {
		t.Fatal("multiple agent files lost their identity or count")
	}
	m.state.Progress.Errors = []string{"agents"}
	if m.agentNoteStatus(false) != "Unreadable" {
		t.Fatal("unreadable files appeared checked")
	}
}

func TestInstructionsGiveAnExampleForTheSelectedLoadout(t *testing.T) {
	m := create(t, dashboardFixture(t), "agents", "")
	if !strings.Contains(ansi.Strip(m.View().Content), "Stripe account") {
		t.Fatal("chooser lacks a task for the saved provider")
	}
	m = enter(m)
	if !strings.Contains(ansi.Strip(m.View().Content), "Stripe account") {
		t.Fatal("copy page lacks the concrete task")
	}
}
