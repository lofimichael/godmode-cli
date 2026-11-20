# Godmode CLI experience

Godmode stores profile fields and provider keys, then supplies selected keys to commands. The dashboard capture uses fictional provider and profile data.

![Godmode home](../images/current/home.png)

![Cloudflare onboarding in Godmode](../images/current/cloudflare.png)

## Native interface

Bubble Tea 2 and Lip Gloss 2 draw the welcome and guided views. Home presents the active loadout. Providers and profile fields open directly for editing, alongside Agent instructions, Switch loadout, Settings and Help. The active profile and key environment appear above each task. Switch loadout stages both choices until Use this loadout applies them to new commands. Recent loadouts lets you review and reuse any of the last five pairs.

Ctrl-K finds an action. The slash key filters providers or opens the finder from other menus. Esc returns to the parent with its selection and query. On Home, q quits and s opens Switch loadout. In a field or search box, both remain ordinary text. See the [navigation audit](NAVIGATION_AUDIT.md), [active selection contract](ACTIVE_SELECTION.md), [intro design](INTRO_DIRECTION.md) and [performance review](PERFORMANCE_REVIEW.md).

```mermaid
flowchart LR
    Terminal[Bubble Tea + Lip Gloss] -->|private operation pipe| Engine[Embedded Python file engine]
    Engine --> Profile[profile.json]
    Engine --> Keys[.env.godmode + seal.key]
    Engine --> Notes[Guarded agent-note appends]
    Direct[Direct and plain commands] --> Engine
```

The Go interface temporarily holds newly entered text. The Python engine validates it, supplies masked key previews, retains file snapshots and performs writes. It never returns a stored plaintext secret to the interface. One Python process serves each native UI session; the executable embeds its source and passes it on a descriptor separate from request input.

[Framework research](CLI_FRAMEWORKS.md) compares ten libraries across Python, Go, Rust and TypeScript. [NFO identity](NFO_DESIGN.md) records the source voice and visual choices. Complete source is available in the separate release source archive; `godmode source` prints the embedded Python engine and `godmode build-info` reports its hash and Go dependencies.

## Research

