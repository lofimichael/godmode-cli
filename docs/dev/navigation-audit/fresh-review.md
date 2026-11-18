# Independent fresh review of godmode-navigation

> Archived review record from 2026-11-17. Personal checkout paths are generalized. Referenced PTY captures, binaries and temporary fixtures remain session evidence and are not included here. Findings and scores describe the reviewed build, not the current candidate.

**Overall: 8/10.** The core utility is usable, deliberate, and visually coherent. I completed the requested tasks without source knowledge or external account access. Its strongest qualities are clear file previews, conservative changes, persistent setup state, and a predictable Back path. Its largest usability costs are repetitive setup construction, a loss of progress information in compact mode, and one reproducible mismatch between search instructions and Escape behavior.

This is a subjective usability score, not a security certification or provider-access test. No target score was supplied.

## Scope and independence

- Reviewed a copied executable at `fresh-review/godmode-navigation`; SHA256 `2910ac68d67c5dd5b45041bcd1d04426c55d578afa8f8ff7a9bb2ff37321c559`.
- Used a private temporary HOME and GODMODE_HOME below this report directory, with synthetic Codex/Claude installations and synthetic credentials only. No real key file or seal.key was opened.
- First impressions were saved before consulting the allowed terminal recording helpers. No implementation source, previous audit, or other reviewer findings were consulted.
- Exercised real PTYs at 80×24 and 40×18. Screenshots render actual captured terminal cells using the existing recorder. Initial launch used default animation; subsequent stable recordings used reduced motion. Checked representative PNGs visually.
- Did not invoke updater, browser, audio, provider APIs, or a real agent. The setup checker explicitly identified itself as local-only.
- Read-only validation confirmed Codex sentinel preservation, one appended Godmode block, untouched Claude sentinel, and no Claude rules file. Captured application output contained none of the four complete synthetic credential strings. Exit output disabled the alternate screen and bracketed paste.

## Task results

| Task | Observed result | Evidence |
| --- | --- | --- |
| Understand and start | Two intro cards lead to a home screen saying “Add a provider key, then connect your agent.” Functional purpose becomes clear at Home; first card emphasizes risk before utility. | `first-impressions.md`, `80x24-02-home.png`, `40x18-34-narrow-intro-warning.png`, `40x18-35-narrow-intro-power.png` |
| Save a provider credential | Opened GitHub guide; pasted synthetic token; saw masked Add/Replace preview and exact file destination; Enter saved; provider count and saved indicator updated. Narrow save also worked. | `80x24-06-github-guide.png`, `80x24-07-token-pasted.png`, `80x24-08-token-saved.png`, `40x18-05-narrow-key-preview.png`, `40x18-06-narrow-key-saved.png` |
| Equip one chosen agent | Detected synthetic Claude and Codex. Chose only Codex. Reviewed +9/-0 diff and appended once. Existing instructions preserved; Claude untouched. | `80x24-13-agent-files-preview.png` through `80x24-16-codex-applied.png`, `sentinel-verification.json` |
| Distinguish current task and future sessions | Copy for this task tells me to paste into the current chat. Agent-file review and success message explicitly require a new agent session, or copying for this task. Reopening Codex at 40×18 says already added. | `80x24-10-connect-agent.png`, `80x24-15-codex-preview-bottom.png`, `80x24-16-codex-applied.png`, `40x18-14-narrow-codex-already-added.png` |
| Create two business/key setups | Created alpha and beta environments and business profiles separately; each has a unique synthetic GH_TOKEN and business name. Header remained on the current pair during selection. Use this setup changed both and returned Home. | `80x24-22-environment-created.png`, `80x24-28-alpha-setup-selected.png`, `80x24-48-beta-active.png`, `80x24-58-beta-name-saved.png` |
| Switch safely and return | Cancelled staged alpha/alpha while beta/beta was active; reopening the switch reset to beta/beta. Later switched back to alpha and saw Alpha Example. At 40×18 switched to beta and saw Beta Example. | `80x24-61-alpha-environment-staged.png` through `80x24-65-setup-reopened-after-cancel.png`, `80x24-75-alpha-returned.png`, `80x24-76-alpha-business-preserved.png`, `40x18-30-narrow-beta-applied.png`, `40x18-31-narrow-beta-business-details.png` |
| Cancel a key change | Pasted a replacement, pressed Esc, returned to saved-provider list without a save notice. This establishes the observed UI behavior; original decrypted value was not independently read. | `80x24-53-replacement-pending.png`, `80x24-54-replacement-cancelled.png` |
| Find settings/help | Direct home items and action finder worked. Help answers distinguish independent key files, copies, Automatic, named businesses, new commands, and existing task scope. Local checker labels provider access as untested. | `80x24-78-settings.png`, `80x24-80-help-menu.png`, `80x24-83-setup-help.png`, `40x18-18-narrow-find-settings.png` through `40x18-23-narrow-find-return.png` |
| Return to previous work | Esc preserved Home selection, selected Help question, action-finder query, and parent-menu position. Active setup persisted after quitting and relaunching at the other size. | `80x24-85-help-return-position.png`, `80x24-86-home-return-position.png`, `40x18-23-narrow-find-return.png`, `40x18-24-narrow-return-original-home.png` |

