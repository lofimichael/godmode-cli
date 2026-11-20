package ui

import (
	"fmt"
	"reflect"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
)

func typeText(m model, text string) model {
	for _, character := range text {
		m = send(m, key(character, string(character)))
	}
	return m
}

func TestNavigationOrderKeepsTaskActionsBeforeSettings(t *testing.T) {
	wantSettings := []string{"Motion", "Check local files", "Update Godmode", "Replay intro", "Back"}
	m := create(t, fake(), "home", "")
	if !reflect.DeepEqual(settingsNames, wantSettings) || m.choiceNames()[0] != "Example" {
		t.Fatal("Home must start with the provider inventory")
	}
	if homeItemIndex(t, m, "Agent instructions") > homeItemIndex(t, m, "Settings") {
		t.Fatal("Agent instructions should precede settings")
	}
}

func TestEverySwitchEntryStagesUntilOneAtomicApply(t *testing.T) {
	for _, route := range []string{"home", "shortcut", "finder"} {
		t.Run(route, func(t *testing.T) {
			f := fake()
			m := create(t, f, "home", "")
			switch route {
			case "home":
				m = openHomeItem(t, m, "Switch loadout")
			case "shortcut":
				m = send(m, key('s', "s"))
			case "finder":
				m = findAction(t, m, "switch loadout")
			}
			if m.page != "active" || !m.draftOpen || m.draftEnvironment != "default" || m.draftContext != "" {
				t.Fatal("Switch loadout did not start with a complete draft of the active pair")
			}
			m = enter(m)
			m.selected = 1
			m = enter(m)
			if m.page != "active" || m.draftEnvironment != "acme-test" {
				t.Fatal("environment did not return as a draft")
			}
			m.selected = 1
			m = enter(m)
			m.selected = 2
			m = enter(m)
			if m.page != "active" || m.draftContext != "acme" {
				t.Fatal("business did not return as a draft")
			}
			if m.state.Environment != "default" || m.state.Context != "" || f.state["environment"] != "default" || f.state["context"] != "" {
				t.Fatal("staging changed the active selection")
			}
			for _, action := range []string{"environment_select", "context_select", "selection_save"} {
				if count(f.calls, action) != 0 {
					t.Fatal("staging called " + action)
				}
			}
			m.selected = 2
			m = enter(m)
			if m.state.Environment != "acme-test" || m.state.Context != "acme" || m.draftOpen || count(f.calls, "selection_save") != 1 {
				t.Fatal("Use this loadout did not apply the complete pair exactly once")
			}
			for i, action := range f.calls {
				if action == "selection_save" && (f.requests[i]["environment"] != "acme-test" || f.requests[i]["context"] != "acme") {
					t.Fatal("atomic apply omitted or changed one selection")
				}
			}
		})
	}
}

func TestCancelStagedSetupLeavesSavedSelectionAndDirectSelectionWorking(t *testing.T) {
	for _, cancel := range []string{"escape", "back", "quit"} {
		t.Run(cancel, func(t *testing.T) {
			f := fake()
			m := create(t, f, "home", "")
			m = openHomeItem(t, m, "Switch loadout")
			m = enter(m)
			m.selected = 1
			m = enter(m)
			switch cancel {
			case "escape":
				m = escape(m)
			case "back":
				m.selected = 3
				m = enter(m)
			case "quit":
				m = send(m, tea.KeyPressMsg(tea.Key{Code: 'c', Mod: tea.ModCtrl}))
			}
			if f.state["environment"] != "default" || f.state["context"] != "" || count(f.calls, "selection_save") != 0 || count(f.calls, "environment_select") != 0 {
				t.Fatal("cancelled setup saved a staged value")
			}
			if cancel == "quit" {
				if !m.quitting {
					t.Fatal("Ctrl-C did not quit from Switch loadout")
				}
				return
			}
			if m.page != "home" || m.selected != homeItemIndex(t, m, "Switch loadout") || m.draftOpen {
				t.Fatal("cancel lost the actual parent or retained a live draft")
			}
			m = findAction(t, m, "key environments")
			m.selected = 1
			m = enter(m)
			if m.state.Environment != "acme-test" || count(f.calls, "environment_select") != 1 || m.page != "actions" {
				t.Fatal("cancelled draft leaked into a later direct environment selection")
			}
		})
	}
}

