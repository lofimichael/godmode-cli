# Connect your agent once

Run `godmode agents` and copy its short hint into the user instructions of each
local agent you want to use Godmode. Keep the existing text. For one project only,
put the hint in that project's existing instruction file instead. The command
prints guidance and changes no configuration.

The hint introduces a capability: when reusable operator facts or provider access
help the task, run `godmode help`. That command explains `profile get`, `provider`,
`list`, `set` and `run`. The agent reads one provider guide when needed. Facts stay
in `profile.json`, credentials stay behind the CLI, and the hint stays small across
updates. The executable must be on that agent's PATH and available on its host.

## Native locations

Checked against official documentation on 2026-11-13. These are distinct client
conventions, not a universal global `AGENTS.md` standard.

| Agent | Where to put the hint | Important detail |
| --- | --- | --- |
| OpenAI Codex | `~/.codex/AGENTS.md`, or under `CODEX_HOME` | A nonempty `AGENTS.override.md` takes its place; project files follow global instructions. [Docs](https://learn.chatgpt.com/docs/agent-configuration/agents-md) |
| Anthropic Claude Code | `~/.claude/CLAUDE.md`, or a dedicated `~/.claude/rules/godmode.md` | User and project guidance combine. Do not overwrite either or rely on deterministic conflict resolution. [Docs](https://code.claude.com/docs/en/memory) |
| Google Gemini CLI | `~/.gemini/GEMINI.md` | Global, workspace and accessed-directory context combine; `/memory show` displays what loaded. [Docs](https://geminicli.com/docs/cli/gemini-md/) |
| Cursor | **Customize → Rules → User Rules** | No documented global rules-file path to target. Team/project rules can take priority. [Docs](https://cursor.com/docs/rules) |
| GitHub Copilot CLI | `~/.copilot/copilot-instructions.md`, or its `COPILOT_HOME` equivalent | `/instructions` shows active files. Other Copilot surfaces can use different settings. [Docs](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions) |
| OpenCode V2 | `~/.config/opencode/AGENTS.md` | Files combine; current V2 has no `CLAUDE.md` fallback. [Docs](https://opencode.ai/docs/instructions) |
| Devin Local/CLI | Dedicated `~/.devin/rules/godmode.md` | Current successor documentation differs from legacy Windsurf; confirm the actual client. [Docs](https://docs.devin.ai/cli/extensibility/rules.md) |
| Legacy Windsurf | Its global rules setting | Legacy docs give `~/.codeium/windsurf/memories/global_rules.md`; do not assume current Devin paths apply. [Docs](https://docs.windsurf.com/de/windsurf/cascade/memories) |
| Aider | A small conventions file registered under `read:` in `~/.aider.conf.yml` | Its filename alone does not enable loading. [Conventions](https://aider.chat/docs/usage/conventions.html), [configuration](https://aider.chat/docs/config/aider_conf.html) |
| Cline | One rule in `~/Documents/Cline/Rules` or another documented global location | Also supports `~/.agents/AGENTS.md`; that is not universal across other clients. Keep the rule enabled. [Rules](https://docs.cline.bot/customization/cline-rules), [layout](https://docs.cline.bot/getting-started/config) |
| Continue | `~/.continue/rules/`, or its `CONTINUE_GLOBAL_DIR` equivalent | Set `alwaysApply: true` for the short discovery hint; confirm it in the rules toolbar. [Rules](https://docs.continue.dev/customize/deep-dives/rules), [global root](https://github.com/continuedev/continue/blob/main/core/util/paths.ts), [directory source](https://github.com/continuedev/continue/blob/main/extensions/vscode/src/extension/VsCodeExtension.ts) |
| Roo Code | A general rule under `~/.roo/rules/` | Project rules take precedence; use general rather than mode-specific rules for all-mode discovery. [Docs](https://roocodeinc.github.io/Roo-Code/features/custom-instructions/) |

After adding the hint, start a fresh session. Ask the agent to identify its active
instructions and run `godmode help`. Check that an existing harmless project rule
still applies. Then try a relevant request without naming Godmode. This verifies
your client/version and workflow; installing a hint cannot guarantee model behavior.
To remove the integration, remove only the hint you added. Your facts and keys stay
where they are.

## Keep the layers simple

The task supplies the objective and authority. Existing organization, user and
project instructions retain their native meaning. The Godmode hint introduces the
utility; its help explains mechanics; the selected provider guide explains access
and recovery. Profile values supply data. A saved credential supplies possible
technical access, not a new instruction or authorization.

Avoid copying a whole operating playbook into every agent. Godmode's standalone
CLI imposes no infrastructure choice, product journal, host, publishing workflow or
mandatory skills. Existing private playbooks remain optional, separately selected
guidance. A plain sentence deferring to existing rules expresses intent; it does
not create an enforced cross-agent precedence system.

Use a prose hint, not a universal `@path` include: import syntax and allowed paths
differ by client. Do not replace an existing global file with a symlink or change
its project-discovery settings just for Godmode. Keep profile data out of always
loaded instructions.

Native skills can be a future optional discovery adapter. MCP can be useful for a
client without shell access, but is unnecessary for the current CLI. Neither is
required to use Godmode. See the [research and tradeoffs](AGENT_RESEARCH.md), including
the limitations of empirical instruction-file studies.
