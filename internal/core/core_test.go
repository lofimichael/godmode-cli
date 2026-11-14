package core

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func isolatedHome(t *testing.T) string {
	t.Helper()
	home, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	t.Setenv("HOME", home)
	t.Setenv("GODMODE_HOME", filepath.Join(home, ".godmode"))
	t.Setenv("GODMODE_CONFIG_DIR", "")
	return filepath.Join(home, ".godmode")
}

func TestPrivateClientReviewsThenSavesWithoutReturningSecret(t *testing.T) {
	home := isolatedHome(t)
	client, err := New(home)
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	state, err := client.Call("state", nil)
	if err != nil || state["home"] != home {
		t.Fatalf("state failed: %v", err)
	}
	plan, err := client.Call("key_plan", map[string]any{"name": "SYNTHETIC_TOKEN"})
	if err != nil {
		t.Fatal(err)
	}
	secret := "test-private-input-1234567890"
	fields := map[string]any{"id": plan["id"], "value": secret, "pasted": true}
	if _, err := client.Call("key_save", fields); err == nil {
		t.Fatal("unreviewed secret was saved")
	}
	checked, err := client.Call("key_check", fields)
	if err != nil {
		t.Fatal(err)
	}
	serialized, _ := json.Marshal(checked)
	if bytes.Contains(serialized, []byte(secret)) {
		t.Fatal("full secret returned in preview")
	}
	if _, err := client.Call("key_save", fields); err != nil {
		t.Fatal(err)
	}
	state, err = client.Call("state", nil)
	if err != nil {
		t.Fatal(err)
	}
	serialized, _ = json.Marshal(state)
	if bytes.Contains(serialized, []byte(secret)) {
		t.Fatal("saved secret returned in state")
	}
	if _, err := os.Stat(filepath.Join(home, ".env.godmode")); err != nil {
		t.Fatal("reviewed key was not saved")
	}
	if err := client.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Call("state", nil); err == nil {
		t.Fatal("closed client accepted another request")
	}
}

func TestUIEnvironmentOmitsInheritedCredentials(t *testing.T) {
	t.Setenv("GH_TOKEN", "synthetic-private-env")
	t.Setenv("AWS_SECRET_ACCESS_KEY", "synthetic-private-env")
	t.Setenv("CODEX_HOME", "/example/agent")
	environment := strings.Join(uiEnvironment(), "\n")
	if strings.Contains(environment, "synthetic-private-env") {
		t.Fatal("UI subprocess inherited management credentials")
	}
	if !strings.Contains(environment, "CODEX_HOME=/example/agent") || !strings.Contains(environment, "GODMODE_EXECUTABLE=") {
		t.Fatal("UI subprocess lacks its agent/executable context")
	}
}

type writeBuffer struct{ bytes.Buffer }

func (w *writeBuffer) Close() error { return nil }

func fixtureClient(response string) (*Client, *writeBuffer) {
	input := &writeBuffer{}
	scanner := bufio.NewScanner(strings.NewReader(response))
	scanner.Buffer(make([]byte, 4096), maxReply+1)
	return &Client{input: input, output: scanner, timeout: time.Second}, input
}

func TestWireBoundsAndErrorsDoNotEchoRequestOrInvalidResponse(t *testing.T) {
	for _, response := range []string{"not-json-private-data\n", `{"ok":true,"data":null}` + "\n",
		`{"ok":true,"data":{}} trailing-private-data` + "\n", strings.Repeat("X", maxReply+2) + "\n"} {
		client, input := fixtureClient(response)
		_, err := client.Call("example", map[string]any{"value": "synthetic-private-request"})
		if err == nil || strings.Contains(err.Error(), "private") || strings.Contains(err.Error(), strings.Repeat("X", 100)) {
			t.Fatal("malformed response was accepted or exposed")
		}
		var request map[string]any
		if json.Unmarshal(input.Bytes(), &request) != nil || request["action"] != "example" {
			t.Fatal("request was not a single JSON object")
		}
	}
	client, input := fixtureClient(`{"ok":true,"data":{}}` + "\n")
	if _, err := client.Call("example", map[string]any{"value": strings.Repeat("x", maxRequest)}); err == nil || input.Len() != 0 {
		t.Fatal("oversized request reached the subprocess")
	}
}

func TestRunHelper(t *testing.T) {
	if os.Getenv("GODMODE_TEST_DIRECT") != "1" {
		return
	}
	for i, argument := range os.Args {
		if argument == "--" {
			os.Exit(Run(os.Args[i+1:]))
		}
	}
	os.Exit(2)
}

func TestDirectCommandsPreserveInputStreamsAndExitCode(t *testing.T) {
	home := isolatedHome(t)
	command := func(args ...string) *exec.Cmd {
		argv := append([]string{"-test.run=^TestRunHelper$", "--", "--home", home}, args...)
		cmd := exec.Command(os.Args[0], argv...)
		cmd.Env = append(os.Environ(), "GODMODE_TEST_DIRECT=1")
		return cmd
	}
	save := command("set", "SYNTHETIC_TOKEN", "--stdin")
	save.Stdin = strings.NewReader("synthetic-direct-input-123456")
	if output, err := save.CombinedOutput(); err != nil {
		t.Fatalf("direct stdin save failed: %v (%d output bytes)", err, len(output))
	}
	child := command("run", "SYNTHETIC_TOKEN", "--", "python3", "-c",
		`import os,sys; assert len(os.environ["SYNTHETIC_TOKEN"])==29; assert sys.argv[1:]==["--plain","--version"]; sys.stdout.write("out\n"); sys.stderr.write("err\n"); sys.exit(37)`, "--plain", "--version")
	var stdout, stderr bytes.Buffer
	child.Stdout, child.Stderr = &stdout, &stderr
	err := child.Run()
	if exitCode(err) != 37 || stdout.String() != "out\n" || stderr.String() != "err\n" {
		t.Fatalf("direct streams/child arguments/exit status changed: code=%d stdout=%d stderr=%d", exitCode(err), stdout.Len(), stderr.Len())
	}
}

func TestEmbeddedEngineIgnoresPythonStartupInjection(t *testing.T) {
	isolatedHome(t)
	attack := t.TempDir()
	marker := filepath.Join(attack, "executed")
	payload := "from pathlib import Path\nPath(" + fmt.Sprintf("%q", marker) + ").write_text('unexpected')\n"
	if err := os.WriteFile(filepath.Join(attack, "sitecustomize.py"), []byte(payload), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(attack, "json.py"), []byte("raise RuntimeError('wrong json imported')\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command(os.Args[0], "-test.run=^TestRunHelper$", "--", "profile", "show")
	cmd.Dir = attack
	cmd.Env = append(os.Environ(), "GODMODE_TEST_DIRECT=1", "PYTHONPATH="+attack)
	output, err := cmd.CombinedOutput()
	if err != nil || strings.TrimSpace(string(output)) != "{}" {
		t.Fatalf("isolated core failed: %v (%d output bytes)", err, len(output))
	}
	if _, err := os.Stat(marker); !os.IsNotExist(err) {
		t.Fatal("Python startup injection ran")
	}
}

var _ io.WriteCloser = (*writeBuffer)(nil)
