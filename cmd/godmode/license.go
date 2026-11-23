package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"strings"
	"time"

	"github.com/charmbracelet/x/term"
	"godmode.build/cli/internal/license"
	"godmode.build/cli/internal/ui"
)

const licenseHelp = `Usage: godmode license activate [--stdin]
       godmode license status [--json]
       godmode license deactivate
       godmode license import --stdin
       godmode license check
       godmode license path

Activation needs your purchase key and an internet connection. Key entry is hidden.
Legacy signed licenses stay on this machine. Local CLI use needs no activation.
Import reads a previously issued license.json from stdin without a network call.
Deactivation releases this installation and removes its local license file.
Provider keys and your profile stay unchanged.

The private preview also asks for the site password. GODMODE_PREVIEW_PASSWORD
can supply that password to automated commands. It is not saved.
`

// Global flags may precede or follow a command; a child owns everything after --.
func commandWords(args []string) []string {
	var words []string
	for i := 0; i < len(args); i++ {
		a := args[i]
		if a == "--" {
			words = append(words, args[i:]...)
			break
		}
		if a == "--home" || a == "--config-dir" || a == "--context" || a == "--env" {
			i++
			continue
		}
		if a == "--plain" || a == "--no-motion" || strings.HasPrefix(a, "--home=") || strings.HasPrefix(a, "--config-dir=") || strings.HasPrefix(a, "--context=") || strings.HasPrefix(a, "--env=") {
			continue
		}
		words = append(words, a)
	}
	return words
}

func secretInput(prompt string, piped bool) (string, error) {
	if piped {
		if term.IsTerminal(os.Stdin.Fd()) {
			return "", errors.New("--stdin requires a pipe. Omit it for hidden entry.")
		}
		b, err := io.ReadAll(io.LimitReader(os.Stdin, 1025))
		if err != nil || len(b) > 1024 {
			return "", errors.New("The license input is unreadable.")
		}
		return strings.TrimSpace(string(b)), nil
	}
	input := os.Stdin
	if !term.IsTerminal(input.Fd()) {
		var err error
		input, err = os.OpenFile("/dev/tty", os.O_RDWR, 0)
		if err != nil {
			return "", errors.New("Hidden entry needs a terminal. Pipe the license key with --stdin.")
		}
		defer input.Close()
	}
	return ui.ReadSecret(prompt, input)
}

func licenseCommand(args []string, home string) int {
	words := commandWords(args)
	if len(words) == 1 || (len(words) == 2 && (words[1] == "help" || words[1] == "--help" || words[1] == "-h")) {
		fmt.Print(licenseHelp)
		return 0
	}
	if len(words) < 2 {
		return 2
	}
	action := words[1]
	valid := false
	switch action {
	case "activate":
		valid = len(words) == 2 || (len(words) == 3 && words[2] == "--stdin")
	case "status":
		valid = len(words) == 2 || (len(words) == 3 && words[2] == "--json")
	case "deactivate", "check", "path":
		valid = len(words) == 2
	case "import":
		valid = len(words) == 3 && words[2] == "--stdin"
	}
	if !valid {
		fmt.Fprintln(os.Stderr, "godmode: Use godmode license --help. Never put a license key in command arguments.")
		return 2
	}
	c, err := license.Default(home, version)
	if err != nil {
		fmt.Fprintln(os.Stderr, "godmode:", err)
		return 2
	}
	fail := func(err error) int {
		fmt.Fprintln(os.Stderr, "godmode:", err)
		if errors.Is(err, ui.ErrCancelled) {
			return 130
		}
		return 2
	}
	password := os.Getenv("GODMODE_PREVIEW_PASSWORD")
	retryPreview := func(call func(string) error) error {
		err := call(password)
		if errors.Is(err, license.ErrPreview) && password == "" {
			password, err = secretInput("Private site password: ", false)
			if err == nil {
				err = call(password)
			}
		}
		return err
	}
	switch action {
	case "path":
		fmt.Println(c.Path())
		return 0
	case "check", "status":
		_, claims, err := c.Read()
		if err != nil {
			return fail(err)
		}
		if action == "check" {
			return 0
		}
		if len(words) == 3 {
			json.NewEncoder(os.Stdout).Encode(struct {
				Claims license.Claims `json:"license"`
				Path   string         `json:"path"`
			}{claims, c.Path()})
		} else {
			fmt.Println("Godmode license active; " + claims.Kind)
			if claims.TestMode {
				fmt.Println("Evaluation ends " + time.Unix(*claims.ExpiresAt, 0).UTC().Format("2006-01-02 15:04 UTC"))
				fmt.Println("No purchase recorded")
			}
			if claims.LifetimeUpdates() {
				fmt.Println("All local CLI versions, including future updates; offline verification")
			} else {
				fmt.Printf("Versions through %d.x; offline verification\n", claims.MaxMajor)
			}
			fmt.Println(c.Path())
		}
		return 0
	case "activate":
		key, err := secretInput("License key: ", len(words) == 3)
		if err != nil {
			return fail(err)
		}
		var claims license.Claims
		err = retryPreview(func(password string) error { var e error; claims, e = c.Activate(key, password); return e })
		if err != nil {
			return fail(err)
		}
		fmt.Println("Godmode license activated. Run godmode.")
		if claims.TestMode {
			fmt.Println("Evaluation ends " + time.Unix(*claims.ExpiresAt, 0).UTC().Format("2006-01-02 15:04 UTC") + "; no purchase recorded")
		}
		return 0
	case "deactivate":
		if err := retryPreview(c.Deactivate); err != nil {
			return fail(err)
		}
		fmt.Println("Godmode license deactivated. Your profile and provider keys remain on this machine.")
		return 0
	case "import":
		if term.IsTerminal(os.Stdin.Fd()) {
			return fail(errors.New("Pipe license.json into godmode license import --stdin."))
		}
		data, err := io.ReadAll(io.LimitReader(os.Stdin, 32769))
		if err != nil {
			return fail(errors.New("Godmode could not read the license input."))
		}
		claims, err := c.Import(data)
		if err != nil {
			return fail(err)
		}
		fmt.Println("Godmode license imported. Run godmode.")
		if claims.TestMode {
			fmt.Println("Evaluation ends " + time.Unix(*claims.ExpiresAt, 0).UTC().Format("2006-01-02 15:04 UTC") + "; no purchase recorded")
		}
		return 0
	}
	return 2
}
