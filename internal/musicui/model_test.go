package musicui

import (
	"errors"
	"reflect"
	"strings"
	"testing"
	"time"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"
)

type fakeBackend struct {
	calls  []action
	status status
	fail   error
}

func (f *fakeBackend) Call(name string, args map[string]any) (map[string]any, error) {
	f.calls = append(f.calls, action{name, args})
	if f.fail != nil {
		return nil, f.fail
	}
	if name == "library" {
		return map[string]any{"configured": true, "player_available": true, "tracks": fixtureTracks()}, nil
	}
	if name == "volume" {
		f.status.Volume = args["value"].(float64)
	}
	if name == "repeat" {
		f.status.Repeat = args["value"].(string)
	}
	if name == "shuffle" {
		f.status.Shuffle = args["value"].(bool)
	}
	return map[string]any{"state": f.status.State, "track": f.status.Track, "queue": f.status.Queue, "index": f.status.Index, "position": f.status.Position, "duration": f.status.Duration, "volume": f.status.Volume, "repeat": f.status.Repeat, "shuffle": f.status.Shuffle, "levels": f.status.Levels}, nil
}
func fixtureTracks() []track {
	return []track{{"chrono/corridors", "Corridors of Time", "Chrono Trigger"}, {"zelda/oot/lost", "Lost Woods", "Zelda/Ocarina of Time"}, {"zelda/oot/storms", "Song of Storms", "Zelda/Ocarina of Time"}, {"zelda/mm/time", "Song of Time", "Zelda/Majora's Mask"}}
}
func fixture() (model, *fakeBackend) {
	f := &fakeBackend{status: status{State: "stopped", Volume: 80, Repeat: "off", Index: -1}}
	m := newModel(f, Options{Plain: true})
	m.status = f.status
	m.loaded = true
	m.library = library{Configured: true, PlayerAvailable: true, Tracks: fixtureTracks()}
	return m, f
}
func key(s string) tea.KeyPressMsg {
	codes := map[string]rune{"enter": tea.KeyEnter, "esc": tea.KeyEscape, "up": tea.KeyUp, "down": tea.KeyDown, "left": tea.KeyLeft, "right": tea.KeyRight, "tab": tea.KeyTab, "space": tea.KeySpace, "backspace": tea.KeyBackspace, "delete": tea.KeyDelete, "pgup": tea.KeyPgUp, "pgdown": tea.KeyPgDown, "home": tea.KeyHome, "end": tea.KeyEnd}
	if code, ok := codes[s]; ok {
		return tea.KeyPressMsg{Code: code}
	}
	if s == "ctrl+c" {
		return tea.KeyPressMsg{Code: 'c', Mod: tea.ModCtrl}
	}
	return tea.KeyPressMsg{Code: []rune(s)[0], Text: s}
}
func press(m model, s string) (model, tea.Cmd) {
	next, cmd := m.Update(key(s))
	return next.(model), cmd
}
func send(m model, msg tea.Msg) (model, tea.Cmd) {
	next, cmd := m.Update(msg)
	return next.(model), cmd
}
func TestLibraryDrilldownSearchAndBack(t *testing.T) {
	m, _ := fixture()
	rows := m.entries()
	if len(rows) != 3 || rows[0].title != "All tracks" || rows[2].title != "Zelda" {
		t.Fatalf("root: %#v", rows)
	}
	m.selected = 2
	m, _ = press(m, "enter")
	if m.collection != "Zelda" || len(m.entries()) != 2 {
		t.Fatal("collection did not open")
	}
	m.selected = 1
	m, _ = press(m, "enter")
	if m.collection != "Zelda/Ocarina of Time" || len(m.entries()) != 2 {
		t.Fatal("nested album did not open")
	}
	m.selected = 1
	m, _ = press(m, "/")
	m, _ = send(m, tea.PasteMsg{Content: "Corridors"})
	if len(m.entries()) != 1 || m.entries()[0].track.Collection != "Chrono Trigger" {
		t.Fatal("search was limited to album")
	}
	m, _ = send(m, tea.PasteMsg{Content: "typo"})
	v := ansi.Strip(m.View().Content)
	if !strings.Contains(v, "Corridorstypo") || !strings.Contains(v, "No tracks match") {
		t.Fatalf("query lost on no results:\n%s", v)
	}
	m, _ = press(m, "esc")
	if m.collection != "Zelda/Ocarina of Time" || m.selected != 1 || m.query != "" {
		t.Fatal("search did not restore original album and row")
	}
	m, _ = press(m, "esc")
	if m.collection != "Zelda" || m.selected != 1 {
		t.Fatal("back did not restore parent selection")
	}
	m, _ = press(m, "esc")
	if m.collection != "" || m.selected != 2 {
		t.Fatal("back did not reach library")
	}
	m, cmd := press(m, "esc")
	if m.closing || cmd != nil {
		t.Fatal("Esc at root quit or stopped playback")
	}
}
func TestPlaySnapshotsVisibleAlbumAndQueueIndex(t *testing.T) {
	m, f := fixture()
	m.collection = "Zelda/Ocarina of Time"
	m.selected = 1
	next, cmd := press(m, "enter")
	if len(f.calls) != 0 {
		t.Fatal("Update performed backend I/O")
	}
	if !next.busy {
		t.Fatal("no pending play")
	}
	result := cmd()
	if len(f.calls) != 1 || f.calls[0].name != "play" {
		t.Fatal("not play")
	}
	if !reflect.DeepEqual(f.calls[0].args, map[string]any{"ids": []string{"zelda/oot/lost", "zelda/oot/storms"}, "index": 1}) {
		t.Fatalf("wrong snapshot %#v", f.calls[0])
	}
	m, _ = send(next, result)
	m.view = "queue"
	m.status.Queue = []track{fixtureTracks()[0], fixtureTracks()[0], fixtureTracks()[2]}
	m.selected = 1
	_, cmd = press(m, "enter")
	cmd()
	if f.calls[1].args["index"] != 1 || len(f.calls[1].args["ids"].([]string)) != 3 {
		t.Fatal("duplicate queue IDs lost selected index")
	}
}
func TestCollectionEnqueueAndQueueRemoval(t *testing.T) {
	m, f := fixture()
	m.selected = 2
	m, cmd := press(m, "a")
	msg := cmd()
	if f.calls[0].name != "enqueue" || len(f.calls[0].args["ids"].([]string)) != 3 {
		t.Fatal("collection enqueue did not contain descendants")
	}
	m, _ = send(m, msg)
	m.status.Queue = fixtureTracks()
	m, _ = press(m, "tab")
	m.selected = 2
	_, cmd = press(m, "d")
	cmd()
	if f.calls[1].name != "remove" || f.calls[1].args["index"] != 2 {
		t.Fatal("queue removal wrong")
	}
}
func TestControlsAreAsyncAndSerialized(t *testing.T) {
	m, f := fixture()
	m, first := press(m, "+")
	m, second := press(m, "+")
	if len(f.calls) > 0 || second != nil || len(m.pending) != 1 {
		t.Fatal("actions not queued asynchronously")
	}
	m, _ = send(m, tea.WindowSizeMsg{Width: 40, Height: 18})
	if m.width != 40 {
		t.Fatal("resize blocked by work")
	}
	_ = m.View()
	if len(f.calls) > 0 {
		t.Fatal("View performed I/O")
	}
	m, next := send(m, first())
	if f.calls[0].args["value"] != float64(85) || next == nil {
		t.Fatal("first volume failed")
	}
	m, _ = send(m, next())
	if f.calls[1].args["value"] != float64(90) || m.status.Volume != 90 {
		t.Fatal("rapid volume updates reused stale value")
	}
	for _, name := range []string{"r", "r", "s", "s"} {
		var cmd tea.Cmd
		m, cmd = press(m, name)
		m, _ = send(m, cmd())
	}
	if m.status.Repeat != "one" || m.status.Shuffle {
		t.Fatal("repeat/shuffle toggles wrong")
	}
}
func TestStalePollNeverRevertsNewerMutation(t *testing.T) {
	m, f := fixture()
	m.status.State = "playing"
	m.pollToken = 7
	stale := statusMsg{epoch: m.epoch, token: 7, status: status{State: "playing", Volume: 20}}
	m, cmd := press(m, "x")
	if m.epoch == 0 {
		t.Fatal("mutation did not invalidate reads")
	}
	m, _ = send(m, stale)
	if m.status.Volume == 20 {
		t.Fatal("stale read applied while busy")
	}
	f.status.State = "stopped"
	m, _ = send(m, cmd())
	m, _ = send(m, stale)
	if m.status.State != "stopped" {
		t.Fatal("stale read resurrected playing")
	}
	m, _ = send(m, resultMsg{id: m.serial - 1, status: status{State: "playing"}})
	if m.status.State != "stopped" {
		t.Fatal("old mutation applied")
	}
}
func TestQuitLeavesPlaybackAndEscDoesNotStop(t *testing.T) {
	for _, k := range []string{"q", "ctrl+c"} {
		m, f := fixture()
		m.status.State = "playing"
		next, cmd := press(m, k)
		if !next.closing || cmd == nil {
			t.Fatalf("%s did not close", k)
		}
		if _, ok := cmd().(tea.QuitMsg); !ok {
			t.Fatal("not quit")
		}
		if len(f.calls) > 0 || next.status.State != "playing" {
			t.Fatal("closing changed audio")
		}
	}
	m, f := fixture()
	m, work := press(m, "n")
	m, quit := press(m, "q")
	if quit != nil || !m.closing {
		t.Fatal("quit did not preserve pending control")
	}
	m, quit = send(m, work())
	if quit == nil || len(f.calls) != 1 || f.calls[0].name != "next" {
		t.Fatal("closing lost control or stopped playback")
	}
}
func TestPollCadenceAndFailureRemainNavigable(t *testing.T) {
	m, _ := fixture()
	if m.interval() < time.Second {
		t.Fatal("idle polls too fast")
	}
	m.status.State = "playing"
	if m.interval() != 100*time.Millisecond {
		t.Fatal("active cadence")
	}
	m.opts.NoMotion = true
	if m.interval() < time.Second {
		t.Fatal("reduced motion polls too fast")
	}
	m, _ = send(m, loadedMsg{library: library{Configured: true, Tracks: fixtureTracks(), NoMotion: true}, err: errors.New("player unavailable")})
	if !m.loaded || !m.opts.NoMotion || m.failure == "" {
		t.Fatal("load error lost library")
	}
	m.selected = 2
	m, _ = press(m, "enter")
	if m.collection != "Zelda" {
		t.Fatal("backend error blocked browsing")
	}
}
func TestMissingPlayerShowsActionWithoutCallingPlay(t *testing.T) {
	m, f := fixture()
	m.library.PlayerAvailable = false
	m.collection = "Zelda/Ocarina of Time"
	m, cmd := press(m, "enter")
	if cmd != nil || len(f.calls) > 0 || !strings.Contains(m.failure, "brew install mpv") {
		t.Fatal("missing player failed without action")
	}
	m.library.Configured = false
	v := ansi.Strip(m.View().Content)
	if !strings.Contains(v, "godmode music setup --songs DIR") {
		t.Fatal("setup command missing")
	}
}
func TestKeyboardProtocolControls(t *testing.T) {
	for k, want := range map[string]string{"space": "toggle", "x": "stop", "n": "next", "p": "previous", "<": "seek", ">": "seek", "-": "volume", "r": "repeat", "s": "shuffle"} {
		m, f := fixture()
		_, cmd := press(m, k)
		if cmd == nil {
			t.Fatalf("%s had no command", k)
		}
		cmd()
		if f.calls[0].name != want {
			t.Fatalf("%s called %s", k, f.calls[0].name)
		}
	}
}
func TestAllLayoutsFitAndKeepTransport(t *testing.T) {
	for _, size := range [][2]int{{40, 18}, {80, 24}, {120, 36}} {
		for _, view := range []string{"library", "queue", "search", "help", "setup", "loading"} {
			m, _ := fixture()
			m.width, m.height = size[0], size[1]
			m.status = status{State: "playing", Track: &track{ID: "playing", Title: "Currently audible", Collection: "Playing album"}, Queue: fixtureTracks(), Index: 1, Duration: 180, Position: 47, Volume: 80, Repeat: "all", Levels: []float64{.1, .8, .4, .9}}
			switch view {
			case "queue":
				m.view = "queue"
			case "search":
				m.query = "no matching song"
				m.searching = true
			case "help":
				m.help = true
			case "setup":
				m.library.Configured = false
			case "loading":
				m.loaded = false
			}
			raw := m.View().Content
			lines := strings.Split(raw, "\n")
			if len(lines) != size[1] {
				t.Fatalf("%v %s rows=%d", size, view, len(lines))
			}
			for i, line := range lines {
				if ansi.StringWidth(line) > size[0] {
					t.Fatalf("%v %s line %d width %d", size, view, i, ansi.StringWidth(line))
				}
			}
			plain := ansi.Strip(raw)
			for _, text := range []string{"NOW PLAYING", "Currently audible", "0:47 / 3:00"} {
				if !strings.Contains(plain, text) {
					t.Fatalf("%v %s missing %q\n%s", size, view, text, plain)
				}
			}
			if view != "search" && !strings.Contains(plain, "q close") {
				t.Fatalf("%v %s close control hidden", size, view)
			}
		}
	}
}
func TestLabelsCannotInjectTerminalControls(t *testing.T) {
	m, _ := fixture()
	m.library.Tracks = []track{{ID: "one", Title: "bad\x1b[2Jname\nnext\u202e", Collection: "game"}}
	m.collection = "game"
	v := m.View().Content
	if strings.Contains(v, "\x1b") || strings.Contains(v, "\u202e") || !strings.Contains(v, "badnamenext") {
		t.Fatalf("untrusted title reached terminal: %q", v)
	}
}

