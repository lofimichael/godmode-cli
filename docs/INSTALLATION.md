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

Installation creates only the executable's directory and file. Acknowledged setup creates the credential file and state; neither installation nor setup writes operating rules. Existing rules remain in place.

The [XDG specification](https://specifications.freedesktop.org/basedir/latest/) describes `~/.local/bin` as a shared user executable directory. Godmode deliberately uses its own `~/.godmode/bin` to keep the requested installation together. It does not claim that `~/.godmode` is an XDG directory or create a second executable in the shared bin.

## Install a local build

From the repository:

```sh
cargo build --release --locked
GODMODE_BINARY_SHA=$(shasum -a 256 target/release/godmode | awk '{print $1}')
sh install.sh --binary target/release/godmode --sha256 "$GODMODE_BINARY_SHA"
```

For a release archive, pass `--archive PATH --checksum SHA256SUMS` instead. Obtain the archive and checksum from the intended release. The installer does not download anything; it verifies the supplied digest before creating the destination.

It prints an absolute command for starting interactive setup. If its bin directory is missing from PATH, it also prints a correctly quoted command for adding it. For the default destination, the equivalent is:

```sh
export PATH="$HOME/.godmode/bin:$PATH"
godmode init
```

That PATH change applies to the current shell. To retain it, put the command in the startup file your shell actually reads. The installer does not choose or modify that file. You can always invoke `~/.godmode/bin/godmode init` without changing PATH.

If another `godmode` command was already on PATH, installation reports its location and leaves it intact. Use the printed absolute path to select this executable. Changing PATH order can change which executable a bare `godmode` command selects.

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

An existing executable destination is refused unless `--force` is explicitly supplied. A symlink destination is always refused, including with `--force`. The installer never runs setup, starts a service, installs hooks or changes shell profiles.

## Remove an installation

Confirm which executable you installed and remove that file. Keys and operating rules remain useful independently. After all CLI sessions are closed, its state can be removed separately. Only remove the entire Godmode home if you also intend to remove its credentials and rules. Deleting a local key does not revoke it at its provider.
