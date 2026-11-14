# Agents

**Agents** in `godmode` lists detected agents, the exact note, and destination files. Enter on **Add to…** writes the note.

Godmode finds Claude Code, Codex, Gemini CLI, Copilot CLI, and OpenCode by their folders. Claude Code uses `~/.claude/rules/godmode.md`. The note is appended between `<!-- godmode:start -->` and `<!-- godmode:end -->`; existing instruction text stays intact. A short terminal blocks the write until the complete note and paths fit. `godmode --plain agents` prints the full preview in sequence.

**Copy the note** supports Cursor and other agents. Paste it into the agent's instructions, then choose **I added it** when that action is available. Redirected output contains only the note, so `godmode agents | pbcopy` works. A project's instruction file limits the note to that project.

The text tells the agent to run `godmode help` before work that needs a key or a profile field. `help` lists what is saved and explains `profile get`, `provider`, `list`, `set` and `run`. The text holds no profile values or key names, so it stays the same across updates. If `godmode` is not on the agent's PATH, the text gives the full path.

## Where each agent reads instructions

Checked against official documentation on 2026-11-13. These are separate conventions for each client, not one global `AGENTS.md` standard.

| Agent | Where to put the text | Important detail |
| --- | --- | --- |
| OpenAI Codex | `~/.codex/AGENTS.md`, or under `CODEX_HOME` | A nonempty `AGENTS.override.md` takes its place; project files follow global instructions. [Docs](https://learn.chatgpt.com/docs/agent-configuration/agents-md) |
| Anthropic Claude Code | `~/.claude/CLAUDE.md`, or a dedicated `~/.claude/rules/godmode.md` | User and project guidance combine. Do not overwrite either or rely on deterministic conflict resolution. [Docs](https://code.claude.com/docs/en/memory) |
| Google Gemini CLI | `~/.gemini/GEMINI.md` | Global, workspace and accessed-directory context combine; `/memory show` displays what loaded. [Docs](https://geminicli.com/docs/cli/gemini-md/) |
| Cursor | **Customize → Rules → User Rules** | No documented global rules-file path to target. Team/project rules can take priority. [Docs](https://cursor.com/docs/rules) |
| GitHub Copilot CLI | `~/.copilot/copilot-instructions.md`, or its `COPILOT_HOME` equivalent | `/instructions` shows active files. Other Copilot surfaces can use different settings. [Docs](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions) |
| OpenCode V2 | `~/.config/opencode/AGENTS.md` | Files combine; current V2 has no `CLAUDE.md` fallback. [Docs](https://opencode.ai/docs/instructions) |
| Devin Local/CLI | Dedicated `~/.devin/rules/godmode.md` | Current successor documentation differs from legacy Windsurf; confirm the actual client. [Docs](https://docs.devin.ai/cli/extensibility/rules.md) |
| Legacy Windsurf | Its global rules setting | Legacy docs give `~/.codeium/windsurf/memories/global_rules.md`; do not assume current Devin paths apply. [Docs](https://docs.windsurf.com/windsurf/cascade/memories) |
| Aider | A small conventions file registered under `read:` in `~/.aider.conf.yml` | Its filename alone does not enable loading. [Conventions](https://aider.chat/docs/usage/conventions.html), [configuration](https://aider.chat/docs/config/aider_conf.html) |
| Cline | One rule in `~/Documents/Cline/Rules` or another documented global location | Also supports `~/.agents/AGENTS.md`; that is not universal across other clients. Keep the rule enabled. [Rules](https://docs.cline.bot/customization/cline-rules), [layout](https://docs.cline.bot/getting-started/config) |
| Continue | `~/.continue/rules/`, or its `CONTINUE_GLOBAL_DIR` equivalent | Set `alwaysApply: true` for the short text; confirm it in the rules toolbar. [Rules](https://docs.continue.dev/customize/deep-dives/rules), [global root](https://github.com/continuedev/continue/blob/main/core/util/paths.ts), [directory source](https://github.com/continuedev/continue/blob/main/extensions/vscode/src/extension/VsCodeExtension.ts) |
| Roo Code | A general rule under `~/.roo/rules/` | Project rules take precedence; use general rather than mode-specific rules for all-mode discovery. [Docs](https://roocodeinc.github.io/Roo-Code/features/custom-instructions/) |

## Check or remove it

Start a new session, ask the agent to run `godmode help`, then try a task that needs a key without naming Godmode. To remove it, delete the lines between `<!-- godmode:start -->` and `<!-- godmode:end -->`, or `~/.claude/rules/godmode.md`. Your profile and keys stay where they are.
