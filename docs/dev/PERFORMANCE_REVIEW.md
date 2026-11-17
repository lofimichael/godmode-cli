# Responsive native navigation

17 November 2026. Baseline: v0.18.0 embedded engine and UI before the active-selection/intro changes. Measurements use an Apple M1 Max, macOS ARM64, Go 1.26.7, and disposable homes with synthetic keys. No provider network calls or real credential files were involved. These are local wall-clock samples, not claims about every machine or filesystem.

## What the current architecture already gets right

Each TUI owns one private Python subprocess. Bounded JSON requests share a serialized pipe; moving between menu rows does not restart Python. Normal rendering and arrow navigation are cheap. The expensive boundary is blocking I/O inside Bubble Tea's `Update`, not Lip Gloss itself.

The backend is intentionally serialized. Keep it that way: key previews, expected file digests, active selections and agent append plans have ordered state. Parallelizing those requests or caching saved credentials would introduce correctness risks without fixing the main interaction problem.

## Measured baseline

The second timing run below included 20 fresh starts and 100 requests per warm action. Key checks used 30 requests per size. A preceding run was also measured to make obvious host-load variation visible: empty start median was 98.8ms versus 125.3ms below; 24-key state median was 5.0ms versus 6.1ms. Neither run was a controlled cold-disk experiment.

| Operation | Median | p95 | Samples |
| --- | ---: | ---: | ---: |
| Start child and receive first empty state | 125.3ms | 158.5ms | 20 |
| Empty state | 1.11ms | 2.12ms | 100 |
| State with 24 stored synthetic keys | 6.14ms | 8.29ms | 100 |
| Agent plan with 24 keys | 0.38ms | 0.47ms | 100 |
| Context list, empty home | 0.26ms | 0.50ms | 100 |
| Environment list, one 24-key file | 1.63ms | 2.13ms | 100 |
| Doctor with 24 keys | 3.58ms | 9.83ms | 100 |
| Validate a 40-byte key | 0.09ms | 0.20ms | 30 |
| Validate a 4KiB paste | 0.66ms | 0.73ms | 30 |
| Validate the permitted 1MiB paste | 139.7ms | 201.9ms | 30 |

Pure Go view measurements used a copied v0.18 UI fixture and `go test -bench`, 500ms per case. They exclude terminal transport and actual painting:

| Operation | Mean per operation |
| --- | ---: |
| Home frame | 0.031ms |
| Provider frame | 0.037ms |
| Long 80-line agent-diff frame | 0.712ms |
| Arrow-key update and home frame | 0.031ms |

The baseline harness called `core.New(home)` plus `Call("state", nil)` for starts, reused one client for warm requests, and populated the synthetic store through `key_plan` → `key_check` → `key_save`. The private source stayed on stdin, and only elapsed durations were emitted. The Go render fixture called `model.View()` or `model.Update(KeyDown)` plus `View()` without writing to a terminal. Scratch sources were moved outside the Go module into the working workspace's ignored `.context/v019-performance/` after measurement, so `go test ./...` cannot mistake them for shipped packages. Only the observations above are the durable record.

## Changes that matter

1. Run backend-bearing actions through `tea.Cmd`. The live model should immediately enter a pending state and continue accepting resize and Ctrl-C. Render a compact activity indicator only if work remains pending after a short threshold, around 80ms; do not hold a fast result to make the spinner visible. The existing doctor command is already asynchronous.
2. Keep navigation immediate. Arrows, scrolling, filtering, section changes needing no new data, and focus movement need no delays, transitional screens or loading animations. A brief accent change can supply polish without moving the selected control.
3. Treat a large paste as a separate validation request. Keep the value masked immediately, associate validation with the exact candidate, and reject stale replies after editing or leaving the field. Normal small typed-key validation is already submillisecond; the permitted 1MiB case is the measured exception.
4. Preserve one write at a time. Disable repeat submission while saving. Escape cannot truthfully undo a mutation already sent. On exit, restore the terminal and interrupt pending backend work; do not claim the last write was rolled back.
5. Stop animation clocks outside the intro and real pending work. Michael explicitly requested a repeating intro in 0.19.2; it uses one bounded 96-frame clock and stops on exit. A busy indicator should tick only while work is pending. No animation is needed in piped commands, `--plain`, no-motion or no-color mode.
6. Keep fresh state after mutations and scope switches. Current calls are fast enough that broad caching is not justified. Never reuse a key/agent plan after a selected environment change; do not cache a saved secret for rendering. A very large environment catalog can be handled asynchronously before it needs any storage optimization.

