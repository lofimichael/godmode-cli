package ui

import (
	"errors"
	"reflect"
	"strings"
	"testing"

	"github.com/charmbracelet/x/ansi"
)

// Prescribed backend replies test UI reconciliation independently of the
// Python history writer, whose MRU/schema/file behavior has separate tests.
type recentTestBackend struct {
	base         *fakeBackend
	afterApply   []setupPair
	applyError   error
	historyError string
}

func (b *recentTestBackend) Call(action string, args map[string]any) (map[string]any, error) {
	if action == "selection_save" && b.applyError != nil {
		b.base.calls = append(b.base.calls, action)
		b.base.requests = append(b.base.requests, args)
		return nil, b.applyError
	}
	result, err := b.base.Call(action, args)
	if action == "selection_save" && err == nil {
		if b.afterApply != nil {
			result["recent_setups"] = b.afterApply
		}
		result["history_error"] = b.historyError
	}
	return result, err
}

func recentFixture(t *testing.T) (model, *recentTestBackend, []setupPair) {
	t.Helper()
	pairs := []setupPair{{"north", "north-business"}, {"south", "south-business"}, {"default", ""}}
	f := fake()
	f.state["environment"], f.state["context"] = pairs[0].Environment, pairs[0].Context
	f.state["recent_setups"] = pairs
	f.state["preferences"] = map[string]any{"motion": false}
	b := &recentTestBackend{base: f, afterApply: []setupPair{pairs[1], pairs[0], pairs[2]}}
	m, err := newModel(b, "home", "", Options{})
	if err != nil {
		t.Fatal(err)
	}
	return m, b, pairs
}

func assertRecentApply(t *testing.T, b *recentTestBackend, wanted setupPair, countWanted int) {
	t.Helper()
	if count(b.base.calls, "selection_save") != countWanted {
		t.Fatalf("selection saves = %d, want %d", count(b.base.calls, "selection_save"), countWanted)
	}
	for i, action := range b.base.calls {
		if action == "selection_save" && (b.base.requests[i]["environment"] != wanted.Environment || b.base.requests[i]["context"] != wanted.Context) {
			t.Fatalf("saved an unreviewed pair: %#v", b.base.requests[i])
		}
	}
}

func TestRecentSetupReviewWaitsForExplicitApply(t *testing.T) {
	for _, route := range []string{"shortcut", "menu", "finder"} {
		t.Run(route, func(t *testing.T) {
			m, b, pairs := recentFixture(t)
			if route == "finder" {
				m = findAction(t, m, "recent loadouts")
			} else {
				m = openHomeItem(t, m, "Switch loadout")
				if route == "shortcut" {
					m = send(m, key('r', "r"))
				} else {
					m.selected = 3
					m = enter(m)
				}
			}
			if m.page != "recent_setups" || m.selected != 1 {
				t.Fatal("recent picker did not focus the first other setup")
			}
			m = enter(m)
			if m.page != "recent_details" || m.state.Environment != pairs[0].Environment || m.state.Context != pairs[0].Context {
				t.Fatal("review changed scope or did not show pair details")
			}
			assertRecentApply(t, b, pairs[1], 0)
			view := ansi.Strip(m.View().Content)
			for _, text := range []string{"Key environment", "Profile", "south-business", "south", "Enter use"} {
				if !strings.Contains(view, text) {
					t.Fatalf("review omitted %q: %s", text, view)
				}
			}
			m = enter(m)
			assertRecentApply(t, b, pairs[1], 1)
			if m.page != "recent_setups" || m.selected != 0 || m.state.Environment != "south" || m.state.Context != "south-business" {
				t.Fatal("applied pair did not reconcile with reordered history")
			}
			if !reflect.DeepEqual(m.state.RecentSetups, b.afterApply) || m.state.Preferences.Motion == nil || *m.state.Preferences.Motion || !m.opts.NoMotion {
				t.Fatal("apply lost backend history or the saved Motion preference")
			}
			if count(b.base.calls, "preferences_save") != 0 {
				t.Fatal("switching setup wrote appearance preferences")
			}
		})
	}
}

func TestRecentSetupCancelPreservesActivePairHistoryAndUnappliedDraft(t *testing.T) {
	for _, leaveList := range []string{"escape", "back"} {
		t.Run(leaveList, func(t *testing.T) {
			m, b, pairs := recentFixture(t)
			m = openHomeItem(t, m, "Switch loadout")
			m = enter(m)
			m.selected = 1
			m = enter(m)
			if m.draftEnvironment != "acme-test" {
				t.Fatal("test did not prepare an unapplied manual draft")
			}
			m = send(m, key('r', "r"))
			m = enter(m)
			m = escape(m)
			if m.page != "recent_setups" || m.selected != 1 {
				t.Fatal("canceling review lost picker focus")
			}
			if leaveList == "back" {
				m.selected = len(pairs)
				m = enter(m)
			} else {
				m = escape(m)
			}
			if m.page != "active" || !m.draftOpen || m.draftEnvironment != "acme-test" || m.draftContext != "north-business" {
				t.Fatal("canceling recent loadouts changed the existing manual draft")
			}
			m = escape(m)
			if m.page != "home" || m.draftOpen {
				t.Fatal("leaving Switch loadout retained a stale draft")
			}
			assertRecentApply(t, b, pairs[0], 0)
			if b.base.state["environment"] != "north" || b.base.state["context"] != "north-business" || !reflect.DeepEqual(b.base.state["recent_setups"], pairs) {
				t.Fatal("cancel changed saved state")
			}
		})
	}
}

