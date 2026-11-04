# Godmode

An interactive editor for `.env.godmode`, with provider links and masked input. It is an ordinary text file: edit it in nano whenever you like. Your agents do not need this CLI.

![Interactive setup using a synthetic key](docs/images/setup.gif)

## Install

Apple Silicon macOS. Requires [GitHub CLI](https://cli.github.com/) signed in with access to this private repo.

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
