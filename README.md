# Godmode

Godmode puts your business profile and API keys in one local place that your coding agents can use.

For example, an agent in Claude Code, Codex or Cursor can buy and register a domain on Cloudflare, deploy a Workers app to it and connect Stripe for payments.

![Setup: choose a provider, follow its steps, paste the key](docs/images/setup.gif)

## Install

macOS or Linux with Python 3.9 or newer. Nothing else is installed.

```sh
curl -fsSL https://github.com/lofimichael/godmode-cli/releases/latest/download/install.sh | sh -s -- --path
```

Setup starts when the install finishes. Pick a provider with the arrow keys, press Enter to open its key page, paste the key and press Enter to save. Everything is optional. `godmode` shows how far you are: profile fields filled, providers saved and agents that know about Godmode. Run `godmode` any time to continue.

## Connect your agent

In `godmode`, choose **Agents**. Godmode shows the short note it will add for Claude Code, Codex, Gemini CLI, Copilot CLI or OpenCode, and writes it when you press Enter. For Cursor and other agents, copy the note into their instructions. In a new session, the agent runs `godmode help` when a task needs a key or a profile field.

## Commands

| Command | What it does |
| --- | --- |
| `godmode` | Set up your profile, providers and agents |
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

Nothing is sent anywhere. Godmode does not sign in to providers or check that a key works; saved means stored, not verified.

Update with `godmodeup`. To uninstall, run `rm -rf ~/.godmode` (this deletes your keys too) and remove the two `# Godmode` lines from your shell startup file. Deleting a key here does not revoke it; revoke it at the provider.

[Installation](docs/INSTALLATION.md) · [Profile](docs/PROFILE.md) · [Agents](docs/AGENT_SETUP.md) · [Providers](docs/PROVIDERS.md) · [Remote machines](docs/REMOTE.md) · [Security](docs/SECURITY.md) · [Picard](docs/PICARD.md)
