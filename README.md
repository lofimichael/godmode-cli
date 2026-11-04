# Godmode

Set up provider access for your agents. Choose a provider, follow its links, and paste keys into masked prompts.

![Interactive setup using a synthetic key](docs/images/setup.gif)

## Install

Apple Silicon macOS. Requires [GitHub CLI](https://cli.github.com/) signed in with access to this private repo.

```sh
gh api -H 'Accept: application/vnd.github.raw+json' \
  repos/lofimichael/godmode-cli/contents/install.sh | sh
```

Installs into `~/.godmode/` and starts setup. Existing `~/.config/godmode/` configurations stay in place.

To run setup again:

```sh
~/.godmode/bin/godmode setup
```

[Installation](docs/INSTALLATION.md) · [Providers](docs/PROVIDERS.md) · [Security](docs/SECURITY.md) · [Picard](docs/PICARD.md) · [Development](docs/RELEASING.md)
