package ui

import (
	"image/color"
	"strings"
	"sync"
	"testing"
	"time"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"
)

// Blocking a synthetic action proves that Update dispatches it without waiting
// and allows rendering, resize and cancellation while the command is in flight.
type gatedBackend struct {
	mu      sync.Mutex
	base    *fakeBackend
	action  string
	started chan struct{}
	release chan struct{}
	once    sync.Once
	end     sync.Once
	calls   map[string]int
}

func newGatedBackend(t *testing.T, action string) *gatedBackend {
	t.Helper()
	b := &gatedBackend{base: fake(), action: action, started: make(chan struct{}), release: make(chan struct{}), calls: map[string]int{}}
	t.Cleanup(b.unblock)
	return b
}

func (b *gatedBackend) unblock() { b.end.Do(func() { close(b.release) }) }

func (b *gatedBackend) Call(action string, args map[string]any) (map[string]any, error) {
	b.mu.Lock()
	b.calls[action]++
	b.mu.Unlock()
	if action == b.action {
		b.once.Do(func() { close(b.started) })
		<-b.release
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.base.Call(action, args)
}

func (b *gatedBackend) count(action string) int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.calls[action]
}

func asyncModel(t *testing.T, backend Backend, route, arg string) model {
	t.Helper()
	m, err := newModel(backend, route, arg, Options{NoMotion: true})
	if err != nil {
		t.Fatal(err)
	}
	return m
}

func updateAsync(m model, msg tea.Msg) (model, tea.Cmd) {
	next, cmd := m.Update(msg)
	return next.(model), cmd
}

// Advance only the worker. Delayed busy/pulse messages are injected explicitly,
// so correctness checks need neither sleeping nor a live terminal.
func asyncWorker(t *testing.T, cmd tea.Cmd) tea.Cmd {
	t.Helper()
	if cmd == nil {
		t.Fatal("no asynchronous command returned")
	}
	batch, ok := cmd().(tea.BatchMsg)
	if !ok || len(batch) != 2 {
		t.Fatal("expected operation and delayed activity commands")
	}
	return batch[0]
}

func runAsyncWorker(t *testing.T, backend *gatedBackend, work tea.Cmd) <-chan tea.Msg {
	t.Helper()
	result := make(chan tea.Msg, 1)
	go func() { result <- work() }()
	select {
	case <-backend.started:
	case <-time.After(3 * time.Second):
		t.Fatal("worker did not reach the backend")
	}
	return result
}

func asyncResult(t *testing.T, result <-chan tea.Msg) tea.Msg {
	t.Helper()
	select {
	case msg := <-result:
		return msg
	case <-time.After(3 * time.Second):
		t.Fatal("released worker did not complete")
		return nil
	}
}

func TestAsyncDispatchKeepsNavigationAndReadsResponsive(t *testing.T) {
	b := newGatedBackend(t, "agents_plan")
	m := asyncModel(t, b, "home", "")
	m, cmd := updateAsync(m, key(tea.KeyDown, ""))
	if m.selected != 1 || m.busy || cmd != nil {
		t.Fatal("ordinary navigation was delayed")
	}
	m, cmd = updateAsync(m, key(tea.KeyEnter, ""))
	if !m.busy || m.page != "home" || b.count("agents_plan") != 0 {
		t.Fatal("Update ran the read or replaced the visible page before dispatch")
	}
	result := runAsyncWorker(t, b, asyncWorker(t, cmd))
	if m.busyVisible || m.loadingText() != "" {
		t.Fatal("fast work immediately showed a loading indicator")
	}
	m, cmd = updateAsync(m, busyMsg{m.operationID})
	if !m.busyVisible || !strings.Contains(m.loadingText(), "Reading agent instructions") || cmd != nil {
		t.Fatal("no-motion loading feedback is missing or keeps ticking")
	}
	if m.View().Content == "" {
		t.Fatal("pending operation prevented rendering")
	}
	b.unblock()
	m, _ = updateAsync(m, asyncResult(t, result))
	if m.busy || m.busyVisible || m.page != "agent_home" || b.count("agents_plan") != 1 {
		t.Fatal("completed operation did not settle on the requested page")
	}
	m, cmd = updateAsync(m, busyMsg{m.operationID})
	if m.busyVisible || cmd != nil {
		t.Fatal("late loading timer revived a completed operation")
	}
}

