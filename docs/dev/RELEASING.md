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

## Package

Set the version in `VERSION`, the `VERSION` constant in `godmode.py`, and
`READTHIS.NFO`. Review, commit to main, then tag and push `vX.Y.Z`.

```sh
python3 scripts/package-native.py --output-dir target/release-vX.Y.Z/dist
```

The packager refuses uncommitted release source before and after building, so archived source matches its recorded commit.

The packager builds macOS arm64/amd64 and Linux arm64/amd64 with `CGO_ENABLED=0`,
then creates deterministic archives, the complete source archive, `install.sh`
and `SHA256SUMS`. All four native archives carry their corresponding binary.
The Linux names retain `-musl` for compatibility with older updaters; the binaries
are static Go builds.

Do not add a `-unix.tar.gz` alias. Pre-0.15 updaters try that name first, then the
native target. With curl, omitting it makes those updaters try the native command.
The 0.14 GitHub CLI route can return success for a checksum-only download and stop
before falling back; use the explicit archive upgrade in docs/INSTALLATION.md for
those installs. The current updater selects a native platform from the public
site's release manifest; it does not discover releases through GitHub.

Create a private draft release with all files in the distribution directory:

```sh
gh release create vX.Y.Z target/release-vX.Y.Z/dist/* \
  --verify-tag --draft --title "Godmode vX.Y.Z" --notes-file release-notes.md
```

A private draft archives the release for repository members. It does not make the
release available to customers. The release workflow runs only through explicit
`workflow_dispatch` and creates a draft; pushing a tag alone does not build or publish.
Private Actions remain opt-in, and local release builds require no Actions minutes.

## Publish the customer channel

In the private `godmode-build` distribution repository, import the completed
distribution directory, check it and deploy through that repository's documented
deployment helper:

```sh
python3 scripts/import-release.py /path/to/godmode-cli/target/release-vX.Y.Z/dist --version vX.Y.Z
npm run check:release
npm run check
```

The importer creates `public/releases/vX.Y.Z`, advances `public/releases/latest.json`
and copies the matching root `public/install.sh`. It refuses changed bytes under an
existing release version. Correct release payloads with a new version; never replace
published archives, checksums or their embedded installer/source files.

Use the saved product deployment credential and deployment procedure in
[`godmode-build/docs/release-cycle.md`](https://github.com/lofimichael/godmode-build/blob/main/docs/release-cycle.md).
The deployment helper verifies release integrity before applying migrations, then
checks migration state, deployed commit and public/member access boundaries. Automatic Git deployment
is currently disabled; a tag, GitHub release or repository push alone does not advance
the deployed customer channel.

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
