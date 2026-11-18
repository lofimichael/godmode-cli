// godmode-music is the optional pack companion. It imports only the music UI
// and music-only engine, never the root credential or management packages.
package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"runtime"
	"strings"

	"github.com/charmbracelet/x/term"
	"github.com/lofimichael/godmode-cli/internal/musiccore"
	"github.com/lofimichael/godmode-cli/internal/musicui"
)

var version = "dev"

const packProtocol = 1

type route struct {
	home            string
	plain, noMotion bool
	words           []string
}

func enabled(s string) bool {
	switch strings.ToLower(s) {
	case "", "0", "false", "no":
		return false
	}
	return true
}
func parse(args []string) (route, error) {
	r := route{plain: enabled(os.Getenv("GODMODE_PLAIN")), noMotion: enabled(os.Getenv("GODMODE_NO_MOTION"))}
	homeSet := false
	for i := 0; i < len(args); i++ {
		word := args[i]
		if word == "--" {
			r.words = append(r.words, args[i:]...)
			break
		}
		switch {
		case word == "--plain":
			r.plain = true
		case word == "--no-motion":
			r.noMotion = true
		case word == "--home" || word == "--config-dir":
			if homeSet || i+1 >= len(args) || args[i+1] == "" {
				return r, errors.New("Pass one --home DIR for the music pack")
			}
			i++
			r.home = args[i]
			homeSet = true
		case strings.HasPrefix(word, "--home=") || strings.HasPrefix(word, "--config-dir="):
			if homeSet {
				return r, errors.New("Pass one --home DIR for the music pack")
			}
			r.home = strings.SplitN(word, "=", 2)[1]
			if r.home == "" {
				return r, errors.New("Pass one --home DIR for the music pack")
			}
			homeSet = true
		default:
			r.words = append(r.words, word)
		}
	}
	if len(r.words) == 0 {
		r.words = []string{"music"}
	}
	return r, nil
}
func (r route) engineArgs() []string {
	out := []string{}
	if r.home != "" {
		out = append(out, "--home", r.home)
	}
	if r.plain {
		out = append(out, "--plain")
	}
	if r.noMotion {
		out = append(out, "--no-motion")
	}
	return append(out, r.words...)
}
func packInfo() map[string]any {
	return map[string]any{"kind": "godmode-music-pack", "protocol": packProtocol, "version": version, "platform": runtime.GOOS, "arch": runtime.GOARCH}
}
func help(out io.Writer) {
	fmt.Fprintln(out, `Godmode Music Pack — local music and jingles

Usage:
  godmode music                         open the player
  godmode music setup --songs DIR       prepare a local .ootrs library
  godmode music list                    list local tracks
  godmode music status                  inspect the player
  godmode music stop                    stop playback
  godmode music --help                  complete music command reference
  godmode jingle --help                 jingle command reference

Companion options: --home DIR  --plain  --no-motion
Companion inspection: --version  source  build-info`)
}
func run(args []string) int {
	r, err := parse(args)
	if err != nil {
		fmt.Fprintln(os.Stderr, "godmode music:", err)
		return 2
	}
	if len(r.words) == 1 {
		switch r.words[0] {
		case "__pack_info":
			if err := json.NewEncoder(os.Stdout).Encode(packInfo()); err != nil {
				return 1
			}
			return 0
		case "--version", "version":
			fmt.Fprintln(os.Stdout, "godmode-music", version)
			return 0
		case "--help", "-h", "help":
			help(os.Stdout)
			return 0
		case "source":
			fmt.Fprint(os.Stdout, musiccore.Source())
			return 0
		case "build-info":
			info := packInfo()
			info["engine_sha256"] = musiccore.SHA256()
			info["go"] = runtime.Version()
			if err := json.NewEncoder(os.Stdout).Encode(info); err != nil {
				return 1
			}
			return 0
		}
	}
	if r.words[0] != "music" && r.words[0] != "jingle" {
		fmt.Fprintln(os.Stderr, "godmode music: this companion only handles music and jingle commands")
		return 2
	}
	if r.words[0] == "music" && len(r.words) == 1 && !r.plain && term.IsTerminal(os.Stdin.Fd()) && term.IsTerminal(os.Stdout.Fd()) {
		client, err := musiccore.New(r.home)
		if err != nil {
			fmt.Fprintln(os.Stderr, "godmode music:", err)
			return 1
		}
		defer func() { client.Abort(); client.Close() }()
		if err := musicui.Run(client, musicui.Options{NoMotion: r.noMotion}); err != nil {
			fmt.Fprintln(os.Stderr, "godmode music:", err)
			return 1
		}
		return 0
	}
	return musiccore.Run(r.engineArgs())
}
func main() { os.Exit(run(os.Args[1:])) }