func TestNewEnvironmentWithinSwitchDoesNotSelectBeforeApply(t *testing.T) {
	f := fake()
	m := create(t, f, "home", "")
	m = openHomeItem(t, m, "Switch loadout")
	m = enter(m)
	m.selected = len(m.environments)
	m = enter(m)
	m = enter(m) // New empty environment.
	m = typeText(m, "quest-test")
	m = enter(m)
	if count(f.calls, "environment_create") != 1 || m.page != "environments" || m.draftEnvironment != "quest-test" {
		t.Fatal("new environment did not return to its staged list")
	}
	for i, action := range f.calls {
		if action == "environment_create" && f.requests[i]["select"] != false {
			t.Fatal("create implicitly selected the new environment")
		}
	}
	if m.state.Environment != "default" || f.state["environment"] != "default" || count(f.calls, "selection_save") != 0 {
		t.Fatal("creating a staged environment changed the saved selection")
	}
	m = escape(m)
	if m.page != "active" {
		t.Fatal("new environment lost Switch loadout as its parent")
	}
	m = escape(m)
	if count(f.calls, "selection_save") != 0 || count(f.calls, "key_save") != 0 {
		t.Fatal("cancel wrote setup or keys")
	}
}

func TestFinderLoadoutDoesNotReopenAStaleCreationForm(t *testing.T) {
	f := fake()
	m := openHomeItem(t, create(t, f, "home", ""), "Switch loadout")
	m = enter(m)
	m.selected = len(m.environments)
	m = enter(m)
	for _, letter := range "sq" {
		m = send(m, key(letter, string(letter)))
	}
	if m.quitting || m.page != "environment_new" {
		t.Fatal("a Home shortcut interrupted environment creation")
	}
	m = findAction(t, m, "switch loadout")
	m = enter(m)
	m.selected = 1
	m = enter(m)
	m.selected = 1
	m = enter(m)
	last := len(f.calls) - 1
	if f.calls[last] != "context_list" || f.requests[last]["environment"] != "acme-test" {
		t.Fatal("profile picker requested Automatic for the active environment instead of the draft")
	}
	m.selected = 2
	m = enter(m)
	m.selected = 2
	m = enter(m)
	m = escape(m) // Return from the finder after applying a different loadout.
	if m.page != "active" || !m.draftOpen || m.draftEnvironment != "acme-test" || m.draftContext != "acme" {
		t.Fatal("finder restored a creation form from the superseded loadout")
	}
	m = escape(m)
	if m.page != "home" || m.draftOpen || count(f.calls, "selection_save") != 1 {
		t.Fatal("a stale form survived the completed switch")
	}
}

func TestFinderRoundTripRestoresQuerySelectionAndActualParent(t *testing.T) {
	m := create(t, fake(), "setup", "")
	m = send(m, key('/', "/"))
	m = typeText(m, "example")
	m = enter(m)
	m = escape(m)
	if m.page != "providers" || m.query != "example" {
		t.Fatal("provider query did not survive its key form")
	}
	m = findAction(t, m, "settings")
	if m.page != "settings" {
		t.Fatal("finder did not open Settings")
	}
	m.selected = 2
	m = enter(m)
	if m.page != "update" || m.quitting {
		t.Fatal("Settings did not show update confirmation")
	}
	m = escape(m)
	if m.page != "settings" || m.selected != 2 {
		t.Fatal("update returned to an inferred parent instead of Settings")
	}
	m = escape(m)
	if m.page != "actions" || m.query != "settings" || m.selected != 0 {
		t.Fatal("finder result lost its original query or selection")
	}
	m = escape(m)
	if m.page != "providers" || m.query != "example" || m.selected != 0 || m.quitting {
		t.Fatal("finder did not restore its actual provider parent")
	}
}

func TestScopeDetailsBackPreservesInspectedList(t *testing.T) {
	f := fake()
	m := create(t, f, "home", "")
	m = openHomeItem(t, m, "Switch loadout")
	m = enter(m)
	m.selected = 1
	m = send(m, key(tea.KeyTab, ""))
	if m.page != "scope_details" {
		t.Fatal("Tab did not open inspected environment details")
	}
	m = escape(m)
	if m.page != "environments" || m.selected != 1 || count(f.calls, "environment_select") != 0 {
		t.Fatal("details Back lost list selection or selected the environment")
	}
	m = send(m, key(tea.KeyTab, ""))
	m = enter(m)
	if m.page != "active" || m.draftEnvironment != "acme-test" || m.state.Environment != "default" {
		t.Fatal("details Enter did not stage exactly the inspected environment")
	}
}

