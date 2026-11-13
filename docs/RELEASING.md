# Develop and release

Keep the core to optional profile facts, masked credential entry, the arrow-key menu and `godmode run`. Agents reach keys only through the CLI; the file stays sealed and explains itself. Profile JSON and provider guidance are data, not another policy engine. Agent setup prints a hint without installing hooks or replacing user instructions. Picard remains optional. Source and installed distributions use only Python's standard library; demo recording has separate development dependencies.

## Check

```sh
python3 -m unittest discover -s tests -p 'test_simple*.py'
python3 scripts/build.py --output target/godmode
target/godmode --version
sh tests/install.sh
sh tests/install-update.sh
shellcheck -s sh install.sh tests/install.sh tests/install-update.sh
```

Tests use synthetic credentials and isolated homes, including real PTY entry, masking, pasted JSON, cancellation, terminal restoration, file preservation and updater behavior. Never test against a real credential inventory.

`scripts/build.py` concatenates the credential and profile writers, terminal helper, optional Picard helper, static provider guidance and menu into ordinary Python source. It does not compile, compress, encrypt, download or execute the generated script. `VERSION` identifies the release. Inspect `target/godmode` directly.

## Package

Commit the checked source to main and create its `vX.Y.Z` tag. The manually dispatched release workflow checks the tag against `VERSION`, runs the Python and installer tests, and builds one universal archive. Include `godmode`, `install.sh`, the license, documentation, `godmode.py`, `lib/`, `providers.json`, `VERSION` and `scripts/build.py`; `SHA256SUMS` covers the archive.

During migration from the Rust CLI, the release also carries identical archive bytes under the four old platform filenames. An old updater can therefore install the readable script and the new universal updater in one operation. Keep those aliases until old updaters no longer need support.

Download the actual release, verify its installed bytes, and exercise `godmodeup` from the previous version in an isolated home. Check that configuration and shell profiles remain unchanged on ordinary updates. A private draft is available only to an authenticated GitHub client with repository access.

Private GitHub Actions runs remain opt-in through `GODMODE_CI_ENABLED=true` or a deliberate workflow dispatch. Check billing authority before dispatching hosted jobs. Publication is separate from creating the draft; there is no crates.io package, native compilation matrix or automatic public publishing.
