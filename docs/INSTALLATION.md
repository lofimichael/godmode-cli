# Installation

Godmode runs on macOS and Linux, on ARM64 and x86-64. Install Python 3.9 or later first and make sure `python3` is on PATH. The release needs no Python packages, Go compiler, or administrator access.

## Install

```sh
curl -fsSL https://get.godmode.build | bash
. "$HOME/.godmode/env"
godmode --version
```

The public bootstrap installs `godmode` and `godmodeup` under `~/.godmode/bin`, verifies the release against its SHA-256 digest, and adds PATH configuration to supported shell startup files. It backs up an existing startup file before adding the source line. Open a new terminal or source the generated `env` file as shown. Then follow the [quickstart](GETTING_STARTED.md).

The public bootstrap accepts `--home DIR` and `--version vX.Y.Z` after `bash -s --`. Check the [release manifest](https://godmode.build/releases/latest.json) for the version served to new installations.

### Review the installer or set PATH yourself

Download the installer directly. Running it without `--path` leaves shell startup files alone.

```sh
curl -fsSL https://godmode.build/install.sh -o godmode-install.sh
less godmode-install.sh
sh godmode-install.sh --install-only
. "$HOME/.godmode/env"
```

| Direct installer option | Effect |
| --- | --- |
| `--install-only` | Install without opening the terminal menu. |
| `--path` | Set up PATH in zsh’s `.zshenv`, bash’s `.bashrc` and its login file, or `.profile` for sh, dash, and ksh. |
| `--home DIR` | Install into `DIR/bin`. Set `GODMODE_HOME` or pass `--home DIR` to select the same data directory for later commands. Source `DIR/env` for PATH. |
| `--bin-dir DIR` | Choose a directory for the executables only. |
| `--version vX.Y.Z` | Install an available version from the release host. |

Run `sh godmode-install.sh --help` for the full syntax.

## Update

```sh
godmodeup
```

The updater checks its installation receipt and release checksums before replacing the executable. It preserves your keys and profile and keeps the previous executable as `godmode.previous` in the same directory. Use `godmodeup --version vX.Y.Z` for an available specific release or `godmodeup --loadout` to open the menu afterward.

In v0.20, you can also choose **Settings → Update Godmode** and review the confirmation, or run `godmode update`. If the updater reports an unrecognized executable, check which copy is on PATH with `command -v godmode`. Use `--force` only to adopt and replace a known unmanaged copy.

## Install offline

From the [release files](https://godmode.build/install#release-files), get the installer, your platform’s archive, and its `SHA256SUMS`. Copy all three to the destination machine, then run:

```sh
sh install.sh --archive godmode-vX.Y.Z-aarch64-apple-darwin.tar.gz --checksum SHA256SUMS
```

Replace `vX.Y.Z` with the release version and use your platform’s suffix.

| System | ARM64 | x86-64 |
| --- | --- | --- |
| macOS | `aarch64-apple-darwin` | `x86_64-apple-darwin` |
| Linux | `aarch64-unknown-linux-musl` | `x86_64-unknown-linux-musl` |

Use `--loadout` to open the menu after a local install.

### Build from source

Use a checkout or the release’s separate source archive. You’ll need Python 3.9 or later and the exact Go toolchain pinned in `go.mod`. For an offline build, install that Go version on PATH first. The archive includes vendored dependencies.

```sh
GOPROXY=off GOSUMDB=off sh scripts/build-native.sh --output target/godmode-native
```

You can run `target/godmode-native` directly or install it with `sh install.sh --binary target/godmode-native --sha256 HEX`. Replace `HEX` with the verified SHA-256 digest of your binary. See [Security](SECURITY.md) for release integrity and identical rebuilds.

## Inspect the source

```sh
godmode source | less
godmode build-info
```

`source` prints the embedded Python engine. `build-info` prints its digest, the Go compiler version, and dependencies. The separate source archive includes the Go interface and Python engine.

## Uninstall

To keep local data, remove the executable, updater, backup, install receipt, and PATH file. With the default paths:

```sh
rm -f "$HOME/.godmode/bin/godmode" "$HOME/.godmode/bin/godmodeup" \
  "$HOME/.godmode/bin/godmode.previous" "$HOME/.godmode/bin/.godmode-install-receipt" \
  "$HOME/.godmode/env"
```

Remove the `# Godmode` comment and its source line from the startup file or files the installer changed. See [Agent instructions](AGENT_SETUP.md#check-or-remove-it) to remove its note.

For a full removal, privately back up any data you want to keep, then delete the Godmode home. That deletes its keys, profiles, and selection. [Remote machines](REMOTE.md) lists the files needed to restore sealed keys. Revoke keys at the provider to invalidate them.

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| `godmode: command not found` | Source the generated `env` file or use `~/.godmode/bin/godmode`. In an unsupported shell such as fish, add the bin directory using that shell’s PATH configuration. |
| Python is missing or too old | Run `python3 --version`. Install Python 3.9 or later and put it first on PATH. |
| Home is a symlink or isn’t a directory | Use `--home` with the real directory. |
| Older updater reports a missing archive or checksum | Download the platform archive and checksum from the release files, then run `godmodeup --archive PATH --checksum SHA256SUMS`. |
| A zsh agent cannot find an older install | Run `godmodeup --path` to enable PATH configuration in `.zshenv` for non-interactive shells. |

For static text and numbered choices use `godmode --plain` or set `GODMODE_PLAIN=1`. Use `--no-motion` or `GODMODE_NO_MOTION=1` to disable animation. Set `NO_COLOR=1` or `CLICOLOR=0` for monochrome output.

## Upgrading from 0.9 or earlier

Older versions can leave plaintext keys in `~/.config/godmode/.env.godmode`. If the default Godmode home has no key file and the legacy file still has values, Godmode can keep using the legacy file. Run `godmode path` to find the active file.

Switch scripts that read the old file to `godmode run NAME -- command`. Then run `godmode migrate` to seal the keys. Migration verifies every value before replacing the legacy file and reports ambiguous or duplicate entries by line and key name. Review any comments left in the old file for credentials you wrote there yourself.
