# Navigation audit

This is a historical navigation audit. Its frozen reviews and screenshots describe
the candidates tested at the time, including the since-removed Music menu.
Current command and menu behavior is described in [CLI experience](CLI_EXPERIENCE.md).

Date: 2026-11-17. Status: **reviewed source candidate; unreleased**. No public release or installation was performed during the audit phase. The subsequent requested [local installation and test run](NAVIGATION_LOCAL_INSTALL.md) is recorded separately. Both final reviewer checkpoints are complete; their scores and coverage are recorded below.

This work reorganizes the existing local credential/profile editor around three tasks: save a provider key, give an existing agent instructions, and edit optional business details. It keeps the Go/Bubble Tea interface, embedded Python file engine, file formats, source-available licensing, provider-login boundary, and distribution model. It does not establish provider access or turn Godmode into an agent runner.

## Evidence and review method

The [durable review records](navigation-audit/README.md) contain independent CLI research, frozen baseline observations, three candidate checkpoints and independent fresh walkthroughs. Reviewers began with the executable and normal help, recorded first impressions before reading implementation/design material, and used temporary homes with synthetic values. They were AI agents, not recruited human participants. Their ratings are subjective assessments of the tasks and terminal sizes stated in each report.

| Review checkpoint | Recorded judgment | Interpretation |
| --- | --- | --- |
| [First-use baseline](navigation-audit/baseline-first-use.md) | 6/10 | Local saves and previews worked; setup sequence and next action required discovery |
| [Returning-user baseline](navigation-audit/baseline-returning.md) | 6.5/10 | Scope stayed visible, but switching a business/environment pair persisted an intermediate combination |
| [Copy/layout baseline](navigation-audit/baseline-copy.md) | No numeric rating | Concrete copy, routing, overflow and narrow-screen findings |
| [Candidate 1](navigation-audit/candidate-1-review.md) | Overall 6/10; 80×24 and 120×36: 8/10; 40×18: 3/10 | Improved standard-width navigation did not compensate for a blocked narrow credential save |
| [Candidate 2](navigation-audit/candidate-2-review.md) | 8/10 overall | No blocker in exercised local key/profile/targeted-append tasks at 40×18, 80×24 and 120×36; contextual copy findings remained |
| [Independent fresh walkthrough](navigation-audit/fresh-review.md) | 8/10 overall | Completed two-business and selected-agent tasks at 80×24 and 40×18; found search-Escape and repeated-switching friction |
| [Candidate 3 fresh reviewer](navigation-audit/candidate-3-fresh-review.md) | 8.5/10 | Called the exercised core navigation great; no blocker in the reviewed tasks, with specific coverage limits |
| [Candidate 3 returning/copy reviewer](navigation-audit/candidate-3-returning-review.md) | 8/10 | Verified narrow/receipt/recent-pair improvements; reproduced wrong-provider Back context and a truncated Help title |
| [Final fresh checkpoint](navigation-audit/final-fresh-checkpoint.md) | 8.5/10 retained | Great for exercised core tasks; repeated saves, targeted append, exact pair reuse and Back detours on the final hash; no blockers |
| [Final returning/copy checkpoint](navigation-audit/final-returning-review.md) | 9/10 | Great for exercised setup/returning flows; independently verified corrected provider/FAQ context, regenerated task copy and narrow-screen copy; no blockers |

Candidate 1 was snapshotted before testing. Its SHA-256 is `9926ce29fbe8872a56aac11872a1621cdb70607f7ffab12bf24c78dff802a2e5`. It reported version `0.19.2`, as did the installed baseline; the version string alone cannot identify these unreleased builds. Later fixes and regression runs are separate checkpoints, not reasons to rewrite that review. Candidate 2 used SHA-256 `eeb513a0a6c3285889a8a376b1fdc2ef62afa038bb8b4bff6cdc7a01b0671912`; the fresh walkthrough used `2910ac68d67c5dd5b45041bcd1d04426c55d578afa8f8ff7a9bb2ff37321c559`. Both Candidate 3 reviews used `2f2a154eede10971a3e6bfe605a776d1e489e9e7027af299b900f93a11f93348`, before the final FAQ/history-restoration fixes.