func TestAsyncSaveIgnoresDuplicateSubmissions(t *testing.T) {
	b := newGatedBackend(t, "key_save")
	m := asyncModel(t, b, "set", "EXAMPLE_TOKEN")
	value := "synthetic_pending_secret_123"
	m, _ = updateAsync(m, tea.PasteMsg{Content: value})
	m, cmd := updateAsync(m, key(tea.KeyEnter, ""))
	result := runAsyncWorker(t, b, asyncWorker(t, cmd))
	id := m.operationID
	for _, msg := range []tea.Msg{key(tea.KeyEnter, ""), key(tea.KeyEnter, ""), tea.PasteMsg{Content: "replacement"}, key(tea.KeyEscape, "")} {
		m, cmd = updateAsync(m, msg)
		if cmd != nil || !m.busy || m.operationID != id || m.text != value {
			t.Fatal("a pending save accepted a duplicate submit or changed its candidate")
		}
	}
	if strings.Contains(m.View().Content, value) {
		t.Fatal("pending save rendered the raw value")
	}
	b.unblock()
	m, cmd = updateAsync(m, asyncResult(t, result))
	if !m.quitting || m.busy || m.text != "" || cmd == nil {
		t.Fatal("direct set did not finish after its receipt")
	}
	if b.count("key_save") != 1 || b.base.saved != value {
		t.Fatal("save did not execute exactly once with the reviewed candidate")
	}
}

func TestAsyncRefreshDoesNotMutateVisibleSnapshotBeforeDelivery(t *testing.T) {
	b := newGatedBackend(t, "key_save")
	b.base.state["profile"] = map[string]string{"name": "Before"}
	m := asyncModel(t, b, "set", "EXAMPLE_TOKEN")
	m, _ = updateAsync(m, tea.PasteMsg{Content: "synthetic_snapshot_candidate"})
	// The backend's next state differs from the last published UI snapshot.
	b.base.state["profile"] = map[string]string{"name": "After"}
	b.base.state["states"] = map[string]string{"EXAMPLE_TOKEN": "set"}
	b.base.state["providers"].([]any)[0].(map[string]any)["name"] = "Updated Provider"
	m, cmd := updateAsync(m, key(tea.KeyEnter, ""))
	result := runAsyncWorker(t, b, asyncWorker(t, cmd))
	b.unblock()
	reply := asyncResult(t, result)
	if m.state.Profile["name"] != "Before" || m.state.States["EXAMPLE_TOKEN"] != "" || m.state.Providers[0].Name != "Example" {
		t.Fatal("worker refresh changed shared maps or slices before its result was delivered")
	}
	m, _ = updateAsync(m, reply)
	if m.state.Profile["name"] != "After" || m.state.States["EXAMPLE_TOKEN"] != "set" || m.state.Providers[0].Name != "Updated Provider" {
		t.Fatal("completed refresh did not publish its new snapshot")
	}
}

func TestAsyncCtrlCCannotBeUndoneByLateSaveResult(t *testing.T) {
	b := newGatedBackend(t, "key_save")
	m := asyncModel(t, b, "set", "EXAMPLE_TOKEN")
	m, _ = updateAsync(m, tea.PasteMsg{Content: "synthetic_interrupt_candidate"})
	m, cmd := updateAsync(m, key(tea.KeyEnter, ""))
	result := runAsyncWorker(t, b, asyncWorker(t, cmd))
	cancel := tea.KeyPressMsg(tea.Key{Code: 'c', Mod: tea.ModCtrl})
	m, cmd = updateAsync(m, cancel)
	if !m.quitting || m.outcome != ErrCancelled || m.text != "" || cmd == nil {
		t.Fatal("Ctrl-C could not immediately exit a pending backend operation")
	}
	b.unblock()
	m, cmd = updateAsync(m, asyncResult(t, result))
	if !m.quitting || m.outcome != ErrCancelled || m.text != "" || cmd != nil {
		t.Fatal("late completion resurrected cancelled input or replaced the exit outcome")
	}
	// Interruption is not rollback: this deliberately released synthetic backend
	// may have saved. The UI must not report that a committed change was undone.
	if b.count("key_save") != 1 {
		t.Fatal("cancellation issued another save")
	}
}

