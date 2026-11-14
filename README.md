# Godmode

Godmode stores your business profile and API keys on this machine. Coding agents read profile fields and run commands with selected keys.

```text
Profile + API keys → Godmode → commands
```

![Godmode setup](docs/images/setup.gif)

## Install

macOS or Linux with Python 3.9 or newer. Private downloads use a GitHub CLI login with repository access. Godmode installs no Python packages.

```sh
gh api -H 'Accept: application/vnd.github.raw+json' repos/lofimichael/godmode-cli/contents/install.sh | sh -s -- --path
```

`godmode` opens **Profile**, **Providers**, and **Agents**, with a completion meter for each. Six profile fields, one saved provider, and one agent note fill the setup meter. Every field and provider remains optional.

| Key | Action |
| --- | --- |
| ↑ ↓ | Select a row |
| Enter | Open a row or save a field |
| `/` | Search providers |
| Tab | Open details |
| Esc | Go back |

`godmode --plain` uses static text and numbered choices. `GODMODE_PLAIN=1` keeps that mode for later commands. Key entry stays hidden; Enter shows the proposed edit, and a second Enter saves it.

## Connect your agent

**Agents** finds Claude Code, Codex, Gemini CLI, Copilot CLI, and OpenCode. It shows the exact note and destination files; Enter on **Add to…** writes the note. Other agents use the copied note. New agent sessions run `godmode help` when a task needs a key or profile field.

## Commands

| Command | What it does |
| --- | --- |
| `godmode` | Set up your profile, providers and agents |
| `godmode --plain` | Static text and numbered choices |
| `godmode setup [PROVIDER]` | Add or replace a provider's keys |
| `godmode list` | Names of saved keys, never values |
| `godmode run NAME... -- CMD` | Run CMD with those keys in its environment |
| `godmode set NAME` | Save or replace a key behind a mask (`--stdin` to pipe one in) |
| `godmode profile get FIELD` | Print one profile field, such as `business_name` |
| `godmode provider [PROVIDER]` | Setup, verification and recovery guide for a provider |
| `godmode help` | The guide your agent reads, with what is saved |

## Files

| Path | Contents |
| --- | --- |
| `~/.godmode/profile.json` | Your profile, plain JSON, readable only by you |
| `~/.godmode/.env.godmode` | Your keys, each value encrypted |
| `~/.godmode/seal.key` | Decrypts them. Anyone with both files has your keys. |

Keys stay local. Godmode stores credentials; provider tools handle sign-in and refresh. `Saved` means stored on this machine.

Update with `godmodeup`. To uninstall, run `rm -rf ~/.godmode` (this deletes your keys too) and remove the two `# Godmode` lines from your shell startup file. Deleting a key here does not revoke it; revoke it at the provider.

[Installation](docs/INSTALLATION.md) · [Profile](docs/PROFILE.md) · [Agents](docs/AGENT_SETUP.md) · [Providers](docs/PROVIDERS.md) · [Remote machines](docs/REMOTE.md) · [Security](docs/SECURITY.md) · [Picard](docs/PICARD.md)
