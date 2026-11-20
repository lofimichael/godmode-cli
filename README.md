# Godmode

Godmode stores provider keys and optional business details on your machine. Your coding agent reads the details it needs and runs commands with the keys you choose.

## Install

Requires macOS or Linux on ARM64 or x86-64 and Python 3.9 or later.

```sh
curl -fsSL https://get.godmode.build | bash
. "$HOME/.godmode/env"
godmode --version
```

Follow the [quickstart](docs/GETTING_STARTED.md) to save a key and connect your agent. See [Installation](docs/INSTALLATION.md) for shell configuration, offline installs, and updates.

These guides describe v0.21.0. The [public release manifest](https://godmode.build/releases/latest.json) shows the version available from the installer.

## Use Godmode

| To | Run |
| --- | --- |
| Open the terminal menu | `godmode` |
| Get guidance for an agent | `godmode help` |
| Print a note for the selected loadout | `godmode agents --print` |
| Check local files | `godmode doctor` |
| Look up a command | `godmode --help` or `godmode help COMMAND` |

A saved key means Godmode stored it locally. Verify access against the intended provider account before making changes.

## Documentation

- [Connect an agent](docs/AGENT_SETUP.md), [set up a provider](docs/PROVIDERS.md), or [add business details](docs/PROFILE.md).
- [Choose an environment and profile](docs/CONTEXTS.md) or [set up a remote machine](docs/REMOTE.md).
- [Read the command reference](docs/COMMANDS.md), [release notes](docs/CHANGELOG.md), or [online docs](https://godmode.build/docs).
- [Review credential storage and verify a release](docs/SECURITY.md), or run the [development checks](docs/dev/TESTING.md).
- Follow the [contributing guide](docs/CONTRIBUTING.md) for pull requests and releases.

The CLI is free for local use without an account or activation. The [source-available license](LICENSE) permits inspection and private modification and restricts redistribution. See [Licensing](docs/LICENSING.md) for earlier purchases and receipts.