func TestAsyncCompletionPreservesLivePresentationAndReviewBoundary(t *testing.T) {
	b := newGatedBackend(t, "agents_plan")
	b.base.longAgent = true
	m := asyncModel(t, b, "home", "")
	m.selected = 1
	m, cmd := updateAsync(m, key(tea.KeyEnter, ""))
	result := runAsyncWorker(t, b, asyncWorker(t, cmd))
	m, _ = updateAsync(m, tea.WindowSizeMsg{Width: 42, Height: 18})
	m, _ = updateAsync(m, tea.BackgroundColorMsg{Color: color.RGBA{R: 255, G: 255, B: 255, A: 255}})
	if m.width != 42 || m.height != 18 || m.dark {
		t.Fatal("presentation events were blocked during work")
	}
	b.unblock()
	m, _ = updateAsync(m, asyncResult(t, result))
	if m.width != 42 || m.height != 18 || m.dark || m.page != "agent_home" {
		t.Fatal("worker restored outdated terminal dimensions or background")
	}
	m = openAgentDiff(t, m)
	if m.scroll != 0 || m.reviewedUntil >= len(m.agentLines()) {
		t.Fatal("resize falsely marked unseen agent instructions reviewed")
	}
	lines := strings.Split(m.View().Content, "\n")
	if len(lines) > m.height {
		t.Fatal("completed view exceeds the resized height")
	}
	for _, line := range lines {
		if ansi.StringWidth(line) > m.width {
			t.Fatal("completed view exceeds the resized width")
		}
	}
}

func TestAsyncStaleResultsCannotReplaceCurrentOperation(t *testing.T) {
	b := newGatedBackend(t, "agents_plan")
	m := asyncModel(t, b, "home", "")
	m.selected = 1
	m, cmd := updateAsync(m, key(tea.KeyEnter, ""))
	work := asyncWorker(t, cmd)
	wrong := m
	wrong.page, wrong.text = "key", "unrelated_stale_candidate"
	m, cmd = updateAsync(m, operationMsg{id: m.operationID - 1, next: wrong, cmd: tea.Quit})
	if !m.busy || m.page != "home" || m.text != "" || cmd != nil {
		t.Fatal("stale result changed the pending operation")
	}
	m, cmd = updateAsync(m, busyMsg{id: m.operationID - 1})
	if m.busyVisible || cmd != nil {
		t.Fatal("stale activity message showed another operation's loader")
	}
	b.unblock()
	m, _ = updateAsync(m, work())
	m, cmd = updateAsync(m, operationMsg{id: m.operationID, next: wrong, cmd: tea.Quit})
	if m.busy || m.page != "agent_home" || m.text != "" || cmd != nil {
		t.Fatal("duplicate result replaced an already completed operation")
	}
}

