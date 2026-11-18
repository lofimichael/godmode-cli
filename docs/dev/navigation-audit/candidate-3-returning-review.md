# Candidate 3 returning-user and copy review

> Archived review record from 2026-11-17. Personal checkout paths are generalized. Referenced PTY captures, binaries and temporary fixtures remain session evidence and are not included here. Findings and scores describe the reviewed build, not the current candidate.

Reviewed 2026-11-17, independently through the binary with isolated synthetic HOME/GODMODE_HOME. No source, other final review, real credential, provider, browser, updater, or product edit was used.

Candidate 3 identity: `.context/navigation-audit/candidate-3/godmode`, SHA-256 `2f2a154eede10971a3e6bfe605a776d1e489e9e7027af299b900f93a11f93348`. It reports v0.19.2. This section judges that snapshot only. The final-build checkpoint below, if present, has a different hash and does not rewrite this evidence.

## Judgment on Candidate 3

**8/10 overall. The main setup and returning-user paths are strong; one reproduced Back-navigation defect keeps this snapshot from feeling consistently great.** At 40×18, 80×24, and 120×36 the reviewed main tasks are clear and usable. The remaining Back defect changes which provider the reader is looking at after a detour, which is more significant than visual polish.

The earlier narrow failures did not return. GitHub's instructions, masked value, destination, and save control fit 40×18. Eleven provider rows are visible. Compact home now communicates both counts and the next action, instead of requiring the user to infer progress from menu labels alone. It updates from adding keys, to connecting an agent, to asking the agent for a result.

## Candidate 2 findings verified as fixed

- First run says **“Enter to continue”** and **“Enter to open Godmode.”** It no longer resembles a phrase the user must type.
- After the first key save, the notice says **“Key saved. Next: Connect agent.”** After the Codex note exists, a returning-user save says **“Saved GH_TOKEN.”** It no longer repeats an already-completed connection step or contradicts Escape on home.
- A Codex-only append says **“Added to 1 file.”** Singular grammar is correct.
- The targeted file preview no longer includes the unrelated `agents --print` command. Its first useful content is the actual changed path and addition.
- Compact home shows **1 saved / 1 added** and “Ask your agent for what you want.” The counts and next step fit the narrow layout without shrinking the provider/task content into a one-row viewport.

Targeted append again succeeded at 40×18, with the review hint changing to Enter append only after the content was traversed. The long binary-path line in this test's note is an artifact of running a fixed build from the audit directory; it is not treated as the normal installed path. Existing synthetic Codex text was retained; Claude was not the selected target.

## Recent setup pairs

Created synthetic empty environments `work` and `sandbox`, business contexts `consulting` and `shop`, and saved the pairs through the CLI. No provider account or real key was involved.

At 40×18, Recent setups clearly shows **keys / business** and the complete pairs. Enter first opens a review that names both values and explains the effect on new commands/running agents. Opening that review did not change `godmode active`. A further explicit Enter applied `work / consulting`; CLI inspection confirmed both values changed together. The same list is clear at 120×36. Escape from Recent setups returned to Switch setup.

This is a useful returning-user shortcut with an inspectable scope change. It is not an invisible switch disguised as browsing. There is one review step before activation, but the step is short and explains precisely what changes.

## Reproduced remaining failures in this snapshot

### P2 — Back returns to the wrong provider after an action-search detour

At 80×24:

1. Open Stripe's key list; it shows its four expected key choices.
2. Press Ctrl-K, search GitHub, and open the GitHub token editor.
3. Escape returns to the GitHub action-search result.
4. Escape again should return to Stripe's prior key list.

Instead, it returns to a **GitHub 1/1 keys saved** list. The screen location returns, but the provider identity does not. No value was entered or saved in the detour. This is an actual wrong-context return, not a suggested or source-inferred problem. Evidence: `candidate-3-cli-patterns/07-provider-back-detour-80.txt`.

### P3 — A help topic is truncated before the second concept is identifiable

The 40-column Help menu shows **“What are key environments and busin…”**. The rest of that menu fits. A shorter topic name would be easier to scan without entering it. Evidence: `candidate-3-cli-patterns/08-help-menu40.txt`.

No credit is assigned here to the separately announced but unpublished fixes for these issues. They require testing against a later binary.

## Evidence and limits

Evidence for this snapshot is in `candidate-3-cli-patterns/`: `snapshot.json`; `01-first-key-40.txt`; `02-targeted-append-40.txt`; `03-recent-first-80.txt`; `04-returning-save-40.txt`; `05-recent-pair-40.txt`; `06-recent-wide-120.txt`; `07-provider-back-detour-80.txt`; `08-help-menu40.txt`; `09-recent-apply-40.txt`; and CLI scope receipts.

Terminal cell grids establish words, wrapping, ordering, and navigation outcomes. This review did not assess color contrast, assistive technology, every provider, or network authorization. Responsiveness was good during the exercised actions, but no latency benchmark was performed. The overall judgment reflects actual tested flows rather than a target score.