func TestTextShortcutsStayTextInSearchAndInput(t *testing.T) {
	for _, page := range []string{"providers", "actions", "key", "profile_field", "name", "scope_name"} {
		t.Run(page, func(t *testing.T) {
			f := fake()
			m := create(t, f, "home", "")
			switch page {
			case "providers":
				m = create(t, f, "loadout", "")
				m = send(m, key('/', "/"))
			case "actions":
				m = send(m, tea.KeyPressMsg(tea.Key{Code: 'k', Mod: tea.ModCtrl}))
			case "key":
				m = create(t, f, "set", "EXAMPLE_TOKEN")
			case "profile_field":
				m = openHomeItem(t, m, "Name")
			case "name":
				m = create(t, f, "loadout", "")
				m.selected = len(m.providerMatches())
				m = enter(m)
			case "scope_name":
				m = findAction(t, m, "key environments")
				m.selected = len(m.environments)
				m = enter(enter(m))
			}
			m = typeText(m, "qs?/")
			value := m.text
			if page == "providers" || page == "actions" {
				value = m.query
			}
			if m.page != page || m.quitting || value != "qs?/" {
				t.Fatalf("shortcuts interrupted %s input", page)
			}
			if count(f.calls, "key_save") != 0 || count(f.calls, "selection_save") != 0 {
				t.Fatal("typing performed a write")
			}
		})
	}
}

func TestCancelKeyFromDirectAndFinderRoutesNeverWrites(t *testing.T) {
	for _, route := range []string{"set", "setup", "finder"} {
		t.Run(route, func(t *testing.T) {
			f := fake()
			var m model
			switch route {
			case "set":
				m = create(t, f, "set", "EXAMPLE_TOKEN")
			case "setup":
				m = create(t, f, "setup", "example")
			case "finder":
				m = create(t, f, "home", "")
				m = findAction(t, m, "example")
			}
			m = send(m, tea.PasteMsg{Content: "synthetic_cancel_candidate"})
			m = escape(m)
			if count(f.calls, "key_save") != 0 || f.saved != "" || m.text != "" || strings.Contains(m.View().Content, "synthetic_cancel_candidate") {
				t.Fatal("cancel saved or retained the pending secret")
			}
			switch route {
			case "set":
				if !m.quitting {
					t.Fatal("direct set cancel did not return to terminal")
				}
			case "setup":
				if m.page != "providers" || m.selected != 0 {
					t.Fatal("direct provider cancel lost provider parent")
				}
			case "finder":
				if m.page != "actions" || m.query != "example" {
					t.Fatal("finder provider cancel lost query")
				}
			}
		})
	}
}

func TestSettingsMotionPersistsPreferenceButCommandOverrideDoesNot(t *testing.T) {
	for _, forced := range []bool{false, true} {
		t.Run(map[bool]string{false: "saved", true: "command-override"}[forced], func(t *testing.T) {
			f := fake()
			m, err := newModel(f, "home", "", Options{NoMotion: forced})
			if err != nil {
				t.Fatal(err)
			}
			m = openHomeItem(t, m, "Settings")
			m = enter(m)
			if !m.opts.NoMotion {
				t.Fatal("Motion did not remain disabled")
			}
			writes := count(f.calls, "preferences_save")
			if forced && writes != 0 {
				t.Fatal("command override changed the saved preference")
			}
			if !forced && writes != 1 {
				t.Fatal("Motion choice did not persist exactly once")
			}
			if count(f.calls, "key_save") != 0 {
				t.Fatal("appearance change wrote keys")
			}
		})
	}
}

