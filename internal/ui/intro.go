package ui

import (
	"strings"

	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"
)

// Motion is decorative, repeating and independent of input. Nothing in the intro
// waits for an animation or pretends to scan a machine or grant permissions.
const introCycleFrames = 96

var introDangerDark = []string{"#FF556D", "#FF6273", "#FF747A", "#FF8B86", "#FFA58F", "#FFC09D"}
var introDangerLight = []string{"#A41438", "#AE1B3A", "#B6263C", "#BF343E", "#A83E2D", "#90441D"}
var introPowerDark = []string{"#BE8CFF", "#B89CFF", "#AAAFFF", "#92C3FF", "#76D7EF", "#69E8D3"}
var introPowerLight = []string{"#7034BA", "#6543B6", "#5056AE", "#35699E", "#197686", "#087C68"}

func (m model) introMotionActive() bool {
	return m.page == "intro" && m.colors && !m.opts.NoMotion && !m.quitting
}

func (m model) introPhase() int { return m.tick % introCycleFrames }

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
	styles := make([]lipgloss.Style, len(colors), len(colors)+3)
	for i, color := range colors {
		styles[i] = lipgloss.NewStyle().Foreground(lipgloss.Color(color)).Bold(true)
	}
	// Feather the sweep rather than flashing a hard white band. The head moves
	// one cell per frame and leaves the art before the cycle wraps around.
	sheen := []string{"#FFF3E7", "#FFDBC8", "#FFB5A6"}
	if m.introStage > 0 {
		sheen = []string{"#F3FDFF", "#CDF5F5", "#A5D8EE"}
	}
	if !m.dark {
		sheen = []string{"#24123F", "#58304B", "#92414B"}
		if m.introStage > 0 {
			sheen = []string{"#161C42", "#293E69", "#395C89"}
		}
	}
	for _, color := range sheen {
		styles = append(styles, lipgloss.NewStyle().Foreground(lipgloss.Color(color)).Bold(true))
	}
	rows := make([]string, 0, len(art))
	motion, head := m.introMotionActive(), m.introPhase()-12
	for y, row := range art {
		if !m.colors {
			rows = append(rows, m.introCenter(row))
			continue
		}
		// Render whole runs of the same color, not one ANSI reset per
		// cell. The letterforms never flicker, disappear or change meaning.
		var line strings.Builder
		rowWidth := ansi.StringWidth(row)
		x, run := 0, ""
		last := -1
		flush := func() {
			if run == "" {
				return
			}
			line.WriteString(styles[max(0, last)].Render(run))
			run = ""
		}
		for _, ch := range row {
			ink := min(len(colors)-1, (x+y*3)*len(colors)/max(1, rowWidth+len(art)*3))
			if motion {
				distance := max(x+y-head, head-x-y)
				if distance < len(sheen) {
					ink = len(colors) + distance
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
		// Enter and leave through invisible cells. At the wrap boundary both
		// frames show the quiet rail, so the pulse never jumps across the view.
		head := m.introPhase()*(w+8)/introCycleFrames - 4
		for offset, ch := range []rune{'▪', '◆'} {
			if at := head + offset; at > 0 && at < w-1 {
				runes[at] = ch
			}
		}
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
			head := m.introPhase()*24/introCycleFrames - 4
			for segment, start := range []int{13, 35} {
				if offset := head - segment*8; offset >= 0 && offset < 8 {
					cells[start+offset] = '▶'
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
	escape := "Esc to exit"
	if len(m.trail) > 0 {
		escape = "Esc back"
	}
	if !m.introRowsFit(rows) {
		return append(m.styledWrap("Enlarge the terminal to read the account-access statement.", p.warn), "", p.muted.Render(escape))
	}
	if m.error != "" {
		rows = append(rows, m.introText(m.error, p.bad)...)
	}
	action := "Enter to continue"
	if m.introStage > 0 {
		action = "Enter to open Godmode"
		if m.initialRoute == "intro" || len(m.trail) > 0 {
			action = "Enter to finish"
		}
	}
	if ansi.StringWidth(action+"  ·  "+escape) > m.innerWidth() {
		action = strings.Replace(action, " to ", " ", 1)
		action = strings.TrimSuffix(action, " Godmode")
	}
	action += " · " + escape
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