func TestAsyncLargePasteValidatesWithoutSubmittingOrRevealingValue(t *testing.T) {
	b := newGatedBackend(t, "key_check")
	m := asyncModel(t, b, "set", "EXAMPLE_TOKEN")
	value := strings.Repeat("synthetic_large_paste_", 300)
	m, cmd := updateAsync(m, tea.PasteMsg{Content: value})
	if !m.busy || b.count("key_check") != 0 || b.count("key_save") != 0 {
		t.Fatal("large paste blocked Update or submitted a value")
	}
	if m.text != value || m.check.Valid || !strings.Contains(m.View().Content, "•") {
		t.Fatal("large paste did not immediately show a masked, unvalidated candidate")
	}
	footer := strings.Join(m.footer(), "\n")
	if !strings.Contains(footer, "edits retained") || strings.Contains(footer, "Enter save") {
		t.Fatal("pending validation advertises submission instead of retained editing")
	}
	result := runAsyncWorker(t, b, asyncWorker(t, cmd))
	if strings.Contains(m.View().Content, "synthetic_large_paste_") {
		t.Fatal("pending large paste appeared unmasked")
	}
	b.unblock()
	m, _ = updateAsync(m, asyncResult(t, result))
	if m.busy || m.text != value || !m.check.Valid || b.count("key_save") != 0 {
		t.Fatal("large paste did not retain the exact validated pending input")
	}
	if strings.Contains(m.View().Content, "synthetic_large_paste_") {
		t.Fatal("validated large paste appeared unmasked")
	}
}

func TestAsyncValidationRetainsQueuedEditsAndChecksOnlyFinalCandidate(t *testing.T) {
	b := newGatedBackend(t, "key_check")
	m := asyncModel(t, b, "set", "EXAMPLE_TOKEN")
	value := strings.Repeat("synthetic_large_paste_", 300)
	m, cmd := updateAsync(m, tea.PasteMsg{Content: value})
	result := runAsyncWorker(t, b, asyncWorker(t, cmd))
	for _, msg := range []tea.Msg{key(tea.KeyBackspace, ""), key('z', "z"), key(tea.KeyLeft, ""), key('_', "_"), key(tea.KeyEnter, "")} {
		m, cmd = updateAsync(m, msg)
		if cmd != nil || !m.busy || b.count("key_check") != 1 {
			t.Fatal("queued editing ran validation inside Update")
		}
	}
	b.unblock()
	m, cmd = updateAsync(m, asyncResult(t, result))
	want := value[:len(value)-1] + "_z"
	if m.text != want || !m.busy || m.check.Valid || len(m.pendingInput) != 0 {
		t.Fatal("queued edits were lost, reordered, or kept a previous candidate's validation")
	}
	if strings.Contains(m.View().Content, "synthetic_large_paste_") {
		t.Fatal("queued candidate appeared unmasked")
	}
	m, _ = updateAsync(m, asyncWorker(t, cmd)())
	if m.busy || !m.check.Valid || m.text != want || b.count("key_check") != 2 || b.count("key_save") != 0 {
		t.Fatal("queued edits did not produce exactly one final validation without saving")
	}
	// Subsequent edits to the already large candidate must also stay off Update.
	m, cmd = updateAsync(m, key(tea.KeyBackspace, ""))
	if !m.busy || b.count("key_check") != 2 {
		t.Fatal("editing an already large key performed synchronous validation")
	}
	m, _ = updateAsync(m, asyncWorker(t, cmd)())
	if m.busy || b.count("key_check") != 3 {
		t.Fatal("large-key edit did not complete its validation")
	}
}

func TestAsyncNewPasteReplacesQueuedEditsWithoutLosingValidation(t *testing.T) {
	for _, same := range []bool{false, true} {
		t.Run(map[bool]string{false: "replacement", true: "same candidate"}[same], func(t *testing.T) {
			b := newGatedBackend(t, "key_check")
			m := asyncModel(t, b, "set", "EXAMPLE_TOKEN")
			value := strings.Repeat("synthetic_original_", 300)
			m, cmd := updateAsync(m, tea.PasteMsg{Content: value})
			result := runAsyncWorker(t, b, asyncWorker(t, cmd))
			m, _ = updateAsync(m, key(tea.KeyBackspace, ""))
			want := "synthetic_replacement"
			if same {
				want = value
			}
			m, _ = updateAsync(m, tea.PasteMsg{Content: want})
			b.unblock()
			m, cmd = updateAsync(m, asyncResult(t, result))
			if m.text != want {
				t.Fatal("new paste did not replace earlier queued edits")
			}
			if !same {
				m, _ = updateAsync(m, asyncWorker(t, cmd)())
			}
			checks := 2
			if same {
				checks = 1
			}
			if m.busy || !m.check.Valid || b.count("key_check") != checks || b.count("key_save") != 0 {
				t.Fatal("replacement paste lost validation, rechecked unchanged input, or submitted")
			}
		})
	}
}

