# Install and update

Godmode is one readable Python script. It needs Python 3.9+ and a POSIX system; it installs no Python packages. The same script runs on macOS and Linux. This release is exercised locally on macOS; the Linux CI workflow is available separately.

For the private repository, use a GitHub CLI login with repository access:

```sh
gh api -H 'Accept: application/vnd.github.raw+json' \
  repos/lofimichael/godmode-cli/contents/install.sh | sh -s -- --path
```

The installer verifies the release checksum, installs under `~/.godmode/bin`, and opens setup. `--path` adds an idempotent source line to your shell startup file, backing up an existing profile. Omit it to manage PATH yourself. No root permissions or package manager are needed when Python is already installed.

Open a new terminal, or use the current one:

```sh
. "$HOME/.godmode/env"
godmodeup
godmode
```

`godmodeup` updates managed scripts, keeps the previous executable, and does not reopen setup unless you pass `--setup`. `--version v0.9.0` pins a release. The updater refuses unrelated or modified executables; `--force` explicitly adopts them. It never edits your keys.

## One home

```text
~/.godmode/
  bin/godmode             readable Python script
  bin/godmodeup           readable shell updater
  env                     shell PATH setup
  .env.godmode            your credentials, sealed
  seal.key                the key that unseals them (mode 0600)
  STOP_AND_READ_ME_FOR_KEYS.md  how agents use keys without opening the file
  state/picard/           optional media cache and playback socket
```

The installer also keeps its small hash receipt and previous-executable backup under `bin`. Setup itself creates no acknowledgement, registry or lock files.

An existing `~/.config/godmode/.env.godmode` that still assigns a value is preserved and selected while `~/.godmode` contains no credential file, operating rules or legacy catalog marker. Otherwise, including a rules checkout with no such file or one holding only blank `NAME=` lines, new keys go to `~/.godmode`. Nothing is copied unless you accept setup's offer to move plain-text keys, or run `godmode migrate`. `godmode path` prints the selected file; `--home DIR` or `GODMODE_HOME` chooses another home. Existing `AGENTS.md` and OAuth state remain untouched. Old `providers.toml` overlays are no longer loaded; their keys can still be edited with `godmode set KEY` or nano.

## Inspect or run the source

```sh
less ~/.godmode/bin/godmode
python3 godmode.py --home /absolute/path/to/a/test-home
```

The installed file is ordinary Python source, assembled without compression or obfuscation from the small files under `lib/`, the menu in `godmode.py`, and static provider guidance. It has no dependencies outside Python's standard library. `godmode edit` opens the file in nano: sealed files show ciphertext, while older plain files expose their values. Do not rename sealed assignments; use `godmode set NAME` to save values.

For an offline install, build the script and pass its SHA-256:

```sh
python3 scripts/build.py --output target/godmode
GODMODE_SCRIPT_SHA=$(shasum -a 256 target/godmode | awk '{print $1}')
sh install.sh --binary target/godmode --sha256 "$GODMODE_SCRIPT_SHA"
```

The installer also accepts a release `--archive` with its `--checksum` file. These local-artifact modes do not download anything. The first portable release includes legacy archive filenames so previously installed `godmodeup` versions can update normally; those archives contain the same readable script, not native binaries.

## Remove

Remove the installed `godmode`, `godmodeup`, their receipt and optional previous-executable backup. If enabled, remove the Godmode source line from your shell profile and the generated `env` file. The key file and `seal.key` stay, but sealed values can be read only through `godmode`: keep the executable, or save the keys elsewhere first. Removing a key locally does not revoke it at the provider.
