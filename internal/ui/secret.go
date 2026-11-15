package ui

import (
	"errors"
	"os"
	"strings"
	"unicode/utf8"

	tea "charm.land/bubbletea/v2"
)

// ReadSecret uses the same bounded paste reader and terminal teardown as key
// onboarding. It needs no credential store or activated backend.
func ReadSecret(prompt string, file *os.File) (string, error) {
	input := &pasteInput{file: file}
	defer input.stop()
	m := secretModel{prompt: strings.TrimSpace(prompt)}
	final, err := tea.NewProgram(m, tea.WithInput(input), tea.WithOutput(os.Stderr), tea.WithFilter(func(_ tea.Model, msg tea.Msg) tea.Msg {
		switch msg.(type) {
		case tea.QuitMsg, tea.InterruptMsg:
			input.stop()
		}
		return msg
	})).Run()
	input.stop()
	if input.parser.err != nil {
		return "", input.parser.err
	}
	if err != nil {
		return "", ErrCancelled
	}
	result, ok := final.(secretModel)
	if !ok {
		return "", errors.New("Godmode could not read that input.")
	}
	if result.cancelled {
		return "", ErrCancelled
	}
	return strings.TrimSpace(result.text), nil
}

type secretModel struct {
	prompt, text, problem string
	done, cancelled       bool
}

func (m secretModel) Init() tea.Cmd { return nil }

func (m secretModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.PasteMsg:
		if len(msg.Content) > 1024 {
			m.text = ""
			m.problem = "Input exceeds 1 KiB."
		} else {
			m.text = msg.Content
			m.problem = ""
		}
		return m, nil
	case tea.KeyPressMsg:
		switch msg.String() {
		case "ctrl+c", "ctrl+d", "esc":
			m.text = ""
			m.cancelled = true
			m.done = true
			return m, tea.Quit
		case "enter":
			if m.problem == "" {
				m.done = true
				return m, tea.Quit
			}
		case "backspace":
			r := []rune(m.text)
			if len(r) > 0 {
				m.text = string(r[:len(r)-1])
			}
			m.problem = ""
		case "ctrl+u":
			m.text = ""
			m.problem = ""
		default:
			add := printable(msg.Text)
			if len(m.text)+len(add) <= 1024 {
				m.text += add
			} else {
				m.problem = "Input exceeds 1 KiB."
			}
		}
	}
	return m, nil
}

func (m secretModel) View() tea.View {
	if m.done {
		return tea.NewView("")
	}
	mask := strings.Repeat("*", min(32, utf8.RuneCountInString(m.text)))
	text := m.prompt + "\n" + mask + "\n"
	if m.problem != "" {
		text += "\n" + m.problem + "\n"
	}
	return tea.NewView(text + "\nEnter confirm  Esc cancel")
}