## What works especially well

1. **State is visible where changes matter.** Business/environment header remains present throughout management. Staged selectors show new choices while the header still shows the active pair. “Chosen” and “active” are distinguishable. Explicit Use this setup is a good final action.
2. **The agent connection flow is unusually inspectable.** Choosing one agent is straightforward; exact additions and destination are visible, scrolling is required before append, existing text stays intact, and the success message explains when the instructions take effect.
3. **Provider saving is bounded.** The key is masked immediately, paste does not submit, Add versus Replace is explicit, and save status is observable. No complete synthetic credential appeared in the application capture.
4. **Navigation is compact and predictable.** Important features are on Home rather than buried in unrelated menus. Search and keyboard help are available; the action finder returns to its prior query; ordinary Back preserves menu position.
5. **Visual identity is strong without overwhelming daily screens.** Purple/cyan accents, full-width selection highlight, spacing, and colored diff markers provide hierarchy. At 80×24 the interface feels calm. The 40×18 intro reflows cleanly and the compact menus stay reachable.
6. **The local checker does not overclaim.** It says local files only and warns that the copied executable lacks an install receipt. Settings description explicitly says provider access is not tested.

## Friction and concrete improvements

### 1. Fix the no-match search Escape instruction after returning from Custom key

**Observed defect, medium priority.** At 40×18:

1. Home → `/provider` → Enter Provider keys.
2. `/openai` produces no matches.
3. Down selects Custom key; Enter opens the form.
4. Type `OPENAI_API_KEY`; Esc cancels.
5. The no-match provider list returns, still showing `/openai` and “No providers match. Esc clears the se…”.
6. Press Esc: it returns to the outer Find an action screen (`/provider`), rather than clearing the provider search.

Evidence: `40x18-46-narrow-missing-provider.png` through `40x18-51-narrow-provider-search-cleared.png`. The last filename describes my expected action; the screenshot shows the actual return to the finder. Earlier, Esc immediately from active provider search did clear it as advertised.

**Improve:** Make Esc clear a nonempty provider filter consistently, regardless of whether focus returned from a form; or change the message to reflect the current Escape behavior. This is small but undermines otherwise predictable navigation.

### 2. Keep progress and the next step on narrow Home

**Observed limitation, medium priority.** At 40×18 the Home screen drops saved-key count, agent-note count, business optionality, contextual explanation, and next action. It has several unused lines below the menu. A first-time user has no visible evidence of whether setup is complete until opening individual screens.

Evidence: compare `80x24-02-home.png` / `80x24-17-home-after-agent.png` with `40x18-02-home.png` / `40x18-07-narrow-home-after-save.png`.

