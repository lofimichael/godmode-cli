// Package core runs the readable Python engine embedded in the native terminal UI.
// Credentials travel through stdin and the existing store, never command arguments.
package core

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	_ "embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"
)

//go:embed core.py
var source string

const maxRequest = 8 * 1024 * 1024
const maxReply = 2 * 1024 * 1024

// The source pipe is separate from stdin. Direct commands retain their original
// stdin, including piped keys; the JSON bridge uses stdin for private requests.
const bootstrap = `import os,sys
with os.fdopen(3, "r", encoding="utf-8") as f:
    source=f.read()
sys.argv=sys.argv[1:]
exec(compile(source,sys.argv[0],"exec"),{"__name__":"__main__","__file__":sys.argv[0]})
`

func Source() string { return source }

func SHA256() string {
	sum := sha256.Sum256([]byte(source))
	return hex.EncodeToString(sum[:])
}

func executable() string {
	path, err := os.Executable()
	if err != nil {
		return "godmode"
	}
	return path
}

func withExecutable(env []string) []string {
	result := make([]string, 0, len(env)+1)
	for _, item := range env {
		if !strings.HasPrefix(item, "GODMODE_EXECUTABLE=") && !strings.HasPrefix(item, "GODMODE_PREVIEW_PASSWORD=") {
			result = append(result, item)
		}
	}
	return append(result, "GODMODE_EXECUTABLE="+executable())
}

func uiEnvironment() []string {
	names := []string{"PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "COLORTERM",
		"TMPDIR", "NO_COLOR", "CLICOLOR", "XDG_CONFIG_HOME", "CODEX_HOME", "COPILOT_HOME",
		"DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS",
		"GODMODE_HOME", "GODMODE_CONFIG_DIR", "GODMODE_STATE_DIR", "GODMODE_PLAIN", "GODMODE_NO_MOTION"}
	result := make([]string, 0, len(names))
	for _, name := range names {
		if value, exists := os.LookupEnv(name); exists {
			result = append(result, name+"="+value)
		}
	}
	return withExecutable(result)
}

func command(args []string, environment []string) (*exec.Cmd, *os.File, *os.File, error) {
	python, err := exec.LookPath("python3")
	if err != nil {
		return nil, nil, nil, errors.New("Godmode needs Python 3.9 or newer")
	}
	reader, writer, err := os.Pipe()
	if err != nil {
		return nil, nil, nil, errors.New("Godmode could not open its local engine")
	}
	// Isolated/no-site execution ignores PYTHONPATH, user startup hooks, and
	// sitecustomize. The child's environment still reaches an explicit `run`.
	argv := append([]string{"-I", "-S", "-c", bootstrap, executable()}, args...)
	cmd := exec.Command(python, argv...)
	cmd.Env = environment
	cmd.ExtraFiles = []*os.File{reader}
	return cmd, reader, writer, nil
}

func sendSource(reader, writer *os.File) {
	reader.Close()
	go func() {
		defer writer.Close()
		io.Copy(writer, strings.NewReader(source)) // Readable source only; no account data.
	}()
}

func exitCode(err error) int {
	if err == nil {
		return 0
	}
	var failure *exec.ExitError
	if errors.As(err, &failure) {
		if status, ok := failure.Sys().(syscall.WaitStatus); ok && status.Signaled() {
			return 128 + int(status.Signal())
		}
		return failure.ExitCode()
	}
	return 1
}

// Run preserves stdin/stdout/stderr, environment, child flags, and exit status.
// The native parent also relays directly addressed termination signals.
func Run(args []string) int {
	cmd, reader, writer, err := command(args, withExecutable(os.Environ()))
	if err != nil {
		fmt.Fprintln(os.Stderr, "godmode:", err)
		return 1
	}
	cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, os.Stdout, os.Stderr
	if err := cmd.Start(); err != nil {
		reader.Close()
		writer.Close()
		fmt.Fprintln(os.Stderr, "godmode: could not start Python 3")
		return 1
	}
	sendSource(reader, writer)
	signals := make(chan os.Signal, 4)
	signal.Notify(signals, os.Interrupt, syscall.SIGTERM, syscall.SIGHUP)
	defer signal.Stop(signals)
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()
	for {
		select {
		case err := <-done:
			return exitCode(err)
		case sig := <-signals:
			_ = cmd.Process.Signal(sig)
		}
	}
}