func TestShortcutHelpAndFinderPreserveTheirActualParent(t *testing.T) {
	f := fake()
	m := create(t, f, "home", "")
	m = openHomeItem(t, m, "Settings")
	m.selected = 3
	m = send(m, key('?', "?"))
	if m.page != "shortcuts" || !strings.Contains(strings.Join(m.body(), "\n"), "Ctrl-K") {
		t.Fatal("question mark did not expose keyboard help")
	}
	m = escape(m)
	if m.page != "settings" || m.selected != 3 {
		t.Fatal("keyboard help lost its actual parent")
	}
	m = send(m, key('/', "/"))
	if m.page != "actions" {
		t.Fatal("slash outside providers did not open the finder")
	}
	m = typeText(m, "help")
	m = enter(m)
	if m.page != "faq" {
		t.Fatal("finder did not open Help")
	}
	m = escape(m)
	if m.page != "actions" || m.query != "help" {
		t.Fatal("Help did not restore its finder query")
	}
	m = escape(m)
	if m.page != "settings" || m.selected != 3 {
		t.Fatal("finder lost its Settings origin")
	}
	m = send(m, key('q', "q"))
	if m.quitting || m.page != "settings" {
		t.Fatal("q quit a nested menu")
	}
	m = escape(m)
	m = send(m, key('q', "q"))
	if !m.quitting || count(f.calls, "accept_intro") != 0 || count(f.calls, "key_save") != 0 {
		t.Fatal("q did not quit the menu without executing its focused action")
	}
}

func TestCopyingTaskNoteDoesNotUnlockAgentAppend(t *testing.T) {
	f := fake()
	f.longAgent = true
	m := create(t, f, "agents", "")
	m = enter(m)
	if m.page != "agent_copy" {
		t.Fatal("first Agent instructions choice did not open the copy note")
	}
	m = send(m, key(tea.KeyEnd, ""))
	m = enter(m)
	if count(f.calls, "copy_agent") != 1 || count(f.calls, "agents_apply") != 0 {
		t.Fatal("copy action appended instructions or failed to copy")
	}
	m = escape(m)
	m = openAgentDiff(t, m)
	m = enter(m)
	if count(f.calls, "agents_apply") != 0 || m.reviewedUntil >= len(m.agentLines()) {
		t.Fatal("viewing a separate task note unlocked an unreviewed file append")
	}
	m = escape(m)
	if m.page != "agent_targets" || m.selected != 0 {
		t.Fatal("cancelled diff lost the chosen agent")
	}
	m = escape(m)
	if m.page != "agent_home" || m.selected != 1 {
		t.Fatal("agent chooser lost the Agent instructions choice")
	}
}

func TestAgentAppendUsesOnlyTheReviewedTargetSelection(t *testing.T) {
	for _, choice := range []string{"single", "all", "already-added"} {
		t.Run(choice, func(t *testing.T) {
			f := fake()
			f.agentTargets = []target{
				{Name: "First agent", Path: "~/.first/AGENTS.md", Real: "/tmp/godmode-test/.first/AGENTS.md", Addition: "\nUse godmode help.\n"},
				{Name: "Second agent", Path: "~/.second/AGENTS.md", Real: "/tmp/godmode-test/.second/AGENTS.md", Addition: "\nUse godmode help.\n"},
			}
			if choice == "already-added" {
				f.agentTargets[1].Added = true
			}
			m := create(t, f, "agents", "")
			m.selected = 1
			m = enter(m)
			if m.page != "agent_targets" || count(f.calls, "agents_apply") != 0 {
				t.Fatal("Add to agent files skipped agent selection")
			}
			m.selected = 1
			m = enter(m)
			if choice == "all" {
				// A previous single selection must not leak into the explicit All choice.
				m = escape(m)
				m.selected = len(m.agents.Targets)
				m = enter(m)
			}
			preview := strings.Join(m.agentLines(), "\n")
			if !strings.Contains(preview, "~/.second/AGENTS.md") {
				t.Fatal("preview omits the chosen agent file")
			}
			if choice != "all" && strings.Contains(preview, "~/.first/AGENTS.md") {
				t.Fatal("single-agent preview includes an unrelated file")
			}
			if choice == "all" && !strings.Contains(preview, "~/.first/AGENTS.md") {
				t.Fatal("All preview omits an included file")
			}
			for step := 0; step < 30; step++ {
				m = send(m, key(tea.KeyPgDown, ""))
			}
			m = enter(m)
			if choice == "already-added" {
				if count(f.calls, "agents_apply") != 0 {
					t.Fatal("already-added selection fell through to another agent")
				}
				return
			}
			if count(f.calls, "agents_apply") != 1 {
				t.Fatal("reviewed selection did not append once")
			}
			for i, call := range f.calls {
				if call != "agents_apply" {
					continue
				}
				selected, present := f.requests[i]["targets"]
				if choice == "single" && (!present || !reflect.DeepEqual(selected, []string{"~/.second/AGENTS.md"})) {
					t.Fatal("single-agent append broadened or changed its reviewed target")
				}
				if choice == "all" && present {
					t.Fatal("All choice retained a stale single-agent restriction")
				}
			}
			if m.page != "agent_home" || m.quitting {
				t.Fatal("append did not return to the connection chooser")
			}
		})
	}
}