func TestSearchCanFocusResultsAndEnqueueWithoutPlaying(t *testing.T) {
	m, f := fixture()
	m, _ = press(m, "/")
	m, _ = send(m, tea.PasteMsg{Content: "Song"})
	m, _ = press(m, "tab")
	if m.searching || m.query != "Song" || len(m.entries()) != 2 {
		t.Fatal("Tab lost search results")
	}
	m, cmd := press(m, "a")
	if cmd == nil {
		t.Fatal("focused result could not enqueue")
	}
	m, _ = send(m, cmd())
	if f.calls[0].name != "enqueue" {
		t.Fatal("search action started playback")
	}
	m, _ = press(m, "/")
	if !m.searching || m.query != "Song" {
		t.Fatal("search could not be edited")
	}
}
func TestQueueShowsCollectionAndContextualControls(t *testing.T) {
	for _, size := range [][2]int{{40, 18}, {80, 24}} {
		m, _ := fixture()
		m.width, m.height = size[0], size[1]
		m.view = "queue"
		m.status.Queue = []track{{ID: "1", Title: "Intro", Collection: "Distinct source game"}}
		m.status.Message = "Stopped"
		v := ansi.Strip(m.View().Content)
		for _, text := range []string{"Distinct source game", "Tab library", "d remove"} {
			if !strings.Contains(v, text) {
				t.Fatalf("%v missing %q\n%s", size, text, v)
			}
		}
	}
}
func TestDetailsShowFullTitleAndReturnToSelection(t *testing.T) {
	m, _ := fixture()
	m.width, m.height = 40, 18
	m.library.Tracks = []track{{ID: "long", Title: "A very long title with a meaningful distinguishing suffix", Collection: "Local game"}}
	m.collection = "Local game"
	m, _ = press(m, "i")
	v := ansi.Strip(m.View().Content)
	if !strings.Contains(v, "distinguishing suffix") {
		t.Fatalf("full title not available:\n%s", v)
	}
	m, _ = press(m, "esc")
	if m.info || m.collection != "Local game" || m.selected != 0 {
		t.Fatal("details return changed library")
	}
}
func TestReloadCannotOverwriteNewerControl(t *testing.T) {
	m, f := fixture()
	m, reload := press(m, "R")
	old := reload()
	m, stop := press(m, "x")
	f.status.State = "stopped"
	m, _ = send(m, stop())
	m, _ = send(m, old)
	if m.status.State != "stopped" {
		t.Fatal("reload replaced a newer transport result")
	}
}
func TestSetupFitsSmallViewport(t *testing.T) {
	m, _ := fixture()
	m.width, m.height = 40, 18
	m.library.Configured = false
	m.library.Error = strings.Repeat("A very long error ", 20)
	v := ansi.Strip(m.View().Content)
	for _, text := range []string{"godmode music setup", "--songs DIR", "folder", "R reloads"} {
		if !strings.Contains(v, text) {
			t.Fatalf("setup omitted %q:\n%s", text, v)
		}
	}
}
func TestPCMComesOnlyFromBackendLevels(t *testing.T) {
	m, _ := fixture()
	m.status.State = "playing"
	m.status.Levels = []float64{0, 1}
	v := ansi.Strip(m.pcmStrip(30))
	if !strings.Contains(v, "▁▁▁▁▁█████") {
		t.Fatalf("unexpected levels %q", v)
	}
	m.status.Levels = nil
	if !strings.Contains(ansi.Strip(m.pcmStrip(78)), "waiting for audio") {
		t.Fatal("fabricated signal without levels")
	}
	m.opts.NoMotion = true
	m.status.Levels = []float64{1}
	if !strings.Contains(ansi.Strip(m.pcmStrip(78)), "motion reduced") {
		t.Fatal("reduced motion still animates")
	}
}

