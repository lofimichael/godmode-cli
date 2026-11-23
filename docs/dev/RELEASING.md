# Release

The native command embeds the Python file engine and provider data. Bubble Tea
and Lip Gloss handle the interactive interface. `VERSION` supplies the release
number; `go.mod` pins the compiler and dependency versions. The source archive
includes vendored libraries and their licenses.

## Check

```sh
python3 -m venv .context/test-venv
.context/test-venv/bin/python -m pip install -r scripts/demo-requirements.txt
.context/test-venv/bin/python scripts/check.py --full --jobs 2 --require-shellcheck
```

The runner verifies generated source, builds the CLI and synthetic
license candidate, then exercises Python, Go, native terminal and installer
coverage without repeating discovery. Full checks add race detection and all
four native build targets. See [TESTING.md](TESTING.md) for dependencies, timing
reports, optional checks and the coverage boundaries.

Tests use synthetic keys and temporary homes. Python 3.9 remains the minimum for
the embedded engine; CI covers that interpreter on Linux and Python 3.14 on macOS.

The explicit vendor test protects the fullscreen newline-mapping patch described
in [vendor/PATCHES.md](../../vendor/PATCHES.md); `go test ./...` excludes vendor tests.
For renderer changes, install `scripts/demo-requirements.txt` in the demo virtual
environment and run the real-PTY regressions as well:

```sh
GODMODE_TEST_NATIVE_BINARY="$PWD/target/godmode-native" target/demo-venv/bin/python -m unittest discover -s tests -p test_native_renderer.py -v
```

These tests enable ONLCR on a disposable PTY or LNM in its emulator after the first
intro frame, then compare logo cells across more than two animation cycles and
verify terminal restoration. They never change the operator's terminal settings.

## Release from main

Update `VERSION`, the version constant in `godmode.py`, and `READTHIS.NFO`.
Regenerate the embedded core with
`python3 scripts/build.py --output internal/core/core.py`. Add a `## vX.Y.Z`
section in [`docs/CHANGELOG.md`](../CHANGELOG.md) with its date on a separate line
and at least one customer-facing bullet. Use ISO dates or spell out the month.
Review the changes in a single PR.

Merging a version increase to `main` requests a stable release. The release
workflow checks the exact source commit on Linux and macOS, packages and tests
the distribution, then creates the matching Git tag and publishes the verified
assets. Main pushes without a version bump skip the release runners. The regular
Linux check reports shipped changes beyond the live updater version so
maintainers can see when unreleased work is accumulating.

**Dry run.** Run **Release CLI → Run workflow**, select the branch under review,
and leave `dry_run` enabled. Leave `tag` and `commit` empty to test the selected
branch tip. The run exercises checks and packaging without writing a tag or
release. The packager also runs locally from a clean checkout.

```sh
python3 scripts/package-native.py --output-dir target/release-vX.Y.Z/dist
```

The distribution contains the four static native builds for macOS and Linux on
arm64 and amd64, a complete source archive, `install.sh`, and `SHA256SUMS`.
The Linux filenames retain `-musl` for older updaters. Preserve these names and
omit the old `-unix.tar.gz` alias. For affected 0.14 installations, see the
[explicit archive upgrade](../INSTALLATION.md).

**Retry.** If publishing stopped partway through, rerun the failed job or
dispatch **Release CLI** on `main` with `dry_run` disabled and the exact
`commit` or existing `tag`. Supply one selector. Matching tags and assets are
reused. Inspect conflicts before retrying and correct published bytes with a
new version. If GitHub rejects creation of a missing tag on a historical
commit because its workflows differ from the default branch, verify the
release commit and create the tag with an authorized maintainer account before
dispatching by tag.

Private Actions use `GODMODE_CI_ENABLED=true`. Keep required checks and review
on `main` before enabling release automation, since a version increase there
authorizes a release. The hosted checks use standard runners.

## Publish the customer channel

The published CLI release starts the website handoff. The workflow verifies the
tag and downloads its published assets. It prepares a PR in `godmode-build`
with the distribution, versioned docs, and changelog. Review the docs and
merge that PR after the website checks pass. The website's production workflow
deploys the checked `main` commit and verifies the live updater manifest.

If the release already exists and only the website handoff needs retrying, run
**Prepare CLI website distribution** on `main`. Supply the published
`version` and matching `source_sha`. It reuses an existing matching PR.
For editorial changes and manual recovery, see `docs/release-cycle.md` in
the `godmode-build` repository.

### Configure the website handoff

1. Create a dedicated private GitHub App under the account that owns both repositories. Turn off
   webhooks. Give it repository **Contents** and **Pull requests** read/write
   permissions and install it on `godmode-build` only.
2. In the CLI repository, create the Actions environment `cli-distribution`
   and allow deployments from the `main` branch only. Save the App's client ID
   as the environment variable `GODMODE_DISTRIBUTION_APP_CLIENT_ID`. Generate an
   App key and save its PEM as the environment secret `GODMODE_DISTRIBUTION_APP_KEY`.
3. Keep the site's review and required checks in place. The installation token
   creates a branch and opens its PR. Production deployment credentials stay
   in the site's `production` environment.

Use the existing live version and exact tag commit for a read-only handoff
check after setup. A matching version already on website `main` succeeds
without opening another PR. [GitHub App setup](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app)

`godmodeup` downloads `https://godmode.build/releases/latest.json`. An explicit
`godmodeup --version vX.Y.Z` selects that version's deployed manifest. Downloads need
no password, account or activation. The updater verifies archive size
and SHA-256, checks its managed-file receipt, keeps the previous executable as
`~/.godmode/bin/godmode.previous`, and preserves profile, provider credentials and
license files. Verify downloaded archive checksums, embedded source, native binary
bytes, the previous version and preserved user files in a disposable home.

## Bootstrap

```sh
curl -fsSL https://get.godmode.build | bash
# Open a new terminal, or run the PATH command printed by the installer.
godmode
```

The public bootstrap downloads the public installer and runs it with
`--path --install-only`, installing both the CLI and `godmodeup`. It needs no
account, preview password or license key.
Later updates use `godmodeup`. Bootstrap-only changes live in the distribution
repository and do not require rewriting immutable CLI release files.

Release SHA-256 checks detect damaged or mismatched downloads and HTTPS authenticates
the transport. Release manifests are not independently signed or Apple-notarized.
The Ed25519 signature on a license entitlement is separate from release integrity.
