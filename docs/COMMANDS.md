# Command reference

These commands cover Godmode v0.22.1. Run `godmode --help` for the installed command list or `godmode help COMMAND` for most commands. In the examples below, replace uppercase placeholders with your own names or command.

## Open and inspect

| Command | Result |
| --- | --- |
| `godmode` | Open the terminal interface. |
| `godmode --version` | Print the installed version. |
| `godmode help` | Print the agent guide for the selected loadout, including saved key names. |
| `godmode faq` | Read local checks and troubleshooting help. |
| `godmode intro` | Replay the welcome. |
| `godmode doctor`, `godmode doctor --json` | Check the local install, selected files and detected agent notes. Failed checks return exit status 1. |
| `godmode source` | Print the embedded Python file engine. |
| `godmode build-info` | Print compiler, dependencies and engine hash. |

## Credentials and providers

| Command | Result |
| --- | --- |
| `godmode loadout`, `godmode loadout PROVIDER` | Choose a provider or open its credential screen directly. |
| `godmode provider`, `godmode provider PROVIDER` | List providers or show credential, verification and recovery steps for one. |
| `godmode list` | Print saved key names, one per line. An invalid store can return a nonzero status. |
| `godmode set NAME`, `godmode set NAME --stdin` | Save a value through a masked prompt or read it from stdin. |
| `godmode run NAME... -- CMD` | Add only the requested saved keys to the command's inherited environment. |
| `godmode run VAR=NAME -- CMD` | Supply a saved key under the variable the command expects. |
| `godmode path` | Print the selected credential file's path. |
| `godmode edit` | Open the file in nano. Sealed entries stay encrypted. |
| `godmode migrate` | Seal keys from an older plaintext store. |

Keep credentials out of command arguments and chat. For an account check, run a provider's read-only command with the minimum key set. See [Providers](PROVIDERS.md).

## Profile and agent instructions

| Command | Result |
| --- | --- |
| `godmode profile` | Edit the optional business fields. |
| `godmode profile show`, `godmode profile path` | Print the selected profile as JSON or print its file path. |
| `godmode profile get FIELD` | Print one field. An unset field returns exit status 1. |
| `godmode profile set FIELD`, `godmode profile set FIELD --stdin` | Set a field through a visible prompt or from stdin. |
| `godmode profile unset FIELD` | Remove a field. |
| `godmode agents` | Copy the selected task note or review additions to detected agent files. |
| `godmode agents --print` | Print the note scoped to the selected loadout. |

See [Profile](PROFILE.md) for field names and [Agent instructions](AGENT_SETUP.md) for the review and verification steps.

## Home and display settings

In the terminal UI, use the arrow keys to move, Enter to open, and Esc to go back. Press Ctrl-K to find an action or `?` for keyboard help.

| Option or command | Result |
| --- | --- |
| `--home DIR` | Select a Godmode home. The default is `~/.godmode`. |
| `--plain` | Use static text and numbered menus for this invocation. |
| `--no-motion` | Disable animations for this invocation. |
| `godmode settings` | Open Settings in a terminal or report the motion preference in plain mode. |
| `godmode settings --json` | Read the stored motion preference and its path. |
| `godmode settings motion on`, `godmode settings motion off` | Save the motion preference. |

`GODMODE_HOME` also selects a home. The older `GODMODE_CONFIG_DIR` alias still works. Use `GODMODE_PLAIN=1`, `GODMODE_NO_MOTION=1` or `NO_COLOR=1` for shell-wide display overrides.

## Profiles and environments

| Command | Result |
| --- | --- |
| `godmode active`, `godmode active --json` | Inspect the resolved key environment and profile. JSON includes paths and selection sources. |
| `godmode active --command` | Print the full command prefix that pins the current loadout. |
| `godmode use --env NAME --context PROFILE` | Save the active pair for future commands. Omit one flag to keep that part of the current selection. `godmode use NAME` is shorthand for `godmode use --env NAME`. |
| `godmode env`, `godmode env list` | List key environment names. Add `--json` to `env list` for metadata. |
| `godmode env create NAME`, `godmode env create NAME --copy SOURCE` | Create an empty store or an independent copy. |
| `godmode env show NAME` | Show the environment's paths and saved names. |
| `godmode context`, `godmode context list` | List business profile names. |
| `godmode context show PROFILE` | Show a profile path and its key mappings. |
| `godmode context create PROFILE` | Create a named business profile. |
| `godmode context map PROFILE VARIABLE SAVED_KEY` | Resolve a variable through another key name in the selected store. |
| `godmode context unmap PROFILE VARIABLE` | Remove a key mapping. |

For one command, put `--env NAME` and `--context PROFILE` before the command. `--env default` selects the default store. `--context -` selects **Automatic**, which uses that environment's own profile. Explicit flags take priority over shell variables, which take priority over the saved loadout. See [Profiles and environments](CONTEXTS.md).

## Update the installation

| Command | Result |
| --- | --- |
| `godmodeup`, `godmode update` | Update the recorded installation to the latest available release. |
| `godmodeup --version vX.Y.Z`, `godmode update --version vX.Y.Z` | Install a specific published version. |

See [Installation](INSTALLATION.md) for recovery and [Licensing](LICENSING.md) for earlier paid releases. Run `godmode license --help` for receipt commands.
