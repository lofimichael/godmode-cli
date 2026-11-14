package ui

import (
	"bytes"
	"errors"
	"io"
	"os"
	"sync"
	"sync/atomic"
	"time"
	"unicode/utf8"

	"golang.org/x/sys/unix"
)

const pasteLimit = 1024 * 1024

var errPasteTooLarge = errors.New("Paste exceeds 1 MiB. Nothing was saved.")
var errPasteInvalidText = errors.New("Paste contains invalid UTF-8 or a replacement character. Nothing was saved.")

// pasteInput recognizes only bracketed-paste boundaries. Bubble Tea still owns
// keys and escape sequences. Holding each paste until its end keeps its decoder
// bounded and lets Ctrl-C/Ctrl-D cancel an interrupted paste.
type pasteInput struct {
	file    *os.File
	mu      sync.Mutex
	stopped atomic.Bool
	parser  pasteBytes
	output  []byte
}

type pasteBytes struct {
	prefix, content          []byte
	inPaste, over, cancelled bool
	err                      error
}

var pasteStart = []byte("\x1b[200~")
var pasteEnd = []byte("\x1b[201~")

func (p *pasteBytes) feed(data []byte) []byte {
	var out []byte
	for _, b := range data {
		if p.cancelled {
			break
		}
		if b == 3 || b == 4 {
			p.cancelled = true
			clear(p.content)
			p.content, p.prefix = nil, nil
			return []byte{3}
		}
		marker := pasteStart
		if p.inPaste {
			marker = pasteEnd
		}
		p.prefix = append(p.prefix, b)
		for len(p.prefix) > 0 && !bytes.HasPrefix(marker, p.prefix) {
			if p.inPaste {
				if len(p.content) < pasteLimit+len(pasteStart) && !p.over {
					p.content = append(p.content, p.prefix[0])
				} else {
					p.over = true
					clear(p.content)
					p.content = nil
				}
			} else {
				out = append(out, p.prefix[0])
			}
			p.prefix = p.prefix[1:]
		}
		if bytes.Equal(p.prefix, marker) {
			p.prefix = nil
			if !p.inPaste {
				p.inPaste = true
				p.content = append(make([]byte, 0, pasteLimit+12), pasteStart...)
			} else {
				p.inPaste = false
				if p.over {
					p.err, p.cancelled = errPasteTooLarge, true
					return []byte{3}
				}
				// The terminal decoder drops RuneError, including valid literal
				// U+FFFD. Refuse those bytes rather than silently change a key.
				body := p.content[len(pasteStart):]
				if !utf8.Valid(body) || bytes.Contains(body, []byte("\ufffd")) {
					p.err, p.cancelled = errPasteInvalidText, true
					clear(p.content)
					p.content = nil
					return []byte{3}
				}
				p.content = append(p.content, pasteEnd...)
				if len(out) == 0 {
					out = p.content
				} else {
					out = append(out, p.content...)
					clear(p.content)
				}
				p.content = nil
			}
		}
	}
	return out
}

func (p *pasteInput) Fd() uintptr                 { return p.file.Fd() }
func (p *pasteInput) Write(b []byte) (int, error) { return p.file.Write(b) }
func (p *pasteInput) Close() error                { p.stop(); return nil }

func (p *pasteInput) Read(dst []byte) (int, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	for len(p.output) == 0 {
		if p.stopped.Load() || p.parser.cancelled {
			return 0, io.EOF
		}
		fds := []unix.PollFd{{Fd: int32(p.file.Fd()), Events: unix.POLLIN}}
		n, err := unix.Poll(fds, 40)
		if errors.Is(err, unix.EINTR) {
			continue
		}
		if err != nil {
			return 0, err
		}
		if n == 0 {
			// A lone Escape belongs to Bubble Tea after its normal short delay.
			if !p.parser.inPaste && len(p.parser.prefix) > 0 {
				p.output, p.parser.prefix = p.parser.prefix, nil
			}
			continue
		}
		var chunk [4096]byte
		n, err = unix.Read(int(p.file.Fd()), chunk[:])
		if errors.Is(err, unix.EINTR) || errors.Is(err, unix.EAGAIN) {
			continue
		}
		if err != nil {
			return 0, err
		}
		if n == 0 {
			return 0, io.EOF
		}
		p.output = p.parser.feed(chunk[:n])
		clear(chunk[:])
	}
	n := copy(dst, p.output)
	clear(p.output[:n])
	p.output = p.output[n:]
	return n, nil
}

// stop runs from the Quit filter, before Bubble Tea restores terminal echo.
// Cancel the reader, then discard queued bytes until 80 ms of quiet (at most
// 500 ms total), matching the readable core's bounded teardown behavior.
func (p *pasteInput) stop() {
	if p.stopped.Swap(true) {
		return
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	clear(p.output)
	clear(p.parser.content)
	p.output, p.parser.content, p.parser.prefix = nil, nil, nil
	deadline := time.Now().Add(500 * time.Millisecond)
	for time.Now().Before(deadline) {
		fds := []unix.PollFd{{Fd: int32(p.file.Fd()), Events: unix.POLLIN}}
		n, err := unix.Poll(fds, 80)
		if errors.Is(err, unix.EINTR) {
			continue
		}
		if err != nil || n == 0 {
			break
		}
		var discard [4096]byte
		n, err = unix.Read(int(p.file.Fd()), discard[:])
		clear(discard[:])
		if err != nil || n == 0 {
			break
		}
	}
}
