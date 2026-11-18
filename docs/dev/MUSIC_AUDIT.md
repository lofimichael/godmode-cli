# Music Pack implementation and evidence audit

Recorded 2026-11-17. This is a local preview audit, with exact-build evidence below. It is not a public release or a listening-quality review.

**Final local-preview handoff:**

- Final core SHA-256: `0de090cb69475ec82fc941f605d959a6787c216ac191e730912211fb2b9e5934`.
- Final companion SHA-256: `6304edecd912fc8d0133447351864e8ec2362c86eda6a7026a1d3d8e3ce8cd17`.
- Full Python suite: **438 passed in 207.265 s** ([log](music-audit/verification/python-pack-final.log)). After the final UI polish, **10 native/isolation tests passed in 7.433 s** ([log](music-audit/verification/native-pack-polish.log)). The final **Go race suite passed across all eight packages with tests**, with cached results noted in the [log](music-audit/verification/go-pack-final.log).
- Optional-build/source separation: [boundary receipt](music-audit/verification/pack-boundary-final.json) verifies the default core excludes player packages, the companion excludes credential/business packages, and the native no-music build omits pack/player/assets while unrelated commands work.
- Post-polish independent review: **9/10, great within the observed terminal-user scope**. The [focused addendum](music-audit/pack-review/ADDENDUM.md) verifies immediate jingle discovery, readable help paging at 40/80 columns, preserved setup scroll on Back, normal exit and terminal restoration. Both prior findings are resolved; no remaining blocker was observed in that focused scope.
- Installed core: `/Users/michael/.godmode/bin/godmode`; installed pack uses the final companion hash above. The [installation receipt](music-audit/local-install/installation.json) records the rollback hash, ten unchanged nonmusic/shell file metadata checks, the owned 13,972,742-byte runtime, a successful muted installed jingle, and stopped music. No Darunia checkout is used. This is a private local preview, not a public release.

## Boundary and lifecycle

The core CLI contains a lightweight Music Pack manager, routing, and opt-in card. It does not embed the player, synth, instruments or jingle engine. The separately built `godmode-music` companion contains the Bubble Tea/Lip Gloss player and a readable Python bundle with only terminal, music, runtime and jingle modules; it imports no credential/profile engine. The default core works without the pack. `--without-music` / native `nomusic` additionally removes the manager hook.

Local installation verifies a supplied artifact hash, probes its platform/protocol, and installs a private executable with a pinned receipt. Forwarded foreground commands hold a shared lease; install/remove requires an exclusive lease, preventing removal during an open view, setup or jingle. Children do not inherit that lease. Removal first stops the owned music session, then removes the pack, compiled runtime and rendered cache while preserving source songs. A remembered local artifact supports reinstall. The manager defines an HTTPS release-manifest URL; only that client contract was verified. The public request returned HTTP 401, and no downloadable pack release was published or successfully installed from that URL.

Playback belongs to one detached per-home Python session, controlled through a private Unix socket and bounded JSON protocol. The TUI is a client. Closing it preserves playback; explicit stop cancels owned synthesis, closes mpv, and ends the daemon. Queue, volume, repeat and shuffle are stored separately from credentials and restored as stopped. No stored PID is trusted for arbitrary process termination. Long-home socket paths use a private hashed temporary endpoint.

`music setup --songs DIR` builds an owned runtime offline from the pack's verified assets. It needs the existing C/C++ compiler, CMake and FFmpeg; playback uses external mpv. A Darunia checkout is no longer required. Failed or canceled setup preserves the working config and removes owned staging/compiler processes. Original rendering behavior remains: mapped OoT instruments are the default; one unsupported instrument makes the whole song use piano. The minimal source/font selection and exact provenance are recorded in [runtime inventory](music-audit/self-contained-inventory.md), [font inventory](music-audit/font-provenance.md), and the bundled third-party notices. The private copy was authorized; asset redistribution rights are not inferred from software licenses.

## Implemented interaction and transport

- Collections, tracks, search, selected details and queue have distinct navigation state. Moving focus does not start playback. Enter opens a collection; after search entry it focuses results before a further Enter plays. Search, selection and parent context survive the tested Back/Tab paths.
- `a` appends; Enter on a library track replaces the queue with its visible context. `c` opens a found track's full collection; `A` appends that collection. Details expose long titles. Queue deletion preserves stopped state, and replacing a paused current entry stays paused. These are collection-and-queue controls, not a personal playlist editor.
- Space pauses/resumes; next/previous, relative seek, volume, repeat off/one/all and shuffle operate through the session. Controls and errors are asynchronous; a canceled/replaced preparation result cannot take over a later generation. Preparation reports elapsed work separately from playback position.
- A bounded one-next-track prefetch runs during playback. A small in-session prepared-track cache reuses validated renders and checks source/runtime/output signatures. This reduces repeated preparation work; gapless transitions are not claimed.
- mpv JSON IPC uses an inherited socketpair rather than an exposed mpv socket. Position comes from `audio-pts`, with `time-pos` fallback; state reports clock source and freshness. The PCM spectrum is calculated from the rendered file at that reported position. It clears while paused/stopped/preparing or when the clock is stale. It represents file analysis before player/output gain, not a microphone, speaker measurement or proof of audible synchronization.
- Plain/non-TTY `music` produces a bounded static guide rather than listing 1,620 tracks or starting an interactive picker. Playing without a track name is an error, not autoplay.