func TestPlayQueueReplacementIntentIsVisibleBeforeEnter(t *testing.T) {
	for _, size := range [][2]int{{40, 18}, {80, 24}, {120, 36}} {
		m, _ := fixture()
		m.width, m.height = size[0], size[1]
		m.collection = "Zelda/Ocarina of Time"
		m.status.Message = "Stopped"
		v := ansi.Strip(m.View().Content)
		if !strings.Contains(v, "replaces queue") || !strings.Contains(v, "a appends") {
			t.Fatalf("%v missing play intent:\n%s", size, v)
		}
		m.collection = ""
		v = ansi.Strip(m.View().Content)
		if strings.Contains(v, "replaces queue") || !strings.Contains(v, "Enter opens collection") {
			t.Fatal("container implied playback")
		}
		m.view = "queue"
		m.status.Queue = fixtureTracks()
		v = ansi.Strip(m.View().Content)
		if strings.Contains(v, "replaces queue") || !strings.Contains(v, "Enter plays this queued track") {
			t.Fatalf("queue intent wrong:\n%s", v)
		}
	}
}

func TestSearchSubmitNeverStartsPlayback(t *testing.T) {
	for _, submit := range []string{"enter", "tab"} {
		t.Run(submit, func(t *testing.T) {
			m, f := fixture()
			m.status.Queue = []track{fixtureTracks()[0]}
			m.status.State = "paused"
			m, _ = press(m, "/")
			m, _ = send(m, tea.PasteMsg{Content: "Song"})
			m, _ = press(m, "down")
			before := m.status
			m, cmd := press(m, submit)
			if cmd != nil || len(f.calls) != 0 || m.busy {
				t.Fatal("submitting search initiated a backend action")
			}
			if m.searching || m.query != "Song" || m.selected != 1 {
				t.Fatal("search submission did not retain focused results")
			}
			if !reflect.DeepEqual(m.status, before) {
				t.Fatal("search submission changed playback or queue")
			}
			m, cmd = press(m, "enter")
			if cmd == nil {
				t.Fatal("second Enter did not play the focused result")
			}
			cmd()
			want := map[string]any{"ids": []string{"zelda/oot/storms", "zelda/mm/time"}, "index": 1}
			if len(f.calls) != 1 || f.calls[0].name != "play" || !reflect.DeepEqual(f.calls[0].args, want) {
				t.Fatalf("second Enter used wrong queue: %#v", f.calls)
			}
		})
	}
}
func TestSearchInputExplainsFocusInsteadOfPlayback(t *testing.T) {
	for _, size := range [][2]int{{40, 18}, {80, 24}, {120, 36}} {
		m, _ := fixture()
		m.width, m.height = size[0], size[1]
		m, _ = press(m, "/")
		m, _ = send(m, tea.PasteMsg{Content: "Song"})
		v := ansi.Strip(m.View().Content)
		if !strings.Contains(v, "Enter/Tab results · Esc clear") || !strings.Contains(v, "focuses search results") {
			t.Fatalf("%v search focus hint missing:\n%s", size, v)
		}
		if strings.Contains(v, "Enter play") || strings.Contains(v, "replaces queue") {
			t.Fatalf("%v input still implies immediate playback:\n%s", size, v)
		}
	}
}