func TestFinderRestoresProviderIdentityBeforeOpeningAKey(t *testing.T) {
	f := fake()
	f.state["providers"] = []provider{
		{ID: "alpha", Name: "Alpha", Key: []providerKey{{Name: "ALPHA_ONE"}, {Name: "ALPHA_TWO"}}},
		{ID: "beta", Name: "Beta", Key: []providerKey{{Name: "BETA_ONE"}, {Name: "BETA_TWO"}}},
	}
	m := create(t, f, "setup", "alpha")
	m.selected = 1
	m = findAction(t, m, "beta")
	if m.page != "provider_keys" || m.selectedProvider.ID != "beta" {
		t.Fatal("finder did not reach the second provider")
	}
	m = escape(escape(m))
	if m.page != "provider_keys" || m.selected != 1 || m.providerAt != 0 || m.selectedProvider.ID != "alpha" {
		t.Fatal("Back restored the row but not its original provider")
	}
	m = enter(m)
	if m.key.Name != "ALPHA_TWO" || m.keyReturn != "provider_keys" {
		t.Fatal("restored provider row opened a different provider's key")
	}
	if count(f.calls, "key_save") != 0 {
		t.Fatal("navigation wrote a key")
	}
}

type navigationBackend struct {
	*fakeBackend
	planNumber int
	validPlan  string
	failPlan   bool
}

func (b *navigationBackend) Call(action string, args map[string]any) (map[string]any, error) {
	reply, err := b.fakeBackend.Call(action, args)
	if err != nil {
		return nil, err
	}
	switch action {
	case "faq":
		return map[string]any{"entries": []faqEntry{{Title: "First answer", Paragraphs: []string{"First text"}}, {Title: "Second answer", Paragraphs: []string{"Second text"}}}}, nil
	case "agents_plan":
		if b.failPlan {
			return nil, fmt.Errorf("synthetic plan read failed")
		}
		b.planNumber++
		b.validPlan = fmt.Sprintf("plan-%d", b.planNumber)
		reply["id"] = b.validPlan
		reply["copy_block"] = fmt.Sprintf("Task scope: %s / %s", b.state["environment"], b.state["context"])
	case "selection_save", "environment_select", "context_select":
		b.validPlan = "" // The real backend invalidates even an unchanged pair.
	case "copy_agent", "agents_apply":
		if b.validPlan == "" || args["id"] != b.validPlan {
			return nil, fmt.Errorf("stale synthetic agent plan")
		}
	}
	return reply, nil
}

func TestFinderRestoresFAQAndScopeDetailContext(t *testing.T) {
	b := &navigationBackend{fakeBackend: fake()}
	m := asyncModel(t, b, "faq", "")
	m = enter(m)
	m = findAction(t, m, "help")
	m.selected = 1
	m = enter(m)
	m = escape(escape(escape(m)))
	if m.page != "faq_text" || m.faqAt != 0 || !strings.Contains(strings.Join(m.body(), "\n"), "First text") {
		t.Fatal("nested Help replaced the original answer")
	}

	m = asyncModel(t, b, "home", "")
	m = findAction(t, m, "key environments")
	m.selected = 1
	m = send(m, key(tea.KeyTab, ""))
	m = findAction(t, m, "business profiles")
	m.selected = 2
	m = send(m, key(tea.KeyTab, ""))
	m = escape(escape(escape(m)))
	if m.page != "scope_details" || m.scopeReturn != "environments" || m.selected != 1 {
		t.Fatal("nested business details replaced the inspected environment")
	}
	m = enter(m)
	if m.state.Environment != "acme-test" || m.state.Context != "" || count(b.calls, "context_select") != 0 {
		t.Fatal("restored environment details applied a business selection")
	}
}

