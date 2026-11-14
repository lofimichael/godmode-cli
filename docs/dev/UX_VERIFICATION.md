# Godmode 0.15.1

Godmode uses Bubble Tea 2 and Lip Gloss 2 for its native terminal interface. A readable embedded Python engine owns credentials, profiles and append-only agent notes. Direct commands and plain prompts use the same engine.

## Checks

| Check | Result |
| --- | --- |
| Full Python suite | 252 tests passed on Python 3.9.6 and 3.14.5 |
| Final native regression suite | 16 tests passed on both interpreters, including the last UTF-8 refusal fix: 11 real-terminal tests and 5 packaging tests |
| Go packages | All packages passed with the race detector and vendored dependencies |
| Installer and updater | Passed; native upgrade preserved synthetic keys, profile, markers, agent notes, and the previous command |
| ShellCheck | Passed for installer, native builder, installer tests and updater tests |
| Agent append | Original bytes, CRLF, final newline state, permissions and inode preserved; repeat notes skipped; stale previews and unsafe targets refused |
| Secret entry | Edited pastes stay masked, pastes never submit, interrupted/oversized pastes cancel without saving, queued test tails stay private |
| Terminal state | Flags, bracketed-paste mode and alternate screen restored after success and cancellation |
| Layout | Dark/light views across 8×5, 28×12, 40×18, 80×24 and 110×36; writes blocked when required previews cannot be read |
| Native artifacts | macOS arm64/amd64 and Linux arm64/amd64 compiled; archive CPU headers checked |
| Source rebuild | Extracted source archive rebuilt byte-identically with the pinned Go compiler on PATH, GOPROXY=off and GOSUMDB=off |
| Embedded engine | `godmode source` matched the readable source assembler byte-for-byte |
| Optional music | Real local synthesis, repeated cache reuse, WAV decoding, playback, PCM visualization, stop cleanup and scoped cache clearing exercised |
| Music removal | `--without-music` build omitted the adapter and kept key/profile commands working |
| Credential-pattern scan | Only the PEM validator and existing synthetic service-account fixture matched; no live credentials found |

The full suites ran before the final UTF-8 refusal case was added; the final native suites include it. The source rebuild used an already installed Go 1.26.7 compiler. Other CPU targets were compiled and inspected, not executed. Terminal sessions used synthetic homes and keys. Human newcomer task completion and screen-reader speech output have not been measured.

The real 0.14 GitHub upgrade exposed a checksum-only download being treated as success. It stopped before changing files. Version 0.15.1 checks both downloaded files; the installer regression covers a successful GitHub response with a missing first-choice archive. An explicit downloaded native archive supplies the compatible upgrade path for the old updater.

## Independent review

Separate agents reviewed the framework choice, copy, visuals, append behavior and native engineering. The [native review](NATIVE_REVIEW.md) records the paste bugs, their reproductions and fixes. The copy review led to working no-result search actions, accurate link hints, clearer multiline-address instructions and visible scroll position. A final visual pass used actual terminal captures.

## Screens

`scripts/record-native.py` records the running command, verifies its interactions and writes a receipt with binary and image hashes. Pillow and pyte belong only to the recording tools. The recorder implements the terminal scroll-region commands used by Bubble Tea.

![Native terminal tour](../images/native/tour.gif)

![Agents append preview](../images/native/agents.png)

![Vercel token entry](../images/native/vercel.png)

The [experience map](CLI_EXPERIENCE.md), [framework comparison](CLI_FRAMEWORKS.md), and [NFO sources](NFO_DESIGN.md) contain the design decisions and primary-source links.
