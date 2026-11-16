package main

import "testing"

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
		{[]string{"setup", "cloudflare"}, "setup", true},
		{[]string{"set", "TOKEN"}, "set", true},
		{[]string{"set", "TOKEN", "--stdin"}, "set", false},
		{[]string{"run", "TOKEN", "--", "tool", "--plain"}, "run", false},
		{[]string{"agents", "--help"}, "agents", false},
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

func TestRoutesKeepHomeAndMotionOptions(t *testing.T) {
	route := selectRoute([]string{"--home=/example", "--no-motion", "setup", "vercel"})
	if route.home != "/example" || !route.noMotion || route.arg != "vercel" || !route.interactive {
		t.Fatal("interactive route lost a display option")
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
