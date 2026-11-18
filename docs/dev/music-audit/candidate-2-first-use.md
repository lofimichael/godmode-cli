# Frozen blind candidate review

Frozen on 2026-11-17 before reading application source, design documents, other reports or developer explanations of the interface. This pass used normal help, visible UI and a separate terminal recorder only.

## Verdict: 7.5/10 for the observed interface

This is a substantial step toward an everyday music player. The library has structure, the queue is visible and persistent, controls are discoverable, and closing feels deliberate. I can browse a collection, append a track, inspect/remove queued entries, return to my place and leave cleanly. It is much easier to understand than the 6/10 baseline.

It is not yet great because its two most useful workflows—search and building a queue—do not connect in a discoverable way. A search result can visibly be played but not queued. The queue loses source information, compact controls are sometimes wrong for the current view, and the important queue-replacement rule is buried near the bottom of help.

**Scope of score:** navigation, search, queue editing, setup explanation and exit only. No audio or synthesis was started in this pass. Playback independence, sound, pause/resume, seeking, next/previous and natural queue advancement are not verified by this review. The larger feature set described by help is not treated as demonstrated behavior.

## Candidate identity and conditions

- Began with `target/godmode-music-candidate-1`, read its ordinary help and captured one initial library screen. The parent then requested switching to candidate 2. Candidate 1 closed normally; no status-command defect was encountered or reproduced in this blind walkthrough.
- Main reviewed executable: `/Users/michael/conductor/repos/godmode-cli/target/godmode-music-candidate-2`.
- SHA256: `2c802090f5aa8791a31b6d76750aa1013ac56ae1f6ae33e11a7eebc213b34975`.
- Main HOME/GODMODE_HOME remained the baseline's private canonical temporary home, with the normal link to the supplied real local Darunia installation and 1,620-track directory. Agent homes/cache paths remained private.
- A second empty HOME nested inside that private home was used only to inspect fresh setup messaging.
- TERM=xterm-256color. Tested 80×24, a live resize to 40×18, and a fresh 40×18 process. No system volume changes and no playback-triggering key or command.
- `music status` at the end of queue work reported Stopped and the installed mpv path; `music queue` reported Queue empty.

## What the walkthrough demonstrated

1. **Help now establishes the product.** `help music` explains the local-only library, Darunia and mpv requirements, library/search/queue/close/stop controls, independent background playback, render duration and render-only option. This is materially more useful than the baseline's usage line. Top-level help now calls music “music library, queue, and playback.”
2. **Initial library is coherent.** The branded header, Library/Queue tabs, track total, collection counts, position indicator, fixed playback panel and footer form a legible hierarchy. Collection names give me a useful starting point instead of 1,620 flat titles. At 80×24, approximately eleven collection rows fit. At 40×18, approximately six fit.
3. **Controls are discoverable.** `?` opens scrollable help while retaining the playback panel. It explains queue append/delete, pause/resume, next/previous, seek, volume, repeat, shuffle, stop, close and reload. Esc returns. At the library root, Esc gives a helpful “q closes view; x stops…” message instead of aborting the command.
4. **Search is responsive and honest.** `/lost woods` yields two results and a visible result count. Adding `a` to that query produces zero results; the query stays visible and the empty state says to edit it or press Esc to clear. This fixes the baseline's hidden-query problem.
5. **Search-to-queue fails discoverability.** In search, the footer says `Type to search all tracks` and `↑↓ choose Enter play Esc clear`. `a` is inserted into the query. Selecting a result with Down does not leave text-entry mode. Tab has no visible effect. Esc clears results and returns to the prior collection view. I did not find a visible action that appends the chosen search result without playing it. This was the most significant task failure.
6. **Browse-to-queue works.** At collection root, selecting `20th Century Fox` and pressing `a` appends its one track. The message `Added to queue · Tab to inspect` gives immediate next-step guidance. Opening `A Hat in Time`, selecting `Clocktowers Beneath the Sea` and pressing `a` appends that track without starting audio. Queue count changes from one to two.
7. **Queue editing works.** Tab opens `Up next · Enter plays from this row`; both queued titles appear in order. Down + d removes the second item and says `Removed from queue`. Tab returns to the same selected track in the collection. Closing and reopening preserves the remaining queue entry. It was then removed; the final queue is empty.
8. **Queue identity is weak.** The queue displays `01 Intro`, with no collection/source. The library had shown which collection it came from, but the queue discards that context. With repeated generic titles such as Intro or Main Theme, I cannot confidently inspect the planned listening order from this view.
9. **Compact UI mostly fits, but its queue controls are wrong.** The 40×18 queue footer says `Tab queue  a add` and uses the generic `Enter open/play` wording. The correct 80×24 queue footer says `d remove` and `Tab library`. d still removes the entry at 40×18, but the useful action is hidden and Tab's displayed destination is wrong.
10. **Metadata access regresses at narrow width.** Source/collection labels disappear from narrow search and track lists; long titles are clipped. Tab is now queue navigation, and the visible controls/help provide no replacement for the baseline's full-title/details view. A user can see the source at 80 columns or use CLI output, but that is not a discoverable compact-player solution.
11. **Queue-replacement rule is hidden.** Near the bottom of `?` help, the player says Enter replaces the queue with the visible tracks at the selected position; `a` appends. This is an important consequence that the ordinary `Enter play` footer does not convey. I did not press Enter on a track, so actual replacement was not exercised. The documented rule is surprising enough to surface at the action, especially after a user has manually assembled a queue.
12. **Setup gives a command, but needs cleanup.** In a clean home at 80×24, the UI explains that Darunia is not linked, displays an init command, defines SYNTH and SONGS and names mpv. The initial error/source text runs together as `TRACK_FOLDER.https://github.com/lofimichael/darunias-cli`. At 40×18, most supporting setup instructions fall below the available content area, with no setup-specific scroll hint. The fixed idle-player panel and normal play controls take space even though nothing is linked.
13. **Exit is clean.** q closed candidate 1 and candidate 2 with exit code 0. No `Cancelled.`/130 failure wording. The help clearly distinguishes closing the view from stopping music; background continuation itself was not tested here.

