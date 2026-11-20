package main

import (
	"reflect"
	"testing"
)

func TestRoutesKeepAutomationAndChildFlagsDirect(t *testing.T) {
	t.Setenv("GODMODE_PLAIN", "")
	t.Setenv("GODMODE_NO_MOTION", "")
	cases := []struct {
		args        []string
		command     string
		interactive bool
	}{
		{nil, "home", true},
		{[]string{"profile"}, "profile", true},
		{[]string{"profile", "show"}, "profile", false},
		{[]string{"setup", "cloudflare"}, "loadout", true},
		{[]string{"loadout", "cloudflare"}, "loadout", true},
		{[]string{"set", "TOKEN"}, "set", true},
		{[]string{"set", "TOKEN", "--stdin"}, "set", false},
		{[]string{"run", "TOKEN", "--", "tool", "--plain"}, "run", false},
		{[]string{"agents", "--help"}, "agents", false},
		{[]string{"settings"}, "settings", true},
		{[]string{"settings", "--help"}, "settings", false},
		{[]string{"music"}, "music", false},
		{[]string{"jingle"}, "jingle", false},
		{[]string{"picard"}, "picard", false},
		{[]string{"music", "stop"}, "music", false},
		{[]string{"music", "status", "--json"}, "music", false},
		{[]string{"music", "play", "Local Song"}, "music", false},
		{[]string{"music", "__bridge"}, "music", false},
		{[]string{"help", "settings"}, "help", false},
		{[]string{"--home", "/example", "faq"}, "faq", true},
	}
	for _, test := range cases {
		route := selectRoute(test.args)
		if route.command != test.command || route.interactive != test.interactive {
			t.Errorf("route %q: got %q interactive=%t", test.args, route.command, route.interactive)
		}
		if route.command == "run" && route.plain {
			t.Fatal("child's --plain became a global option")
		}
	}
}

func TestEnvironmentSelectionAndExternalActionsKeepScope(t *testing.T) {
	r := selectRoute([]string{"--context", "acme", "--env=acme-test", "setup", "stripe"})
	if r.context != "acme" || r.environment != "acme-test" || !r.interactive || r.command != "loadout" {
		t.Fatal("selected setup lost scope")
	}
	for _, args := range [][]string{{"--env=", "profile"}, {"--env", "a", "--env", "b"}, {"--env"}} {
		if !selectRoute(args).envError {
			t.Fatal("invalid environment entered UI")
		}
	}
	child := selectRoute([]string{"run", "TOKEN", "--", "tool", "--env", "other"})
	if child.envSelected {
		t.Fatal("child environment flag selected parent")
	}
	r.home = "/tmp/example"
	if want := []string{"--home", "/tmp/example", "--context", "acme", "--env", "acme-test", "update"}; !reflect.DeepEqual(selectedArgs(r, "update"), want) {
		t.Fatal("external update lost scope")
	}
	if want := []string{"source"}; !reflect.DeepEqual(commandWords([]string{"--env", "acme-test", "--context=acme", "source"}), want) {
		t.Fatal("scope flags became command words")
	}
}

func TestRoutesKeepHomeAndMotionOptions(t *testing.T) {
	route := selectRoute([]string{"--home=/example", "--no-motion", "setup", "vercel"})
	if route.home != "/example" || !route.noMotion || route.arg != "vercel" || !route.interactive {
		t.Fatal("interactive route lost a display option")
	}
	plain := selectRoute([]string{"--plain", "settings"})
	if plain.command != "settings" || !plain.plain {
		t.Fatal("plain Settings lost its text-engine route")
	}
}

func TestContextSelectionBelongsToTheParentCommand(t *testing.T) {
	r := selectRoute([]string{"--context", "acme", "profile"})
	if !r.contextSelected || r.context != "acme" || r.command != "profile" || !r.interactive {
		t.Fatal("context profile lost its selection")
	}
	for _, args := range [][]string{{"--context=", "profile"}, {"--context", "a", "--context", "b", "profile"}, {"--context"}} {
		if !selectRoute(args).contextError {
			t.Fatal("invalid context selection entered the interactive route")
		}
	}
	r = selectRoute([]string{"run", "TOKEN", "--", "tool", "--context", "other"})
	if r.contextSelected || r.context != "" {
		t.Fatal("child context flag changed the parent command")
	}
}