The final frozen source candidate has SHA-256 **`0da6fa2c7384285accffb7540fd87686818783a8d90e096324adaa163307e9e9`**, verified from the session artifact. This identifies the binary used for the final native regression run and capture set. Earlier reviewer scores describe their own hashes; do not silently transfer them to a later build. The binary, raw captures and temporary fixtures are not checked into this record.

Only selected Markdown reports are retained in this directory. Raw ANSI streams, binaries, synthetic credential stores, clipboard content, screenshots and temporary-home inventories are not durable repository records here. Historical capture filenames in the archived reports identify the session evidence available during review; they are not download promises.

## Current route map

```text
Home
  Provider keys
    / filters the provider list
    Provider -> choose key if needed -> guidance + masked edit -> Enter save
    Custom key -> key name -> masked edit
  Connect agent
    Copy for this task -> scoped note -> copy -> paste into an existing chat
    Add to agent files -> one detected agent OR All detected agents
      -> exact file/addition preview -> continuous review -> Enter append
      -> Connect agent with receipt
  Business details -> optional fields -> edit one field -> save/unchanged/remove
  Switch setup
    Key environment -> inspect / choose / explicitly create
    Business profile -> inspect / choose / explicitly create
    Use this setup -> save the complete pair once -> parent
    Recent setups / r -> choose a remembered pair -> review both names
      -> Enter use -> save pair -> return to recent list with applied pair focused
    Back -> discard staged selection
  Settings
    Motion -> persist local preference
    Check setup -> local diagnostics
    Update Godmode -> review confirmation -> updater after terminal restoration
    Replay intro -> intro -> Settings
  Help -> How do I start? / connection / scope / checks / files / source
  Exit -> terminal

From menus: Ctrl-K opens Find an action; / does the same outside Provider keys.
? opens keyboard help. Esc returns to the actual entry point with focus/query.
```

The action finder supplements visible routes. It can open a provider directly, the business fields, environment/profile lists, setup switching, Recent setups when history exists, Settings, checks or help. It searches action/provider metadata, not secret values. A result reached through the finder returns to that finder and its query, rather than an assumed home page.

Direct `setup PROVIDER`, `set NAME`, `profile`, `agents`, `faq` and `settings` remain useful entry points. Bare `godmode help` remains the agent contract. `godmode --help`, `godmode COMMAND --help` and `godmode help COMMAND` serve people looking for command help. Plain/redirected `settings` reports Motion; `settings motion on|off` changes it and `settings --json` exposes the preference and path.

## Observed problem → implemented change

“Implemented” below means present in the candidate source. Tests and independent review evidence are identified separately; a source change is not a substitute for a completed final walkthrough.