## Changes needed to approach great

1. **Connect search and queue building.** Add a visible, non-text key to append a selected result, or separate query editing from result actions. Preserve query and selection while inspecting the queue. A new user should be able to search → append → search again without playing or losing context.
2. **Make playback and queue replacement explicit.** Present the intended scope of Enter where it is used. Playing one selected result, playing the remaining visible list and replacing an existing queue are different user intentions. The control should not leave that distinction to the bottom of help.
3. **Keep track identity available.** Show source/collection in queue rows when space permits; provide a compact details view or selected-item metadata when it does not. Retain full title access for clipped tracks.
4. **Make narrow footers reflect the current view.** Queue needs `d remove` and `Tab library`. Search needs an add action. Empty/unlinked views should not emphasize unusable play controls.
5. **Polish setup and transient feedback.** Separate the source link from the error sentence, keep the shortest complete setup instruction visible at 40×18, and expose scrolling or a dedicated setup view for additional detail. Messages such as `Added to queue` and `Removed from queue` persist across unrelated views; clearing or aging these would reduce stale feedback.

## Strengths to retain

- Collections with counts, global search with result counts, and a clear Library/Queue distinction.
- Fixed now-playing context across browsing, queue and help.
- Explicit add acknowledgement and the immediate Tab-to-inspect cue.
- Queue changes are reflected immediately and survive closing/reopening.
- Returning from queue preserves the selected collection track.
- Search empty state preserves the query and supplies useful recovery.
- Clear q-close versus x-stop language, reachable controls help, and exit code 0.
- Compact header and fit at 40×18 without requiring a wider terminal for basic browsing.

## Screenshot and transcript evidence

The PNGs are reconstructions of captured PTY cells using pyte and a monospace font, not screenshots of a native terminal window. Matching `.txt` files preserve their screen text. Complete ANSI transcripts and timed input logs are retained. Screens after terminal exit show an unsupported terminal-negotiation suffix in the emulator; it is not claimed as an application defect. A live-resize capture also showed stale cells after later updates; a fresh 40×18 capture was clean, so the resize artifact is not included as a verified product finding.

- `03-candidate-2-library-80x24.png` — structured library.
- `04-controls-80x24.png`, `05-controls-scrolled-80x24.png`, `20-narrow-controls-bottom.png` — visible control contract.
- `07-search-results.png`, `08-attempt-add-from-search.png`, `10-tab-while-searching.png` — search-to-queue obstacle and improved empty state.
- `13-add-collection.png`, `15-add-track.png`, `16-queue.png`, `17-queue-remove.png`, `18-back-collection.png` — successful queue workflow.
- `27-fresh-narrow-search.png`, `29-narrow-queue.png`, `30-narrow-empty-queue.png`, `32-escape-at-root.png` — fresh compact layout and control context.
- `34-clean-home-setup.png`, `35-narrow-setup.png` — first-run guidance.
- `candidate-1-walkthrough.ansi` — initial candidate 1 screen and normal close only.
- `candidate-2-wide-walkthrough.ansi`, `candidate-2-narrow-walkthrough.ansi`, `walkthrough.ansi` — candidate 2 wide, fresh narrow and setup sessions, respectively.

No implementation review informed this report. Later findings must be recorded separately rather than rewriting the frozen first-use account.