func TestRecentDetailBackKeepsReviewedPairAcrossDetoursAndReordering(t *testing.T) {
	f := fake()
	first := setupPair{"default", ""}
	second := setupPair{"acme-test", "acme"}
	f.state["recent_setups"] = []setupPair{first, second}
	m := create(t, f, "home", "")
	m = findAction(t, m, "recent loadouts")
	m.selected = 0
	m = enter(m)
	m = findAction(t, m, "recent loadouts")
	m.selected = 1
	m = enter(m)
	m = escape(escape(m))
	// Another applied pair can reorder history while an older detail is hidden.
	m.state.RecentSetups = []setupPair{second, first}
	m = escape(m)
	if m.page != "recent_details" || m.recentAt != 1 || m.state.RecentSetups[m.recentAt] != first {
		t.Fatal("Back restored a recent-history index instead of the reviewed pair")
	}
	if count(f.calls, "selection_save") != 0 {
		t.Fatal("browsing recent details applied a pair")
	}
	m = send(m, key('?', "?"))
	m.state.RecentSetups = []setupPair{second}
	m = escape(m)
	if m.page != "recent_setups" {
		t.Fatal("missing reviewed pair silently selected a different detail")
	}
}

func TestAgentReturnReloadsScopeAndRetainsOnlyTheChosenTarget(t *testing.T) {
	for _, change := range []string{"same-pair", "different-pair", "target-removed", "all", "read-failure", "copy"} {
		t.Run(change, func(t *testing.T) {
			f := fake()
			f.longAgent = true
			f.agentTargets = []target{
				{Name: "First", Path: "~/.first/AGENTS.md", Addition: "\nInstructions\n"},
				{Name: "Second", Path: "~/.second/AGENTS.md", Addition: "\nInstructions\n"},
			}
			b := &navigationBackend{fakeBackend: f}
			m := asyncModel(t, b, "agents", "")
			if change == "copy" {
				m = enter(m)
			} else {
				m = openAgentDiff(t, m)
				if change == "all" {
					m = escape(m)
					m.selected = len(m.agents.Targets)
					m = enter(m)
				}
				for i := 0; i < 30; i++ {
					m = send(m, key(tea.KeyPgDown, ""))
				}
			}
			oldID := m.agents.ID
			m = findAction(t, m, "switch loadout")
			if change != "same-pair" {
				m = enter(m)
				m.selected = 1
				m = enter(m)
			}
			if change == "target-removed" {
				f.agentTargets = f.agentTargets[1:]
			}
			b.failPlan = change == "read-failure"
			m.selected = 2
			m = enter(m)
			m = escape(m) // Leave the finder and restore the original agent route.
			if change != "same-pair" && (m.state.Environment != "acme-test" || f.state["environment"] != "acme-test") {
				t.Fatal("agent readback changed or rolled back the applied setup")
			}
			if count(f.calls, "selection_save") != 1 || count(f.calls, "agents_plan") != 2 || count(f.calls, "agents_apply") != 0 {
				t.Fatal("return did not reload once after the atomic selection, or appended implicitly")
			}
			if change == "target-removed" || change == "all" || change == "read-failure" {
				if m.page != "agent_home" || m.agentOnly != "" {
					t.Fatal("invalid old review did not fall back to Agent instructions")
				}
				if change == "read-failure" && (m.agents.ID != "" || !strings.Contains(m.error, "synthetic plan read failed")) {
					t.Fatal("failed read retained stale agent instructions or hid the failure")
				}
				return
			}
			if m.agents.ID == oldID || m.agents.ID != b.validPlan {
				t.Fatal("return retained an invalidated backend plan")
			}
			if change == "copy" {
				if m.page != "agent_copy" || !strings.Contains(m.agents.CopyBlock, "acme-test") {
					t.Fatal("task copy retained the old setup")
				}
				m = enter(m)
				if strings.Contains(m.error, "stale") || count(f.calls, "copy_agent") != 1 {
					t.Fatal("task copy used the invalidated plan")
				}
				return
			}
			if m.page != "agents" || m.agentOnly != "~/.first/AGENTS.md" || len(m.reviewTargets()) != 1 || m.scroll != 0 {
				t.Fatal("return broadened or lost the chosen target")
			}
			m = enter(m)
			if count(f.calls, "agents_apply") != 0 {
				t.Fatal("old review progress unlocked the refreshed diff")
			}
			for i := 0; i < 30; i++ {
				m = send(m, key(tea.KeyPgDown, ""))
			}
			m = enter(m)
			for i, action := range f.calls {
				if action == "agents_apply" && !reflect.DeepEqual(f.requests[i]["targets"], []string{"~/.first/AGENTS.md"}) {
					t.Fatal("reviewed single-target return applied to other agents")
				}
			}
			if count(f.calls, "agents_apply") != 1 {
				t.Fatal("freshly reviewed plan did not apply")
			}
		})
	}
}