**Improve:** Add one compact summary line such as “1 key · Codex connected” plus one short next step. Retain optional markers where feasible. Keep the uncluttered compact menu.

### 3. Make complete setup creation and reuse less repetitive

**Observed friction, medium priority.** I had to create the environment, select it, create a separately named business, select it, apply, then navigate separately to provider keys and business details. Switching between alpha and beta means choosing both again. The distinction is understandable, but the primary “setup” mental model does not have a reusable named pair in the UI I explored.

**Improve:** Offer “New setup” that walks through the two existing choices with an explicit review, or remember recent environment/business pairs. Preserve independent selectors for users who need recombination. No broad architecture change is needed.

### 4. Put the scope consequence next to Use this setup

**Observed clarity gap, low-to-medium priority.** Switch setup says “for new commands,” which is good. The fuller explanation that existing agent tasks keep captured scope lives in Help. Someone returning to a running agent can miss that boundary.

**Improve:** Add a short line beside the final action or its success state: “New commands use this setup. Running agent tasks keep their current setup.” The current current-task/future-session distinction elsewhere is already strong.

### 5. Explain the utility before or alongside the intro warning

**First-impression friction, low priority.** The risk statement is clear and the brand voice is deliberate, but the first card still does not explain the program’s actual job. Two Enter gates precede the useful home overview. “Enter I understand” is also slightly ambiguous as key instruction versus typed phrase.

**Improve:** Add one concrete description such as “Save provider keys locally and tell your agent how to use them.” Label the key action “Press Enter to continue.” Preserve the established tone if it is intentional.

### 6. Minor discoverability and copy polish

- Searching OpenAI yielded no guide. Custom key fallback was reachable and its draft cancelled cleanly. This is a catalog gap, not a block on storing a custom credential. A direct OpenAI guide may be useful if that provider is in scope.
- No-match fallback actions initially have no selection highlight; one Down selects Custom key. Selecting that first option automatically would make the empty state more actionable.
- “Added to 1 files” and “1 optional fields” should use singular grammar.
- Narrow Help truncates the environment/profile question even while selected; its detail heading truncates too. A shorter title such as “Environments and businesses” would improve recognition.
- I did not discover UI rename/delete actions for key environments or business profiles. If managing many setups is an intended use, expose lifecycle controls beside the lists. This is a UI discovery observation, not a claim that the CLI lacks such commands.

## Scores

| Dimension | Score | Reason |
| --- | ---: | --- |
| First-run understanding | 7/10 | Strong consequences, later functional explanation, two intro gates. |
| Navigation and reachability | 8/10 | Direct menus, useful finder, good return behavior; one Escape mismatch. |
| Copy and conceptual clarity | 8/10 | Strong current/future-session language and detailed help; setup concepts need more local explanation. |
| State visibility and deliberate changes | 9/10 | Explicit setup staging, masked previews, exact agent-file review; narrow Home loses progress. |
| Visual quality | 8/10 | Coherent color and hierarchy, clear diffs and selection, clean responsive rendering. |
| 40×18 usability | 8/10 | Core tasks remain reachable and usable; context/status removal and long copied instructions cost clarity. |
| Overall | **8/10** | Successful core tasks with focused, fixable friction. |

## Evidence limits and recorder notes

The screenshots and `.txt` screens are indexed in this directory; `80x24-pty.bin` and `40x18-pty.bin` contain application terminal output. `session.json`, `sentinel-verification.json`, and `capture-verification.json` record isolation and checks.

No production account behavior, actual credential validity, clipboard integration, updater behavior, or agent execution was tested. The long path in copy instructions is partly a consequence of this unusually deep isolated test home. I therefore do not treat its specific 32-line compact length as representative of an ordinary install.

Screens 80×24-66 through -69 resulted from a recorder burst crossing asynchronous transitions, with misleading intended-action labels. I corrected the sequence using one transition per command and do not count that as a product defect. Initial blank screens and final `1u` capture residue are recording/emulator artifacts; they are not used as UI findings. Actual exit control sequences were verified in the capture.
