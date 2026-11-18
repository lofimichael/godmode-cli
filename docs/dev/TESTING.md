# Local checks

Run the same broad checks locally and in CI:

```sh
python3 -m venv .context/test-venv
.context/test-venv/bin/python -m pip install -r scripts/demo-requirements.txt
.context/test-venv/bin/python scripts/check.py
```

Python 3.9+ and the Go compiler pinned in `go.mod` must already be installed.
The setup command installs Python test dependencies; the check runner itself
does not download dependencies, contact providers, or require keys. Vendored
Go dependencies are used with the network proxy and checksum lookup disabled.
The terminal screen tests require pyte, wcwidth and Pillow. Missing dependencies
fail before a build rather than silently omitting screen assertions.

The standard command verifies generated Python source before any build, builds
the native CLI and synthetic-license candidate once each, then runs:

- One complete Python discovery, including native PTY, installer transport,
  source/package integrity and licensing tests.
- Go package tests, the explicit patched Ultraviolet renderer tests, and Go vet.
- Installer and updater shell tests using the newly built native candidate.
- Shell syntax checks and ShellCheck when installed.

The complete discovery covers these product boundaries:

| Area | Checks |
| --- | --- |
| Credential files | Parsing, quoting, masking, sealing, permissions, symlinks/hardlinks, atomic write failures and preservation of unrelated bytes |
| Profiles and selection | Named environments/contexts, saved defaults, command overrides, malformed state, migration and process isolation |
| Agent notes | Reviewed append behavior, duplicate prevention, concurrent edits, newline/metadata preservation and unsafe destinations |
| CLI and terminal | Help/error paths, input and pasted secrets, cancellation, narrow screens, navigation, intro rendering and terminal restoration |
| Installation and updates | Platform choice, manifest/archive checks, managed receipts, refusal and rollback paths, previous executable, PATH setup and protected files |
| Licensing | Synthetic signed receipts, expiry and malformed input, locking, deactivation races and preservation of existing state |
| Release identity | Version agreement, pinned compiler, embedded source hashes, exported standalone engine and reproducible archive contents |
| Test runner | Failed commands, missing executables, cancellation, deadlines, observed-child cleanup, bounded concurrency and refused coverage skips |

Generation/build steps run sequentially because they share generated files.
Independent test phases use two workers by default; `--jobs N` bounds both
phase concurrency and Go build workers. Each test phase has a 20-minute limit,
adjustable with `--timeout SECONDS`; build phases have 10-minute limits.
On failure, timeout or interruption the runner terminates that job's process group and
observed descendants, including children that open new sessions. Descendants
are tracked by PID and start time; unrelated processes are never selected by
name. Tests must still clean up deliberately detached daemons in `finally`
blocks: an already-orphaned daemon that escaped before observation cannot be
identified safely by a portable process-tree supervisor.
Failure prevents dependent work, produces a nonzero exit, and is retained in
the summary. A missing, invalid or unsuccessful Python report also fails even
if its child process exits zero. Existing compiler cache entries are reused
for fast repeat checks.

For release candidates and changes to shared/native code:

```sh
.context/test-venv/bin/python scripts/check.py --full --require-shellcheck
```

Full mode adds the Go race detector and cross-compiles the CLI for macOS/Linux
on arm64/amd64. It needs a working C compiler for the race detector.
Cross-compilation proves compilation, not execution
on another CPU; the macOS and Linux CI jobs exercise their host binaries.

Every skipped Python test, including a missing native binary or terminal
renderer, fails the run. Empty discovery also fails. The report must explicitly
record zero skipped tests before the overall run can pass.

ShellCheck is optional locally and its availability is recorded. CI uses
`--require-shellcheck` so absence is a failure. Install it on macOS with
`brew install shellcheck`; on Ubuntu with `sudo apt-get install shellcheck`.

The default machine-readable report is `target/checks/summary.json`; override
it with `--summary PATH`. It includes total and per-phase wall time, status,
commands, exit codes, log locations, Python test counts and exact skips.
Per-run logs and full-mode cross-built executables live under
`target/checks/run-*`. A failed phase prints its log path. These are local
verification artifacts, not a packaged release.

Checks run with a disposable HOME and an allowlisted environment. Provider
credentials, active Godmode setup, shell startup hooks and Python path
overrides are not forwarded. Tests use temporary homes and synthetic
credentials; the user's installed CLI, keys, profile and licenses are untouched.
The Go compiler cache is intentionally shared. Do not run two check runners in
the same worktree simultaneously: native build outputs are shared.

The companion `godmode-build` repository has its own `npm run check`, covering
membership/auth/access behavior, documentation,
all shipped release inventories and a Worker dry build. Its
`npm run verify:deployed-release` separately downloads and verifies deployed
release bytes; `npm run smoke:bootstrap` exercises anonymous installation and
the current-version updater in a disposable home. These network checks are
explicit, and the ordinary test suite does not invoke real provider accounts,
Stripe billing, email delivery or production deployment.
