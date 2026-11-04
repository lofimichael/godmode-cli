# Install Godmode

New installations use one home directory, `~/.godmode`. The executable lives in its `bin` subdirectory, while keys, optional provider instructions and CLI state remain under the same home. You can select another home with `--home DIR` or `GODMODE_HOME`.

```text
~/.godmode/
  bin/godmode          executable
  .env.godmode         credentials
  providers.toml       optional provider instructions
  AGENTS.md            existing operating rules, if supplied separately
  state/               acknowledgements, locks and requested Picard media
```

The install step creates only the executable's directory and file. The interactive setup that follows creates the credential file and state after acknowledgement; neither installation nor setup writes operating rules. Existing rules remain in place.

The [XDG specification](https://specifications.freedesktop.org/basedir/latest/) describes `~/.local/bin` as a shared user executable directory. Godmode deliberately uses its own `~/.godmode/bin` to keep the requested installation together. It does not claim that `~/.godmode` is an XDG directory or create a second executable in the shared bin.

## Download and start setup

With a source checkout, run `sh install.sh`. For the private repository, an already authenticated GitHub CLI can fetch and run the installer directly:

```sh
gh api -H 'Accept: application/vnd.github.raw+json' \
  repos/lofimichael/godmode-cli/contents/install.sh | sh
```

The installer detects macOS/Linux and the native architecture, selects a compatible release artifact, downloads its archive and SHA-256 checksum, verifies it, and installs the binary. Authenticated GitHub CLI access supports private draft releases. Without that access, the HTTPS download path requires a publicly accessible published release. No token is requested or read from Godmode's credential file. A compatible prebuilt artifact must exist; the installer does not build from source or substitute another architecture.

Download installs start interactive `godmode init` using the controlling terminal, even when the script arrived through a pipe. `--no-setup` installs without prompts. Without a controlling terminal, installation prints the setup command for later. `--version vX.Y.Z` pins a release instead of selecting one automatically.

Only Apple Silicon macOS artifacts have been built and verified for the current private draft. The four-target workflow is available for later releases; its presence is not proof that the other artifacts exist.

## Existing executables and upgrades

An existing executable is refused by default, before downloading. The installer shows its path and a compatible `init` command for starting it. To replace that executable intentionally, run `sh install.sh --force`; this changes the binary only, leaving credentials and rules in place. A symlink destination is always refused, including with `--force`. Keep a copy of the prior binary if you want to retain it.

No PATH or shell-profile changes happen automatically. You can always run:

```sh
~/.godmode/bin/godmode setup
```

For the current shell, a shorter command is available after:

```sh
export PATH="$HOME/.godmode/bin:$PATH"
godmode setup
```

If another `godmode` is on PATH, the installer reports it and leaves it intact. Use the absolute path to choose this installation. To retain a PATH change, add it to the startup file your shell actually reads.

## Cargo and offline installation

There is no published crates.io package yet. From a checkout with Rust installed:

```sh
cargo install --path . --locked --root "$HOME/.godmode"
```

Cargo manages its own binary and install metadata under that root; it does not initialize Godmode credentials. Run `~/.godmode/bin/godmode setup` afterwards. Cargo's default root, if omitted, is `~/.cargo`, which would place the executable outside the all-in-one Godmode home. [Cargo installation reference](https://doc.rust-lang.org/cargo/commands/cargo-install.html).

To build without installing, run `cargo build --release --locked`, then `./target/release/godmode --home "$PWD/target/try-home" setup`. Use synthetic values for development.

Explicit local artifacts retain the offline installer path:

```sh
GODMODE_BINARY_SHA=$(shasum -a 256 target/release/godmode | awk '{print $1}')
sh install.sh --binary target/release/godmode --sha256 "$GODMODE_BINARY_SHA"
```

For an existing release archive, use `--archive PATH --checksum SHA256SUMS`. These modes make no download requests and print the setup command; add `--setup` to start it immediately. Checksums detect damaged downloads but do not authenticate a compromised publisher. Obtain the archive and checksum from the intended release. macOS binaries are currently unsigned and not notarized.

## Existing configurations

The CLI first looks for `.env.godmode`, `providers.toml` or `AGENTS.md` in `~/.godmode`. If none exists there and the legacy `~/.config/godmode` exists, it adopts that existing location and keeps using `~/.local/state/godmode/cli` for its state. A newly installed `~/.godmode/bin/godmode` by itself does not hide or replace the legacy configuration. No keys, rules, OAuth state or other files are migrated.

An explicit `--home DIR` selects that directory without automatic discovery; its default state directory is `DIR/state`. `--config-dir DIR` remains an alias. `GODMODE_HOME` also selects an explicit home, with `GODMODE_CONFIG_DIR` supported as a fallback. `--state-dir` or `GODMODE_STATE_DIR` can override the state location.

For a separate installation and configuration:

```sh
sh install.sh --binary target/release/godmode \
  --sha256 "$GODMODE_BINARY_SHA" --home "$PWD/target/try-home"
"$PWD/target/try-home/bin/godmode" --home "$PWD/target/try-home" init
```

The installer's `--bin-dir DIR` is still available for selecting only an executable directory. It cannot be combined with installer `--home`. Selecting a binary directory alone does not isolate the CLI's configuration; use an explicit CLI `--home` when that is intended.

The installer does not start a service, install hooks or change shell profiles. Download installs hand off to attended setup; writes still require the CLI acknowledgement and explicit key entry.

## Remove an installation

Confirm which executable you installed and remove that file. Keys and operating rules remain useful independently. After all CLI sessions are closed, its state can be removed separately. Only remove the entire Godmode home if you also intend to remove its credentials and rules. Deleting a local key does not revoke it at its provider.