func TestEnqueueReceiptExpiresThenRestoresContext(t *testing.T) {
	for _, view := range []string{"library", "queue"} {
		t.Run(view, func(t *testing.T) {
			m, f := fixture()
			m.width, m.height = 40, 18
			m.collection = "Zelda/Ocarina of Time"
			m.view = view
			m.status.Queue = fixtureTracks()
			f.status.Queue = fixtureTracks()
			m, work := press(m, "a")
			m, follow := send(m, work())
			token := m.noticeToken
			if !strings.Contains(ansi.Strip(m.View().Content), "Added to queue") {
				t.Fatal("enqueue acknowledgement hidden by selection context")
			}
			batch, ok := follow().(tea.BatchMsg)
			if !ok || len(batch) != 2 {
				t.Fatal("receipt expiry and status poll were not both scheduled")
			}
			m, _ = send(m, noticeExpiredMsg{token: token})
			v := ansi.Strip(m.View().Content)
			if strings.Contains(v, "Added to queue") {
				t.Fatal("receipt did not expire")
			}
			want := "replaces queue"
			if view == "queue" {
				want = "Selected · Chrono Trigger"
			}
			if !strings.Contains(v, want) {
				t.Fatalf("context did not return after acknowledgement: %s", v)
			}
		})
	}
}
func TestNavigationClearsReceiptAndOldExpiryCannotClearNewOne(t *testing.T) {
	m, _ := fixture()
	m.collection = "Zelda/Ocarina of Time"
	m, work := press(m, "a")
	m, _ = send(m, work())
	old := m.noticeToken
	m, _ = press(m, "down")
	v := ansi.Strip(m.View().Content)
	if m.notice != "" || !strings.Contains(v, "replaces queue") {
		t.Fatal("navigation left acknowledgement over next action intent")
	}
	m, work = press(m, "a")
	m, _ = send(m, work())
	m, _ = send(m, noticeExpiredMsg{token: old})
	if !strings.Contains(ansi.Strip(m.View().Content), "Added to queue") {
		t.Fatal("old timer cleared newer acknowledgement")
	}
}