The design research is preserved in [research.md](music-audit/research.md). Primary references include [spotify-player commands](https://github.com/aome510/spotify-player#commands), [Spotify TUI configuration](https://github.com/Rigellute/spotify-tui#configuration), [ncspot controls](https://github.com/hrkfdn/ncspot/blob/main/doc/users.md#key-bindings), [MPD protocol](https://mpd.readthedocs.io/en/stable/protocol.html), and [mpv IPC](https://github.com/mpv-player/mpv/blob/master/DOCS/man/ipc.rst). These informed the separation of focus, queue and transport. The research file is a dated proposal: its early tool-availability notes and proposed extras are not claims about the final implementation.

## Independent review progression

Scores are each reviewer's judgment within its stated scope, not averaged product scores or audio-quality ratings. Historical reports remain unchanged.

| Stage | Observed judgment | Scope/evidence |
| --- | --- | --- |
| Original baseline | 5/10 library; 6/10 first use | [Library](music-audit/baseline-library.md), [first use](music-audit/baseline-first-use.md) |
| Candidate 6 / build 7 follow-up | 9/10 interface; 8/10 broader candidate | [Interface](music-audit/candidate-6-interface.md), [lifecycle](music-audit/candidate-6-lifecycle.md), [interface follow-up](music-audit/build-7-interface-addendum.md), [lifecycle follow-up](music-audit/build-7-lifecycle-addendum.md). These predate the separate pack and owned setup. |
| Separate-pack fresh review | 8.5/10; no observed functional blocker | [Frozen report](music-audit/pack-review/REPORT.md). Covered opt-in, owned setup, search/collection/queue, muted playback, exit/stop, remove/reinstall, and unchanged contents of all 1,620 source tracks. |
| Final polish retake | 9/10 within the observed terminal-user scope | [Independent addendum](music-audit/pack-review/ADDENDUM.md): both fresh-review findings verified resolved at 40×18 and 80×24; paging, Back, exit and terminal restoration passed. This focused retake did not repeat the longer lifecycle or listening tests. |

The fresh review's pack SHA-256 is `9a6ff3e2044f70204eebe39df5ccbfb4597ee7e8a31af2cf0d99d366708f39d0`; its core is `759952ebb39f41958d0aad831be9863983a35b3feb980809b7d24d12401e5a9e`. Those hashes also identify the historical measurements and lifecycle receipt below. The final manager/UI builds have the identities listed at the top. The music-only Python engine remains `670a2e1399be206b5e572101d81f3e0d4fd9f38af3c0b72578149011363dde92`; the final companion is 176 bytes larger after UI polish. Earlier evidence is not relabeled as a rerun of the final executables.

## Actual transport proof and limits

[real-session.json](music-audit/verification/real-session.json) records real synthesis and mpv on the default audio device at **player volume 0**: actual audio clock, pause holding position and clearing analysis, paused seek, bridge disconnect preserving the session, next-track preparation, repeat-one and repeat-all at EOF, explicit-stop cleanup, jingle use before setup and alongside music, and removal/reinstall preserving sources. First track readiness in that separate run was 1.733 seconds; cold setup was 15.129 seconds. This is process/clock/lifecycle evidence, not a claim that anyone heard or judged the music.

The refreshed [final capture receipt](music-audit/final-polish/capture.json) identifies the exact final core/companion hashes and three actual PTY captures at [120×36](music-audit/final-polish/player-120x36.png), [80×24](music-audit/final-polish/player-80x24.png), and [40×18](music-audit/final-polish/player-40x18.png), with real synthesis, muted playback, an `mpv:audio-pts` clock and the same session surviving three UI exits. The [previous capture receipt](music-audit/final/capture.json) remains unchanged. Images reconstruct terminal cells; they are not photographs of a native terminal or the desktop. Earlier review-emulator artifacts were explicitly corrected rather than treated as application defects.

## Measured cost

[Performance data](music-audit/pack-performance.json) and [method/samples](music-audit/pack-performance-notes.md) use fresh private homes, local pack installation, owned setup, the full 1,620-track library, and actual 80×24 PTYs on a 10-core MacBook Pro with 64 GiB RAM. Other apps and OS services were active; caches were not flushed. These are local measurements under competing load, not cross-platform guarantees.

| Measurement | Observed result |
| --- | ---: |
| Core executable / gzip level 6 | 11.792 MB / 6.157 MB |
| Optional companion / gzip level 6 | 15.231 MB / 10.027 MB |
| Compiled runtime | 13.973 MB |
| Installed optional pack + receipt + runtime | 29.204 MB |
| Local install | 0.709 s |
| Fresh owned setup / verified reuse | 12.752 s / 0.779 s |
| Complete 1,620-track UI startup, median of 5 | 1.028 s |
| Collection / full-queue navigation medians | 16.86 ms / 16.45 ms |
| Search query burst to rendered result | 16.32–32.56 ms |
| Append all 1,620 tracks | 565.30 ms |
| Full-queue status roundtrip + JSON decode, median | 6.83 ms |

The short 10.304-second stopped idle sample measured 0.19 CPU seconds across the six UI/router/bridge processes: about 1.84% of one core, with 63 output bytes. Detached-daemon CPU was not measured; failure to identify its socket owner is not zero-CPU evidence. This performance run made no playback request, left the render cache empty, and verified stop/remove/socket/home cleanup.

The on-disk render cache is currently **unbounded**: prepared-memory/prefetch bounds do not impose a disk quota. A three-minute stereo PCM render is roughly 32 MB. `music clear` removes rendered cache; removing the pack also removes it. The footprint table excludes this cache, source tracks, external prerequisites and the retained local preview artifact. No automatic eviction, every-track/instrument validation, Linux setup proof, public download proof, or perceptual audio certification is established by this audit.

Copied evidence is indexed by size and SHA-256 in [evidence-index.json](music-audit/evidence-index.json). The final install, build/test and focused independent-review receipts are complete; the scope limits above remain in force.
