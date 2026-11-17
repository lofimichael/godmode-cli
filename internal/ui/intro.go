package ui

import (
	"strings"

	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"
)

// Motion is decorative, finite and independent of input. Nothing in the intro
// waits for an animation or pretends to scan a machine or grant permissions.
const introAnimationFrames = 48

var introDangerDark = []string{"#FF556D", "#FF6273", "#FF747A", "#FF8B86", "#FFA58F", "#FFC09D"}
var introDangerLight = []string{"#A41438", "#AE1B3A", "#B6263C", "#BF343E", "#A83E2D", "#90441D"}
var introPowerDark = []string{"#BE8CFF", "#B89CFF", "#AAAFFF", "#92C3FF", "#76D7EF", "#69E8D3"}
var introPowerLight = []string{"#7034BA", "#6543B6", "#5056AE", "#35699E", "#197686", "#087C68"}

func (m model) introMotionActive() bool {
	return m.page == "intro" && m.colors && !m.opts.NoMotion && m.tick < introAnimationFrames
}

func (m model) introArt() []string {
	art := smallLogo
	if m.innerWidth() >= 63 && m.height >= 22 {
		art = nfoLogo
	}
	if m.innerWidth() < 31 || m.height < 16 {
		art = []string{"G O D M O D E"}
	}
	colors := introDangerDark
	if !m.dark {
		colors = introDangerLight
	}
	if m.introStage > 0 {
		colors = introPowerDark
		if !m.dark {
			colors = introPowerLight
		}
	}
	styles := make([]lipgloss.Style, len(colors))
	for i, color := range colors {
		styles[i] = lipgloss.NewStyle().Foreground(lipgloss.Color(color)).Bold(true)
	}
	highlight := lipgloss.NewStyle().Foreground(lipgloss.Color("#FFF3E7")).Bold(true)
	if !m.dark {
		highlight = lipgloss.NewStyle().Foreground(lipgloss.Color("#24123F")).Bold(true)
	}
	rows := make([]string, 0, len(art))
	for y, row := range art {
		if !m.colors {
			rows = append(rows, m.introCenter(row))
			continue
		}
		// A diagonal sheen travels over the letters once, then leaves a quiet
		// gradient. Render whole runs of the same color, not one ANSI reset per
		// cell. The letterforms never flicker, disappear or change meaning.
		var line strings.Builder
		rowWidth := ansi.StringWidth(row)
		x, run := 0, ""
		last := -1
		flush := func() {
			if run == "" {
				return
			}
			if last == len(styles) {
				line.WriteString(highlight.Render(run))
			} else {
				line.WriteString(styles[max(0, last)].Render(run))
			}
			run = ""
		}
		for _, ch := range row {
			ink := min(len(styles)-1, (x+y*3)*len(styles)/max(1, rowWidth+len(art)*3))
			if m.introMotionActive() {
				head := m.tick*2 - 12
				if x+y >= head-2 && x+y <= head+2 {
					ink = len(styles)
				}
			}
			if ink != last {
				flush()
				last = ink
			}
			run += string(ch)
			x++
		}
		flush()
		rows = append(rows, m.introCenter(line.String()))
	}
	return rows
}

func (m model) introCenter(text string) string {
	width := m.innerWidth()
	text = ansi.Truncate(text, width, "…")
	return strings.Repeat(" ", max(0, (width-ansi.StringWidth(text))/2)) + text
}

func (m model) introText(text string, style lipgloss.Style) []string {
	width := min(m.innerWidth(), 66)
	rows := strings.Split(ansi.Wrap(text, width, ""), "\n")
	for i := range rows {
		if m.colors {
			rows[i] = style.Render(rows[i])
		}
		rows[i] = m.introCenter(rows[i])
	}
	return rows
}

