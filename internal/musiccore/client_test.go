package musiccore

import (
	"bytes"
	"encoding/json"
	"os"
	"os/exec"
	"strings"
	"sync"
	"testing"
	"time"
)

const echoEngine = `import json,sys
for line in sys.stdin:
    request=json.loads(line)
    print(json.dumps({"ok":True,"data":request}),flush=True)
`

func testHome(t *testing.T) {
	t.Helper()
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("GODMODE_HOME", home+"/.godmode")
	t.Setenv("XDG_CONFIG_HOME", home+"/.config")
}
func TestEnvironmentExcludesCredentialsAndInjection(t *testing.T) {
	testHome(t)
	forbidden := []string{"GH_TOKEN", "OPENAI_API_KEY", "GODMODE_ENV", "GODMODE_CONTEXT", "CODEX_HOME", "COPILOT_HOME", "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "GODMODE_PREVIEW_PASSWORD", "UNRELATED_PRIVATE_VALUE"}
	for _, name := range forbidden {
		t.Setenv(name, "synthetic-do-not-inherit")
	}
	t.Setenv("GODMODE_EXECUTABLE", "/synthetic/wrong-program")
	env := map[string]string{}
	for _, entry := range engineEnvironment() {
		parts := strings.SplitN(entry, "=", 2)
		env[parts[0]] = parts[1]
	}
	for _, name := range forbidden {
		if _, ok := env[name]; ok {
			t.Errorf("engine inherited forbidden variable %s", name)
		}
	}
	if env["GODMODE_EXECUTABLE"] != executable() {
		t.Fatal("daemon launcher can be overridden by ambient environment")
	}
	if env["HOME"] != os.Getenv("HOME") || env["GODMODE_HOME"] != os.Getenv("GODMODE_HOME") {
		t.Fatal("local music home was not retained")
	}
}
func TestTextCommandsUseSameIsolatedEnvironment(t *testing.T) {
	testHome(t)
	t.Setenv("GH_TOKEN", "synthetic-do-not-inherit")
	t.Setenv("GODMODE_ENV", "private-business")
	t.Setenv("PYTHONPATH", t.TempDir())
	t.Setenv("GODMODE_EXECUTABLE", "/synthetic/wrong-program")
	script := `import json,os,sys
print(json.dumps({"names":sorted(os.environ),"executable":os.environ.get("GODMODE_EXECUTABLE"),"args":sys.argv[1:]}))
`
	var out, stderr bytes.Buffer
	if code := run([]string{"jingle", "list"}, script, strings.NewReader(""), &out, &stderr); code != 0 {
		t.Fatalf("text engine failed: %s", stderr.String())
	}
	var got struct {
		Names      []string
		Executable string
		Args       []string
	}
	if err := json.Unmarshal(out.Bytes(), &got); err != nil {
		t.Fatal(err)
	}
	for _, name := range got.Names {
		if name == "GH_TOKEN" || name == "GODMODE_ENV" || name == "PYTHONPATH" {
			t.Fatalf("text command inherited %s", name)
		}
	}
	if got.Executable != executable() || strings.Join(got.Args, " ") != "jingle list" {
		t.Fatal("companion dispatch changed executable or args")
	}
}
func TestMusicBridgePassesHomeAndSerializesConcurrentCalls(t *testing.T) {
	testHome(t)
	client, err := newClient([]string{"--home", os.Getenv("GODMODE_HOME"), "music", "__bridge"}, echoEngine)
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	var wg sync.WaitGroup
	errors := make(chan string, 12)
	for i := 0; i < 12; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			reply, err := client.Call("status", map[string]any{"index": n, "action": "must-not-override"})
			if err != nil {
				errors <- err.Error()
				return
			}
			if reply["action"] != "status" || reply["index"] != float64(n) {
				errors <- "crossed JSON replies"
			}
		}(i)
	}
	wg.Wait()
	close(errors)
	for err := range errors {
		t.Error(err)
	}
}
func TestProtocolBoundsAndMalformedReplies(t *testing.T) {
	testHome(t)
	client, err := newClient(nil, echoEngine)
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	if _, err := client.Call("status", map[string]any{"large": strings.Repeat("x", maxRequest)}); err == nil {
		t.Fatal("oversized request accepted")
	}
	if _, err := client.Call("status", nil); err != nil {
		t.Fatal("rejected request damaged protocol")
	}
	scripts := []string{
		`import sys
sys.stdin.readline()
print('{"ok":true,"data":{}} {"extra":1}',flush=True)
`,
		`import sys
sys.stdin.readline()
print('{"data":{}}',flush=True)
`,
		`import sys
sys.stdin.readline()
print('x'*(2*1024*1024+1),flush=True)
`,
	}
	for _, script := range scripts {
		client, err := newClient(nil, script)
		if err != nil {
			t.Fatal(err)
		}
		_, err = client.Call("status", nil)
		client.Abort()
		client.Close()
		if err == nil {
			t.Fatal("malformed or oversized reply accepted")
		}
	}
}
func TestTimeoutAndAbortRestoreControl(t *testing.T) {
	testHome(t)
	script := `import sys,time
sys.stdin.readline()
time.sleep(30)
`
	client, err := newClient(nil, script)
	if err != nil {
		t.Fatal(err)
	}
	client.timeout = 40 * time.Millisecond
	started := time.Now()
	if _, err := client.Call("status", nil); err == nil {
		t.Fatal("unresponsive engine did not time out")
	}
	if time.Since(started) > 2*time.Second {
		t.Fatal("timeout did not bound process wait")
	}
	if err := client.Close(); err != nil {
		t.Fatal(err)
	}
	client, err = newClient(nil, script)
	if err != nil {
		t.Fatal(err)
	}
	done := make(chan error, 1)
	go func() { _, err := client.Call("status", nil); done <- err }()
	client.Abort()
	select {
	case err := <-done:
		if err == nil {
			t.Fatal("aborted engine succeeded")
		}
	case <-time.After(2 * time.Second):
		t.Fatal("Abort did not interrupt pending read")
	}
	client.Close()
}
func TestBackendErrorIsSafeForTerminal(t *testing.T) {
	testHome(t)
	script := `import sys,json
sys.stdin.readline()
print(json.dumps({"ok":False,"error":"bad\u001b[2J\nmessage\u202e"}),flush=True)
`
	client, err := newClient(nil, script)
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	_, err = client.Call("status", nil)
	if err == nil || strings.ContainsAny(err.Error(), "\x1b\n\u202e") {
		t.Fatal("backend control text reached UI")
	}
}
func TestEmbeddedMusicSourceDoesNotContainCredentialModules(t *testing.T) {
	for _, forbidden := range []string{"class Store:", "def profile_main(", "import godmode_store", "from godmode_store", "def provider_main(", "def run_with_keys("} {
		if strings.Contains(Source(), forbidden) {
			t.Fatalf("pack embeds unrelated engine marker %q", forbidden)
		}
	}
	if len(SHA256()) != 64 || !strings.Contains(Source(), "music_pack_main") {
		t.Fatal("missing inspectable music source")
	}
}
func TestPythonIsRequiredClearly(t *testing.T) {
	t.Setenv("PATH", t.TempDir())
	if _, err := New(t.TempDir()); err == nil || !strings.Contains(err.Error(), "Python 3.9") {
		t.Fatal("missing Python did not return setup action")
	}
}
func TestGeneratedEngineSupportsOnlyMusicAndJingle(t *testing.T) {
	testHome(t)
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("Python unavailable")
	}
	client, err := New(os.Getenv("GODMODE_HOME"))
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	reply, err := client.Call("library", nil)
	if err != nil {
		t.Fatal(err)
	}
	if configured, ok := reply["configured"].(bool); !ok || configured {
		t.Fatal("fresh music home unexpectedly configured")
	}
	if _, err := client.Call("profile", nil); err == nil {
		t.Fatal("music bridge accepted profile action")
	}
}
