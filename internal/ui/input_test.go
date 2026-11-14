package ui

import (
	"bytes"
	"testing"
)

func TestPasteGuardPreservesCompleteFragmentedPaste(t *testing.T) {
	p := pasteBytes{}
	wire := append(append(append([]byte{}, pasteStart...), []byte("synthetic\nprivate\r\nvalue")...), pasteEnd...)
	var got []byte
	for i, b := range wire {
		got = append(got, p.feed([]byte{b})...)
		if i < len(wire)-1 && len(got) != 0 {
			t.Fatal("partial paste reached terminal decoder")
		}
	}
	if !bytes.Equal(got, wire) {
		t.Fatal("complete paste changed")
	}
}

func TestPasteGuardCancelsIncompletePasteAndDiscardsTail(t *testing.T) {
	for _, cancel := range []byte{3, 4} {
		p := pasteBytes{}
		if got := p.feed(append(append([]byte{}, pasteStart...), []byte("synthetic-private")...)); len(got) != 0 {
			t.Fatal("partial paste escaped")
		}
		if got := p.feed(append([]byte{cancel}, []byte("shell-command\r")...)); !bytes.Equal(got, []byte{3}) {
			t.Fatal("cancellation did not replace all pending input")
		}
		if len(p.feed([]byte("late-shell-command\r"))) != 0 || len(p.content) != 0 {
			t.Fatal("cancelled paste retained input")
		}
	}
}

func TestPasteGuardBoundsOversizedPasteBeforeDecoder(t *testing.T) {
	p := pasteBytes{}
	p.feed(pasteStart)
	chunk := bytes.Repeat([]byte{'x'}, 4096)
	for i := 0; i < 512; i++ {
		if got := p.feed(chunk); len(got) != 0 {
			t.Fatal("oversized partial paste escaped")
		}
		if len(p.content) > pasteLimit+len(pasteStart) {
			t.Fatal("paste buffer exceeded bound")
		}
	}
	if !p.over || len(p.content) != 0 {
		t.Fatal("oversized paste was retained")
	}
	if got := p.feed(append(append([]byte{}, pasteEnd...), []byte("shell-command\r")...)); !bytes.Equal(got, []byte{3}) || p.err != errPasteTooLarge {
		t.Fatal("oversized paste was not safely refused")
	}
}

func TestPasteGuardLeavesKeySequencesToBubbleTea(t *testing.T) {
	p := pasteBytes{}
	wire := []byte("text\x1b[A\x1b[1;5D\r")
	if got := p.feed(wire); !bytes.Equal(got, wire) {
		t.Fatal("ordinary keys changed")
	}
}

func TestPasteGuardRefusesTextTheDecoderWouldSilentlyChange(t *testing.T) {
	for _, body := range [][]byte{[]byte("synthetic_\ufffd_value"), {'s', 0xff, 'x'}} {
		p := pasteBytes{}
		wire := append(append(append([]byte{}, pasteStart...), body...), pasteEnd...)
		if got := p.feed(wire); !bytes.Equal(got, []byte{3}) || p.err != errPasteInvalidText {
			t.Fatal("alterable credential text was not refused")
		}
		if len(p.content) != 0 {
			t.Fatal("refused paste was retained")
		}
	}
	p := pasteBytes{}
	wire := append(append(append([]byte{}, pasteStart...), []byte("synthetic_é_日本語_value")...), pasteEnd...)
	if got := p.feed(wire); !bytes.Equal(got, wire) {
		t.Fatal("valid Unicode paste changed")
	}
}
