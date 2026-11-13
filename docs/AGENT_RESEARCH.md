# Agent integration: evidence and design decision

Research snapshot: 2026-11-13. Scope: major local coding-agent conventions, shared
formats, empirical instruction-file research, and this CLI's existing behavior.
This is design evidence for maintainers; agents do not need to load it during use.

## Decision

Use one optional profile, one credential store and one executable interface. Add
one short discovery hint through each chosen agent's native user instructions.
The hint leads to current CLI help, then a selected provider guide. Keep existing
project policy separate and avoid generating personal facts into instructions.

This combines persistent discovery with a small initial context cost. It is a
design inference from the evidence below, not a measured universal optimum. A
plain CLI without a hint remains usable when the user names it; no instruction
format guarantees an agent will notice an otherwise unknown local executable.

## What the major clients actually do

The [setup table](AGENT_SETUP.md) gives the current native locations. Several
details rule out a single universal installer target or import syntax:

- Codex checks global `AGENTS.override.md` before `AGENTS.md`, then discovers
  project instructions down to the working directory. It builds the chain at
  session start and caps combined project guidance by default. A file inside
  `~/.godmode` is not automatically part of that chain.
  [OpenAI instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
- Claude combines user and project guidance; conflicts are not a dependable
  override mechanism. `@` imports are eager and support external paths with
  approval rules. Its new native `AGENTS.md` fallback is version-sensitive and
  depends on whether Claude-specific project instructions exist.
  [Anthropic memory and instructions](https://code.claude.com/docs/en/memory).
- Gemini combines global, workspace and just-in-time context. Its `@` imports can
  load files eagerly; configurable filenames do not make a new convention
  universal. Changing that setting would affect unrelated project discovery.
  [Gemini context](https://geminicli.com/docs/cli/gemini-md/).
- Cursor supports user rules in its UI, project `.mdc` rules and `AGENTS.md`.
  Referenced `@` files are read when needed, not automatically inlined. Team and
  project precedence differs from assumptions about a universal user-first stack.
  [Cursor rules](https://cursor.com/docs/rules).
- Copilot CLI combines applicable formats. Its supported automatic imports have
  path and file-type restrictions; `~/` or arbitrary absolute imports are not a
  portable way to load Godmode. CLI configuration is not proof of support in every
  Copilot surface. [Copilot CLI instructions](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions),
  [VS Code harness distinctions](https://code.visualstudio.com/docs/agents/reference/custom-instructions-reference).
- OpenCode V2 combines instructions and no longer falls back to `CLAUDE.md`.
  Configured `instructions` adds eagerly loaded files; using it for a whole utility
  manual would increase every session's context.
  [OpenCode instructions](https://opencode.ai/docs/instructions).
- Current Windsurf English documentation redirects to Devin Local/CLI, with
  different native paths from legacy Windsurf. Check the installed client before
  choosing an adapter; no migration should be inferred just from the product name.
  [Devin rules](https://docs.devin.ai/cli/extensibility/rules.md),
  [legacy Windsurf rules](https://docs.windsurf.com/de/windsurf/cascade/memories).

Therefore preservation is chiefly a content decision: Godmode explains its
mechanics and does not add competing product policies. Stating that existing rules
continue to apply expresses intent; it is not a new enforced hierarchy.

The additional clients in the setup table reinforce that conclusion. Aider needs
explicit `read:` registration for a conventions file; naming it `CONVENTIONS.md`
does not load it. Cline currently supports multiple global locations and both
`.clinerules/` and `.cline/rules/` projects. Continue has global and project rule
directories with conditional activation; its default global root was verified in
upstream source as well as documentation. Roo distinguishes global/project and
general/mode-specific rules. These are harness behaviors, independent of which
model provider the user selects inside the client. Use one appropriate source,
not duplicate hints in every compatible format. The table links the primary
documentation/source for each of these conventions.

## Mechanism comparison

| Mechanism | Discovery and detail loading | Fit today |
| --- | --- | --- |
| CLI alone | No guaranteed startup notice; explicit user mention or tool inspection | Fully supported, but fresh agents may need a reminder |
| Short user hint → CLI help | A few sentences at startup; details when relevant | Chosen default recommendation |
| Whole manual imported globally | All content whenever the native source loads | Excess duplication and conflicting-policy risk |
| Conditional native rule | Harness or model selects by description/path/manual trigger | Optional client-specific convenience; path globs poorly describe general credential needs |
| Agent Skill | Name/description initially, body after activation, resources later | Reasonable optional packaging if users want a skills catalog |
| MCP | Client discovers schemas and callable tools; decides what reaches the model | Useful for shell-less clients or typed operations when actually needed |

The [AGENTS.md format](https://agents.md/) standardizes a readable project guide,
not a universal user-directory registry. Its nearest-file convention must be
checked against each runtime's actual behavior.

[Agent Skills](https://agentskills.io/specification) standardizes a directory and
metadata. Its [client guide](https://agentskills.io/client-implementation/adding-skills-support)
recommends progressive disclosure; common `.agents/skills` paths are conventions,
not requirements of the format. A skill can contain only instructions and requires
no service. Codex supports explicit and implicit activation, but a large skill
catalog can have descriptions shortened or entries omitted from initial context.
Adding a skill does not prove reliable selection or confer authority.
[OpenAI skill behavior](https://learn.chatgpt.com/docs/build-skills).

[MCP tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
offer `tools/list`, schemas and `tools/call`, without prescribing how a client
presents them to the model. MCP does not inherently require a daemon:
[stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio)
uses a client-launched process. The reason to defer it here is the extra protocol,
implementation and client setup when shell commands already suffice. A future
adapter should expose useful operations, not dump credentials into tool results.

## What the empirical papers support—and what they do not

These papers are primary research snapshots, with different models, workloads and
evaluation methods. They do not test this utility or establish a universal rule.

| Study | Evidence | Important limit |
| --- | --- | --- |
| [On the Impact of AGENTS.md Files on the Efficiency of AI Coding Agents](https://arxiv.org/html/2601.20404v1) | 124 small PR tasks across 10 selected repositories; one Codex model. Existing guidance reduced median runtime by 28.64% and output tokens by 16.58%. | No functional correctness evaluation. Manual checking of 50 outputs ruled out obvious degenerate edits, not semantic failures. |
| [Evaluating AGENTS.md](https://arxiv.org/html/2602.11988v1) | Four agent/model combinations; 300 SWE-bench Lite and 138 AGENTbench tasks. Generated context reduced success in five of eight settings and increased average cost by 20–23%. Human guidance generally helped success while adding cost. | Python-heavy tasks, one completion per setting, and generated descriptions/tests for the new benchmark. Removing other documentation changed the benefit. Operational security and credential use were outside scope. |
| [Do Context Files Help Coding Agents?](https://arxiv.org/html/2607.27250v1) | 288 evaluated runs, two agents, 17 tasks from three repositories; no measurable correctness benefit among tested context strategies. | Small task sample and substantial detection limits. Selective retrieval also changed corpus size; injection channels differed by agent. This is not proof that guidance has no value. |
| [Toward an Evidence-Based Template for Agent Instruction Files](https://arxiv.org/html/2611.02383v1) | 3,387 files across 1,000 repositories; 16.1% of 386 examined corresponding section pairs diverged. More template coverage did not establish preserved intent. | Observational/document-generation evaluation, not a causal agent-success test. Their broad template is not evidence that this small utility needs all categories. |

The defensible inference is to keep unique, actionable knowledge—how to discover
local facts and use credentials—while avoiding copied policies and source-code
summaries the agent can already inspect. Fewer words are not automatically better;
removing the only reliable route to a credential would be harmful. Nor do papers
about repository bug fixing prove that a prose hint is superior to a native skill.

## Data, provider power and recovery

JSON is chosen for optional named facts and repeatable field edits; Markdown is
chosen for explanations. Both are plain, portable files. No template engine is
needed to substitute company names across agent configurations. Unknown facts stay
absent; unknown JSON fields survive edits for straightforward manual extension.

Provider instructions stay in one catalog embedded in the installed executable.
Broad access remains intentional. Instructions distinguish what the credential
could do, which account the consumer selects, what the user authorized, and what
was actually verified. These distinctions help an agent complete a task without
repeating onboarding or making up capabilities.

Routine token renewal belongs to official provider tools/libraries. Underlying
credential failure calls for diagnosis, official reauthorization/replacement,
`godmode set`, then a relevant verification. Saving a key does not update a
deployment or another host. See [provider guidance](PROVIDERS.md) and
[Google's credential types](GOOGLE.md) for the concrete lifecycle.

The current legacy-key selector uses credential/rules/catalog markers in the new
home. Creating a new `AGENTS.md` there could hide old keys from discovery. This
implementation creates no such file: optional `profile.json` coexists with the
legacy credential selection. Profile and provider commands also work independently
of damaged credential files.

## Validation and remaining evidence

Local automated checks cover fresh optional onboarding, real PTY field entry,
profile edits and removal, preservation of unknown data, malformed JSON, private
permissions, concurrent writes, legacy credential selection, no-write agent hints,
and noninteractive provider help. Installer/update checks cover distribution.
These establish software behavior, not model compliance or provider access.

Before promising automatic discovery for a particular client, run a fresh isolated
project with a distinctive harmless existing rule. Compare explicit Godmode use
with a native hint under three requests: unrelated work, relevant work without
naming Godmode, and explicit use. Record discovery, appropriate help/provider
loading, preservation of the project rule, and task completion. Add a skill variant
only if it is a serious alternative. Repeat across relevant client versions and
compaction boundaries. No such cross-client benchmark is claimed by this release.

“Set and forget” means one-time details, credentials and discovery setup on an
execution host. It cannot guarantee permanent provider grants, future client
compatibility or access from a cloud agent. The CLI remains a short-lived process
over explicit local files, without synchronization or a hidden runtime.
