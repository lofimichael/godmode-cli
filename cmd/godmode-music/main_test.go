package main

import (
	"encoding/json"
	"os/exec"
	"reflect"
	"runtime"
	"strings"
	"testing"
)

func TestRoutesOnlyMusicCompanionArguments(t *testing.T) {
	t.Setenv("GODMODE_PLAIN", "")
	t.Setenv("GODMODE_NO_MOTION", "")
	cases := []struct {
		in, want        []string
		home            string
		plain, noMotion bool
	}{
		{nil, []string{"music"}, "", false, false},
		{[]string{"--home", "/tmp/music-home", "--no-motion", "music"}, []string{"music"}, "/tmp/music-home", false, true},
		{[]string{"jingle", "play", "test", "--plain"}, []string{"jingle", "play", "test"}, "", true, false},
		{[]string{"music", "setup", "--songs", "/tmp/My Songs"}, []string{"music", "setup", "--songs", "/tmp/My Songs"}, "", false, false},
		{[]string{"--config-dir=/tmp/music", "music", "__serve"}, []string{"music", "__serve"}, "/tmp/music", false, false},
	}
	for _, c := range cases {
		r, err := parse(c.in)
		if err != nil {
			t.Fatal(err)
		}
		if !reflect.DeepEqual(r.words, c.want) || r.home != c.home || r.plain != c.plain || r.noMotion != c.noMotion {
			t.Fatalf("route mismatch for %q: %#v", c.in, r)
		}
	}
	for _, bad := range [][]string{{"--home"}, {"--home="}, {"--home", "one", "--home", "two"}} {
		if _, err := parse(bad); err == nil {
			t.Fatalf("bad home accepted %q", bad)
		}
	}
}
func TestPackMetadataIsMachineReadableAndPlatformSpecific(t *testing.T) {
	info := packInfo()
	if info["kind"] != "godmode-music-pack" || info["protocol"] != 1 || info["version"] != version || info["platform"] != runtime.GOOS || info["arch"] != runtime.GOARCH {
		t.Fatal("pack protocol metadata mismatch")
	}
	if _, err := json.Marshal(info); err != nil {
		t.Fatal(err)
	}
}
func TestPassThroughPreservesHomeAndPresentationFlags(t *testing.T) {
	r := route{home: "/tmp/My Music", plain: true, noMotion: true, words: []string{"music", "__bridge"}}
	want := []string{"--home", "/tmp/My Music", "--plain", "--no-motion", "music", "__bridge"}
	if !reflect.DeepEqual(r.engineArgs(), want) {
		t.Fatal("engine args altered")
	}
}
func TestCompanionDependenciesExcludeRootEngineAndUI(t *testing.T) {
	cmd := exec.Command("go", "list", "-deps", ".")
	raw, err := cmd.Output()
	if err != nil {
		t.Fatal(err)
	}
	deps := strings.Split(strings.TrimSpace(string(raw)), "\n")
	for _, dep := range deps {
		if dep == "github.com/lofimichael/godmode-cli/internal/core" || dep == "github.com/lofimichael/godmode-cli/internal/ui" {
			t.Fatalf("companion linked root package %s", dep)
		}
	}
	joined := strings.Join(deps, "\n")
	if !strings.Contains(joined, "/internal/musiccore") || !strings.Contains(joined, "/internal/musicui") {
		t.Fatal("music packages missing from companion")
	}
}
