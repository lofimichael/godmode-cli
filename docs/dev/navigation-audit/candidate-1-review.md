# Candidate 1 independent task review

> Archived review record from 2026-11-17. Personal checkout paths are generalized. Referenced PTY captures, binaries and temporary fixtures remain session evidence and are not included here. Findings and scores describe the reviewed build, not the current candidate.

Reviewed 2026-11-17. Overall judgment: **6/10 for the tested experience.** The standard-width navigation is materially clearer, but the 40×18 experience regresses enough to block saving a normal-length credential. I would fix that before treating this candidate as an improvement across supported sizes.

These scores are subjective review judgments, not measured user-test results: **80×24: 8/10; 40×18: 3/10; 120×36: 8/10.** The overall score gives substantial weight to being able to complete the primary task in the narrow terminal. A pleasing standard-width menu does not offset that blocked task.

## Fixed build and review conditions

- Snapshot: `candidate-1/godmode-navigation-snapshot`, copied before testing from `<checkout>/target/godmode-navigation`.
- SHA-256: `9926ce29fbe8872a56aac11872a1621cdb70607f7ffab12bf24c78dff802a2e5`.
- Version output: `godmode 0.19.2`; the hash identifies this candidate, since the version string also describes the baseline.
- Isolated HOME/GODMODE_HOME, synthetic business details, one synthetic credential, and synthetic existing Codex/Claude files. No provider link was opened, no remote credential validation occurred, and no update/install/release action ran.
- I did not read candidate implementation, design explanations, or other candidate reviews. First impressions and subsequent task results came from the snapshotted binary.
- Evidence is reconstructed PTY cell grids and CLI output. Color contrast and perceptual animation quality were not evaluated. An incremental UTF-8 decoder was added after the first capture to prevent split-byte replacement characters in the capture harness; do not treat the first splash's isolated replacement character as a product defect.

## What improved in actual use

The home screen leads with Provider keys, Connect agent, and Business details. Switch setup, Settings, Help, and Music have a visibly secondary position at 80 columns. The initial sentence explains the next task; after saving a key and adding instructions, it changes to “Ask your agent for the result you want.” This is a much clearer starting point than leading with Active setup.

Business details now opens the fields directly. The page no longer requires a Business → Edit profile detour, and its title remains Business details. Optionality and the distinction between saving and publishing are explicit. At standard width, fields and values align well and remain readable.

The provider URL is shortened at standard width, giving both GitHub instructions room. Empty provider search now says “Esc clears the search.” Custom key is named more clearly and is explained before the external issue option. A `/git` filter survived opening and canceling a credential; it also survived a successful save.

Connect agent now makes the two actual outcomes explicit: Copy for this task and Add to agent files. The file preview excludes the long task-copy section. Before full review, its footer says “PgDn review changes”; after review, it offers “Enter append.” This fixes the baseline's misleading action availability. The outcome tells users to start a new agent session or copy instructions into the current task.

Action search is useful without replacing visible navigation. Searching “business” found Business details, Switch setup, and Business profiles. Back from Business details returned to that search with the query intact. The keyboard-help overlay returned to the prior environment list without losing its selection. Settings groups secondary controls rather than keeping them all on the main task menu.

## Findings to fix

### P1 — Saving a credential is blocked at 40×18

Reproduction: open Provider keys → GitHub at 40×18; type the 29-character synthetic value `synthetic-candidate-one-value`.

The entire screen changes to:

```text
Enlarge the terminal to review the
full edit.

Esc back
```

Enter cannot save. The previous input, preview, and provider identity are no longer visible. Escape returns safely and the canceled value was not stored. This is a real primary-task failure at the requested narrow size; the baseline accepted a comparable synthetic value at the same dimensions.

Resizing the same live session to 80×24 restored the masked draft, and a later explicit Enter at 120×36 saved it. State retention is good; the layout constraint is the problem. The test does not establish the exact minimum credential length or terminal height that triggers the failure. Evidence: `09-key-save-40.txt`, `11-live-resize-and-save.txt`.

### P1 — Narrow screens allocate almost no space to the content being navigated

At 40×18:

| Screen | Initially visible task content | Visible counter |
| --- | --- | --- |
| Provider keys | GitHub and Cloudflare only | `1–2 of 18` |
| Business details | Your name only | `1–1 of 8` |
| GitHub guidance | “Visit GitHub's token page” only | `1–1 of 7` |

Several blank rows remain between content and footer. The two-line scope header, page headings, descriptive copy, and footer consume most of the remaining height. Baseline narrow showed six provider rows and four business fields; the candidate has reduced those to two and one. Counters make hidden content more discoverable, but they do not make repeatedly scrolling a one-line viewport comfortable.

The long provider URL is no longer the main cost. The layout now hides even the useful provider steps because the available content window is too small. Preserve readable spacing, but let content reclaim reserved blank space before reducing a list or guide to a single row. Evidence: `03-narrow-first-pass.txt`, `05-business-edit-40.txt`.

### P1 — The misleading configuration-permission error remains

