# Frozen independent candidate 5 review

Frozen 2026-11-17. This review used normal command help, the visible terminal interface, my own prior findings, and an independent terminal recorder. No application implementation, research, design document or other review report was read. Messages from the parent about work in progress did not substitute for observations below.

## Verdict: 8.5/10 for the observed interface

Good and much closer to an everyday music player, but I would not yet call this great. Search → focus results → append → inspect queue now works without playback. The queue identifies tracks, compact controls are correct, full metadata is available, and setup instructions fit at 40 columns. The main remaining friction is that inspecting the queue discards a search, while the details screen advertises actions that do nothing there.

This is an interface score, not certification of the complete music experience. Playback was kept stopped throughout this pass. Sound, synthesis, buffering, pause/resume, skipping, seeking, background continuation, natural completion and audio-reactive visualization were not exercised. No player-volume or system-volume change was made. No audio-quality claim is warranted.

## Identity and test boundary

- Executable: `/Users/michael/conductor/repos/godmode-cli/target/godmode-music-candidate-5`.
- SHA256: `8adbaab281b1c3fcc95e26aa747ae637eebb0315a5affa98d02e6ce5f9b9d4a1`.
- Main isolated home: `/private/tmp/godmode-music-firstuse.pDRO9K`, with its private Godmode/agent/cache directories and existing normal link to the supplied Darunia installation and 1,620 local tracks.
- Clean setup home: `final-clean-home` nested inside that private home. It was linked through normal `music init`, then reloaded through the UI's documented R key.
- Fresh PTYs at 80×24, 40×18 and 120×36; TERM=xterm-256color.
- Final main status, saved as `final-status.json`: stopped, no track, empty queue, volume 35.0, repeat off, shuffle false.
- All opened UI processes closed through q with exit code 0.

## Earlier blockers: independent retest

| Earlier issue | Observed result in candidate 5 |
| --- | --- |
| Search results cannot be enqueued | **Resolved.** `/lost woods`, Enter to focus results, Down to choose, a to append. Queue count updates; Tab shows the selected track. Search-edit and results modes have distinct instructions. |
| Queue-replacement behavior hidden in help | **Resolved as a disclosure issue.** A selected result says `Enter plays from here · replaces queue · a appends` at 80 columns and `Enter replaces queue · a appends` at 40. Actual playback/replacement was not triggered. |
| Queue omits source | **Resolved.** Source appears in 80/120-column queue rows. At 40 columns, selected source appears in the context line and i exposes the full value. |
| Narrow queue footer shows wrong actions | **Resolved.** It now says `Tab library`, `d remove` and `i info`; the tested queue removal still works. |
| No full metadata access at narrow width | **Resolved for reading.** i opens full title/source at 40×18, and Esc returns. Its action guidance has a separate inconsistency below. |
| Compact setup hides instructions | **Resolved for the tested local setup.** The complete init command, folder meanings, mpv requirement and R-reload hint fit on the initial 40×18 screen. Normal init succeeded and R changed the open UI from 0 to 1,620 tracks. |
| Exit feels like cancellation | **Resolved.** q exits 0, and the visible contract distinguishes close from stop. No Cancelled/130 wording appeared. |

## Everyday-flow evidence

- Read `help music`; it explains that Enter/Tab ends search editing and focuses results, while a appends and Tab switches library/queue.
- Searched Lost Woods, focused results, appended one result and later the other, inspected both in order and verified their source collections.
- Switched back from the queue: the search was gone and the UI returned to Collections. Reproduced this with the corrected recorder at 80×24 and again at 40×18.
- Opened a queued track's i page at 40×18. The full title/source were readable. The page says `a appends it to the queue`; pressing a did not change the queue count or produce feedback. Repeated this from a search-result details page at 80×24 with the same result.
- At 120×36, browsed A Hat in Time, selected Death Wish, visited the queue and returned. The collection and selected track were preserved. This isolates the restoration problem to search context rather than all browsing context.
- Viewed the compact queue, info and controls pages. Basic navigation fits. Longer help lines still truncate rather than wrap, although the key workflow instructions are now visible elsewhere.
- At 120×36, the selected-item sidebar makes source and available actions easy to inspect. The larger logo consumes more rows, but the layout still leaves useful browsing space.
- Removed both test queue entries, closed normally, and checked CLI JSON status. It reported stopped with an empty queue.
- Opened the clean-home 40×18 setup screen, used its normal init command with the supplied local paths, pressed R and observed the populated library. No file editing or undocumented flag was needed.

## Remaining issues that prevent a great rating

1. **Queue inspection loses search context.** Search results → Tab queue → Tab library returns to Collections and drops the query/selection. This interrupts assembling several tracks from one search. Preserve the search as the library view until the user explicitly clears it. Evidence: `15-search-enqueue-corrected-80x24.png`, `16-queue-corrected-80x24.png`, `17-return-loses-search-80x24.png`.
2. **Details advertises inactive actions.** The i page says `a appends it to the queue`, but a is ignored there; only the reading/return controls visibly work. Either support the action there or say “Return to the list to append/play.” Enter was not pressed because playback was excluded, so only a's failure is verified. Evidence: `20-queue-info-40x18.png`, `22-queue-info-add-attempt-40x18.png`, plus the initial-pass input transcript.
3. **Enqueue acknowledgement is less visible than before.** On the focused library/search list, a changes the queue count, but the main context line immediately continues to show the Enter/replacement hint. The explicit `Added to queue · Tab to inspect` message becomes visible after switching to the queue. A brief visible acknowledgement on the action would improve confidence and reduce duplicate additions. Evidence: `15-search-enqueue-corrected-80x24.png` then `16-queue-corrected-80x24.png`.

The first issue is the most important remaining daily-workflow interruption. None of these prevented the tested user from constructing and editing a queue, but together they make the interaction less consistent than a great player should be.

Lower-priority polish: `PCM / player clock`, `waiting for audio` and `No signal` expose implementation language in an idle music UI. “Stopped” already communicates the user-relevant state. Compact help could wrap long descriptions. Empty queue still offers actions requiring a selected entry; its recovery copy remains understandable.

## Capture quality and exclusions

PNGs are reconstructions of captured terminal cells, not photographs of a native terminal window. Each has matching text. Complete ANSI output and timed input logs are retained for the wide, narrow, large and clean-setup sessions.

The initial recorder used ordinary pyte, which does not implement the ANSI backward-tab sequence CSI Z. Candidate 5 legitimately emitted CSI Z for right alignment; the recorder consequently wrapped the count and left stale text. Inspecting the emitted ANSI identified this exact cause. I added standard backward-tab support to the recorder and fresh captures aligned correctly. **The count-wrap is not a product defect.** Incremental UTF-8 decoding was also added to avoid split-character artifacts. Exit captures include an unsupported keyboard-protocol suffix in pyte; this is likewise not a product finding.

Use these corrected, fresh screenshots for review:

- `01-initial-80x24.png`, `01-initial-40x18.png`, `01-initial-120x36.png`.
- `15-search-enqueue-corrected-80x24.png`, `16-queue-corrected-80x24.png`, `17-return-loses-search-80x24.png`.
- `19-queue-40x18.png`, `20-queue-info-40x18.png`, `25-result-intent-40x18.png`, `26-help-40x18.png`.
- `28-selected-collection-track-120x36.png`, `30-collection-selection-restored-120x36.png`, `31-controls-120x36.png`.
- `setup-01-initial-40x18.png`, `35-setup-reload-success-40x18.png`.

The report is frozen for the exact candidate 5 hash above. Any later candidate or fix requires a separate addendum; it must not retroactively change these observations.