func TestSearchResultsSurviveQueueRoundTrip(t *testing.T) {
	m, f := fixture()
	m.status.Queue = fixtureTracks()
	m.collection = "Zelda/Ocarina of Time"
	m.selected = 1
	m, _ = press(m, "/")
	m, _ = send(m, tea.PasteMsg{Content: "Song"})
	m, _ = press(m, "enter")
	m, _ = press(m, "down")
	m, _ = press(m, "tab")
	if m.view != "queue" || m.query != "Song" {
		t.Fatal("Tab cleared library search")
	}
	queueNav := ansi.Strip(strings.Join(m.nav(), "\n"))
	if strings.Contains(queueNav, "/ Song") || !strings.Contains(queueNav, "Enter plays this queued track") {
		t.Fatalf("queue displayed hidden library query: %s", queueNav)
	}
	m, _ = press(m, "down")
	m, _ = press(m, "down")
	m, _ = press(m, "tab")
	if m.view != "library" || m.query != "Song" || m.selected != 1 || len(m.entries()) != 2 {
		t.Fatal("queue round trip lost filtered selection")
	}
	m, _ = press(m, "tab")
	if m.selected != 2 {
		t.Fatal("queue cursor was not restored")
	}
	m, _ = press(m, "esc")
	if m.view != "library" || m.query != "Song" || m.selected != 1 {
		t.Fatal("Esc from queue cleared hidden search")
	}
	m, _ = press(m, "esc")
	if m.searchActive || m.query != "" || m.collection != "Zelda/Ocarina of Time" || m.selected != 1 {
		t.Fatal("clear search lost actual library origin")
	}
	if len(f.calls) != 0 {
		t.Fatal("navigation changed playback")
	}
}
func TestQueueOriginSearchDetailsEnqueueReturnsToQueue(t *testing.T) {
	m, f := fixture()
	m.view = "queue"
	m.status.Queue = fixtureTracks()
	f.status.Queue = fixtureTracks()
	m.selected = 2
	m.libraryAt = 1
	m.collection = "Zelda"
	m, _ = press(m, "/")
	m, _ = send(m, tea.PasteMsg{Content: "Song"})
	m, _ = press(m, "tab")
	m, _ = press(m, "down")
	m, _ = press(m, "i")
	m, _ = press(m, "esc")
	if m.query != "Song" || m.selected != 1 || m.view != "library" {
		t.Fatal("details return lost search")
	}
	m, work := press(m, "a")
	m, _ = send(m, work())
	m, _ = press(m, "tab")
	if m.view != "queue" || m.selected != 2 {
		t.Fatalf("Tab after queue-origin search went to %s row%d", m.view, m.selected)
	}
	m, _ = press(m, "tab")
	if m.view != "library" || m.query != "Song" || m.selected != 1 {
		t.Fatal("return to results lost selection")
	}
	m, _ = press(m, "esc")
	if m.view != "queue" || m.selected != 2 || m.query != "" || m.searchActive {
		t.Fatal("clearing search did not restore queue origin")
	}
	if len(f.calls) != 1 || f.calls[0].name != "enqueue" || !reflect.DeepEqual(f.calls[0].args["ids"], []string{"zelda/mm/time"}) {
		t.Fatalf("flow changed playback or queued wrong track: %#v", f.calls)
	}
}
func TestDetailsActionsMatchDisplayedInstructions(t *testing.T) {
	t.Run("track append", func(t *testing.T) {
		m, f := fixture()
		m.collection = "Zelda/Ocarina of Time"
		m.selected = 1
		m, _ = press(m, "i")
		m, work := press(m, "a")
		if work == nil {
			t.Fatal("displayed append action ignored")
		}
		m, _ = send(m, work())
		if !m.info || !strings.Contains(ansi.Strip(m.View().Content), "Added to queue") {
			t.Fatal("details closed or acknowledgement missing")
		}
		if f.calls[0].name != "enqueue" || !reflect.DeepEqual(f.calls[0].args["ids"], []string{"zelda/oot/storms"}) {
			t.Fatal("details appended wrong track")
		}
	})
	t.Run("collection append and open", func(t *testing.T) {
		m, f := fixture()
		m.selected = 2
		m, _ = press(m, "i")
		m, work := press(m, "a")
		m, _ = send(m, work())
		if !m.info || len(f.calls[0].args["ids"].([]string)) != 3 {
			t.Fatal("details collection append failed")
		}
		m, cmd := press(m, "enter")
		if cmd != nil || m.info || m.collection != "Zelda" || len(f.calls) != 1 {
			t.Fatal("Enter in collection details did not open collection")
		}
	})
	t.Run("track play", func(t *testing.T) {
		m, f := fixture()
		m.collection = "Zelda/Ocarina of Time"
		m.selected = 1
		m, _ = press(m, "i")
		v := ansi.Strip(m.View().Content)
		if !strings.Contains(v, "replaces queue") {
			t.Fatal("details play effect missing")
		}
		_, work := press(m, "enter")
		if work == nil {
			t.Fatal("displayed Enter action ignored")
		}
		work()
		if f.calls[0].name != "play" || f.calls[0].args["index"] != 1 {
			t.Fatal("details played wrong row")
		}
	})
}
func TestEmptySearchCanFocusAllTracksAndClearToOrigin(t *testing.T) {
	m, _ := fixture()
	m.collection = "Zelda"
	m.selected = 1
	m, _ = press(m, "/")
	m, _ = press(m, "enter")
	if !m.searchActive || len(m.entries()) != len(fixtureTracks()) {
		t.Fatal("empty focused query dropped out of search")
	}
	m, _ = press(m, "tab")
	m, _ = press(m, "tab")
	if len(m.entries()) != len(fixtureTracks()) {
		t.Fatal("empty query lost across tabs")
	}
	m, _ = press(m, "esc")
	if m.searchActive || m.collection != "Zelda" || m.selected != 1 {
		t.Fatal("empty query could not restore origin")
	}
}