func TestAsyncEscapeDiscardsReadOnlyValidationAndQueuedSecrets(t *testing.T) {
	b := newGatedBackend(t, "key_check")
	m := asyncModel(t, b, "setup", "example")
	m, cmd := updateAsync(m, tea.PasteMsg{Content: strings.Repeat("synthetic_original_", 300)})
	result := runAsyncWorker(t, b, asyncWorker(t, cmd))
	m, _ = updateAsync(m, tea.PasteMsg{Content: "synthetic_pending_replacement"})
	m, _ = updateAsync(m, key(tea.KeyEscape, ""))
	if m.busy || m.page != "providers" || m.text != "" || len(m.pendingInput) != 0 {
		t.Fatal("Escape failed to leave read-only validation and discard pending input")
	}
	b.unblock()
	m, cmd = updateAsync(m, asyncResult(t, result))
	if m.page != "providers" || m.text != "" || m.busy || cmd != nil || b.count("key_save") != 0 {
		t.Fatal("stale validation resurrected the abandoned field")
	}
}

func TestEnvironmentBackRestoresInspectedListWithoutAnotherRead(t *testing.T) {
	b := fake()
	m := create(t, b, "home", "")
	m = openHomeItem(t, m, "Switch setup")
	m = enter(m)
	m.selected = len(m.environments)
	m = enter(m)
	if m.page != "environment_new" {
		t.Fatal("New did not open environment creation choices")
	}
	m.selected = 2
	reads := count(b.calls, "environment_list")
	m, cmd := updateAsync(m, key(tea.KeyEnter, ""))
	if cmd != nil {
		m, _ = updateAsync(m, asyncWorker(t, cmd)())
	}
	if m.page != "environments" || m.busy || m.selected != len(m.environments) || count(b.calls, "environment_list") != reads {
		t.Fatal("Back reread or lost the inspected environment list")
	}
}

func TestAsyncWorkCannotLeaveNavigationPulseRunning(t *testing.T) {
	b := newGatedBackend(t, "agents_plan")
	m := asyncModel(t, b, "home", "")
	m.opts.NoMotion, m.colors = false, true
	m, _ = updateAsync(m, key(tea.KeyDown, ""))
	if m.pulseFrame <= 0 {
		t.Fatal("navigation did not create a finite accent pulse")
	}
	pulseID := m.pulseID
	m, cmd := updateAsync(m, key(tea.KeyEnter, ""))
	work := asyncWorker(t, cmd)
	m, _ = updateAsync(m, pulseMsg{pulseID})
	b.unblock()
	m, _ = updateAsync(m, work())
	if m.pulseFrame != 0 {
		t.Fatal("work completion restored a pulse whose timer stopped while busy")
	}
	m, cmd = updateAsync(m, pulseMsg{pulseID})
	if m.pulseFrame != 0 || cmd != nil {
		t.Fatal("late pulse message restarted an idle animation")
	}
}

func TestAsyncSaveStillRequiresVisibleReview(t *testing.T) {
	b := newGatedBackend(t, "unused")
	m := asyncModel(t, b, "set", "EXAMPLE_TOKEN")
	m, _ = updateAsync(m, tea.PasteMsg{Content: "synthetic_review_candidate"})
	m, _ = updateAsync(m, tea.WindowSizeMsg{Width: 24, Height: 8})
	m, cmd := updateAsync(m, key(tea.KeyEnter, ""))
	m, _ = updateAsync(m, asyncWorker(t, cmd)())
	if b.count("key_save") != 0 || m.quitting || m.error == "" {
		t.Fatal("pending presentation bypassed the visible-review requirement")
	}
}