Two existing external helpers can exceed the normal request budget: the browser opener waits up to two seconds and clipboard copying up to five seconds. Those operations make synchronous `Update` visibly unresponsive even if ordinary reads are fast.

## Async integration constraints

A model copy returned from a worker must not overwrite more recent width, height, background theme, tick counters or cancellation state. Tag requests with a generation and reject stale replies. Busy handling must prevent live edits to shared map/slice state while a worker owns it, or those members need independent copies. Preserve the current reviewed-diff viewport rule after a resize; never restore an outdated review-complete state.

`Client.Call` owns a mutex for the entire request. Previously, a deferred `Close` could wait behind that mutex after Ctrl-C. `Client.Abort()` now interrupts the subprocess without taking the request mutex, is safe to call repeatedly/concurrently, and lets the call unwind before `Close` reaps the child. A committed file operation remains committed; killing the process is interruption, not transaction rollback.

The UI subprocess allowlist now forwards `GODMODE_ENV` and `GODMODE_CONTEXT`, which are nonsecret selection metadata. It still excludes inherited provider credentials. Native and plain selection should have matching precedence.

## Primary-source guidance

- Bubble Tea's commands tutorial places I/O in commands and returns results as messages, keeping `Update` responsive. It explicitly recommends doing the work inside the asynchronous function. [Commands tutorial](https://github.com/charmbracelet/bubbletea/blob/main/tutorials/commands/README.md)
- Bubble Tea supplies a renderer frame-rate option; increasing it is not a fix for blocking `Update`. The vendored version is v2.1.1. [API](https://pkg.go.dev/charm.land/bubbletea/v2#WithFPS)
- Lip Gloss v2 provides layouts, color blending and terminal-profile downsampling. Godmode already uses it; there is no need to change framework to obtain a more polished appearance. [Lip Gloss](https://github.com/charmbracelet/lipgloss)
- Evil Martians recommends meaningful feedback for real work, measurable counts when available, and clean machine-consumable output. A spinner should describe pending work, while bars need actual quantities. These principles support delayed busy feedback rather than fake loading sequences. [Progress guidance](https://evilmartians.com/chronicles/cli-ux-best-practices-3-patterns-for-improving-progress-displays)

## Exercised checks

Focused core tests passed with Go's race detector: selected metadata survives the allowlist, inherited credentials remain excluded, reviewed synthetic key saves remain private, and concurrent Abort calls interrupt a deliberately stalled subprocess without waiting for its request lock. Close reaps it and subsequent calls fail.

The integrated UI suite also passes with the race detector. Gated synthetic backends prove that reads and saves are dispatched before backend execution, loading appears only after its timer, repeat Enter cannot duplicate a save, Ctrl-C remains immediate, stale results cannot restore abandoned input, and resize/theme changes survive completion. Large candidates appear masked immediately; edits received during validation are retained and checked together before submission becomes available. Escape can leave read-only validation; it cannot undo a dispatched save. A deterministic regression verifies that refresh decodes into a new snapshot instead of modifying the maps or slices still rendered by the live UI. The final candidate was also exercised in actual PTYs: first-run onboarding, both intro phases, persisted active setup, light and dark backgrounds, 40×18 and 80×24 terminals, NO_COLOR, masking and terminal restoration. The recorder is `scripts/record-v019.py`; representative captures are in `docs/images/v019/`.

## Final candidate measurement

A fresh native v0.19.0 process to its first empty bridge-state response measured 121.22 ms median and 134.65 ms p95 over 20 isolated-home starts. This includes native launch and Python startup, but excludes terminal painting. The integrated cinematic-frame benchmark measured 0.235 ms per frame (2,590 iterations, Apple M1 Max). Startup is comparable to the baseline; responsiveness improves by keeping slow operations outside the input loop, without adding artificial delay.
