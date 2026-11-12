# Godmode

Pick a provider with the arrow keys. Godmode shows what to create and where, in three steps or fewer, and Enter opens the page. Paste the key behind a mask; before you save, it shows a shell command with the same effect, with your value filled in as `sk_•••••123`, and the file it writes. Everything goes into one ordinary `.env.godmode` file. The CLI is readable Python; your agents do not need it.

![Interactive setup using a synthetic key](docs/images/setup.gif)

## Install

macOS/Linux, Python 3.9+. Requires [GitHub CLI](https://cli.github.com/) signed in with access to this private repo.

```sh
gh api -H 'Accept: application/vnd.github.raw+json' \
  repos/lofimichael/godmode-cli/contents/install.sh | sh -s -- --path
```

Installs into `~/.godmode/`, adds its commands to your shell, and starts setup. Existing `~/.config/godmode/` configurations stay in place.

Update and run from a new terminal:

```sh
godmodeup
godmode
```

[Installation](docs/INSTALLATION.md) · [Providers](docs/PROVIDERS.md) · [Security](docs/SECURITY.md) · [Picard](docs/PICARD.md) · [Development](docs/RELEASING.md)
