# Candidate 6 independent retest

**8/10. The core local-sequence player is now good for everyday use. I would still stop short of calling the entire first-time experience great.** The material playback and navigation defects from my 6.5/10 review are fixed in the flows I exercised. One minor action-promise mismatch remains in the detail view, and first-time setup still assumes the user already knows how to acquire/install Darunia and tracks.

This judgment uses my own help, UI, and command observations only. I read no implementation or other reviewer reports. Near the end of recording, the parent notified me that a newer build exists and supplied test context; those claims are not used as evidence for this candidate's score or findings.

Candidate SHA-256: `50cf317351bdd9c788663c25ebb6c3ce2a3d572709423a364eb11d508e110d77`.

## Verified fixes

- **Stopped-current removal stays stopped.** With Ganondorf as the stopped current entry, I queued Clocktowers Beneath the Sea and removed the current entries until Clocktowers became current. State remained STOPPED, position 0, volume 0. See `49-stopped-queue-three.png`, `50-stopped-remove-duplicate-current.png`, `51-stopped-remove-current-to-different.png`, and `stopped-removal-confirmed-status.json`.
- **Paused-current removal stays paused.** I exercised both duplicate-next and different-next cases. Removing paused Gerudo with Ganondorf next prepared the next track and left it PAUSED at 0:00 / 0:10, volume 0; a later snapshot remained paused. See `23-paused-current-removal.png`, `32-paused-removal-different-track.png`, `33-paused-replacement-stable.png`, and `paused-removal-different-status.json`.
- **Search Enter is safe and understandable.** Typing `/gerudo` then Enter focuses results without starting playback. The query-entry footer says Enter/Tab results, and the focused result says that Enter plays and replaces the queue while `a` appends. See `05-query-editing.png` and `06-enter-focuses-results.png`.
- **Queue-origin search returns correctly.** From queue, I searched Ganondorf, focused results, opened details, appended, returned to results, and pressed Tab. It opened the queue with the added track and retained the current paused track. See `26-queue-before-fresh-search.png` through `31-fresh-tab-queue.png`. Small-terminal search-to-queue navigation also worked (`42`–`46`).
- **Adding from details works.** `a` now increments the queue with an Added message while the panel remains open. This worked for Gerudo, Ganondorf, and A City Of Calcite And Adventure. See `08`, `29`, and corrected-render `74`.

## Everyday use and remaining friction

Collection browsing has a clear breadcrumb and stable selection/playing separation. Reopening retains the queue and stopped track. The 40×18 layout remains usable; full long titles and collection names wrap and scroll in details. The dedicated current-track area and explicit PLAYING/PAUSED/STOPPED labels are legible.

**Remaining minor issue:** after adding from details, the visible message says `Added to queue · Tab to inspect`, but Tab leaves the detail panel open. I had to use Esc before Tab. This is the same class of misleading action hint as the earlier detail issue, but the append itself now succeeds and the workaround is obvious in the footer. Corrected screenshots `74-corrected-details-add.png` and `75-corrected-details-tab-inspect.png` show it.

The search field retains its last query. Starting a new search from the queue and typing another name appended it to the hidden previous query (`gerudoganondorf`) until I cleared/edited it. This is recoverable, but selecting the old text or making a fresh-search action explicit would reduce first-use friction. Backspace editing, Esc clearing, and refocusing results work.

Organization is still source collections plus a queue; I did not find personal collection creation, saving, renaming, or queue reordering in normal help/UI. That does not block the advertised local player loop, but it limits it as a full music organizer.

## Setup and plain fallback

Clean homes at 80×24 and 40×18 show a legible `music init SYNTH --songs SONGS` command, mpv install hint, reload, and exit instructions. The screen does not explain where to get/install Darunia or compatible tracks. I could proceed because the audit supplied those directories.

`--plain music` exits successfully with a useful static setup/find/play/queue/stop guide. It distinguishes an unconfigured home from the configured 1,620-track library. Running `music` with non-TTY captured output also returns this fallback rather than hanging. Evidence: `03-plain-unconfigured.png`, `53-plain-configured.png`, `54-empty-setup-40x18.png`, and `non-tty-fallback.json`.

## Renderer correction and evidence limits

The apparent wrapped `/ 492` counter and stale text in early screenshots were **my renderer's error**, not a demonstrated product defect. The live ANSI output uses cursor-backward-tab (`CSI Z`), which stock pyte omitted. I added that terminal operation to the harness and captured fresh output; the same library and detail screens align cleanly. Use screenshots `71`–`75` for visual judgment. `initial-terminal.ansi` preserves the raw fixture capture supporting this correction. Earlier screenshots remain useful for state and action sequences but should not be used to allege those layout artifacts.

Some early screenshot filenames describe an intended action that navigation did not perform; I did not count those attempts as passed checks. In particular, the definitive stopped-removal evidence is `49`–`51` and `stopped-removal-confirmed-status.json`, not the earlier similarly named attempt.

Before **any** playback action, I queued a track, used documented `music volume 0`, and verified `volume: 0.0` in `verify-muted-before-any-play.json`. Deliberate playback used `--seconds 10`. The technical paused status reports a 10-second duration, advancing position, and `mpv:audio-pts`; later removal tests remained at volume 0. This establishes technical player behavior, not heard musical quality or fidelity. The fixture was stopped at the end; all homes and agent/XDG paths were private fixture directories. No real keys/profile/seal were read.

**No remaining material functional blocker was observed in the exercised player flows.** My remaining reservations concern the details Tab promise, first-time setup guidance, and the limited organization surface.
