# Godmode

Pick a provider with the arrow keys. Godmode shows what to create and where, in three steps or fewer, and Enter opens the page. Paste the key behind a mask; before you save, it shows the edit it will make as a shell command, with your value filled in as `sealed(sk_•••••123)`, and the file it writes. Keys are sealed in one file: reading it shows names, never values. (Keys still in an older plain-text `~/.config/godmode` file stay plain until you move them.) The CLI is readable Python.

Agents use keys through it, one command at a time:

```sh
godmode list                                  # key names
godmode run CLOUDFLARE_API_TOKEN -- npx wrangler whoami
godmode help                                  # the guide agents need
```

Plain-text keys in `~/.config/godmode/.env.godmode` are detected at setup, with an offer to move them to `~/.godmode` and seal them (`godmode migrate` does the same).

![Interactive setup using a synthetic key](docs/images/setup.gif)

## Install

macOS/Linux, Python 3.9+. Requires [GitHub CLI](https://cli.github.com/) signed in with access to this private repo.

```sh
gh api -H 'Accept: application/vnd.github.raw+json' \
  repos/lofimichael/godmode-cli/contents/install.sh | sh -s -- --path
```

Installs into `~/.godmode/`, adds its commands to your shell, and starts setup. Existing `~/.config/godmode/` keys stay where they are until you choose to move them.

Update and run from a new terminal:

```sh
godmodeup
godmode
```

[Installation](docs/INSTALLATION.md) · [Providers](docs/PROVIDERS.md) · [Security](docs/SECURITY.md) · [Picard](docs/PICARD.md) · [Development](docs/RELEASING.md)
