# Godmode

Godmode keeps provider credentials in one `.env.godmode` file. Choose a provider, follow its setup links, and paste the key into a masked prompt. Your local agents can reuse the file instead of asking you to configure the same account for every project.

## Install and set up

While this repository is private, use a signed-in [GitHub CLI](https://cli.github.com/) account with access:

```sh
gh api -H 'Accept: application/vnd.github.raw+json' \
  repos/lofimichael/godmode-cli/contents/install.sh | sh
```

The installer selects the build for your machine, downloads it with its checksum, verifies it, installs into `~/.godmode/bin`, and starts interactive setup. No Rust toolchain or manual archive selection is needed. The available prebuilt release currently supports **Apple Silicon macOS**; missing builds produce an error rather than installing the wrong binary.

An existing executable is preserved. [Installation and upgrades](docs/INSTALLATION.md) explains explicit replacement, offline installs and alternate homes. Your existing `~/.config/godmode` is detected; credentials and rules stay where they are. Shell profiles are not changed.

To run setup later:

```sh
~/.godmode/bin/godmode setup
```

Choose a provider by number or name. Open its login, key page or documentation when needed, then paste at the credential prompt and press Enter. Input is masked, including multiline JSON; pasting alone never saves. An empty answer skips a missing key, and an existing key is kept unless you choose to replace it. Esc or Ctrl-C cancels the current input. Keys already saved remain on disk.

![Interactive setup recorded from the real CLI using synthetic credentials](docs/images/setup.gif)

This is the actual CLI in a temporary home with a synthetic key. It demonstrates local entry and storage, not provider authentication. [Recording instructions](https://github.com/lofimichael/godmode-cli/blob/main/scripts/README.md).

You can go straight to one provider with `godmode setup github`. Bare `godmode` and interactive `godmode init` also start these prompts. `godmode onboard` opens the full-screen provider board, with its original keyboard controls and optional Picard view.

For unfamiliar providers, `godmode set NAME_OF_KEY` opens masked entry. A [TOML catalog entry](docs/PROVIDERS.md) is only needed if you want that provider's instructions in setup. No editor is involved. Headings, provider status, links and key prompts are colored; `NO_COLOR=1` requests plain text. The program is one Rust executable with no service, account of its own, telemetry or automatic updater. [READTHIS.NFO](READTHIS.NFO) and the [culture study](docs/CULTURE.md) describe its presentation.

## Cargo and local builds

There is no crates.io release yet. If you already have Rust and this source checkout, Cargo can install it directly:

```sh
cargo install --path . --locked --root "$HOME/.godmode"
~/.godmode/bin/godmode setup
```

Cargo compiles from source. The prebuilt installer above avoids that toolchain requirement. See [the installation guide](docs/INSTALLATION.md) for isolated trials and building without installation.

## Use a saved credential

```sh
godmode status --json
godmode doctor --json
godmode run --with GH_TOKEN -- gh api user --jq .login
```

For automation, `init --accept-disclaimer` initializes without prompts; `set KEY --stdin` reads a pipe or redirected file, and `set KEY --from-file PATH` reads a private file. There is no positional secret argument. Never put a credential into a shell command, issue or agent transcript. Paste JSON directly, without shell quotes.

Setup asks for acknowledgement before creating its files. It keeps existing credentials and operating rules. In a Git checkout, `.env.godmode` must be ignored and untracked before writes. Stored values are plaintext with mode 0600; programs running as your user can read them. Read [the storage and authority notes](docs/SECURITY.md).

## Picard mode

```sh
godmode picard link    # print https://picard.ytmnd.com/
godmode picard open    # open the original site
godmode picard show    # show its original image in the terminal
godmode picard play    # loop the original YTMND audio; stays in the foreground
godmode picard stop    # stop it from another terminal
```

On the provider board, `i` opens the picture, `p` toggles audio and `v` opens the original site. In the picture view, `t` switches between a fitted portrait and tiling; `i` or Esc returns to the board. `picard show` opens the picture directly without loading credentials. Its `p` key starts audio only if requested. Quitting stops any player owned by that session. When using a custom `--state-dir`, give `stop` the same directory.

The picture is the original YTMND JPEG rendered as terminal cells, with colour half-blocks or monochrome ASCII when `NO_COLOR` is set. It is a terminal adaptation of the source image, not a replica of the web page.

The recording is the approximately eight-second excerpt used by the original Picard YTMND, repeated until stopped, **not the full DarkMateria track**. The first request for a picture or audio downloads that asset from YTMND into a private local cache and checks its pinned SHA-256. Neither source asset is bundled in the code or release archive. YTMND receives the download request; no credential file is read or sent by the standalone Picard commands. Attribution and implementation details are in [PICARD.md](docs/PICARD.md).

## Commands

| Command | Result |
| --- | --- |
| `godmode` / `setup [PROVIDER]` | Interactive provider selection and masked credential prompts |
| `onboard` | Full-screen provider board |
| `init [--accept-disclaimer]` | Interactive setup; the flag initializes without prompts |
| `status [--json]` | Key names and local presence; never stored values |
| `doctor [--json]` | Offline file ownership, permissions, size, symlink and syntax checks |
| `set KEY [--stdin \| --from-file PATH]` | Save or replace one key; no source flag opens masked entry |
| `unset KEY` | Remove assignments for one key, preserving unrelated content |
| `has KEY...` | Exit successfully when every requested key has a usable value |
| `guide PROVIDER` | Setup, scope, documentation and manual verification guidance |
| `providers [--json]` | List the merged provider catalog |
| `providers-template` | Print a credential-free TOML overlay template |
| `run --with KEY[=ALIAS] -- CMD...` | Give selected credentials to a child process |
| `picard [link \| open \| show \| play \| stop]` | Original YTMND picture, audio and source link |

Repeat `--with` to pass multiple credentials. In `SOURCE_KEY=CHILD_NAME`, the left side names the stored key and the right side names the child's environment variable. `run` clears the inherited environment, preserves basic process context such as PATH, HOME, locale and terminal settings, and adds only the selected credentials. Its stdout/stderr are the child's own output and are **not redacted**.

Exit codes are `0` for success, `1` for a failed `has`/`doctor` check or declined initialization, and `2` for invocation or operation errors. `run` propagates the child exit code (or `128 + signal`). `status` reports presence, not provider authentication, scope, account ownership, billing readiness or permission to act.

Global options: `--home DIR` (alias `--config-dir`), `--state-dir DIR`, `--no-motion`. Home selection uses the explicit flag, then `GODMODE_HOME`, then the compatibility variable `GODMODE_CONFIG_DIR`, then automatic discovery. State selection uses its flag, then `GODMODE_STATE_DIR`, then the selected home's default. `GODMODE_REGISTRY` selects an explicit overlay; `GODMODE_NO_MOTION=1` also disables animation.

## One credential file, optional metadata

New installations keep everything in one home:

```text
~/.godmode/
  bin/godmode          executable
  .env.godmode         credentials, mode 0600
  providers.toml       optional provider metadata, no credentials
  AGENTS.md            operating rules, if supplied separately
  state/               acknowledgements, locks and optional Picard media
```

If `~/.godmode` has no credential file, provider catalog or operating rules, an existing `~/.config/godmode` is adopted with its existing `~/.local/state/godmode/cli` state path. Installing only the new binary does not hide that legacy setup. No credentials, rules or OAuth state are migrated. An explicit `--home` selects that home and defaults its state to `DIR/state`.

Existing configuration directories and operating rules stay in place. New directories are private; state files use mode 0600. Acknowledgments are named `ack-v1-<config-path hash>` and locks `write-<config-path hash>.lock`. Writes use a private temporary file and atomic replacement; this is local plaintext storage, not encryption.

Use literal names that explain the capability: `STRIPE_TEST_SECRET_KEY`, `ACME_ACCOUNT_ADMIN_TOKEN`, `ACME_PROJECT_READ_TOKEN`. Any valid environment-variable name works without registering a provider. [Extend the catalog](docs/PROVIDERS.md) when you want that provider's instructions in the board. The bundled catalog covers twelve providers; none is mandatory. [Google OAuth](docs/GOOGLE.md) uses a separate login-state model.

Godmode gives agents access to real capabilities. It does not enforce your business authority or spending limits, and an unrestricted process running as your user can read the file. Read [the storage and authority details](docs/SECURITY.md) before storing credentials.

## Develop, release and remove

```sh
cargo fmt --all -- --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
sh tests/install.sh
```

[Release instructions](docs/RELEASING.md) describe local checks, CI opt-in for private repositories and the four-target draft release workflow. CI does not need provider secrets. There is no telemetry or automatic updater. Picard runs only while its foreground command or board is open; it leaves no background service.

To uninstall, first confirm which binary this installer placed, then remove that executable. Credentials and operating rules remain intact. Remove the CLI's acknowledgment/lock directory separately if no CLI process is active; do not delete an entire Godmode home merely to remove its executable. Deleting a local key does not revoke it at its provider.
