# Blind first-use review — candidate 4

Verdict: **6.5/10. Not yet great for everyday use.** The main browse/search/queue/player loop is useful and visually coherent, including at 40×18. Unexpected queue behavior and misleading detail-view actions still undermine confidence. I would use it experimentally, but would not yet trust queue maintenance to preserve a stopped session.

This report is frozen before receiving developer/design context. I used normal command help and the actual interactive executable. I did not read implementation, prior reviews, or product design documents. The only repository code read was permitted PTY/recorder harness material. Screenshots are actual PTY output rendered through pyte/Pillow, not recreated UI mockups.

Executable: `/Users/michael/conductor/repos/godmode-cli/target/godmode-music-candidate-4`

SHA-256: `38dc92621ebeaac432295cd509f3615aaf68377071ac4750725bd5e399e02120`

## What worked

- Normal help led directly to `music --help`, then the music UI. The empty UI explains the link command, local-only files, mpv, reload, and close. Both 80×24 and 40×18 empty states are legible. It does assume I already know where to obtain/install Darunia and tracks; it gives no acquisition/setup route beyond the link command.
- Linking the supplied local synth and song directory reported 1,620 tracks. The library grouped them into named collections, with counts and an All tracks entry. Opening A Hat in Time, browsing its three tracks, and returning to the collection root were understandable.
- Searching titles and collection names worked across the whole library. `/final` found 87 results. After using the documented Tab-to-results action, `a` appended the selected result without playing it.
- Appending an entire collection worked: A Hat in Time added its three tracks to the queue. Queue rows identify their originating collection at 80 columns. At 40 columns, a selected-origin line and `i` provide the detail that cannot fit on the row.
- Full long title and collection details work at 40×18. `Demon King Ganondorf Battle - Second Form (Second Half)` and `The Legend of Zelda Tears of the Kingdom` wrap legibly; the detail panel scrolls. See `30-small-long-title-details.png` and `31-small-details-scrolled.png`.
- The fixed NOW PLAYING area distinguished the active track from a different highlighted collection. Browsing did not change that active track. Muted play, Space pause/resume, and player-clock advancement were observed. Closing and reopening retained the paused track and queue. Closing explains that music remains paused/playing and gives the stop command.

## Concrete blockers and friction

1. **Removing the current queue entry starts playback from a stopped session.** Reproduction: play a bounded track, stop with `x` (UI says `Stopped · queue kept`), append A Hat in Time, open queue, press `d` on the first/current entry. The player changed from STOPPED to PREPARING and then PLAYING the next entry. I expected queue editing to preserve stopped state. Evidence: `43-stop-owned-playback.png`, `44-append-whole-collection.png`, `45-collection-in-queue.png`, `46-remove-queue-entry.png`, and `48-help-controls-lower.png`. This is the main everyday-use blocker.

2. **Searching from the queue leaves Tab behavior inconsistent with its label.** From queue: `/ganondorf`, Tab to results, `i`, Esc, `a`, Tab. The results footer said `Tab queue`, but the final Tab took me to the library Collections root rather than the queue. See `29-small-search-long-title.png` through `34-small-queue-long-track.png`. The last filename describes the intended action; its actual screenshot is Collections. I had to reconstruct where I was.

3. **Detail text advertises actions that do nothing while details are open.** The panel says `a appends it to the queue.` Pressing `a` there left Queue 0 unchanged with no feedback. I returned to the list before using the action successfully. See `07-collection-track-details.png` and `08-append-from-details.png`. Either make those actions work in the panel or explicitly say to return to the list first.

4. **Organization remains basic.** I could browse source collections and append/remove queue entries. Neither help nor the UI exposed creating/saving a personal collection, renaming one, or reordering the queue. This is a limitation for an everyday music organizer, not a claim that hidden functionality does not exist.

5. **Search has a first-use trap, although its footer documents the behavior.** I typed a query then Enter expecting to finish the query; Enter starts playback immediately. Arrowing through search results also leaves text-entry focus active, so `a` becomes part of the query until Tab moves to results. The contextual footer is accurate once noticed. I would put the focus/action distinction nearer the query or selected result.

6. **Visible rendering artifacts need independent terminal validation.** In this pyte render, the initial collection counter wrapped into the separator as `/ 492`, and stale fragments persisted into later headers/help rows. Examples: `05-library-80x24.png`, `25-reopen-small.png`, `48-help-controls-lower.png`. These are real captured PTY bytes interpreted by the harness, but I have not verified whether every artifact reproduces in a native terminal emulator. Do not treat this as a proven native-terminal defect without that check. My score does not depend on it.

## Playback and safety evidence boundary

There was an unintended action in the audit: Enter after the first search initiated PREPARING at the default 35% before I had established mute. I stopped that isolated session as soon as I observed it, then ran documented `music volume 0` and verified `status --json` showed `volume: 0.0`. I cannot certify what was audible in that brief interval. The audit therefore does **not** establish a perfectly silent entire session.

All deliberate playback after that point used verified volume 0 and `music play "Gerudo Fortress" --seconds 10`. The technical status reported a 10.0-second duration, a nonzero position, PAUSED state, and `clock_source: mpv:audio-pts`; the UI subsequently showed PLAYING at 0:01 / 0:10 and PAUSED. See `paused-state.json`, `39-small-playing-muted.png`, and `40-small-paused-ui.png`. The unexpected playback from removal also showed 0% and a 0:10 duration. No claim about heard quality, faithful instrumentation, or subjective listening quality is made.

`--render-only` while the player session was stopped returned `Music is running. Stop it before changing its cache.` This was recorded in `render-ten-seconds.json`; I used bounded normal playback afterward. It was not investigated through source.

The fixture was stopped at the end. `final-state.json` reports STOPPED and volume 0.0. All interactive PTYs exited successfully, and a final process-name check found no remaining candidate/Darunia/fresh-candidate process. No keystrokes were sent after PTY exit. HOME, GODMODE_HOME, CODEX_HOME, COPILOT_HOME, and XDG paths were isolated beneath this evidence directory; no real provider keys/profile/seal were accessed.

## Evidence map

- `01-clean-unconfigured-80x24.png`, `50-clean-unconfigured-40x18.png`: first-run empty state.
- `05-library-80x24.png`, `06-open-collection.png`: collection organization.
- `21-search-results-focus.png`, `22-append-found-safely.png`, `23-queue-three-origins.png`: search, append, queue origin.
- `25-reopen-small.png`, `26-small-queue-origin.png`, `30-small-long-title-details.png`: small-terminal persistence and details.
- `39-small-playing-muted.png`, `40-small-paused-ui.png`, `42-reopen-paused-player.png`: technical playback/pause/reopen.
- `43-stop-owned-playback.png` through `48-help-controls-lower.png`: stopped-session queue edit that starts playback.
- Each PNG has a same-name `.txt` containing the terminal grid. `harness.py` records the fixture/rendering method.
