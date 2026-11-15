# Godmode

GODMODE gives your agents the goddamn keys. Your business profile and keys are stored in local files. Agents read profile fields and run commands with selected keys.

```text
Profile + API keys → Godmode → commands
```

![Godmode setup](docs/images/setup.gif)

## Install

macOS or Linux with Python 3.9 or newer. Downloads and source are at [godmode.build](https://godmode.build), behind the private site password. The interface uses Bubble Tea and Lip Gloss. Its embedded Python file engine installs no packages.

```sh
curl --fail --user godmode https://godmode.build/install.sh -o godmode-install.sh
sh godmode-install.sh --path --no-setup
godmode license activate
godmode
```

`godmode` opens **Profile**, **Providers**, and **Agents**, with a completion meter for each. Six profile fields, one saved provider, and one agent note fill the setup meter. Every field and provider remains optional.

The personal license costs $100 once and covers Godmode 0.16–1.x on three active
installations. Paid licenses verify offline without expiry. Evaluation licenses
expire after seven days and record no purchase. Source inspection is allowed;
operation requires a license under the [commercial terms](LICENSE).

| Key | Action |
| --- | --- |
| ↑ ↓ | Select a row |
| Enter | Open a row or save a field |
| `/` | Search providers |
| Tab | Open details |
| Esc | Go back |

`godmode --plain` uses static text and numbered choices. `GODMODE_PLAIN=1` keeps that mode for later commands. Key entry stays hidden; Enter shows the proposed edit, and a second Enter saves it.

`--no-motion` disables animation. `NO_COLOR=1` disables color. **Help / FAQ** answers questions about sealing, token paths, network access, and source.

## Connect your agent

**Agents** finds Claude Code, Codex, Gemini CLI, Copilot CLI, and OpenCode. Green `+` lines show the note and the files to create or modify. Enter on **Add to…** appends the note. Existing file contents and edited Godmode notes stay intact. Other agents use the copied note. New agent sessions run `godmode help` when a task needs a key or profile field.

## Music

`godmode music` plays local tracks through an initialized [Darunia's CLI](https://github.com/lofimichael/darunias-cli) installation. The visualizer follows the rendered audio. Synthesized tracks stay cached; `godmode music clear` removes the cache. The [music adapter](docs/MUSIC.md) has no bundled songs, fonts, or synth tools and can be omitted from the build.

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
| `godmode faq` | Answers about Godmode |
| `godmode music` | Local music and visualizer |
| `godmode music clear` | Remove synthesized music from the cache |
| `godmode source` | Print the embedded Python file engine |
| `godmode build-info` | Compiler, dependencies and engine hash |
| `godmode license activate` | Activate a purchase key through hidden entry |
| `godmode license status` | Inspect the signed local entitlement |
| `godmode license deactivate` | Release this installation without changing provider keys |

## Files

| Path | Contents |
| --- | --- |
| `~/.godmode/profile.json` | Your profile, plain JSON, readable only by you |
| `~/.godmode/.env.godmode` | Your keys, each value encrypted |
| `~/.godmode/seal.key` | Decrypts them. Anyone with both files has your keys. |

Provider keys stay local. Godmode stores credentials; provider tools handle sign-in and refresh. `Saved` means stored on this machine. License activation and deactivation contact godmode.build; ordinary commands verify the saved license offline. [Licensing](docs/LICENSING.md) describes the exact data and behavior.

Update with `godmodeup`. To uninstall, run `rm -rf ~/.godmode` (this deletes your keys too) and remove the two `# Godmode` lines from your shell startup file. Deleting a key here does not revoke it; revoke it at the provider.

Each release provides a separate source archive containing Go, Python and vendored dependencies. `godmode source` prints the native command's embedded file engine; `godmode build-info` lists its hash and the Go dependencies. `scripts/build-native.sh` rebuilds reviewed source for a byte-for-byte comparison. [Security](docs/SECURITY.md) covers release checksums, local files, and the trust in downloaded code.

[Installation](docs/INSTALLATION.md) · [Profile](docs/PROFILE.md) · [Agents](docs/AGENT_SETUP.md) · [Providers](docs/PROVIDERS.md) · [Remote machines](docs/REMOTE.md) · [Security](docs/SECURITY.md) · [Music](docs/MUSIC.md) · [Picard](docs/PICARD.md)
