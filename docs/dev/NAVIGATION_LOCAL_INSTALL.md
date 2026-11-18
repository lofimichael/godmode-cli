# Navigation candidate: local installation

Initial installation checkpoint, 2026-11-17. The reviewed navigation candidate was installed locally as
`~/.godmode/bin/godmode`. No public release was published. The unreleased build
still reports `godmode 0.19.2`; its exact identity is SHA-256
`0da6fa2c7384285accffb7540fd87686818783a8d90e096324adaa163307e9e9`.

The existing managed installer installed the checksum-verified executable in
offline binary mode. PATH already resolved to that destination. The original
installed executable is retained as `godmode.previous`, SHA-256
`50f2ce5e9fd16974b9113136c3f3d076f0841308255feeba1c72b1ff02db3d65`.
The installer receipt matches both binaries and the updater.

## Local checks

| Check | Result |
| --- | --- |
| Full Python suite against the fixed reviewed candidate | 356 passed in 177.817 seconds |
| Native suite against the installed executable, after the isolation fix below | 28 passed in 31.760 seconds |
| Native suite against a disposable managed installation with invocation sentinels | 28 passed in 31.428 seconds; updater and external helper sentinels were not called |
| `go test -race ./...` | Passed |
| Vendored ultraviolet `TestGodmode` transport regressions | Passed |
| Installer fixtures and exact-candidate updater fixtures | Passed |
| Individual shell syntax checks for installer, updater tests and build scripts | Passed |
| Installed human help, agent help and read-only Settings smoke checks | Passed in an isolated home |
| Final installed/rollback/updater checksums and protected-path metadata | Matched |

The native subset is also included in the full suite; these are separate runs,
not 384 unique tests. Runtime code did not change during this installation task.
The only test change isolates updater dispatch from a managed executable.

## Test isolation failure and recovery

The first installed-path native run exposed a test-harness assumption:
`test_doctor_button_and_update_version_dispatch` expected its executable to have
no install receipt. Changing HOME did not isolate the updater beside the actual
installed executable. The test invoked the real updater with `v0.18.0`, which
temporarily replaced the executable and caused subsequent native tests to fail.

The test now copies the executable into its disposable fixture directory,
asserts that no sibling install receipt exists, and uses that copy for updater
dispatch. The original pre-task executable was recovered from the local
checksum-verified 0.19.2 release archive and matched its pre-task binary hash.
It was restored through the managed installer, then the reviewed candidate was
installed again so the intended original rollback was retained. The corrected
installed-path native suite passed, and final binary/receipt checks matched.
An independent managed-fixture run verified the receipt first, ran all 28 native
tests, and confirmed that its sibling updater was never called. Its executable,
updater, receipt and rollback bytes and metadata remained identical.

All 39 protected configuration and shell paths retained their inode, ownership,
mode, size, modification time and change time after installation and tests.
These were metadata-only checks: credential, profile and seal contents were not
opened by the preservation audit. Test values and instruction-file changes used
isolated synthetic homes. No provider authorization or real agent execution was
claimed.

The [navigation audit](NAVIGATION_AUDIT.md) preserves the preceding design,
research and reviewer checkpoints. Its no-install statements describe that
earlier audit phase; this document records the subsequently requested local
installation.

## Follow-up: visible note under agent locations

The installed build now has SHA-256
`2fc536eb3fc1438c765dc77f8aaf9562db2e704908bfe28991e163e21b90c979`.
All detected agents always shows the standard Godmode note beneath the file
locations, including when every target is already configured. Pending additions
retain green `+` lines; a completed setup shows the note as plain reference text.
The explanation identifies marker/`godmode help` detection and preserves edited
existing notes. The copy shortcut remains explicitly labeled for the current task.

Go UI tests and all 14 native CLI tests passed. The installed executable also
passed the agent append/repeat regression. A rendered PTY check with two already
configured agents confirmed the note appears after both paths and Enter changes
neither customized file. The managed update preserved configuration metadata and
retained the preceding navigation build as `godmode.previous`.