func TestRecentMRUReorderDoesNotApplyOldIndexOrStaleManualDraft(t *testing.T) {
	m, b, pairs := recentFixture(t)
	m = openHomeItem(t, m, "Switch loadout")
	m = enter(m)
	m.selected = 1
	m = enter(m)
	m = send(m, key('r', "r"))
	m = enter(enter(m))
	if m.selected != 0 || m.draftEnvironment != "south" || m.draftContext != "south-business" {
		t.Fatal("applied recent setup left the old selection index or draft")
	}
	m = enter(m)
	if m.recentAt != 0 || !strings.Contains(ansi.Strip(m.View().Content), "south-business") {
		t.Fatal("reopening the focused MRU row reviewed a different pair")
	}
	m = enter(m)
	assertRecentApply(t, b, pairs[1], 2)
	m = escape(m)
	if m.page != "active" || m.draftEnvironment != "south" || m.draftContext != "south-business" {
		t.Fatal("returning to Switch loadout restored a stale manual draft")
	}
	m = escape(m)
	if m.draftOpen {
		t.Fatal("finished Switch loadout retained a draft")
	}
}

func TestRecentApplyFailureKeepsReviewedPairAndPreviousSelection(t *testing.T) {
	m, b, pairs := recentFixture(t)
	b.applyError = errors.New("Selected environment is no longer saved.")
	m = findAction(t, m, "recent loadouts")
	m = enter(enter(m))
	assertRecentApply(t, b, pairs[1], 1)
	if m.page != "recent_details" || m.state.Environment != pairs[0].Environment || m.state.Context != pairs[0].Context || m.error == "" {
		t.Fatal("failed apply replaced the active pair or dismissed its review")
	}
	if !reflect.DeepEqual(m.state.RecentSetups, pairs) {
		t.Fatal("failed apply changed history")
	}
}

func TestRecentApplyDistinguishesAutomaticFromBusinessNamedDefault(t *testing.T) {
	for _, context := range []string{"", "default"} {
		t.Run(businessName(context), func(t *testing.T) {
			_, b, pairs := recentFixture(t)
			wanted := setupPair{"default", context}
			b.base.state["recent_setups"] = []setupPair{pairs[0], wanted}
			b.afterApply = []setupPair{wanted, pairs[0]}
			m, err := newModel(b, "home", "", Options{NoMotion: true})
			if err != nil {
				t.Fatal(err)
			}
			m = findAction(t, m, "recent loadouts")
			m = enter(m)
			view := ansi.Strip(m.View().Content)
			if strings.Contains(view, "Automatic") != (context == "") {
				t.Fatal("review confused Automatic with a business named default")
			}
			m = enter(m)
			assertRecentApply(t, b, wanted, 1)
			if m.state.Environment != "default" || m.state.Context != context {
				t.Fatal("recent apply reinterpreted the reviewed business name")
			}
		})
	}
}

func TestRecentHistoryWriteWarningDoesNotHideSuccessfulApply(t *testing.T) {
	m, b, pairs := recentFixture(t)
	b.afterApply = pairs // History write failed; active save still succeeded.
	b.historyError = "Active loadout saved, but recent loadouts were not updated. Check ui.json."
	m = findAction(t, m, "recent loadouts")
	m = enter(enter(m))
	assertRecentApply(t, b, pairs[1], 1)
	if m.state.Environment != "south" || m.state.Context != "south-business" || m.page != "recent_setups" || m.selected != 1 {
		t.Fatal("history warning hid the applied pair or focused a different row")
	}
	if !strings.Contains(m.notice, "Using south") || !strings.Contains(ansi.Strip(m.View().Content), "recent loadouts were not updated") {
		t.Fatal("success and separate history warning are not both visible")
	}
}

func TestRecentMalformedHistoryShowsSettingsWarningWithoutBlocking(t *testing.T) {
	f := fake()
	f.state["recent_setups"] = []setupPair{}
	f.state["history_error"] = "ui.json recent_setups must be a list of at most five setups."
	f.state["preferences"] = map[string]any{"motion": false}
	m := create(t, f, "home", "")
	m = openHomeItem(t, m, "Settings")
	view := ansi.Strip(m.View().Content)
	if !strings.Contains(view, "recent_setups must be") || !strings.Contains(view, "Motion") {
		t.Fatalf("Settings hid the nonfatal history error: %s", view)
	}
	if m.state.Preferences.Motion == nil || *m.state.Preferences.Motion || m.quitting {
		t.Fatal("malformed history blocked settings or lost valid Motion")
	}
}
