package ui

import (
	"fmt"
	"strings"
	"testing"

	"github.com/charmbracelet/x/ansi"
)

func introWords(rows []string) string {
	return strings.Join(strings.Fields(ansi.Strip(strings.Join(rows, "\n"))), " ")
}

func TestCinematicIntroMeaningNeverDependsOnAnimation(t *testing.T) {
	m := create(t, fake(), "intro", "")
	m.opts.NoMotion = false
	m.colors, m.width, m.height = true, 80, 24
	for frame := 0; frame <= introAnimationFrames+2; frame++ {
		m.tick = frame
		m.introStage = 0
		text := introWords(m.cinematicIntroView())
		for _, want := range []string{
			"You will fuck shit up if you don't know what you're doing.",
			"Agents use your keys as you.",
			"They can spend money, publish and delete data.",
			"Your accounts. Your consequences.",
			"Enter I understand", "Esc exit",
		} {
			if !strings.Contains(text, want) {
				t.Fatalf("frame %d hides %q", frame, want)
			}
		}
		m.introStage = 1
		text = introWords(m.cinematicIntroView())
		for _, want := range []string{"Put your agent to fucking work.", "YOUR KEYS", "YOUR AGENT", "YOUR APP", "Keys stay local. You set the limits.", "Enter finish"} {
			if !strings.Contains(text, want) {
				t.Fatalf("frame %d hides %q", frame, want)
			}
		}
	}
}

func TestCinematicIntroFitsUsefulTerminalsAndBothThemes(t *testing.T) {
	for _, size := range [][2]int{{40, 18}, {80, 24}, {100, 32}, {160, 48}} {
		for _, dark := range []bool{false, true} {
			for _, colors := range []bool{false, true} {
				for stage := 0; stage < 2; stage++ {
					t.Run(fmt.Sprintf("%dx%d-dark%v-colors%v-stage%d", size[0], size[1], dark, colors, stage), func(t *testing.T) {
						m := create(t, fake(), "intro", "")
						m.width, m.height, m.dark, m.colors, m.introStage = size[0], size[1], dark, colors, stage
						if !m.cinematicIntroFits() {
							t.Fatal("intro unnecessarily requires a larger terminal")
						}
						rows := m.cinematicIntroView()
						if len(rows)+1 > m.height {
							t.Fatal("intro exceeds available height")
						}
						for _, row := range rows {
							if ansi.StringWidth(row) > m.innerWidth() {
								t.Fatal("intro exceeds available width")
							}
							if !colors && row != ansi.Strip(row) {
								t.Fatal("NO_COLOR produced ANSI styling")
							}
						}
						if !strings.Contains(introWords(rows), "Esc exit") {
							t.Fatal("exit control is missing")
						}
					})
				}
			}
		}
	}
}

func TestCinematicIntroReducedMotionAndFiniteMotion(t *testing.T) {
	m := create(t, fake(), "intro", "")
	m.colors, m.width, m.height = true, 80, 24
	for stage := 0; stage < 2; stage++ {
		m.introStage = stage
		m.opts.NoMotion = true
		m.tick = 0
		first := strings.Join(m.cinematicIntroView(), "\n")
		m.tick = 20
		if first != strings.Join(m.cinematicIntroView(), "\n") {
			t.Fatal("reduced-motion scene still changes with ticks")
		}
		m.opts.NoMotion = false
		m.tick = 0
		if !m.introMotionActive() {
			t.Fatal("intro does not animate")
		}
		m.tick = introAnimationFrames
		if m.introMotionActive() {
			t.Fatal("settled intro keeps animating")
		}
		first = strings.Join(m.cinematicIntroView(), "\n")
		m.tick += 20
		if first != strings.Join(m.cinematicIntroView(), "\n") {
			t.Fatal("settled scene is not stable")
		}
	}
	for _, page := range []string{"home", "key", "agents"} {
		m.page, m.tick = page, 0
		if m.introMotionActive() {
			t.Fatal("intro animation continues outside intro")
		}
	}
}

func TestCinematicIntroAdvancesImmediatelyAndAcknowledgesOnlyAtEnd(t *testing.T) {
	f := fake()
	f.state["intro_seen"] = false
	m := create(t, f, "intro", "")
	m.opts.NoMotion, m.colors = false, true
	m.tick = 0
	m = enter(m)
	if m.introStage != 1 || m.quitting || count(f.calls, "accept_intro") != 0 {
		t.Fatal("first Enter was delayed or acknowledged both cards")
	}
	if m.tick != 0 {
		t.Fatal("power card did not start its own finite animation")
	}
	m = enter(m)
	if !m.quitting || count(f.calls, "accept_intro") != 1 {
		t.Fatal("second Enter waited for animation or failed to acknowledge")
	}
	for stage := 0; stage < 2; stage++ {
		f := fake()
		m := create(t, f, "intro", "")
		m.introStage = stage
		m = escape(m)
		if !m.quitting || count(f.calls, "accept_intro") != 0 {
			t.Fatal("Escape did not cancel without acknowledgement")
		}
	}
}

func BenchmarkCinematicIntroFrame(b *testing.B) {
	m := model{page: "intro", width: 80, height: 24, colors: true, dark: true, introStage: 1}
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		m.tick = i % introAnimationFrames
		_ = m.cinematicIntroView()
	}
}
