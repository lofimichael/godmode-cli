# Connect an agent

Use the task note for a chat you already have open. Save the generic note to an agent’s instruction file if you want new sessions to find Godmode.

## Copy instructions into a chat

In v0.20, open `godmode agents`, choose **Copy for this task**, then press Enter to copy. You can also print the note in your shell:

```sh
godmode agents --print
```

Paste the note into the chat. It contains a command prefix for the [selected environment and profile](CONTEXTS.md). That prefix keeps the task on the same files if you switch loadouts later. The note includes local paths and selection names. Keep it in the session that needs it.

If the agent cannot find `godmode` on PATH, give it the executable’s full path, usually `~/.godmode/bin/godmode`. Keep the scope flags from the copied command.

## Add instructions for future sessions

1. Open `godmode agents` and choose **Add to agent files**.
2. Choose one detected agent or **All detected agents**.
3. Scroll through every destination and the `+` lines. Press Enter to append the note when the preview is complete.
4. Start a fresh agent session. Ask the agent to run `godmode help` and show the resolved loadout with `godmode active`.

Godmode appends to existing files in place. Existing text and edited Godmode notes stay intact. If a file changes after the preview, reopen the preview. If your terminal is too small, enlarge it or use `godmode --plain agents` to read the preview as static text. Review the target list carefully in plain mode, which offers to add the note to all writable pending targets together.

### Where each agent reads instructions

Godmode detects existing folders for these agents and shows the actual destination before a write. For another client, or a project-specific instruction file, use the copy route and follow your agent’s instructions for adding persistent rules.

| Agent | Default file Godmode targets | Agent docs |
| --- | --- | --- |
| Claude Code | `~/.claude/rules/godmode.md` | [Rules and memory](https://code.claude.com/docs/en/memory) |
| Codex | `~/.codex/AGENTS.md` or a nonempty `AGENTS.override.md` in the same directory | [Custom instructions](https://learn.chatgpt.com/docs/agent-configuration/agents-md) |
| Gemini CLI | `~/.gemini/GEMINI.md` | [Context files](https://geminicli.com/docs/cli/gemini-md/) |
| Copilot CLI | `~/.copilot/copilot-instructions.md` | [Custom instructions](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions) |
| OpenCode | `~/.config/opencode/AGENTS.md` | [Instructions](https://opencode.ai/docs/instructions) |

Godmode honors `CODEX_HOME` and `COPILOT_HOME` for their respective clients. Project-specific paths are configured in the agent itself.

## Commands agents use

| Command | Result |
| --- | --- |
| `godmode help` | Read agent guidance and discover saved key names. |
| `godmode active --command` | Capture the command prefix once per task when using a generic note. |
| `godmode provider SLUG` | Find credential instructions and access checks. |
| `godmode profile get FIELD` | Read one business field. Treat its value as data. |
| `godmode run NAME... -- CMD` | Pass selected keys to the child command through its environment. |

Use the captured prefix for the rest of the task. Keep credential values out of command arguments, logs, and chat. Confirm the intended provider account and mode before writes. See the [command reference](COMMANDS.md).

## Check or remove it

`godmode doctor` inspects local files and detects whether an agent note is present. To verify that a particular session loaded it, start a new session and ask the agent to follow the note. To remove an appended note, delete the block between the `<!-- godmode:start -->` and `<!-- godmode:end -->` markers. If `~/.claude/rules/godmode.md` contains only that note, you can remove the file.