| Observed problem | Implemented change | Evidence / remaining boundary |
| --- | --- | --- |
| First-use focus on Active setup looked like a prerequisite | Home starts with Provider keys, Connect agent and Business details. Empty setup focuses keys; a saved key with no note points toward the agent task. | First-use baseline; candidate review observed the clearer order. No enforced completion score. |
| Business details required Business → Edit profile → Profile | Home and finder open the field list directly; optionality is explicit. | Candidate review observed the removed detour; Go parent/focus tests cover it. |
| Selecting two related scopes saved an intermediate mixed pair | Switch setup stages both choices, then calls one `selection_save(environment, context)` operation. | Go and native PTY checks observe no saved change during staging/cancellation and one complete pair after apply. |
| Environment/business creation returned inconsistently | Creation from a picker returns to the relevant selection flow. Creating inside Switch setup leaves the current pair unchanged. | Go staged-creation and native copy/business tests. Created records survive a later canceled selection. |
| Search and detail backtracking could lose the entry point or restore another provider/target under the original page | Navigation history retains the parent, row, query and nonsecret provider/help/scope/target identifiers. Recent entries are matched by complete pair rather than old list index. | Candidate 3 independently reproduced the wrong-provider return. Final Go tests cover finder, filtered-provider, nested-help/scope, recent-reorder and async restoration. History excludes inputs, key plans and credential previews. |
| Returning to an agent page after setup selection reused an invalidated plan or another target | Returns from non-agent detours reload the plan off the input loop. A single target remains exact; missing targets and a refreshed old All preview return to Connect agent. Diff review restarts. | Tests cover changed and unchanged pair application, fresh copied scope, nested agent choices, missing targets, read failures, review gating and render/resize during readback. Applied scope is never rolled back by a failed plan read. |
| q/s/? shortcuts intercepted text in a provider filter | Search/edit handlers keep printable characters as text. Menu shortcuts apply outside text entry. | Regression types `qs?/` in provider/action search and key/profile/name inputs. |
| File append implicitly covered all detected agents | Connect agent now offers a target chooser: one agent or an explicit All choice. | Native Codex-only append leaves detected Claude files untouched; backend validates selected paths against the reviewed plan. |
| File preview included an unrelated task-copy block | Current-task copy has its own screen. File review shows selected destinations and the append block. | Candidate review observed the separation; copying/reading a task note cannot unlock file append. |
| Footer advertised append before review was complete | It offers review first, and Enter append only after the preview has been traversed. | Go tests retain the no-jump review gate and width-change boundary. |
| Agent setup ended without a useful next step | Copy and append receipts describe the completed action and the next use: paste into a running chat or start a fresh session. | Candidate review and native append/copy-route tests. Agent execution remains unverified. |
| No detected global folder left a vague manual path | Copy for this task works without detected files; help states that project instructions are not detected and agents are not installed. | Scope clarified rather than claiming project integration was implemented. |
| `help` addressed an agent without an early human route | Early interactive/reference pointers; task-first human usage; first FAQ is How do I start?; conventional `help COMMAND`. | Focused Python tests preserve the old guide and ensure static help does not need saved-setup resolution. |
| Doctor/Update competed with primary tasks; Update ran immediately | Settings groups Motion, Check setup, Update confirmation and Replay intro. | Native checks reach local diagnostics and verify the updater starts only after confirmation and terminal restoration. No update installation was performed. |
| Narrow lists hid overflow and provider URLs dominated guidance | Lists/documents show position/overflow; provider links are shortened in the main view, with detail available separately. Compact layout reduces header/footer cost. | Baseline and Candidate 1 identified different narrow failures; later 40×18 native save regression passes. Candidate 2 and the fresh review completed narrow tasks; their remaining copy/status findings remain in the frozen reports. |
| Candidate 1 could not save a normal credential at 40×18 | Compact scope/status, input preview and footer allocation restore usable edit space. | Native PTY test saves an exact synthetic GitHub value at 40×18 only after Enter; too-small-view refusal remains tested. This does not prove every input/size combination. |
| A persistent receipt said Esc home after returning home, or recommended connecting an already configured agent | The Escape instruction is removed; the key-save next step is conditional on whether an agent note is already present. | Candidate 2 confirmed the Escape fix and identified the second issue; Candidate 3 independently verified the state-aware next step. |
| Empty profile submission said Saved despite no change | The backend returns whether a write changed data; UI distinguishes Saved, Unchanged and Removed. | Candidate 2 observed Unchanged for blank submission and correct cancel/save outcomes; backend change receipts and native field tests cover the implementation. |
| Directory permissions were misreported as corrupt active.json | Directory-specific errors retain their actual cause and repair path instead of the generic selection-file wrapper. | Candidate 2 observed the specific directory/mode repair message and usable human help with an unsafe directory mode. |
| Music setup errors vanished when home reopened | A failing external music command leaves its error visible in the restored terminal. | Launcher change; no successful audio playback was exercised in this navigation audit. |
| Intro action hints could be read as phrases to type | Hints now say Enter to continue/open Godmode/finish. | Candidate 3 independently verified the shorter Enter instructions; historical reviews retain the older wording they saw. |
| Repeated daily switching required both selectors | Recent setups recalls complete pairs, with a review before applying one. | Both Candidate 3 reviews exercised pair review and reuse. Focused bridge, settings, selection and Go tests cover failure boundaries below. |
| Returning from Custom key left a provider filter whose Esc hint did not match behavior | Esc clears any nonempty provider filter before returning to its parent, including after a canceled form. | Fresh review reproduction; final native and navigation regression runs include the corrected return behavior. |
| Single-file receipt grammar and an unrelated task-copy command crowded the append preview | Singular/plural receipt uses the count; file preview omits the task-copy command. | Candidate 2 findings; Candidate 3 verified the fixes, and updated native receipt assertions pass on the final binary. |
| Compact Home dropped inventory and the next step | A short status/count and context-sensitive next step remain at 40 columns. | Candidate 3 returning review observed the compact state changing after key save and agent append. |
| The scope Help title hid its second concept at 40 columns | The topic is now Environments and businesses. | Candidate 3 recorded the longer title; the final candidate contains the shorter title. |