func TestDetailsReceiptTabInspectsQueueAndPreservesResults(t *testing.T) {
	m, f := fixture()
	m.view = "queue"
	m.status.Queue = fixtureTracks()
	f.status.Queue = fixtureTracks()
	m.selected = 2
	m.libraryAt = 1
	m.collection = "Zelda"
	m, _ = press(m, "/")
	m, _ = send(m, tea.PasteMsg{Content: "Song"})
	m, _ = press(m, "enter")
	m, _ = press(m, "down")
	m, _ = press(m, "i")
	m, work := press(m, "a")
	m, _ = send(m, work())
	if !m.info || !strings.Contains(ansi.Strip(m.View().Content), "Tab to inspect") {
		t.Fatal("details append did not advertise queue inspection")
	}
	m, cmd := press(m, "tab")
	if cmd != nil || m.info || m.view != "queue" || m.selected != 2 {
		t.Fatal("receipt Tab did not inspect original queue row")
	}
	m, _ = press(m, "tab")
	if m.view != "library" || m.query != "Song" || !m.searchActive || m.selected != 1 {
		t.Fatal("queue inspection lost original search result")
	}
	if len(f.calls) != 1 || f.calls[0].name != "enqueue" {
		t.Fatal("queue inspection triggered playback or duplicate mutation")
	}
}
func TestTabFromQueueDetailsDoesNotToggleToLibrary(t *testing.T) {
	m, f := fixture()
	m.view = "queue"
	m.status.Queue = fixtureTracks()
	f.status.Queue = fixtureTracks()
	m.selected = 2
	m, _ = press(m, "i")
	m, work := press(m, "a")
	m, _ = send(m, work())
	m, cmd := press(m, "tab")
	if cmd != nil || m.info || m.view != "queue" || m.selected != 2 {
		t.Fatal("Tab left queue instead of closing its details")
	}
	if len(f.calls) != 1 {
		t.Fatal("details Tab made extra backend call")
	}
}

