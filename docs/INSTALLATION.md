# Installation

Godmode uses a native Go interface built with Bubble Tea and Lip Gloss. Its embedded file engine needs Python 3.9 or newer. Native releases support macOS and Linux on Apple Silicon/ARM64 and x86-64. Installation needs no Go compiler, Python packages or root access.

```sh
gh api -H 'Accept: application/vnd.github.raw+json' repos/lofimichael/godmode-cli/contents/install.sh | sh -s -- --path
```

The installer selects the release for your operating system and CPU, checks its SHA-256, installs `~/.godmode/bin/godmode` and `godmodeup`, and starts setup. Options go after `--`:

| Option | Effect |
| --- | --- |
| `--path` | Adds a line that sources `~/.godmode/env` to your shell's startup file (`~/.zshenv` for zsh, so agents' non-interactive shells find `godmode` too), backing it up first. Without it, no startup file changes. |
| `--no-setup` | Installs without starting setup. |
| `--home DIR` | Installs into `DIR/bin` instead of `~/.godmode/bin`. Later commands need `--home DIR` or `GODMODE_HOME=DIR` to use that home. |
| `--version vX.Y.Z` | Installs that release instead of the newest. |

`sh install.sh --help` lists every option.

The repository is private. The installer and `godmodeup` use a [GitHub CLI](https://cli.github.com/) login with repository access to download releases.

## Update

```sh
godmodeup
```

`godmodeup` replaces only the files it installed, keeps the previous executable as `~/.godmode/bin/godmode.previous`, and never touches your profile or keys. It refuses an executable it did not install; `--force` adopts it. `--version vX.Y.Z` installs a specific release and `--setup` opens setup afterwards.

## Install offline

Download the native archive for the destination machine and its `SHA256SUMS`, then install them locally. For example, on Apple Silicon macOS:

```sh
sh install.sh --archive godmode-vX.Y.Z-aarch64-apple-darwin.tar.gz --checksum SHA256SUMS
```

Other native archive suffixes are `x86_64-apple-darwin`, `x86_64-unknown-linux-musl`, and `aarch64-unknown-linux-musl`. Replace `vX.Y.Z` with the release version. Offline installs do not open setup unless you add `--setup`.

To build from a checkout or the separate `godmode-vX.Y.Z-source.tar.gz` archive, use Python 3.9+ and the Go 1.26.7 toolchain pinned in `go.mod`:

```sh
sh scripts/build-native.sh --output target/godmode-native
GODMODE_BINARY_SHA=$(shasum -a 256 target/godmode-native | awk '{print $1}')
sh install.sh --binary target/godmode-native --sha256 "$GODMODE_BINARY_SHA"
```

The source archive includes pinned vendored Go dependencies. For an offline build, the exact pinned Go 1.26.7 compiler must already be installed and selected by `go` on PATH (`go version` confirms it); run the build with `GOPROXY=off GOSUMDB=off`. An older `go` on PATH may try to download or verify the pinned toolchain instead. The installer's `--archive` and `--binary` modes download nothing. Add `--without-music` to the build command to omit the optional music adapter.

## Inspect the source

The installed command is a native executable. These commands inspect its readable embedded Python engine and build metadata:

```sh
godmode source | less
godmode build-info
```

The separate source archive contains the matching Go and Python sources, build scripts and vendored dependencies. Native archives include build metadata and dependency license notices. See [Security](SECURITY.md) for source and rebuild checks. `python3 godmode.py --home /absolute/path/to/a/test-home` still runs the Python compatibility interface from a checkout; it does not run the native UI.

## Files

```text
~/.godmode/
  bin/godmode                   native UI with embedded Python file engine
  bin/godmodeup                 the updater
  env                           PATH setup, sourced by your shell with --path
  profile.json                  your profile
  .env.godmode                  your keys, sealed
  seal.key                      the key that unseals them
  STOP_AND_READ_ME_FOR_KEYS.md  tells agents to use godmode instead of opening the files
  intro.seen                    empty; you finished the welcome
  agent.added                   empty; you added the Agents text by hand
  state/picard/                 optional Picard media cache
  state/music/                  optional local music settings and render cache
```

`--home DIR` or `GODMODE_HOME` selects another home. `godmode path` and `godmode profile path` print where the key file and profile are.

`godmode --plain` uses static text and numbered choices through the Python interface. `GODMODE_PLAIN=1` selects the same mode for later commands; `TERM=dumb` selects it automatically. `NO_COLOR=1` or `CLICOLOR=0` removes color while keeping the arrow-key interface. `--no-motion` or `GODMODE_NO_MOTION=1` disables decorative animation.

## Uninstall

```sh
rm -rf ~/.godmode
```

This deletes your keys and profile too. Then remove the `# Godmode` line and the line below it from each startup file that `--path` changed. To keep your keys, remove only the programs and PATH setup:

```sh
rm -f ~/.godmode/bin/godmode ~/.godmode/bin/godmodeup ~/.godmode/bin/godmode.previous \
  ~/.godmode/bin/.godmode-install-receipt ~/.godmode/env
```

Keep a working Godmode executable or its matching Python engine if you keep sealed keys. The matching `seal.key` is also required to read them. Deleting a key here does not revoke it; revoke it at the provider.

## Troubleshooting

- `godmode: command not found`: open a new terminal, or run `. ~/.godmode/env`. An agent whose shell skips your startup file can run `~/.godmode/bin/godmode`.
- `--path` with a shell other than zsh, bash, sh, dash or ksh (fish, for example): Godmode installs anyway; add `~/.godmode/bin` to PATH in that shell's startup file yourself.
- Updating from 0.12 or earlier with zsh: run `godmodeup --path` once so `~/.zshenv` gets the PATH line; the old `~/.zshrc` line can stay.
- `is a symlink or not a directory`: the Godmode home must be a real directory. Symlinks above it, such as a linked `/home` or macOS `/tmp`, are fine. Run with `--home` and the real path.
- `Godmode needs Python 3.9 or newer`: install a newer `python3`; Godmode uses the first one on PATH.

## Upgrading from 0.9 or earlier

Godmode 0.9 and earlier saved keys as plain text, and some setups kept them in `~/.config/godmode/.env.godmode`. While `~/.godmode` has no `.env.godmode` and that old file still holds a value, Godmode keeps using it: `list` and `run` read it as before, and keys saved there stay plain text. `godmode path` shows which file is in use. The profile still lives in `~/.godmode/profile.json`. `GODMODE_CONFIG_DIR` still works as an older name for `GODMODE_HOME`.

Setup offers to move those keys to `~/.godmode` and seal them; `godmode migrate` does the same without the menu. First change any program that reads the old file directly to use `godmode run NAME -- command`. Godmode reads and changes only `.env.godmode` in `~/.config/godmode`.

`migrate` changes nothing until every value reads back identically from the sealed copy. It refuses a file it cannot carry exactly, naming line numbers and key names but never values: a key saved twice, a value with unquoted spaces, a comment after a value, a line that is not `NAME=value`, or a known key's `NAME=` inside another value. Keys already in `~/.godmode` stay, and a name in both files must hold the same value, so an interrupted move finishes when run again. Afterwards the old file says where the keys went and keeps its own `#` comment lines, which never go into the sealed file; Godmode says how many stayed so you can delete any key written in one.