// Client serializes bounded JSON requests to one private local subprocess.
type Client struct {
	mu      sync.Mutex
	cmd     *exec.Cmd
	input   io.WriteCloser
	output  *bufio.Scanner
	done    chan error
	closed  bool
	timeout time.Duration
}

func New(home string) (*Client, error) {
	return NewForContext(home, "")
}

func NewForContext(home, context string) (*Client, error) {
	args := []string{"__ui"}
	if home != "" {
		args = append([]string{"--home", home}, args...)
	}
	if context != "" {
		args = append([]string{"--context", context}, args...)
	}
	cmd, reader, writer, err := command(args, uiEnvironment())
	if err != nil {
		return nil, err
	}
	cleanup := func() { reader.Close(); writer.Close() }
	input, err := cmd.StdinPipe()
	if err != nil {
		cleanup()
		return nil, errors.New("Godmode could not open its local engine")
	}
	output, err := cmd.StdoutPipe()
	if err != nil {
		cleanup()
		input.Close()
		return nil, errors.New("Godmode could not open its local engine")
	}
	cmd.Stderr = io.Discard // A Python traceback must never disclose request data.
	if err := cmd.Start(); err != nil {
		cleanup()
		input.Close()
		output.Close()
		return nil, errors.New("Godmode could not start Python 3")
	}
	sendSource(reader, writer)
	scanner := bufio.NewScanner(output)
	scanner.Buffer(make([]byte, 65536), maxReply+1)
	client := &Client{cmd: cmd, input: input, output: scanner, done: make(chan error, 1), timeout: 30 * time.Second}
	go func() { client.done <- cmd.Wait() }()
	return client, nil
}

func safeMessage(message string) string {
	message = strings.Map(func(r rune) rune {
		if r < 32 || r == 127 {
			return ' '
		}
		return r
	}, message)
	if len(message) > 1024 {
		message = message[:1024]
	}
	if message == "" {
		message = "Godmode could not save that change"
	}
	return message
}

func (c *Client) Call(action string, fields map[string]any) (map[string]any, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.closed {
		return nil, errors.New("Godmode's local engine is closed")
	}
	request := make(map[string]any, len(fields)+1)
	for key, value := range fields {
		request[key] = value
	}
	request["action"] = action
	data, err := json.Marshal(request)
	if err != nil || len(data) > maxRequest {
		return nil, errors.New("Godmode could not read that request")
	}
	data = append(data, '\n')
	type result struct {
		data map[string]any
		err  error
	}
	answer := make(chan result, 1)
	go func() {
		if _, err := c.input.Write(data); err != nil {
			answer <- result{err: errors.New("Godmode's local engine stopped")}
			return
		}
		if !c.output.Scan() || len(c.output.Bytes()) > maxReply {
			answer <- result{err: errors.New("Godmode's local engine returned an unreadable reply")}
			return
		}
		var reply struct {
			OK    *bool          `json:"ok"`
			Data  map[string]any `json:"data"`
			Error string         `json:"error"`
		}
		decoder := json.NewDecoder(bytes.NewReader(c.output.Bytes()))
		if err := decoder.Decode(&reply); err != nil || reply.OK == nil {
			answer <- result{err: errors.New("Godmode's local engine returned an unreadable reply")}
			return
		}
		var extra any
		if err := decoder.Decode(&extra); err != io.EOF {
			answer <- result{err: errors.New("Godmode's local engine returned an unreadable reply")}
			return
		}
		if !*reply.OK {
			answer <- result{err: errors.New(safeMessage(reply.Error))}
			return
		}
		if reply.Data == nil {
			answer <- result{err: errors.New("Godmode's local engine returned an unreadable reply")}
			return
		}
		answer <- result{data: reply.Data}
	}()
	select {
	case result := <-answer:
		return result.data, result.err
	case <-time.After(c.timeout):
		c.closed = true
		c.input.Close()
		_ = c.cmd.Process.Kill()
		<-c.done
		return nil, errors.New("Godmode's local engine took too long; reopen Godmode")
	}
}

func (c *Client) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.closed {
		return nil
	}
	c.closed = true
	c.input.Close()
	select {
	case <-c.done:
	case <-time.After(time.Second):
		_ = c.cmd.Process.Kill()
		<-c.done
	}
	return nil
}
