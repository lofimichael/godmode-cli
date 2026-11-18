# Candidate 6 performance observations

Measured frozen candidate SHA-256 `50cf317351bdd9c788663c25ebb6c3ce2a3d572709423a364eb11d508e110d77` in an isolated 80x24 PTY with the actual 1,620-track local library. No render or playback command was sent. No source changes or global CPU/cache settings were made during measurement.

| Operation | Observed |
| --- | --- |
| Startup to populated library, 3 runs | 345.7–350.1 ms; median 348.8 ms |
| Arrow-key navigation, 8 changes | 15.7–17.6 ms; median 16.6 ms |
| Full query to filtered results, 3 searches | 16.0–32.9 ms; median 32.3 ms |
| Enqueue all 1,620 tracks through UI | 349.3 ms |
| Status IPC with 1,620-track queue, 10 warm calls | 6.2 ms median wire round trip; 7.3 ms including JSON decode |
| Encoded full status response | 189,322 bytes |
| Open queue after idle polling | 14.2 ms |
| Navigate 1,620-track queue, 6 changes | 15.6–17.1 ms; median 16.5 ms |

During a 4.31-second stopped observation, this fixture's native UI and its engine child used about 0.07 CPU seconds combined (roughly 1.63% of one core). This short sample includes the acknowledgement expiring and normal idle polling. It excludes the daemon and measurement harness; ps CPU time has 0.01-second resolution. There were only 63 bytes of incremental PTY output during that interval. Navigation remained responsive afterward.

These are local observations under the current concurrent workload, not general performance guarantees. Host caches were not flushed. Active playback/rendering CPU and audio latency were deliberately not measured. The first request through a newly launched bridge took 224.5 ms; that startup cost is excluded from warm IPC figures.

Final state was stopped, position 0, no current track, and all 1,620 entries queued. The private fixture daemon was then stopped successfully, and both the terminal and bridge were closed. Raw metrics and individual samples are in `performance.json`; the measurement script is under `performance-fixture/measure.py`.