func (m model) introRail() string {
	w := min(m.innerWidth(), 72)
	if w < 12 {
		return ""
	}
	runes := []rune("╶" + strings.Repeat("─", w-2) + "╴")
	if m.introMotionActive() {
		head := (m.tick * 2) % (w - 4)
		runes[head+1], runes[head+2] = '▪', '◆'
	}
	style := m.palette().bad
	if m.introStage > 0 {
		style = m.palette().cyan
	}
	return m.introCenter(style.Render(string(runes)))
}

func (m model) introCircuit() []string {
	p := m.palette()
	var rows []string
	if m.innerWidth() >= 64 {
		rows = []string{
			"┌───────────┐        ┌────────────┐        ┌───────────┐",
			"│ YOUR KEYS ├────────┤ YOUR AGENT ├────────┤ YOUR APP  │",
			"└───────────┘        └────────────┘        └───────────┘",
		}
		if m.introMotionActive() {
			cells := []rune(rows[1])
			// Only the connector cells move. Labels remain readable on every
			// frame and indicate a relationship, never completed work.
			for _, start := range []int{13, 35} {
				at := start + (m.tick/2)%7
				if at < len(cells) {
					cells[at] = '▶'
				}
			}
			rows[1] = string(cells)
		}
	} else {
		rows = []string{"YOUR KEYS → YOUR AGENT", "↓", "BUILD  ·  FIX  ·  DEPLOY"}
	}
	for i, row := range rows {
		rows[i] = m.introCenter(p.cyan.Render(row))
	}
	return rows
}

func (m model) cinematicIntroLines() []string {
	p := m.palette()
	roomy := m.height >= 18
	rows := m.introArt()
	if roomy {
		rows = append(rows, "", m.introRail(), "")
	}
	if m.introStage == 0 {
		rows = append(rows, m.introText("You will fuck shit up if you don't know what you're doing.", p.bad.Bold(true))...)
		if roomy {
			rows = append(rows, "")
		}
		rows = append(rows, m.introText("Agents use your keys as you.", p.title)...)
		rows = append(rows, m.introText("They can spend money, publish and delete data.", p.warn)...)
		if roomy {
			rows = append(rows, "")
		}
		rows = append(rows, m.introText("Your accounts. Your consequences.", p.muted)...)
	} else {
		rows = append(rows, m.introText("Put your agent to fucking work.", p.title)...)
		if roomy {
			rows = append(rows, "")
		}
		if m.height >= 18 {
			rows = append(rows, m.introCircuit()...)
		} else {
			rows = append(rows, m.introText("Your keys → your agent → your app", p.cyan)...)
		}
		if roomy {
			rows = append(rows, "")
		}
		rows = append(rows, m.introText("Keys stay local. You set the limits.", p.muted)...)
	}
	return rows
}

func (m model) cinematicIntroFits() bool {
	return m.introRowsFit(m.cinematicIntroLines())
}

func (m model) introRowsFit(rows []string) bool {
	leading := 0
	if m.height > 12 {
		leading = 1
	}
	return m.width >= 28 && len(rows)+2+leading <= m.height
}

func (m model) cinematicIntroView() []string {
	p := m.palette()
	rows := m.cinematicIntroLines()
	if !m.introRowsFit(rows) {
		return append(m.styledWrap("Enlarge the terminal to read the account-access statement.", p.warn), "", p.muted.Render("Esc exits"))
	}
	if m.error != "" {
		rows = append(rows, m.introText(m.error, p.bad)...)
	}
	action := "Enter I understand  ·  Esc exit"
	if m.introStage > 0 {
		action = "Enter open Godmode  ·  Esc exit"
		if m.initialRoute == "intro" {
			action = "Enter finish  ·  Esc exit"
		}
	}
	if m.innerWidth() < 31 {
		action = "Enter continue · Esc exit"
	}
	rows = append(rows, "", m.introCenter(p.title.Render(action)))
	// Keep the small scene poised in a large terminal without introducing
	// blank-screen frames or letting decorative padding hide the controls.
	leading := 0
	if m.height > 12 {
		leading = 1
	}
	pad := min(3, max(0, (m.height-leading-len(rows))/2))
	return append(make([]string, pad), rows...)
}
