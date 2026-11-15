package main

import (
	"errors"
	"fmt"
	"os"
	"runtime/debug"
	"strings"

	"github.com/charmbracelet/x/term"
	"github.com/lofimichael/godmode-cli/internal/core"
	"github.com/lofimichael/godmode-cli/internal/license"
	"github.com/lofimichael/godmode-cli/internal/ui"
)

var version = "dev"

type route struct {
	command, arg, home string
	plain, noMotion    bool
	interactive        bool
}

func enabled(value string) bool {
	switch strings.ToLower(value) {
	case "", "0", "false", "no":
		return false
	}
	return true
}

func selectRoute(args []string) route {
	r := route{plain: enabled(os.Getenv("GODMODE_PLAIN")), noMotion: enabled(os.Getenv("GODMODE_NO_MOTION"))}
	words := make([]string, 0, len(args))
	for i := 0; i < len(args); i++ {
		word := args[i]
		if word == "--" {
			words = append(words, args[i:]...)
			break
		}
		switch {
		case word == "--plain":
			r.plain = true
		case word == "--no-motion":
			r.noMotion = true
		case word == "--home" || word == "--config-dir":
			if i+1 == len(args) {
				return r
			}
			i++
			r.home = args[i]
		case strings.HasPrefix(word, "--home=") || strings.HasPrefix(word, "--config-dir="):
			r.home = strings.SplitN(word, "=", 2)[1]
		default:
			words = append(words, word)
		}
	}
	if len(words) == 0 {
		r.command, r.interactive = "home", true
		return r
	}
	r.command = words[0]
	if len(words) == 2 {
		r.arg = words[1]
	}
	switch r.command {
	case "onboard", "init":
		r.command, r.interactive = "home", len(words) == 1
	case "intro", "profile", "agents", "faq":
		r.interactive = len(words) == 1
	case "setup":
		r.interactive = len(words) <= 2 && !strings.HasPrefix(r.arg, "-")
	case "set":
		r.interactive = len(words) == 2 && !strings.HasPrefix(r.arg, "-")
	}
	return r
}

func buildInfo() {
	fmt.Println("Godmode " + version)
	fmt.Println("Core SHA-256 " + core.SHA256())
	if info, ok := debug.ReadBuildInfo(); ok {
		fmt.Println("Go " + strings.TrimPrefix(info.GoVersion, "go"))
		for _, dependency := range info.Deps {
			fmt.Println(dependency.Path + " " + dependency.Version + " " + dependency.Sum)
		}
	}
}

func run(args []string) int {
	words := commandWords(args)
	if len(words) == 1 {
		switch words[0] {
		case "source":
			fmt.Print(core.Source())
			return 0
		case "build-info":
			buildInfo()
			return 0
		}
	}
	r := selectRoute(args)
	if words := commandWords(args); len(words) > 0 && words[0] == "license" {
		return licenseCommand(args, r.home)
	}
	if !inspection(args) {
		config, err := license.Default(r.home, version)
		if err == nil {
			_, _, err = config.Read()
		}
		if err != nil {
			fmt.Fprintln(os.Stderr, "godmode:", err)
			return 2
		}
	}
	if !r.interactive || r.plain || os.Getenv("TERM") == "dumb" || os.Getenv("TERM") == "" ||
		!term.IsTerminal(os.Stdin.Fd()) || !term.IsTerminal(os.Stdout.Fd()) {
		return core.Run(args)
	}
	for {
		client, err := core.New(r.home)
		if err != nil {
			fmt.Fprintln(os.Stderr, "godmode:", err)
			return 1
		}
		err = ui.Run(client, r.command, r.arg, ui.Options{Home: r.home, Plain: r.plain, NoMotion: r.noMotion})
		client.Close()
		if errors.Is(err, ui.ErrMusic) {
			musicArgs := []string{"music"}
			if r.home != "" {
				musicArgs = append([]string{"--home", r.home}, musicArgs...)
			}
			if r.noMotion {
				musicArgs = append(musicArgs, "--no-motion")
			}
			core.Run(musicArgs)
			r.command, r.arg = "home", ""
			continue
		}
		if errors.Is(err, ui.ErrCancelled) {
			return 130
		}
		if err != nil {
			fmt.Fprintln(os.Stderr, "godmode:", err)
			return 1
		}
		return 0
	}
}

func main() { os.Exit(run(os.Args[1:])) }