The current [navigation research](navigation-audit/research.md) compares ten CLI/TUI examples using primary sources and separates documented behavior from design inference. The [audit](NAVIGATION_AUDIT.md#cli-comparisons-and-design-inferences) explains which patterns were adopted. Earlier [framework research](CLI_FRAMEWORKS.md) remains the record of the framework choice. These comparisons are not human usability experiments or a ranking of the tools.

## Routes

```mermaid
flowchart TD
    Entry[godmode] --> Welcome[First-use intro if needed]
    Welcome --> Home[Loadout dashboard]
    Home -->|Select provider| Input
    Catalog[Provider catalog and local filter] --> Providers[Provider keys]
    Providers --> Input[Choose key and review masked edit]
    Input -->|Explicit Enter save| Providers
    Home --> Connect[Agent instructions]
    Connect --> Copy[Copy scoped note for current task]
    Connect --> Target[Choose one agent or All]
    Target --> Diff[Exact file and addition preview]
    Diff -->|Review then append| Connect
    Home -->|Select profile field| Field
    Profile[Optional profile fields]
    Profile --> Field[Edit one field]
    Field -->|Save or cancel| Origin[Calling profile or dashboard]
    Home --> Switch[Stage environment and profile]
    Switch -->|Use this loadout| Home
    Switch -->|Cancel selection| Home
    Switch --> Recent[Recent loadouts / r]
    Recent --> Pair[Review both names]
    Pair -->|Enter use| Recent
    Home --> Settings[Motion / Check local files / Update / Replay intro]
    Settings --> Confirm[Update confirmation]
    Confirm -->|Explicit update| Shell[Restore terminal before updater]
    Home --> Help[Quickstart and FAQ]
    Home -->|Exit / q / Esc| Shell
    Finder[Ctrl-K action finder] --> Destination[Selected route]
    Destination -->|Esc retains query| Finder
```

`intro` replays the welcome. On a fresh home, native `loadout` and `set NAME` also show it before their requested route. Native `profile`, `agents`, `faq` and `settings` open their sections directly. Back follows the actual navigation history. Leaving a direct entry route returns to the terminal; a provider reached through the finder returns to its query. See the audit for the complete route map and scope semantics.

Recent loadouts is available from Switch loadout, its `r` shortcut, and the action finder when history exists. It records up to five applied pairs in `ui.json`; browsing, cancellation and unselected creation do not add history. Choosing a row shows both names before Enter applies them together. A separate history-write warning does not undo an already saved active pair. See the [tested semantics](NAVIGATION_AUDIT.md#recent-setup-pairs).

Back restores provider, help, scope and agent-target identity as well as menu position. Recent entries are matched by pair, so reordered history cannot change what a detail screen means. Returning to Agent instructions after a non-agent detour reloads its plan asynchronously; an exact target is retained when available, and a refreshed file diff must be reviewed again. Missing targets and an old All preview return to Agent instructions rather than expanding the write.

## Guided tasks

| Surface | Visible content | Action and return |
| --- | --- | --- |
| Welcome | Original block lettering and account-access consequences | Enter advances only while the required statement/action fit. Esc exits without recording completion. |
| Home | Active loadout, provider inventory, profile fields and tools | Enter edits the selected item. Saved state reflects local inventory. |
| Provider keys | Names, provider uses, saved state and overflow position | / filters locally. Esc clears active filtering first. No-match Enter cannot open a provider or URL. |
| Provider key | Provider benefit, numbered steps, official destination and masked input | Ctrl-O opens the link with or without a value. Tab shows the full URL and edit details. Enter saves a valid value after the change preview fits. Esc cancels the field. |
| Multiple-key provider | Provider benefit, credential choices and saved states | Choose a field for your task. Paired credentials indicate that each field is needed. |
| Custom key | Name entry, then masked input | Name fields ignore pastes. Supported JSON values retain the existing validation path. |
| Profile | Six optional fields and existing values | Opens directly from Home. Saving a detail does not publish it. |
| Profile field | Prefilled text and explicit clear behavior | Save/unchanged/remove receipt reflects the backend result. Esc discards the draft. Return retains the field-list route. |
| Agent instructions | Copy instructions for chat or Add to agent files | Current-task copy is separate from permanent instruction-file changes. |
| Agent target choice | Detected destinations plus explicit All and Back | Choose one or all, then inspect the exact preview. Arbitrary project files are not detected. |
| Agent preview | Selected paths, additions/removals and append block | Continuous review unlocks Enter append; jumping past unseen lines does not. Width changes restart review. Append returns to Agent instructions. |
| Switch loadout | Current pair and staged environment/profile choices | Use this loadout saves both once. Back cancels the selection. Explicitly created records remain even if selection is later canceled. |
| Recent loadouts | Up to five applied environment/profile pairs | Choose a pair, review both names, then Enter uses it. Cancel preserves active state and any unapplied manual draft. |
| Settings | Motion, Check local files, Update Godmode, Replay intro | Motion persists in ui.json; command no-motion overrides do not rewrite it. Update requires confirmation before external handoff. |
| Help | Quickstart first, then connection/scope/files/source topics | Enter opens a topic; Esc returns to its list or finder origin. ? opens keyboard help from menus. |

The profile fields are `operator_name`, `business_name`, `legal_name`, `website`, `public_email`, and `business_mailing_address`. A provider instruction must still name the correct scope, account and page. Brief copy does not remove information needed for a decision.

## Commands and compatibility

| Command | Result |
| --- | --- |
| `godmode`, `godmode onboard` | Native home in a capable interactive terminal; first-use welcome when needed |
| `godmode intro` | Replay welcome |
| `godmode loadout [PROVIDER]` | Native catalog or requested provider |
| `godmode set NAME` | Native masked entry and preview |
| `godmode set NAME --stdin` | Save one key from a pipe/file through the core |
| `godmode list` | Saved key names, one per line; no values |
| `godmode run NAME... -- CMD` | Supply requested stored keys to CMD; native parent waits and relays termination signals, preserving streams and child exit status |
| `godmode run VAR=NAME -- CMD` | Supply a stored key under another environment variable name |
| `godmode profile` | Native field list |
| `godmode profile edit` | Python compatibility field menu |
| `godmode profile get FIELD` | One value; missing field exits 1 |
| `godmode profile show` | Complete profile JSON |
| `godmode profile set FIELD [--stdin]` | Python field entry or piped value |
| `godmode profile unset FIELD`, `profile path` | Remove one field; print profile path |
| `godmode agents` | Native copy/target chooser and guarded append; redirected output contains the instruction note |
| `godmode provider [SLUG]` | Catalog summary or printable provider guide |
| `godmode faq` | Native topic list; core output when plain or redirected |
| `godmode help` | Saved names/profile state and agent usage contract |
| `godmode --help`, `godmode COMMAND --help`, `godmode help COMMAND` | Command reference and command-specific help; bare help remains the agent guide |
| `godmode settings` | Native Settings in a terminal; plain/redirected output reports Motion |
| `godmode settings motion on\|off`, `settings --json` | Save Motion; inspect preference and local ui.json path |
| `godmode path`, `edit`, `migrate` | Print key-file path; open nano; verify and seal compatible legacy keys |
| `godmode source`, `build-info` | Embedded Python source; core hash, compiler and dependency metadata |
| `godmode --version` | Version only |
| `godmode init` | Compatibility alias for onboarding |

`--home DIR`, `--config-dir`, `GODMODE_HOME` and `GODMODE_CONFIG_DIR` retain their existing core selection behavior. `init --accept-disclaimer` remains a compatibility route. None of these controls expands a key's authority.

The native launcher handles guided routes only with both input and output attached to a suitable terminal. `--plain`, `GODMODE_PLAIN=1`, an empty/dumb `TERM`, and redirected operation use the Python path. In a plain terminal, Tab shows the masked edit for review and Enter saves it. The compatibility menu may advance through fields differently from the native list; it is not the native renderer without color.

## Installation and recovery

The shell installer selects a compatible native release for macOS/Linux ARM64 or x86-64, checks its SHA-256, installs the executable and updater, and opens the terminal menu on an interactive first install. Python 3.9+ remains required. Native installation needs neither Go nor pip; source builds use pinned Go 1.26.7 and vendored modules.

| Route | Behavior |
| --- | --- |
| Private release | Existing GitHub CLI login supplies repository access |
| Offline archive | `--archive PATH --checksum SHA256SUMS` verifies/installs the supplied compatible archive |
| Offline program | `--binary PATH --sha256 HEX` verifies/installs the supplied executable |
| Alternate destination | `--home DIR` selects data/executable home; `--bin-dir DIR` changes executable directory only |
| Shell integration | `--path` backs up startup files before adding the generated environment source line |
| Existing executable | Receipt identifies managed files; `--force` explicitly adopts an unknown existing program |
| Update | `godmodeup` preserves the previous executable as `godmode.previous`. Use `--loadout` to open the terminal menu afterward |
| Legacy keys | `migrate` verifies the sealed copy before replacing the compatible legacy file |
| Remove programs | [Installation](../INSTALLATION.md#uninstall) distinguishes programs from keys/profile |
| Remote machine | [Remote guide](../REMOTE.md) explains explicit selected-file copies |
| Revoke access | Revoke at the provider; deleting a local key does not revoke it |

## Completion and visual rules

The native task menu does not use a completion percentage. Business fields and unused providers are optional. `Saved` means stored locally; an appended note means the specified file changed. Neither proves provider access, agent instruction loading or successful execution. Current-task copying is its own operation and does not mark file installation complete.

The native interface uses Unicode block art, arrows, separators and bars. It currently has no complete ASCII substitution layer; use plain mode for ASCII-oriented terminals. Light/dark palettes adapt to terminal background information. `NO_COLOR=1` and `CLICOLOR=0` retain selection text and symbols without color. Motion can be saved in Settings or with `godmode settings motion off`. `--no-motion` or `GODMODE_NO_MOTION=1` overrides it for the current command; the native welcome also skips its reveal when colors are disabled. Plain mode provides static sequential output.

File previews carry meaning in text and signs, not color alone. Native keys show `+ Add` or `± Replace` with a masked assignment. Agent appends show plus-prefixed additions and a zero removal count. Ordinary field entry has no spinner or invented progress animation. Direct outputs remain complete and pipeable.

## Design boundaries

| Choice | Current decision |
| --- | --- |
| Go terminal framework | Bubble Tea and Lip Gloss are the selected default; Python retains file operations and compatibility routes |
| Responsive home | Aligned task rows; compact scope/header/footer at narrow sizes; list overflow remains visible |
| Source inspection | Embedded engine through `source`; complete matching sources and vendor tree in the separate source archive |
| Provider login/refresh | Provider tools own these operations; Godmode stores credentials |
| Full-catalog completion target | Not required; users choose the services they need |
| Agent append review | Chosen target paths and append block must be reviewed before write; task copy is separate; existing file text is preserved |
| Color versus plain mode | Distinct controls; plain mode changes interaction, not only styling |

The [0.15 verification record](UX_VERIFICATION.md) is historical. The current [navigation audit](NAVIGATION_AUDIT.md#validation-checkpoints-actually-completed) records executed candidate checks and separates frozen reviewer checkpoints from the unreleased final candidate. No public release or installation was performed by that audit.

## Verification requirements

| Area | Required checks |
| --- | --- |
| State | Empty, partial, complete, malformed store/profile, no detected agents |
| Size | Wide/narrow/short terminals, long paths, resizing during entry and agent review |
| Rendering | Light/dark, no color, no motion, native Unicode, plain ASCII, dumb terminal and redirected output |
| Entry | Typed key, complete/fragmented bracketed paste, large-paste refusal, JSON/file input, replacement and invalid values |
| Navigation | Search/no match, Escape behavior, Ctrl-C, profile return selection, multi-key checklist and direct-route exit |
| Agent changes | Exact preview, scroll gate, width-change re-review, prior note, guarded append and partial failure |
| Commands | Stable names/JSON/guides, stdin, child streams/signals/exit codes, source/build-info |
| Preservation | Existing keys/profile/instructions, terminal state, unrelated files, updater backup |

Use synthetic keys and temporary homes. Record native and compatibility checks separately. Screenshots, successful local storage and protocol tests do not prove provider permissions, paid demand or screen-reader usability. Executed results belong in the release verification record.
