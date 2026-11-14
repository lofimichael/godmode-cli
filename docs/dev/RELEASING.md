# Release

The native command embeds the Python file engine and provider data. Bubble Tea
and Lip Gloss handle the interactive interface. `VERSION` supplies the release
number; `go.mod` pins the compiler and dependency versions. The source archive
includes vendored libraries and their licenses.

## Check

```sh
scripts/build-native.sh
go test -mod=vendor ./...
python3 -m unittest discover -s tests -p 'test_*.py'
target/godmode-native --version
target/godmode-native source > target/installed-core.py
python3 scripts/build.py --verify target/installed-core.py
sh tests/install.sh
GODMODE_TEST_NATIVE_BINARY="$PWD/target/godmode-native" sh tests/install-update.sh
shellcheck -s sh install.sh scripts/build-native.sh tests/install.sh tests/install-update.sh
```

Tests use synthetic keys and temporary homes. Native PTY tests require the
candidate at `target/godmode-native`. Python 3.9 remains the minimum for the
embedded engine; test both that interpreter and the current local interpreter.

## Package

Set the version in `VERSION`, the `VERSION` constant in `godmode.py`, and
`READTHIS.NFO`. Review, commit to main, then tag and push `vX.Y.Z`.

```sh
python3 scripts/package-native.py --output-dir target/release-vX.Y.Z/dist
```

The packager builds macOS arm64/amd64 and Linux arm64/amd64 with `CGO_ENABLED=0`,
then creates deterministic archives, the complete source archive, `install.sh`
and `SHA256SUMS`. All four native archives carry their corresponding binary.
The Linux names retain `-musl` for compatibility with older updaters; the binaries
are static Go builds.

Do not add a `-unix.tar.gz` alias. Pre-0.15 updaters try that name first, then the
native target. Omitting it makes those updaters install the native command.
New updaters prefer native targets and retain the legacy universal fallback.

Create a private draft release with all files in the distribution directory:

```sh
gh release create vX.Y.Z target/release-vX.Y.Z/dist/* \
  --verify-tag --draft --title "Godmode vX.Y.Z" --notes-file release-notes.md
```

Install with `godmodeup --version vX.Y.Z`. A draft is visible only to a GitHub
login with repository access. The updater keeps the previous executable as
`~/.godmode/bin/godmode.previous`. Verify downloaded archive checksums, embedded
source, native binary bytes, the previous version, and preserved user files.

The README uses authenticated GitHub downloads for the private repository.
Private Actions remain opt-in; local release builds require no Actions minutes.
