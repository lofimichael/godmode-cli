# Music player patterns and transport research

Researched 2026-11-17. Primary documentation/source only. This report does not inspect the Godmode UI, its source, or earlier audits. Recommendations below are design proposals, not claims about current Godmode behavior. No dependencies were installed and no audible playback was tested.

## Decision

Use an independently owned playback session with a real player clock, and make the TUI a client. Keep library navigation, selected row, queue, current item, preparation job, and audio transport as separate state. Prefer **mpv JSON IPC** as the optional full-control transport. The current machine has ffmpeg, ffplay, and afplay, but no mpv; **ffplay with reported-clock parsing and restart-based controls** is a feasible no-install fallback with gaps and parser fragility. **afplay is a basic fallback**, not a foundation for precise interactive controls.

## Documented reference patterns

| Reference | Documented facts | Useful application here (recommendation) |
|---|---|---|
| [spotify-player commands](https://github.com/aome510/spotify-player#commands) | Separate commands exist for selecting/scrolling, opening selected items, going back, opening the current context, queueing, and controlling playback. Space controls pause, while Enter chooses an item. Help is searchable. | A cursor is navigation state. Moving it must never change playback. Keep a persistent Now Playing strip. Show the command for the selected object, not only generic global hints. |
| [spotify-player features](https://github.com/aome510/spotify-player#audio-visualization) | Its visualization appears only for locally streamed audio and is hidden when playback is remote or inactive. Daemon mode and optional streaming builds are documented. CLI controls use a client socket. | Source the animation from the audio actually being played. Expose detach versus stop. Keep playback optional in the core utility. These are interaction references; the Spotify products require Premium and are not proposed dependencies. |
| [Spotify TUI](https://github.com/Rigellute/spotify-tui#configuration) | It documents separate playback, seek, volume, search, back, jump-to-context, album/artist, and enqueue controls. Its Web API client does not stream; another Spotify client or spotifyd provides playback. | A UI can remain thin when session ownership is explicit. Display the backend/session status so a functioning screen cannot imply functioning audio. |
| [ncspot user guide](https://github.com/hrkfdn/ncspot/blob/main/doc/users.md#key-bindings) | Queue, Search, and Library are separate screens. Return plays; Space enqueues; another command inserts after the current item. There are distinct selected-item and currently-playing-item actions. Escape closes search/command mode. Queue deletion, clearing, and saving are explicit. | Borrow the distinction among play-now, play-next, and enqueue, but choose one consistent keymap. Do not copy ncspot's Space-to-enqueue if the UI uses the more familiar Space-to-pause. Preserve search, cursor, scroll, and parent context on Back. |
| [ncmpcpp bindings](https://raw.githubusercontent.com/ncmpcpp/ncmpcpp/master/doc/bindings) and [configuration](https://raw.githubusercontent.com/ncmpcpp/ncmpcpp/master/doc/config) | Browser, library, search, queue, and visualizer are distinct screens. Library has two/three-column modes and a configurable primary tag. Queue cursor and now-playing navigation are distinct. | A file library can use collection → album/project → track, with breadcrumbs and a parent action. At narrow widths collapse columns into a single drill-down list rather than truncating every pane. |
| [MPD protocol](https://mpd.readthedocs.io/en/stable/protocol.html) | MPD exposes queue song IDs/version, play/pause/stop state, elapsed/duration, volume, repeat/random, errors, and idle notifications. Repeat-current and repeat-queue are differentiated through repeat/single modes. | Maintain stable queue item IDs, ordered entries, current ID, repeat `off/one/all`, shuffle state, and explicit errors in the session. A queue is not an incidental copy of the visible list. |

## Proposed interaction contract

- **Browse:** Enter opens a container; Enter on a track plays it. Backspace goes to parent; Esc closes the topmost modal/search first and otherwise goes back. Tab changes pane focus. Up/down changes selection only. Remember each view's selected ID, scroll, and filter.
- **Find:** `/` opens a clearly focused search input; typing cannot trigger playback shortcuts. Esc restores the prior view. Empty search and no matches are distinct states. Searching/filtering must not mutate queue order.
- **Transport:** Space pause/resume; `n/p` next/previous; `< >` seek ±5 seconds; `+/-` volume; `r` cycles Off/One/All; `s` shuffle. Keep text labels for modes and current values. Give unsupported operations an explanation rather than accepting ineffective keys.
- **Queue:** Use an explicit key/action for Add to queue and another for Play next; show queued confirmation and upcoming count. Queue view supports select, play, remove, and reorder. Playing a collection snapshots its resolved track IDs. Shuffle an explicit traversal with history; do not choose a new random song on every redraw or repeat past entries unexpectedly.
- **Playing identity:** Show a play/pause marker on the current track, an independent focus treatment on the selected row, and a persistent title/time/volume/repeat/shuffle footer. A Now Playing command returns to the current context without destroying the previous browser state.
- **Session:** `q` detaches the UI when background playback is supported; an explicit Stop ends playback. Print a short detached status after leaving. Reattach queries the owner; persisted JSON alone cannot prove a process still plays.

The exact keys are recommendations, not a claim that all references agree. Include a compact footer and a full help overlay generated from the same dispatch table.

## Preparation and synthesis

Playback references do not establish a synthesis workflow. Recommended state machine: `queued → preparing → starting → playing ↔ paused`, with separate `seeking`, `stopped`, `ended`, and `error` events. Preparation should show the actual stage (for example, parsing, synthesizing, writing audio), elapsed work time, and cancellation. Use percentages only when the renderer supplies measurable units. Render progress is not playback progress.

Give each request a generation ID. Canceling or replacing work invalidates its result even if the child exits later. Publish completed cache files atomically; validate duration/format before starting transport. Retain the previous playable audio until the replacement is ready when practical. Never show Playing until the backend reports a usable playback clock/state. Missing tools, missing files, unsupported inputs, and output-device failure need distinct messages with a retry action.

## Transport comparison

| Backend | Evidence | Recommendation |
|---|---|---|
| **mpv** | [JSON IPC](https://github.com/mpv-player/mpv/blob/master/DOCS/man/ipc.rst) supports local sockets, command replies, and property observations. [Input/properties](https://github.com/mpv-player/mpv/blob/master/DOCS/man/input.rst) documents `time-pos`, `audio-pts`, seek, pause, volume, and end-of-file events. `audio-pts` accounts for driver delay but may be negative. | Preferred optional adapter. Start audio-only idle mpv with terminal input disabled and a private socket. Keep one IPC connection, subscribe to state/position/duration/volume, and serialize controls. Python `socket`, `json`, and `subprocess` suffice; Go needs no audio library. |
| **ffplay** | [Official manual](https://ffmpeg.org/ffplay.html) documents start seek (`-ss`), starting volume, `-stats`, audio-master synchronization, and window controls. [Source](https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/fftools/ffplay.c) prints master clock roughly every 30ms, compensates audio buffers, and handles keys through SDL events. | Already present. Run `-nodisp -autoexit -stats -sync audio`; parse CR-separated status in a worker. Resume/seek/volume can stop and restart with `-ss` and `-volume`, retaining the last confirmed position. Show Starting/Seeking until a fresh clock arrives. This has audible gaps and a human-format parser, so retain fixtures for supported versions and mark stale clocks unknown. |
| **afplay** | Local `/usr/bin/afplay -h` lists volume, duration limit, rate, and quality; no position query, seek, or command IPC. The installed executable is Apple's version 2.0. | Basic play/stop compatibility only unless a separately tested adapter supplies more. A monotonic elapsed estimate is not output-device time. Do not claim precision or a synchronized spectrum from it. |
| **MPD** | [MPD manual](https://mpd.readthedocs.io/en/stable/user.html) describes a server controlled through its protocol; it supplies its own library and queue machinery. | Strong for an existing MPD installation or large shared library, but extra database/configuration ownership is unnecessary for a small file engine. Borrow its model before adopting its daemon. |

**Do not simulate ffplay pause with SIGSTOP and call it accurate.** Process suspension does not set ffplay's internal pause state; buffered output and the advancing clock can diverge. This is an inference from the documented source clock/control paths. Writing `p` to ffplay stdin is also not the SDL key-event interface. A restart fallback must be described and tested as a restart fallback.

## Honest clocks and visualizers

Use a backend report containing `session_id`, `track_id`, `position_seconds`, `duration_seconds`, `state`, `observed_monotonic`, and `clock_source`. Paint at a modest frame rate. Interpolate only between fresh reports while Playing, with a short cap; freeze immediately for pause, seek, or preparation. On stale reports, stop extrapolating and reconnect/check the owner. Handle natural EOF separately from deliberate replacement/cancel and failure. Monotonic time is for freshness/interpolation, never the source of musical position.

For a file engine, precompute low-cost PCM peak/RMS envelopes or spectral frames while preparing the final rendered audio, then index them by confirmed playback position. The analysis must reference the exact rendered file hash, duration, sample rate, and hop interval. Label it **file analysis**, not live output measurement. If using output gain, apply known player volume/mute to amplitude; it still cannot measure hardware output or external EQ.

Alternatively consume PCM from the same playback pipeline. [ncmpcpp's configuration](https://raw.githubusercontent.com/ncmpcpp/ncmpcpp/master/doc/config) explicitly requires an MPD PCM FIFO and discusses audio-output buffering to address visualization lag. Either approach should freeze/clear at pause, cancel, missing data, or stale clock; a spinner can signal preparation, but random bars cannot represent sound. A MIDI note timeline can be useful if labeled as notes rather than waveform/spectrum.

## File engine and optional UI boundary

The Python session owner should hold the process, queue, generation IDs, and persisted settings; the Go UI consumes snapshots and events and sends semantic commands. An atomic JSON snapshot plus a private local control socket keeps file-oriented inspectability without concurrent writers. Validate session/process identity before cleanup; never kill an arbitrary persisted PID. Persist repeat/shuffle/volume/queue and last known item, but restore as Stopped/Paused until the owner confirms live playback.

[Python subprocess](https://docs.python.org/3/library/subprocess.html) supports child processes/pipes; POSIX `start_new_session` can separate the owner from the terminal. Detach stdin/stdout/stderr appropriately, drain child output, bound logs, and reap children. Session survival across TUI exit requires a session owner that itself survives; merely detaching a child and dropping its pipes is insufficient.

[Bubble Tea's command guide](https://github.com/charmbracelet/bubbletea/blob/main/tutorials/commands/README.md) puts disk/network/timer I/O in asynchronous Commands that return Messages. Keep synthesis, file scans, decoder work, and socket waits outside `Update`/`View`; carry generation IDs in completion messages. Preserve existing optional music feature gates; [Go build constraints](https://pkg.go.dev/cmd/go#hdr-Build_constraints) support tagged implementation/stub files. The default utility build should not require an audio backend or new native libraries. At runtime expose backend capabilities so the same UI can distinguish full, restart-based, and basic playback.

## Acceptance evidence worth collecting

1. Move focus/search/back while audio plays: track, clock, and queue stay stable.
2. Pause for several seconds, resume, seek both ways, change volume, reach EOF, and traverse repeat/shuffle: report backend position and audible result separately.
3. Exit/reopen UI: identify the same live session and queue; Stop reaps only owned children.
4. Cancel preparation and immediately select another item: no late result replaces it, no orphan player, no partial cache reuse.
5. Silence and a fixed-frequency test tone: analysis matches expected energy and freezes on pause; do not certify speaker synchronization from null-output tests.
6. Missing backend, malformed clock output, broken file, process crash, resize, tiny terminal, and disabled-music build: useful state with no blocked UI.