func TestAgentBackReloadRunsOutsideTheInputLoop(t *testing.T) {
	f := fake()
	m := create(t, f, "agents", "")
	m = enter(m)
	m = send(m, tea.KeyPressMsg(tea.Key{Code: 'k', Mod: tea.ModCtrl}))
	b := newGatedBackend(t, "agents_plan")
	b.base = f
	m.backend = b
	m, cmd := updateAsync(m, key(tea.KeyEscape, ""))
	if !m.busy || m.page != "actions" || b.count("agents_plan") != 0 {
		t.Fatal("Esc blocked the input loop on agent readback")
	}
	result := runAsyncWorker(t, b, asyncWorker(t, cmd))
	m, _ = updateAsync(m, tea.WindowSizeMsg{Width: 100, Height: 30})
	if m.View().Content == "" || m.width != 100 {
		t.Fatal("agent readback blocked resize or rendering")
	}
	b.unblock()
	m, _ = updateAsync(m, asyncResult(t, result))
	if m.busy || m.page != "agent_copy" || b.count("agents_plan") != 1 {
		t.Fatal("async readback did not restore the task-copy route")
	}
}

func TestNavigationHistoryDoesNotCaptureInputsOrCredentialPreviews(t *testing.T) {
	f := fake()
	m := create(t, f, "set", "EXAMPLE_TOKEN")
	m = send(m, tea.PasteMsg{Content: "synthetic_history_secret"})
	m.check.Masked = "synthetic_sensitive_preview"
	m.key.Note = "synthetic_sensitive_guidance"
	m.remember(m.location())
	stored := fmt.Sprintf("%+v", m.trail)
	for _, private := range []string{m.text, m.check.Masked, m.key.Note} {
		if strings.Contains(stored, private) {
			t.Fatal("navigation history captured input or a credential preview")
		}
	}
}

func TestNestedAgentFinderRestoresExactTargetAndChooserFocus(t *testing.T) {
	for _, origin := range []string{"agents", "agent_targets"} {
		t.Run(origin, func(t *testing.T) {
			f := fake()
			f.agentTargets = []target{
				{Name: "First", Path: "~/.first/AGENTS.md", Addition: "\nInstructions\n"},
				{Name: "Second", Path: "~/.second/AGENTS.md", Addition: "\nInstructions\n"},
			}
			b := &navigationBackend{fakeBackend: f}
			m := asyncModel(t, b, "agents", "")
			m.selected = 1
			m = enter(m)
			m.selected = 1
			if origin == "agents" {
				m = enter(m)
			}
			m = findAction(t, m, "agent instructions")
			m = openAgentDiff(t, m)
			if m.agentOnly != "~/.first/AGENTS.md" {
				t.Fatal("detour did not choose a different target")
			}
			m = escape(escape(escape(m)))
			f.agentTargets = []target{f.agentTargets[1], f.agentTargets[0]}
			m = escape(m)
			if m.page != origin {
				t.Fatalf("Back returned to %s instead of %s", m.page, origin)
			}
			if origin == "agent_targets" {
				if m.selected != 0 || m.agents.Targets[m.selected].Path != "~/.second/AGENTS.md" {
					t.Fatal("chooser focus tracked an index instead of the chosen path")
				}
				m = enter(m)
			}
			if m.agentOnly != "~/.second/AGENTS.md" || len(m.reviewTargets()) != 1 || m.reviewTargets()[0].Path != "~/.second/AGENTS.md" {
				t.Fatal("nested Agent instructions changed or broadened the original target")
			}
		})
	}
}
