# Terminal navigation and interface-writing research

> Archived review record from 2026-11-17. Personal checkout paths are generalized. Referenced PTY captures, binaries and temporary fixtures remain session evidence and are not included here. Findings and scores describe the reviewed build, not the current candidate.

Research date: 2026-11-17. Scope: ten CLI/TUI examples, plus two supporting design references. This is independent research for a local utility that stores selected provider credentials and business details, and appends instructions to existing agent files. No Godmode implementation, earlier Godmode review, credential store, or provider account was inspected.

Evidence boundary: **Documented behavior** below comes from current official manuals or project-owned source repositories. It was not exercised locally. **Design inference** means a recommendation derived from that behavior and this utility's stated job. The examples are not a popularity ranking, usability experiment, or proof that borrowing a pattern will improve task completion. Moving documentation and repository default branches can change after this date.

## Ten concrete examples

### 1. GitHub CLI: guided setup alongside direct commands and explicit account status

**Documented behavior.** `gh auth login` defaults to a browser flow; a token can instead arrive through standard input, or an environment variable for headless use. `gh auth status` identifies the active account for each host, tests accounts, and reports authentication problems. Its current documentation also describes refresh behavior: this particular status operation is not necessarily read-only. [Login manual](https://cli.github.com/manual/gh_auth_login), [status manual](https://cli.github.com/manual/gh_auth_status).

GitHub's accessibility guide contrasts the default arrow-key/type-to-filter prompt with an alternate numbered, static prompt. It also describes text progress as an alternative to animated spinners. This is documentation evidence, not verification of the installed version's settings. [Official accessibility guide](https://accessibility.github.com/documentation/guide/cli/#configuring-accessibility-settings).

**Design inference.** Offer a guided path and a direct command to the same operation. Put identity, scope, and storage state in the status view. Do not copy gh's account-authentication language into a utility that only stores a supplied key: “Saved locally” is accurate; “Connected” requires evidence. If checking status can contact a provider or refresh something, label that action separately from local inspection. A numbered, line-oriented alternative should be available before the user must navigate a rich TUI.

### 2. uv: progressive help and explicit configuration precedence

**Documented behavior.** `uv --help` and command-level `--help` are condensed. `uv help` and `uv help <command>` are longer, and may use a pager; the guide tells readers that `q` exits it. Repeated `-v` increases diagnostic detail. [Getting help](https://docs.astral.sh/uv/getting-started/help/).

uv documents project, user, and system configuration layers, with environment and command-line overrides above persistent settings. It provides `--no-config` and `--config-file` escape hatches. [Configuration files](https://docs.astral.sh/uv/concepts/configuration-files/).

**Design inference.** A small, useful default help screen can lead to a complete reference. Each detail screen can expose one command for repeating the operation later. If several scopes really exist, show both the effective value and its source. Avoid adding layered configuration just because uv has it: a small utility may only need one readable location and an explicit target path. Show how to leave any pager or help overlay.

### 3. rustup: recommended defaults, optional customization, and scope inspection

**Documented behavior.** rustup groups components into installation profiles. The standard profile is recommended for general use; setup permits customization, and `--profile` supports an explicit choice. Components can be added later. The profile affects new toolchain installations. The official guide warns that the `complete` profile is unsuitable and often fails. [Profiles](https://rust-lang.github.io/rustup/concepts/profiles.html).

Overrides can come from a command, environment, directory setting, toolchain file, or default; `rustup show` reveals the active toolchain and `rustup override unset` removes a directory override. [Overrides](https://rust-lang.github.io/rustup/overrides.html).

**Design inference.** Let setup reach a useful stopping point with a small choice and allow later additions. “Everything” is a poor option when many entries are irrelevant or mutually awkward. Give every override an inspect path and a removal path. Use “profile” only if it names a real reusable bundle; a provider selection, business identity, and agent destination are different concepts and should not be collapsed into one ambiguous profile.

### 4. npm init: preserve existing data and let experienced users skip questions

**Documented behavior.** The current npm v12 manual distinguishes bare `npm init` from package-driven initializers. Bare init asks questions, derives defaults from existing package information, and preserves fields and values already present. `-y` skips that questionnaire. Named initializers execute a `create-*` package and can perform other work; the preservation statement does not cover every initializer. [npm init, v12](https://docs.npmjs.com/cli/v12/commands/npm-init/).

**Design inference.** Re-running setup should begin from current data, not an empty form. Distinguish blank/keep, explicit clear, and replace. For agent files, adapt the preservation intent to a stricter, inspectable append transaction: show the exact destination and addition before writing. Do not imply npm's field-preservation claim establishes byte-for-byte preservation of arbitrary text files. A skip-questions option should use explicit inputs and documented defaults; it should not silently enroll every provider or target every agent.

### 5. Docker contexts: separate listing, inspection, creation, and activation

**Documented behavior.** A Docker context has a name/description, endpoint, and TLS information. `docker context ls` lists contexts and marks the active one with an asterisk. `inspect` exposes detail. `create` creates a context without the example making it active; `use` changes the current context and reports the new name. Environment or command-line options can override the stored current context. [Docker contexts](https://docs.docker.com/engine/manage-resources/contexts/).

**Design inference.** Make browsing and selecting an item for inspection harmless. “Save,” “Use,” and “Run with” should have distinct meanings if they cause different effects. Prefer a persistent textual scope label over a color-only active marker. If the utility has no actual active-provider concept, do not invent one: the useful translation is to show the selected credential names for the pending command, and the exact agent-file target for a pending append.

### 6. kubectl contexts: define precisely what a named context includes

**Documented behavior.** A Kubernetes context groups cluster, namespace, and user under a name. kubectl normally uses the current context; `use-context` changes it, while `config view` exposes effective configuration. A `--context` option can override the current selection. The documentation describes merging and precedence rules rather than leaving the effective configuration implicit. [Organizing cluster access](https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/).

**Design inference.** When a name stands for several values, show the expansion at the point of action. Avoid a generic “Current: default” that hides identity and destination. One-off overrides are useful when the user wants a single operation to use a different scope. Do not transplant kubeconfig's merge complexity into a simple local utility; it is an example of why configuration provenance becomes necessary once layers exist.

### 7. lazygit: searchable local actions and a clear cancel/quit distinction

**Documented behavior.** `/` searches or filters the focused view. In the commit view it searches without removing neighboring commits; other views can filter. The keybindings menu and recent-repository menu filter as the user types. [Searching and filtering](https://github.com/jesseduffield/lazygit/blob/master/docs/Searching.md).

`?` opens keybindings. Escape cancels or closes the current interaction; global `q`/Ctrl-C quits. Confirmation and input panels document Enter to confirm and Escape to close/cancel. The keybindings also expose an external-editor path for configuration. [Keybindings](https://github.com/jesseduffield/lazygit/blob/master/docs/keybindings/Keybindings_en.md).

**Design inference.** Show actions relevant to the current screen, and let people find them by typing rather than requiring mnemonic recall. Name the active search mode: “Filter providers” and “Search instruction text” promise different behavior. Keep neighboring text visible when it explains a pending change. Escape should unwind the immediate layer before quitting the tool. Preserve focus and query when returning from details so repeat work does not restart at the top.

### 8. fzf: a compact searchable picker with a preview

**Documented behavior.** fzf is a general list filter. Enter accepts an item; Escape/Ctrl-C/Ctrl-G exits; multiselect uses Tab/Shift-Tab. Its optional height mode runs below the shell cursor rather than occupying the full screen. A preview pane can show information about the focused item, with configurable placement and size. The preview executes an external command; the README cautions against applying a file-specific preview globally because fzf can filter other kinds of input. [Project README](https://raw.githubusercontent.com/junegunn/fzf/master/README.md).

**Design inference.** A searchable chooser can be a small, bounded part of an ordinary CLI. Preview provider requirements, destination paths, or intended additions without turning focus into a write. Derive the preview from safe structured metadata, never from credential values or a generic shell command built from untrusted display text. Make the selected count visible in multiselect. “No matches” should retain the query and offer clearing it, rather than appearing to be an empty configuration.

### 9. k9s: expert jump commands and local escape paths

**Documented behavior.** k9s has `?` for active keyboard help, `:` commands for direct resource/context/namespace navigation, and `/` filtering. Escape exits the current view/command/filter mode; `:q` and Ctrl-C quit. Launch flags can choose a namespace, context, initial view, or read-only mode. The command table explicitly warns that context-qualified navigation changes current context; it also distinguishes a confirmed delete shortcut from a kill shortcut without confirmation. [k9s commands](https://k9scli.io/topics/commands/).

**Design inference.** A direct jump route can coexist with a visible menu, but it should not be the only way to discover destinations. Make changes of scope obvious. A credential/settings utility should not copy the unconfirmed destructive shortcut simply because an expert operational console offers it. Treat its numerous modes as a complexity warning: three primary jobs do not necessarily justify a resource-console interface.

### 10. rclone config: a configuration hub with named objects and direct equivalents

**Documented behavior.** `rclone config` opens an interactive session for creating and maintaining remotes. Separate subcommands create, update, delete, show configuration paths, and produce redacted configuration. [Config command](https://rclone.org/commands/rclone_config/).

The documented encryption menu displays current state and the currently available operations. Its top-level `q` quits configuration; in the encryption submenu `q` returns to the main menu, explicitly described in the label. [Configuration encryption](https://rclone.org/docs/#configuration-encryption).

**Design inference.** This is the closest conceptual example: small persistent named records, an interactive editor, and direct CLI operations. Keep the object list distinct from available actions. Prefer a plain “Back” label for returning to a parent instead of making the word “Quit” mean two levels of exit. Distinguish removing a local stored record from revoking the actual provider credential. A configuration-path view and redacted diagnostics are useful; avoid exposing secret-bearing “show” or “dump” behavior as an ordinary default.

## Two supporting references

### Charm: form components and layout are available mechanisms, not evidence of usability

Charm's Huh groups fields into pages, supports select/input/text fields, and offers an accessible mode that replaces rich rendering with standard prompts. [Huh README](https://github.com/charmbracelet/huh).

Lip Gloss provides padding, margins, alignment, width limits, wrapping, and color adaptation. These capabilities make deliberate spacing practical; the library does not establish an ideal screen density or a specific information architecture. [Lip Gloss README](https://github.com/charmbracelet/lipgloss).

**Design inference.** Group a small number of related fields; avoid either a giant form or a wizard that asks one trivial question per entire screen. Reserve vertical space between title, task explanation, editable area, and actions. Allow longer provider-specific guidance to wrap and scroll without hiding the input or cancel route. The grouping and spacing choices still need testing at narrow terminal widths and with long paths.

### Command Line Interface Guidelines: authored advice, not comparative experimental evidence

The authors recommend concise initial help, examples, consistent command vocabulary, human-readable errors, visible state, and prompts limited to interactive terminals. They advise an explicit noninteractive path, error messages that identify recovery, and clear exit behavior. [Command Line Interface Guidelines](https://clig.dev/).

**Design inference.** Use these as review questions rather than a rigid visual template. A local utility can remain conversational and discoverable without a permanently running dashboard. Error copy should identify the attempted action, the concrete obstacle, whether anything changed, and one next step. Keep debugging detail available separately.

## Practical design conclusions for the stated local utility

Everything in this section is a design proposal, not a claim about current Godmode behavior or a proven outcome. The precedents above support mechanisms; they do not prescribe this exact structure.

| Need | Recommended mechanism | Failure to avoid |
| --- | --- | --- |
| First run | Brief purpose statement, current local state, one immediate action, and an optional guided path | A compulsory tour requiring unrelated fields/providers before anything works |
| Return visits | Land on saved records or a small task menu; remember local view position | Replaying onboarding or re-entering completed choices |
| Primary navigation | Three recognizable jobs: provider credentials, business details, agent instructions; secondary settings/help | Organizing the home screen around internal storage engines, provider operations, or a vague control panel |
| Provider discovery | Searchable catalog, then provider-specific detail and add action | Scrolling a long catalog, or interpreting catalog presence as a saved/working credential |
| Expert use | Stable direct subcommands for the same operations; task-specific help and examples | Rich UI as the only path; hidden shortcut-only destinations |
| Scope | Show current record, local storage scope, and exact pending destination when relevant | “Default,” “active,” or “profile” without explaining what that selection changes |
| Status | Separate “Selected,” “Saved locally,” “Not checked,” and independently verified outcomes | Green checkmarks that conflate selection, storage, provider authorization, and successful execution |
| Search | Local list filter plus a separately labeled action/help search if needed | One unlabeled global search mixing provider records, actions, secret values, and documentation |
| Back/cancel/quit | Escape dismisses the current layer; visible Back returns to the parent; explicit Quit leaves the tool | Escape silently commits, a Back button that quits, or character shortcuts firing while typing |
| Editing | Prefill existing data; separate keep/clear/replace; maintain draft until an explicit save | Blank input unexpectedly deleting an existing value; selection itself saving |
| Agent appends | Preview exact target paths and addition/diff, then apply the bounded change and report the result | Broad “Install integration” copy concealing which existing files will be touched |
| Errors | State action, cause, write outcome, and recovery; keep user input available | Stack traces as primary copy, generic “Failed,” or declaring a whole task saved after a partial write |
| Presentation | Left-aligned task title; short purpose text; space before fields and actions; limited visible hints | Every item squeezed onto one dense line; decorative boxes consuming the small viewport |
| Automation/accessibility | No prompts without an interactive input; plain text/numbered mode; machine-readable output where needed | Redraw-only output, color-only state, or unattended processes waiting indefinitely for a choice |

### Proposed navigation contract

Use the smallest hierarchy that keeps different decisions distinct:

```text
Home / task menu
  Provider credentials -> saved records / find a provider -> detail -> add or update
  Business details      -> current values -> edit -> save
  Agent instructions    -> choose target -> preview additions -> apply -> result
  Help / settings       -> specific topic or setting
```

This does not require a full-screen TUI. A short menu, inline prompts, and direct commands could implement the same contract. Search is useful when the catalog is large; it should not become another obligatory layer for three main destinations. Keep Help available at the moment an unfamiliar field or consequence appears.

For draft forms, the keyboard contract should be explicit: Enter accepts a selection or submits the focused field; it applies a write only when a clearly named save/apply action is focused. Escape closes an overlay or cancels the current draft step. Back returns to the parent without writing. A quit command works outside text entry; Ctrl-C cancels promptly. If unsaved work would be discarded, make that outcome clear at the point of cancellation without turning every harmless back action into another confirmation.

### Copy examples for review, not commands to implement verbatim

| Situation | Suggested wording | Why |
| --- | --- | --- |
| No provider records | “No credentials saved. Find a provider to add one.” | Describes local state and a concrete next action |
| Stored key | “Saved locally. Provider access has not been checked.” | Separates storage from working access |
| Provider detail | “Add a credential for [provider].” then specific accepted format and intended use | Names the action before technical requirements |
| Existing value | “Leave blank to keep the current value.” with a separate clear action | Removes ambiguity before submission |
| Agent preview | “Append instructions to [path]” with exact added text and any detected existing managed block | Names target and operation before consent |
| Successful append | “Added [count] lines to [path].” only after verification | Reports the actual observed write |
| Nothing to append | “These instructions are already present. No changes made.” | Makes an idempotent outcome understandable |
| Write error | “Could not update [path]: [specific cause]. [Verified write outcome]. [Recovery action].” | Avoids claiming that nothing changed unless that is known |
| No search results | “No providers match ‘[query]’. Clear the search to see all providers.” | Distinguishes a filtered-empty list from no available data |

Do not use success styling for merely navigating, selecting a provider, or completing an unverified prerequisite. Avoid “connected,” “enabled,” “installed,” or “ready” unless each word has a documented, exercised condition. Keep technical identifiers visible when needed to choose the right record; put explanatory prose around them rather than replacing recognizable names with branding.

## Review and testing implications

The source comparison cannot settle whether users prefer an inline menu or full-screen interface, how much guidance a particular provider needs, or whether action search is worth its cost. Validate those choices with a few realistic tasks: add one credential, update it later, edit one business field, append instructions to one existing target, cancel each operation, and recover from a failed write. Use empty, partial, and already-configured states; long paths and narrow terminals; keyboard-only and plain-text use.

Check the navigation graph for reachable exits and retained state, not just whether individual screens render. Verify that help can be read without initialization; that inspecting a record does not mutate it; that back/cancel produces no write; that repeated append does not duplicate content; and that the final receipt matches the files actually changed. These are proposed acceptance criteria for later implementation review, not tests performed in this research task.