func TestSearchResultOpensCollectionAndBackRestoresSearch(t *testing.T) {
	m, f := fixture()
	m.status.State = "paused"
	m.status.Track = &fixtureTracks()[0]
	m.status.Queue = fixtureTracks()
	before := m.status
	m, _ = press(m, "/")
	m, _ = send(m, tea.PasteMsg{Content: "Song"})
	m, _ = press(m, "enter")
	m, cmd := press(m, "c")
	if cmd != nil || m.collection != "Zelda/Ocarina of Time" || m.searchActive || m.query != "" || m.selected != 1 || len(m.entries()) != 2 {
		t.Fatal("c did not open whole collection at selected result")
	}
	v := ansi.Strip(m.View().Content)
	if !strings.Contains(v, "A add collection") {
		t.Fatal("whole collection action not visible")
	}
	m, _ = press(m, "esc")
	if m.view != "library" || !m.searchActive || m.query != "Song" || m.selected != 0 || len(m.entries()) != 2 {
		t.Fatal("Esc lost actual search origin")
	}
	if len(f.calls) != 0 || !reflect.DeepEqual(m.status, before) {
		t.Fatal("opening collection changed playback")
	}
}
func TestQueueAndDetailsCollectionBackDestinations(t *testing.T) {
	for _, details := range []bool{false, true} {
		m, f := fixture()
		m.view = "queue"
		m.status.Queue = fixtureTracks()
		m.selected = 2
		if details {
			m, _ = press(m, "i")
		}
		m, _ = press(m, "c")
		if m.view != "library" || m.collection != "Zelda/Ocarina of Time" || m.info || m.selected != 1 {
			t.Fatal("queue c did not open source collection")
		}
		m, _ = press(m, "esc")
		if m.view != "queue" || m.selected != 2 || m.info != details {
			t.Fatal("c back lost queue/details origin")
		}
		if len(f.calls) != 0 {
			t.Fatal("collection inspection called backend")
		}
	}
}
func TestWholeCollectionAppendFromFilteredResult(t *testing.T) {
	for _, details := range []bool{false, true} {
		m, f := fixture()
		m, _ = press(m, "/")
		m, _ = send(m, tea.PasteMsg{Content: "Storms"})
		m, _ = press(m, "enter")
		if details {
			m, _ = press(m, "i")
		}
		m, work := press(m, "A")
		if work == nil {
			t.Fatal("whole collection action missing")
		}
		m, _ = send(m, work())
		if f.calls[0].name != "enqueue" || !reflect.DeepEqual(f.calls[0].args["ids"], []string{"zelda/oot/lost", "zelda/oot/storms"}) {
			t.Fatalf("A queued only search result instead of collection: %#v", f.calls)
		}
		if m.query != "Storms" || m.info != details || !strings.Contains(ansi.Strip(m.View().Content), "Added to queue") {
			t.Fatal("collection append lost context or receipt")
		}
	}
}
func TestOpenedCollectionAppendKeepsBackOrigin(t *testing.T) {
	m, f := fixture()
	m, _ = press(m, "/")
	m, _ = send(m, tea.PasteMsg{Content: "Storms"})
	m, _ = press(m, "enter")
	m, _ = press(m, "c")
	m, work := press(m, "A")
	m, _ = send(m, work())
	if !reflect.DeepEqual(f.calls[0].args["ids"], []string{"zelda/oot/lost", "zelda/oot/storms"}) {
		t.Fatal("collection A snapshot incorrect")
	}
	m, _ = press(m, "esc")
	if m.query != "Storms" || m.selected != 0 || !m.searchActive {
		t.Fatal("append changed collection back origin")
	}
}
func TestSetupGuideScrollsWithoutBackendCalls(t *testing.T) {
	for _, size := range [][2]int{{40, 18}, {80, 24}} {
		m, f := fixture()
		m.width, m.height = size[0], size[1]
		m.library = library{}
		initial := ansi.Strip(m.View().Content)
		for _, text := range []string{"godmode music setup --songs DIR", ".ootrs", "↑↓ scroll", "R reloads"} {
			if !strings.Contains(initial, text) {
				t.Fatalf("%v setup first action missing %q", size, text)
			}
		}
		seen := initial
		for i := 0; i < 6; i++ {
			m, _ = press(m, "pgdown")
			v := ansi.Strip(m.View().Content)
			seen += "\n" + v
			for _, line := range strings.Split(v, "\n") {
				if ansi.StringWidth(line) > size[0] {
					t.Fatal("setup wrapped outside viewport")
				}
			}
		}
		for _, text := range []string{"Quote paths containing spaces", "AFTER SETUP", "Subfolders become collections"} {
			if !strings.Contains(seen, text) {
				t.Fatalf("%v setup text inaccessible: %s", size, text)
			}
		}
		m, _ = press(m, "home")
		if m.setupAt != 0 || ansi.Strip(m.View().Content) != initial {
			t.Fatal("setup Home did not return to first action")
		}
		m, _ = press(m, "down")
		if m.setupAt != 1 {
			t.Fatal("setup arrow scrolling ignored")
		}
		m, _ = press(m, "up")
		if m.setupAt != 0 {
			t.Fatal("setup up ignored")
		}
		if len(f.calls) != 0 {
			t.Fatal("reading setup performed backend action")
		}
	}
}
func TestCollectionKeysAndSearchClearHintFit(t *testing.T) {
	for _, size := range [][2]int{{40, 18}, {80, 24}, {120, 36}} {
		m, _ := fixture()
		m.width, m.height = size[0], size[1]
		m, _ = press(m, "/")
		m, _ = send(m, tea.PasteMsg{Content: "Storms"})
		if !strings.Contains(ansi.Strip(m.View().Content), "Ctrl+U") {
			t.Fatal("query-clear hint missing")
		}
		m, _ = press(m, "enter")
		if !strings.Contains(ansi.Strip(m.View().Content), "c collection") {
			t.Fatal("collection action hidden on result")
		}
		m, _ = press(m, "c")
		if !strings.Contains(ansi.Strip(m.View().Content), "A add collection") {
			t.Fatal("whole-collection action hidden")
		}
		for _, line := range strings.Split(m.View().Content, "\n") {
			if ansi.StringWidth(line) > size[0] {
				t.Fatalf("%v collection controls overflow", size)
			}
		}
	}
}