With an existing synthetic GODMODE_HOME of mode 0755, `help` exits 2 and starts:

```text
Cannot read active.json. Repair the active selection file,
or select both --env NAME and --context NAME ...
The profile directory must be yours and mode 0700.
```

The actual cause is the directory permission, not a corrupt selection file. The relevant fact appears last after unrelated advanced recovery instructions. This is unchanged from baseline. It matters especially because help itself becomes unavailable in that state. Evidence: `state-checks.json`.

### P2 — A save notice retains obsolete navigation instructions after changing screens

After saving the synthetic key, the provider page correctly shows:

```text
Key saved. Esc home · Connect agent to use it.
```

After Escape returns home, that same notice remains, while the home footer says `Esc quit`. The same key now has two contradictory instructions on one screen. The notice also recommends Connect agent when the home state already shows two notes added and the main next-step sentence says to ask the agent for a result.

Keep portable result text across screens, but render location-specific key hints and next steps from the current screen/state. Evidence: `11-live-resize-and-save.txt`.

### P3 — Empty field submission reports a saved value that does not exist

Pressing Enter on the empty Your name field returned to Business details, advanced selection, and displayed “Saved Your name,” while the header still showed `0/6` and `profile show` returned `{}`. No unexpected value was stored, but the receipt overstates what happened. “No change” or retaining the editor would be less ambiguous.

This occurred during an exploratory traversal with an extra Enter; it is still a real input case rather than a failed capture. Evidence: `04-actions-business-80.txt`; CLI state check before the later intentional save.

### P3 — Some keyboard labels still rely on interpretation

The first-run `Enter I understand` still looks like a phrase to type, although Enter alone advances. At narrow width, the home hint becomes `↑↓ Enter · / find` and loses the move/open verbs. In the business page, the footer wraps `? keys` across lines, while “optional fields” in the title is truncated. These are secondary to the narrow viewport failures and should be assessed after the layout fix.

## Task outcomes and retained state

| Task/check | Observed outcome |
| --- | --- |
| Cancel a typed credential | Returned to the filtered provider list; `list` remained empty before an explicit later save |
| Cancel an edited business field | List still showed unset; the canceled text was not stored |
| Save a business field | `profile show` returned only `operator_name: Saved Candidate One`; menu advanced to the next field |
| Search → open → back | Provider query and action-search query were retained in tested paths |
| Narrow draft → live resize | Masked value survived 40×18 → 80×24 → 120×36 |
| Save credential after widening | `list` reported GH_TOKEN; UI called it saved, not verified or connected |
| Review then append agent note | Reported two files; existing Codex text remained an exact prefix; expected Claude rules file was created |
| Preserve unrelated agent text | Synthetic `.claude/CLAUDE.md` stayed unchanged |
| Repeat agent append route | Preview reported already added; Enter did nothing; file hashes stayed identical and each managed file had one block |
| Back from repeated agent preview | Returned to Connect agent with Add to agent files still selected |
| Help overlay → back | Returned to the prior environment list |

The task-copy action also copied the synthetic instruction block to the local clipboard and displayed a clear copy receipt. It did not claim to have appended files. I initially followed the new default Copy route while expecting the old direct file-preview route; the screen labels made the actual operation visible, and a separate traversal then tested file append correctly. Capture labels describe intended script steps in a few places, so actual titles and content are authoritative.

I found no unexpected credential/profile/agent writes in these checks. “No unexpected writes” is limited to the examined synthetic state and agent files, not a filesystem-wide trace. The rich UI remained responsive to the scripted actions; each capture allowed roughly 500 ms for output. That is an observation of no visible stalls, not a latency benchmark. I did not test provider availability, true credentials, all providers, plain interactive menus, or every context-creation case.

## Evidence map

All evidence is under `candidate-1/` beside this report:

- `snapshot.json` and `godmode-navigation-snapshot`: fixed build identity.
- `01-first-run-80.txt`, `help.txt`: first run and human CLI help.
- `02-provider-navigation-80.txt`: filter retention and provider input/cancel. The final harness traceback came from sending another key after the script had intentionally exited; it is not a product crash.
- `03-narrow-first-pass.txt`, `05-business-edit-40.txt`, `09-key-save-40.txt`: narrow regressions and business edit/save.
- `04-actions-business-80.txt`: action search, direct business route, empty submission, search restoration.
- `06-agents-80.txt`: task-copy route; `08-agent-file-append-80.txt`: review and successful append; `10-agent-repeat.txt`: repeat behavior.
- `07-wide-navigation.txt`: 120×36 lists, search-empty recovery, scope inspection, and keyboard help.
- `11-live-resize-and-save.txt`: restored draft, successful save, and stale notice on home.
- `12-settings.txt`: secondary controls and retained home selection.
- `state-checks.json`: local state/agent-file observations and directory-permission error.

The next review should first repeat the 40×18 provider and business tasks, including a long masked credential, then verify the contextual save notice. Preserve the improvements to task-oriented home navigation, filter restoration, and explicit agent-copy versus append choices while addressing those failures.
