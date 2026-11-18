# Optional Music Pack measurements

Measured 2026-11-18T01:10:43.527847+00:00 on MacBookPro18,2, 10 CPU cores, 64 GiB RAM. The full test suite had finished before this run. Other apps and OS services were active: the snapshot at UI start included wakatime-cli at 140% of one core, BTLEServer at 88%, and WindowServer at 37%. These are local observations under competing load, not an idle-host or cross-platform performance guarantee. Filesystem caches were not flushed.

The reproducible fixture is `pack-performance-fixture/measure.py`; run it with the existing `target/demo-venv/bin/python`. It launches the actual core executable in an 80×24 PTY, reconstructs output incrementally (including UTF-8 across read boundaries), and measures input-to-visible-result latency. Each run uses a fresh private home, installs the local companion with its SHA-256, and runs `music setup --songs DIR` against the existing 1,620-track library. Setup compiles and performs a silent validation render; no music or jingle playback was requested.

## Measured timings

| Operation | Observed time |
| --- | ---: |
| Local Music Pack install | 0.709 s |
| Fresh owned setup, command launch through completion | 12.752 s |
| Repeated setup, validates and reuses runtime | 0.779 s |
| Open music UI with 1,620 tracks, median of 5 | 1.028 s |
| UI startup range | 0.997–1.046 s |
| Collection navigation, median of 8 | 16.86 ms |
| Search full query to rendered results, 3 queries | 16.32–32.56 ms |
| Append all 1,620 tracks and display receipt | 565.30 ms |
| Navigate full queue, median of 6 | 16.45 ms |
| Full-queue persistent status response plus JSON decode, median of 10 | 6.83 ms |

The full-queue status reply was 189,322 bytes. Its first request includes the process launch and is recorded separately in the JSON. Navigation timing includes terminal emission and recorder detection; observed ~17 ms values align with a rendered-frame interval, not pure CPU execution time.

During 10.304 seconds at rest with all tracks queued, the six UI/router/bridge processes used 0.19 CPU seconds, approximately 1.84% of one core, and emitted 63 PTY bytes. This short sample uses `ps` CPU totals with 0.01-second resolution. It excludes the recorder and detached playback daemon. The daemon socket ownership lookup returned no PID, so its CPU usage was not measured and must not be read as zero.

## Footprint

| Component | File bytes | Gzip level 6 |
| --- | ---: | ---: |
| Core native executable | 11.792 MB (11.25 MiB) | 6.157 MB (5.87 MiB) |
| Optional companion executable | 15.231 MB (14.53 MiB) | 10.027 MB (9.56 MiB) |
| Compiled runtime, summed regular-file sizes | 13.973 MB (13.33 MiB) | — |

The installed companion plus receipt and runtime totaled 29.204 MB (27.85 MiB), excluding the core, external prerequisites, source library, and playback render cache. Gzip values are reproducible compression measurements, not published download artifacts. The render cache remained empty during this queue-only test. Runtime sizes are logical bytes, not allocated filesystem blocks.

## Identity and cleanup

- Core SHA-256: `759952ebb39f41958d0aad831be9863983a35b3feb980809b7d24d12401e5a9e`
- Companion SHA-256: `9a6ff3e2044f70204eebe39df5ccbfb4597ee7e8a31af2cf0d99d366708f39d0`
- Both binary hashes remained unchanged throughout the run.
- Final transport: stopped; 1,620 queued tracks; position zero; no selected playing track.
- Both `music stop` and `music remove` exited 0 after closing the UI and bridge.
- The owned control socket and music state were absent afterward; the isolated home was removed. Source songs were retained.

`pack-performance.json` contains individual timing samples, setup progress, process-load snapshots, and cleanup checks. `pack-performance-fixture/library-screen.txt` and `queue-screen.txt` contain the actual reconstructed PTY screens. `first-run.json` is retained separately for transparency; its screen reconstruction predated the incremental UTF-8 fix, so the final report uses the corrected run.
