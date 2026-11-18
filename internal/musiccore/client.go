// Package musiccore runs the optional pack's music-only Python engine. It does
// not import or embed the Godmode credential, profile, or management engine.
package musiccore

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
	"unicode"
)

//go:embed player.py
var source string

const maxRequest = 1024 * 1024
const maxReply = 2 * 1024 * 1024
const bootstrap = `import os,sys
with os.fdopen(3, "r", encoding="utf-8") as stream:
    source=stream.read()
sys.argv=sys.argv[1:]
exec(compile(source,sys.argv[0],"exec"),{"__name__":"__main__","__file__":sys.argv[0]})
`

func Source() string { return source }
func SHA256() string { sum := sha256.Sum256([]byte(source)); return hex.EncodeToString(sum[:]) }
func executable() string {
	path, err := os.Executable()
	if err != nil {
		return "godmode-music"
	}
	return path
}

// All entry points, including text commands and setup, receive only this list.
// Ambient API keys, agent homes, Python injection settings, and business/key
// selection variables never cross into the optional pack engine.
func engineEnvironment() []string {
	names := []string{"PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "COLORTERM", "COLORFGBG", "TMPDIR", "NO_COLOR", "CLICOLOR", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR", "DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "PULSE_SERVER", "GODMODE_HOME", "GODMODE_CONFIG_DIR", "GODMODE_STATE_DIR", "GODMODE_PLAIN", "GODMODE_NO_MOTION"}
	env := make([]string, 0, len(names)+1)
	for _, name := range names {
		if value, ok := os.LookupEnv(name); ok {
			env = append(env, name+"="+value)
		}
	}
	return append(env, "GODMODE_EXECUTABLE="+executable())
}
func command(args []string) (*exec.Cmd, *os.File, *os.File, error) {
	python, err := exec.LookPath("python3")
	if err != nil {
		return nil, nil, nil, errors.New("Music needs Python 3.9 or newer")
	}
	reader, writer, err := os.Pipe()
	if err != nil {
		return nil, nil, nil, errors.New("Could not open the music engine")
	}
	argv := append([]string{"-I", "-S", "-c", bootstrap, executable()}, args...)
	cmd := exec.Command(python, argv...)
	cmd.Env = engineEnvironment()
	cmd.ExtraFiles = []*os.File{reader}
	return cmd, reader, writer, nil
}
func sendSource(reader, writer *os.File, script string) {
	reader.Close()
	go func() { defer writer.Close(); io.Copy(writer, strings.NewReader(script)) }()
}
func exitCode(err error) int {
	if err == nil {
		return 0
	}
	var failed *exec.ExitError
	if errors.As(err, &failed) {
		if status, ok := failed.Sys().(syscall.WaitStatus); ok && status.Signaled() {
			return 128 + int(status.Signal())
		}
		return failed.ExitCode()
	}
	return 1
}

// Run handles text commands through the same isolated environment as the UI.
func Run(args []string) int { return run(args, source, os.Stdin, os.Stdout, os.Stderr) }
func run(args []string, script string, input io.Reader, output, stderr io.Writer) int {
	cmd, reader, writer, err := command(args)
	if err != nil {
		fmt.Fprintln(stderr, "godmode music:", err)
		return 1
	}
	cmd.Stdin, cmd.Stdout, cmd.Stderr = input, output, stderr
	if err := cmd.Start(); err != nil {
		reader.Close()
		writer.Close()
		fmt.Fprintln(stderr, "godmode music: could not start Python 3")
		return 1
	}
	sendSource(reader, writer, script)
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

type Client struct {
	mu      sync.Mutex
	abort   sync.Once
	cmd     *exec.Cmd
	input   io.WriteCloser
	output  *bufio.Scanner
	done    chan error
	closed  bool
	timeout time.Duration
}

func New(home string) (*Client, error) {
	args := []string{"music", "__bridge"}
	if home != "" {
		args = append([]string{"--home", home}, args...)
	}
	return newClient(args, source)
}
func newClient(args []string, script string) (*Client, error) {
	cmd, reader, writer, err := command(args)
	if err != nil {
		return nil, err
	}
	cleanup := func() { reader.Close(); writer.Close() }
	input, err := cmd.StdinPipe()
	if err != nil {
		cleanup()
		return nil, errors.New("Could not open the music engine")
	}
	output, err := cmd.StdoutPipe()
	if err != nil {
		cleanup()
		input.Close()
		return nil, errors.New("Could not open the music engine")
	}
	cmd.Stderr = io.Discard
	if err := cmd.Start(); err != nil {
		cleanup()
		input.Close()
		output.Close()
		return nil, errors.New("Could not start Python 3 for music")
	}
	sendSource(reader, writer, script)
	scanner := bufio.NewScanner(output)
	scanner.Buffer(make([]byte, 65536), maxReply+1)
	client := &Client{cmd: cmd, input: input, output: scanner, done: make(chan error, 1), timeout: 30 * time.Second}
	go func() { client.done <- cmd.Wait() }()
	return client, nil
}

// Abort interrupts an outstanding read without taking the request mutex.
func (c *Client) Abort() {
	c.abort.Do(func() {
		if c.cmd != nil && c.cmd.Process != nil {
			_ = c.cmd.Process.Kill()
		}
		if c.input != nil {
			_ = c.input.Close()
		}
	})
}
func safeMessage(message string) string {
	message = strings.Map(func(r rune) rune {
		if unicode.IsControl(r) || unicode.In(r, unicode.Cf) {
			return ' '
		}
		return r
	}, message)
	runes := []rune(message)
	if len(runes) > 1024 {
		message = string(runes[:1024])
	}
	if message == "" {
		message = "Music could not complete that action"
	}
	return message
}
func (c *Client) Call(action string, fields map[string]any) (map[string]any, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.closed {
		return nil, errors.New("Music engine is closed")
	}
	request := make(map[string]any, len(fields)+1)
	for key, value := range fields {
		request[key] = value
	}
	request["action"] = action
	data, err := json.Marshal(request)
	if err != nil || len(data)+1 > maxRequest {
		return nil, errors.New("Music request is too large or invalid")
	}
	data = append(data, '\n')
	type result struct {
		data map[string]any
		err  error
	}
	answer := make(chan result, 1)
	go func() {
		if _, err := c.input.Write(data); err != nil {
			answer <- result{err: errors.New("Music engine stopped")}
			return
		}
		if !c.output.Scan() || len(c.output.Bytes()) > maxReply {
			answer <- result{err: errors.New("Music engine returned an unreadable reply")}
			return
		}
		var reply struct {
			OK    *bool          `json:"ok"`
			Data  map[string]any `json:"data"`
			Error string         `json:"error"`
		}
		decoder := json.NewDecoder(bytes.NewReader(c.output.Bytes()))
		if err := decoder.Decode(&reply); err != nil || reply.OK == nil {
			answer <- result{err: errors.New("Music engine returned an unreadable reply")}
			return
		}
		var extra any
		if err := decoder.Decode(&extra); err != io.EOF {
			answer <- result{err: errors.New("Music engine returned an unreadable reply")}
			return
		}
		if !*reply.OK {
			answer <- result{err: errors.New(safeMessage(reply.Error))}
			return
		}
		if reply.Data == nil {
			answer <- result{err: errors.New("Music engine returned an unreadable reply")}
			return
		}
		answer <- result{data: reply.Data}
	}()
	timer := time.NewTimer(c.timeout)
	defer timer.Stop()
	select {
	case result := <-answer:
		return result.data, result.err
	case <-timer.C:
		c.closed = true
		c.Abort()
		<-c.done
		return nil, errors.New("Music engine took too long; reopen music")
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
		c.Abort()
		<-c.done
	}
	return nil
}