### Recent setup pairs

Recent setups is implemented and covered by focused tests. The Switch setup menu and its `r` shortcut open a picker; the action finder also exposes it when history exists. Choosing a row shows its key environment and business profile. Enter applies the reviewed complete pair through the same atomic selection operation, then returns to the recent list with that pair focused. Browsing and cancellation leave active selection unchanged; canceling the recent picker also preserves any unapplied manual draft in Switch setup.

The optional nonsecret `ui.json` stores at most five unique pairs in most-recently-used order: the newly applied pair, the previous active pair, then existing history, with duplicates removed. This is history of used selections, not a new named-preset model. Unselected creation, inspection, drafts and failed selection do not add history. Automatic remains distinct from a business literally named `default`. The CLI history tests also ensure a shell override is not mistaken for the previous saved pair.

The active pair and optional history are separate writes. Active selection is validated and saved first. If `ui.json` cannot be read or safely updated, the selected pair stays applied and an explicit warning reports that recent setups were not updated; the existing preferences file is preserved. A history warning is not reported as a failed selection. Invalid history does not hide a valid Motion preference. Normal updates preserve Motion and unknown preference fields, reject malformed/unsafe files, do not open or unseal keys, and avoid an unnecessary rewrite when history is already unchanged.

Go tests cover menu/shortcut/finder entry, review-before-use, cancel, reordered history, missing selected resources, Automatic versus named default, preference preservation and nonfatal history warnings. Python checkpoints report 30 bridge, 8 settings and 21 active-selection tests passing. These are local behavior checks, not provider-access validation.

## CLI comparisons and design inferences

The [research record](navigation-audit/research.md) compares ten tools using official manuals/project-owned repositories. These are documented patterns, not a benchmark ranking or evidence that the tools themselves were exercised. The selected primary pages were reopened while preparing this audit on 2026-11-17; moving documentation can change later.

