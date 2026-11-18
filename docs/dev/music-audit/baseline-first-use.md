# Frozen blind first-use review

Frozen after the walkthrough on 2026-11-17. No implementation, design document, prior audit, or repository harness was read before this report. Only the installed command's help, its visible output, filesystem path canonicalization, and an independent PTY safety/capture harness were used.

## Verdict: 6/10

The normal terminal library is usable and the synthesis-to-play path works. It feels like a one-song command with a pleasant visualizer, rather than a music player I can comfortably stay in. Search and details are the strongest parts. Stopping playback ends the command, empty search hides what I typed, and the help does not establish what controls or limitations to expect.

This score covers observed first-use usability, not audio fidelity. I could inspect the terminal and child process but did not hear the output; no listening-quality claim is made. Only one song was synthesized. No slow render, render failure, natural end of playback, playlist, seeking, or full song listening was exercised.

## Test boundary

- Executable: `/Users/michael/.godmode/bin/godmode`.
- Synth: `/Users/michael/Documents/GitHub/darunias-cli`; tracks: the supplied local OoT-Custom-Sequences `data/Music` directory. These were linked through normal `music init`; neither was edited.
- All music configuration/cache work used private `/private/tmp/godmode-music-firstuse.pDRO9K` HOME and `.godmode`, with private Codex/Claude homes. Initial `--help` preceded isolation; it was a help-only invocation, with no configuration operation requested.
- Normal PTYs: TERM=xterm-256color, 80 columns × 24 rows and 40 × 18. An initial inherited TERM=dumb run was separately observed as the static fallback.
- One owned `/usr/bin/afplay` process ran for approximately 4.2 seconds, then `q` stopped it. The harness verified no owned descendants remained. No system volume changes. No further audio after the parent requested the narrow check only.

## Task walkthrough

1. **Find the entry.** Top-level `--help` lists `godmode music` as “local music and visualizer.” It also establishes Arrow/Enter/Esc/q and `/`. This is discoverable if the user already checks help. `help music` contains just usage and a cache sentence; it does not explain what `init DIR` expects, how to obtain inputs, or playback controls.
2. **Link local assets.** Precreating the private Godmode directory with normal mkdir permissions yielded an exact actionable `chmod 700` error. After that, init failed with `Music paths must not contain symlinks.` Both supplied music paths were canonical and symlink-free. Changing the private HOME spelling from `/tmp/...` to `/private/tmp/...` fixed it. The error never identified the offending path. Successful setup said `Darunia's CLI linked. 1620 local tracks.`
3. **Open at 80×24.** Compact library, roughly 18 visible tracks, selected source context at right, and a helpful footer: `↑↓ choose  Enter play  Esc back  / search`. Long source labels are truncated with ellipsis; Tab details becomes available. The library lacks a visible total count, current position or cache state, but the core scan is clean.
4. **Find Lost Woods.** `/lost woods` filters instantly to `Lost Woods (End Credits Version)` and `Path of the Lost Woods`. Tab shows the full selected title and source (`The Legend of Zelda Ocarina of Time`). Tab returns cleanly. Esc clears the search while preserving the selected track's place in the full library, which is useful.
5. **Synthesize and preview.** Enter displays a spinner and `Synthesizing Lost Woods (End Credits Version) · q stop`. In this run the owned player appeared about 0.99 seconds after Enter. Success said `Synthesized · 3:00`. The playback title changed to `OOT - Lost Woods (ED version)` with `OoT instruments`; the title mismatch slightly weakens continuity with the selection. The visualizer and time/progress display are legible at 80×24. The sole visible playback control is `q stop`.
6. **Stop and return.** Sent q after ~4.2 seconds of player lifetime. The owned player stopped, `Music stopped.` printed, and the command exited with code 130. No library was presented. The harness tried an Esc intended for the expected library and received a closed-PTY error; this is a harness expectation failure, not an application crash. A user would need to invoke music and find the track again to continue browsing. Plain Esc from the library also exits with `Cancelled.` and code 130, which sounds like an aborted operation rather than an ordinary exit.
7. **Narrow terminal, 40×18.** The library fits, long titles truncate, and the footer wraps across two lines. Source labels disappear from the list, but Tab details reveals them clearly. `/lost woods`, Tab, Tab-back, Esc-clear, and Esc-exit all worked. No narrow-screen playback was performed.
8. **Empty search.** Typing `/zzzznotatrack` changed the query row to `/ No matches` and printed another `No matches` in the result area. The actual typed query disappeared, making correction harder. The footer still offered `Enter play` and `Tab details` despite no selected result. Esc cleared it successfully.
9. **Errors/status.** `music status` clearly lists synth, tracks, cache and source locations, but no track/cache counts. `music play zzzznotatrack` fails with `No local tracks match. Run godmode music list.` This is comprehensible, but the offered recovery is a full-list command rather than an example of interactive search.

## Separate static fallback observation

The tool PTY initially inherited TERM=dumb. Music printed all 1,620 tracks (3,243 output lines) followed by a numbered prompt. `q` plus Enter was rejected as an invalid choice despite the global help's “q quits from menus.” Esc exited. This is a fallback experience, not evidence that the normal xterm library overflows. Nevertheless, 1,620 unpaged entries and inconsistent quit behavior are real first-use friction in that supported-looking mode.

## Highest-impact changes, in order

1. **Keep the music session open.** Give playback an explicit library/back action that stops audio and restores query/selection. Make exit a separate, clearly named action. At minimum, `q stop` should not promise only a stop while also discarding the session.
2. **Preserve the search query on no matches.** Keep `/ zzzznotatrack` visible, show one empty-state message, and offer backspace/edit and Esc-clear guidance. Remove inactive play/detail hints from that state.
3. **Explain the minimal music contract.** Music help should state the two required folder types, show one init/play example, explain synthesis/caching and supported playback controls. If pause, next and seek do not exist, do not imply a richer player; better visible controls would materially improve the experience.
4. **Make normal exits normal.** Distinguish library exit, playback stop and render cancellation in both wording and exit code. `Cancelled.`/130 for a deliberate menu exit reads as failure.
5. **Repair fallback browsing and recovery.** Paginate or provide query-first search for static mode; ensure q/Esc behavior matches instructions. Name the actual path rejected by the symlink guard, including cache/home paths.

## Strengths to retain

- Responsive incremental search across both track and source context.
- Search-clear restores selection and location in the library.
- Tab details recovers truncated metadata, including at 40×18.
- Clear render verb, animated activity indication and a visible stop control.
- Time/progress and successful owned-player cleanup.
- Simple setup success message with a concrete local track count.

## Evidence files

- `observations-live.md`: notes taken before playback and narrow-screen tests.
- `80x24-preview.ansi`: complete raw walkthrough/playback transcript.
- `80x24-before-play.ansi`, `80x24-player-start.ansi`, `80x24-after-q.ansi`: event captures.
- `80x24-preview-events.json`: monotonic timestamps and owned-player lifecycle.
- `blind_pty_preview.py`: independent capture/safety harness; its attempted post-exit Esc caused its own expected-state error after successful cleanup.
- `40x18-snapshots.txt`: verbatim representative narrow-screen text transcribed from tool output.

The report is frozen before any implementation review. Later discoveries must be recorded separately rather than retroactively changing these first impressions.