func TestEmptyPlayerShowsImmediateJingleBeforeLibrarySetup(t *testing.T) {
	for _, size := range [][2]int{{40, 18}, {80, 24}, {120, 36}} {
		m, f := fixture()
		m.width, m.height = size[0], size[1]
		m.library = library{}
		v := ansi.Strip(m.View().Content)
		for _, text := range []string{"Play a cue: godmode jingle play", "Only mpv needed; no track library.", "godmode music setup --songs DIR"} {
			if !strings.Contains(v, text) {
				t.Fatalf("%v immediate jingle/setup path missing %q:\n%s", size, text, v)
			}
		}
		if strings.Index(v, "godmode jingle play") > strings.Index(v, "godmode music setup") {
			t.Fatal("immediate cue buried after synth setup")
		}
		if len(f.calls) != 0 {
			t.Fatal("showing cue instructions started backend work")
		}
	}
}
func TestNarrowHelpRetainsEveryWordAcrossScrolling(t *testing.T) {
	for _, size := range [][2]int{{40, 18}, {80, 24}} {
		m, f := fixture()
		m.width, m.height = size[0], size[1]
		m.query = "Song"
		m.searchActive = true
		m.selected = 1
		m, _ = press(m, "?")
		wantedRows := helpLines(m.innerWidth())
		seen := map[int]string{}
		for step := 0; step < len(wantedRows)+1; step++ {
			v := m.View().Content
			lines := strings.Split(v, "\n")
			if len(lines) != size[1] {
				t.Fatal("help height changed")
			}
			for _, line := range lines {
				if ansi.StringWidth(line) > size[0] {
					t.Fatal("wrapped help exceeds terminal width")
				}
			}
			plain := ansi.Strip(v)
			if !strings.Contains(plain, "NOW PLAYING") || !strings.Contains(plain, "Esc return") {
				t.Fatal("help displaced transport or back control")
			}
			start := min(m.helpAt, max(0, len(wantedRows)-m.bodyRows()))
			bodyStart := len(m.header()) + 3
			for row := 0; row < m.bodyRows() && start+row < len(wantedRows); row++ {
				seen[start+row] = strings.TrimSpace(ansi.Strip(lines[bodyStart+row]))
			}
			old := m.helpAt
			m, _ = press(m, "pgdown")
			if m.helpAt == old {
				break
			}
		}
		if len(seen) != len(wantedRows) {
			t.Fatalf("%v help rows unreachable: %d/%d", size, len(seen), len(wantedRows))
		}
		collected := []string{}
		for i := range wantedRows {
			collected = append(collected, seen[i])
		}
		actual := strings.Join(strings.Fields(strings.Join(collected, " ")), " ")
		want := strings.Join(strings.Fields(strings.Join(helpText, " ")), " ")
		if actual != want {
			t.Fatalf("%v help lost or truncated text:\nactual: %s\nwant: %s", size, actual, want)
		}
		m, _ = press(m, "pgup")
		if m.helpAt >= len(wantedRows)-m.bodyRows() {
			t.Fatal("help cannot page back")
		}
		m, _ = press(m, "home")
		if m.helpAt != 0 {
			t.Fatal("help Home ignored")
		}
		m, _ = press(m, "esc")
		if m.help || m.query != "Song" || m.selected != 1 {
			t.Fatal("help exit lost library search")
		}
		if len(f.calls) != 0 {
			t.Fatal("reading help changed playback")
		}
	}
}