| Example and primary source | Documented pattern | Inference applied to Godmode |
| --- | --- | --- |
| [GitHub CLI login](https://cli.github.com/manual/gh_auth_login) | Interactive login and a token-from-stdin route coexist. | Keep guided entry and direct commands; do not borrow authentication-success language for merely storing a key. |
| [uv help](https://docs.astral.sh/uv/getting-started/help/) | Command help has both `--help` and `help COMMAND` forms. | Make conventional help work while retaining Godmode's existing bare agent guide. |
| [rustup profiles](https://rust-lang.github.io/rustup/concepts/profiles.html) | Recommended defaults provide a useful subset; additional components can be added later. | One needed provider is a useful start. Optional fields/providers are not unfinished mandatory setup. |
| [npm init](https://docs.npmjs.com/cli/v12/commands/npm-init/) | Bare init derives defaults from existing package data and preserves existing values. Named initializers have different behavior. | Prefill/reuse existing state and preserve agent files. This analogy does not prove byte preservation; local append tests do. |
| [Docker contexts](https://docs.docker.com/engine/manage-resources/contexts/) | List, inspect, create and use are distinct operations; current scope is visible. | Inspecting a scope must not activate it. Make the final Use action explicit. |
| [kubectl context organization](https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/) | A context expands to cluster, namespace and user; current context and overrides matter. | Explain exactly what an environment/profile selects and show the effective pair. Do not import kubeconfig's merge complexity. |
| [lazygit searching](https://github.com/jesseduffield/lazygit/blob/master/docs/Searching.md) | Local views distinguish filtering from searching; menus can filter by typed text. | Separate provider filtering from finding actions, and retain the query when returning. |
| [fzf preview](https://github.com/junegunn/fzf#preview-window) | A focused selection can show a preview; its external preview command is a separate mechanism. | Preview structured metadata and exact additions. Godmode does not need arbitrary shell preview execution. |
| [k9s commands](https://k9scli.io/topics/commands/) | Visible keyboard help coexists with direct jump commands and filtering. | Add discoverable shortcuts and an action finder without replacing the small task menu. |
| [rclone config](https://rclone.org/commands/rclone_config/) | Interactive configuration has direct create/update/file-oriented equivalents. | Keep this a small local configuration utility, with inspectable files and automation routes. |

The supporting [Command Line Interface Guidelines](https://clig.dev/) are authored design advice, not experimental evidence. Charm's [Huh](https://github.com/charmbracelet/huh) and [Lip Gloss](https://github.com/charmbracelet/lipgloss) provide interaction/layout mechanisms; they cannot determine whether the resulting hierarchy is understandable. No framework replacement was needed for these changes.

## Copy and display principles

1. Name the task before the storage mechanism. Provider keys, Connect agent and Business details are the primary jobs. Introduce environments/contexts where a user chooses scope, with an explanation of Automatic.
2. Describe the action that actually happened. Saved is local storage; appended is a bounded file change; copied is clipboard delivery. None means provider access works or an agent has loaded its instructions.
3. State optionality without a completion percentage. Business facts and unused providers may remain empty. A count is inventory, not permission or readiness.
4. Keep exact targets and changes visible at a write boundary. Technical names, paths and masked assignments belong in a review. Large URLs, repeated task-note text and long success placeholders should not crowd out that review.
5. Keep move/open/back/quit distinctions consistent. Avoid mnemonic-only destinations. Printable shortcuts must not hijack text entry; Esc first dismisses the current filter/detail/edit layer.
6. Reserve space for the task, not decorative chrome. At narrow sizes, reduce optional descriptions and scope-header cost before turning a useful list into a one-row window. Keep overflow and the exit route visible. Too-small views still refuse an unreviewable write.
7. Preserve meaning without color or motion. `+`, removal counts, status words and focus markers carry meaning. Plain mode changes the interaction; it is not just a color setting. Human screen-reader testing remains outstanding.
8. Do not let the brand intro stand in for orientation. Its voice and two-stage structure remain. The task menu, first FAQ and command help must explain what to do after the intro.

## State, cancellation and write boundaries

### Keys and fields

A complete bracketed paste is input data, including its line endings. It never submits by itself. Keys stay masked while pending and in receipts; stored plaintext values are not returned to the Go interface. The full edit/review area must fit before save. Escape abandons an unsubmitted draft. Direct `set NAME` exits after its explicit save; provider editing returns to its actual list/finder origin.

Escape can cancel a read-only validation and invalidate its late response. Once a write has been dispatched, the UI prevents duplicate Enter submissions and does not present Escape as a rollback. Ctrl-C/Ctrl-D can exit promptly, but an operation already committed is not undone. Late asynchronous responses must not revive canceled input or replace a newer operation. These boundaries are covered by the existing async/paste/race tests rather than inferred from a screenshot.

### Scope

A key environment is a complete independent file. Missing keys do not fall back to another environment. A copy is a snapshot. A named business profile selects optional facts; Automatic uses the selected environment's own facts.

Switch setup maintains a draft environment/context pair. The active header continues to describe the current pair until Use this setup succeeds. Its backend operation validates the complete pair before saving once and invalidates scope-bound previews after success. Creating a record inside this flow passes `select: false`; that creates a real record without activating it. Back cancels selection, not the separately confirmed creation.

Direct environment/profile pickers outside Switch setup may select immediately. CLI flags override shell selection, which overrides saved selection. Existing processes and explicitly scoped agent tasks keep their captured selection. This is a scoped-command contract, not a guarantee that an unscoped external process will ignore later defaults.

### Navigation history

History contains page identifiers, menu selection, query and nonsecret context identifiers. It excludes input text, credential plans and masked or unmasked key previews. A restored provider menu resolves its provider identity against current definitions; FAQ and scope details restore their own context. Recent details resolve the previously reviewed complete pair even if the list reordered; a removed pair returns to the picker instead of silently presenting another pair.

Agent history needs an additional boundary: the backend invalidates previews whenever a setup is applied, including reapplying the same names. A return from a non-agent detour or a replaced plan reloads agent instructions asynchronously. Existing selected paths are matched exactly, and a refreshed diff starts a new review. A missing target, failed read or refreshed old All preview returns to Connect agent; it never broadens a single-target selection. A plan-read failure clears stale plan data and leaves the successfully applied setup intact.

### Agent instructions

Copy for this task carries the explicit selected environment/business into a running conversation. Add to agent files is separate: choose a detected destination or All, inspect the exact paths/additions, traverse the preview, then append. Looking at the task-copy text does not satisfy the append-review gate. A width change or return to a hidden diff restarts file review.

The Python backend holds the reviewed target snapshots. A selected-target request must name a nonempty, unique subset of exact pending paths from that plan. Unknown, duplicate, already-added or substituted paths are rejected before writes. Selecting one agent must not create or alter another agent's file. Existing text, edited Godmode blocks and unrelated files retain their preservation behavior.

This does not detect arbitrary project instruction files, install agents, launch sessions or prove that any agent followed the note. A new session is the documented route for loading saved global instructions; an existing conversation can receive the scoped task note directly.

### Settings and external handoffs

Motion uses optional nonsecret `ui.json`. Inspection does not create it. Writes use the existing ownership, permissions, snapshot, locking and atomic-replace checks; unknown fields remain. Invalid preferences produce an actionable error rather than changing keys or business data. `--no-motion`/`GODMODE_NO_MOTION` override the current command without rewriting the saved preference.

Check setup/Doctor inspects local state, not provider permissions. Update is a confirmation followed by a handoff after the terminal is restored. The tested unmanaged candidate reaches the existing install-receipt refusal rather than an installation. Architecture, licensing and network/distribution rules are unchanged by this audit.

## Validation checkpoints actually completed

These are session checkpoints, not certification of a final release. The listed results identify completed checkpoints, including the full final Python and Go regression runs. All tests used synthetic inputs and temporary homes.

| Check | Recorded result | What it establishes |
| --- | --- | --- |
| `python3 -m unittest discover -s tests -p test_experience_help.py` | 8 passed at the help-copy checkpoint | Human escape hatch, conventional help, protected agent guide, no setup reads for static help, existing local help/source checks |
| `go test ./internal/ui` | Passed after the history-restoration fix | Navigation routes, staged pair/cancel, recent pairs, query/context history, text shortcuts, exact agent targets, renewed review and existing input checks |
| `go test -race ./internal/ui` | Passed after the history-restoration fix | Includes asynchronous agent-plan readback; no race detected in the exercised schedules |
| `go test -race ./...` | Maintainer reported pass on the final source | Complete Go package/race run; not proof of every possible schedule |
| `go test ./cmd/godmode` | Passed | Native settings route, human-help fallback and existing scope/child-flag routing |
| Native CLI suite against explicit `target/godmode-navigation` | 14 passed | Agent chooser/preservation/idempotence, selected-agent-only writes, staging/apply/cancel, Settings/Update dispatch, exact 40×18 GitHub paste/save and existing input cases |
| Native input, selection and renderer suites against the same candidate path | 8 passed | Fragmented/oversized/invalid paste refusal, teardown, invalid-selection recovery, intro output-newline transport |
| Final native suite, all `test_native_*.py`, against the frozen binary above | Maintainer reported 28 passed | Includes the updated receipt checks and all native PTY suites at the final binary identity |
| Recent-history Python checks | Maintainer reported 30 bridge, 8 settings and 21 active-selection tests passed | Applied-pair history, cap/deduplication, preference preservation, safe-file handling and unchanged scope on failed selection |
| Go recent-history tests | Passed in the UI suite; focused test owner also reported pass | Picker review/apply/cancel, draft preservation, reordered history, missing resources, Automatic, history warnings |
| [Earlier backend handoff](navigation-audit/backend-validation.md) | Implementer reported 22 bridge and 17 agent-append tests after selected-target enforcement; earlier 16 selection, 11 environment and 8 context tests | Historical preservation checkpoint; newer recent-history counts above supersede the affected suite totals |
| Full Python suite against the immutable final binary above | Maintainer reported **356 passed, no skips**, in 180.306 seconds | Clean complete aggregate with the explicit candidate selected; local synthetic/test fixtures do not establish provider or agent execution |
| Vendored renderer `TestGodmode` regressions | Maintainer reported 3 passed | Existing transport/rendering regression cases |
| Shell syntax checks | Maintainer reported pass | Syntax validation of the checked scripts, not execution or installation |
| `git diff --check` | Passed at the implementation/test checkpoints | Patch whitespace check only |

Native runs explicitly set `GODMODE_TEST_NATIVE_BINARY` to the candidate and used the existing `target/demo-venv/bin/python`. The native screen assertions reconstruct terminal cells using the existing capture helper: an optimized redraw can preserve part of a word without repeating that complete word in the raw stream. A raw-substring timeout is not by itself a missing-label defect.

The 40×18 regression checks that paste alone creates no key file, Enter saves the exact synthetic GH_TOKEN, and raw synthetic secret text does not appear in captured output. It does not validate a real GitHub token, permissions or token-creation instructions. Agent tests verify local file outcomes, not agent behavior. Intro transport tests verify layout/terminal flags, not animation preference or perceptual quality.

## Local performance and visual checks

The maintainer ran 12 launches in isolated homes at 80×24 with motion off. Startup median was **177.63 ms**, maximum **200.14 ms**; the provider-menu transition median was **16.15 ms**, maximum **16.77 ms**. These measurements include the PTY/harness process startup, use one local machine, and are not universal latency guarantees or a before/after comparison. The maintainer identifies this timing checkpoint as Candidate 3, SHA-256 `2f2a154eede10971a3e6bfe605a776d1e489e9e7027af299b900f93a11f93348`, before the final FAQ/history-restoration changes. It is not a timing run of the final hash.

A local intro-frame Go microbenchmark on Apple M1 Max reported **267,692 ns/op**, **38,222 B/op**, and **1,266 allocations/op**. Rendering one frame is a different measurement from launching the application or completing a task. Neither benchmark establishes accessibility, absence of stalls in every operation, or perceived animation quality.

The final hash has a 23-screenshot capture set. The maintainer reported inspecting representative 80-column, 40-column, light, no-color, key-edit, setup-switch and agent screens. These are visual spot checks of captured terminal cells; the Markdown archive intentionally omits binaries, raw streams and screenshots. The frozen independent reviews record their own viewport and renderer limits.

## Evidence limits and final handoff

The final binary identity, both independent reviewer checkpoints and completed regression runs are recorded above. The fresh reviewer retained 8.5/10 and the returning-user reviewer gave the final build 9/10; both called the exercised navigation great and observed no blockers. These bounded assessments do not imply a second full blind first-use audit of the final hash. The archived baseline and earlier candidate judgments stay unchanged.

- **Accessibility and human usability:** not established. No recruited novice/expert study, screen-reader exercise or quantitative human time-to-completion comparison was conducted. The recorded action counts describe individual AI walkthroughs.
- **Provider and agent execution:** not established. No real credential validation, provider login, actual agent task, paid demand or production operation was proven.
- **Release/install:** not performed in this work. This remains an unreleased source candidate. Packaging, installer verification and any future release are separate work, not implied by the successful local checks.

Remaining minor friction: filtered key saves require clearing the filter before returning home; creating an already-chosen environment/business adds a confirmation; narrow masked assignments can wrap; an empty environment with an existing agent note still suggests connecting again; and the malformed-history warning lacks a repair instruction. These are recorded follow-ups, not hidden completed fixes.

No 10/10 outcome is claimed. Preserve final reviewers' actual scores, disagreements, skipped tasks and limits. A newly found failure should be fixed and rechecked or recorded as a remaining limitation, not removed from the evidence history.
