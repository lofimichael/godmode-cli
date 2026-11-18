# Independent navigation audit — candidate 3

> Archived review record from 2026-11-17. Personal checkout paths are generalized. Referenced PTY captures, binaries and temporary fixtures remain session evidence and are not included here. Findings and scores describe the reviewed build, not the current candidate.

**Judgment frozen before checking the later build: 8.5/10.** I would call navigation great for the core tasks exercised here, with small friction rather than blockers. This is a bounded new-user walkthrough, not a complete quality or release verdict. No implementation source, prior audits or design documents were consulted.

Binary: `.context/navigation-audit/candidate-3/godmode`

SHA-256: `2f2a154eede10971a3e6bfe605a776d1e489e9e7027af299b900f93a11f93348`

## What worked

- The initial help and first home screen make the sequence clear: add only needed keys, connect the existing agent, then ask the agent for the desired result. Optional business information is clearly optional. Once keys and the agent note are present, the home message changes to asking the agent for the result.
- Provider search found Cloudflare quickly. Paste produced a masked pending preview; Enter saved it. The first save explicitly said “Key saved. Next: Connect agent.” Cancelling a replacement with Esc preserved the original exact synthetic value, checked through `godmode run` without printing it.
- Connecting only Codex was straightforward: choose Add to agent files, choose Codex, review the append and scroll to its end, then append. The UI gave the next step: start a new session or copy into the current task. Existing CRLF bytes and missing final newline were preserved as an exact prefix, mode remained 0600, and only one Godmode block was appended. Claude's existing file stayed byte-for-byte unchanged and no Claude rule was created.
- Business-name editing is simple and returns a visible confirmation. Saving advances the selected row to the next field. Separate business A and B profiles retained their distinct values.
- Switch setup stages the environment and business separately, showing both before “Use this setup.” Creating an item distinguishes “chosen” from “active.” Cancelling the staged switch left default/Automatic active and reopening discarded the pending pair.
- Created two empty named environments and two named business profiles using the UI. Saved a distinct synthetic Cloudflare key and business name into each. Recent setups listed exact pairs, reviewed both values before applying, and warned that running agents need new task instructions. Cancelled a recent-pair review, then reused A and B. Independent `active`, `profile get`, and `run` checks confirmed both exact pairs and their corresponding key/profile values.
- Ctrl-K action search found Settings and Help. Settings contained local setup checks, updates and intro replay. Check setup correctly described itself as local-files-only. Help explained the first-use workflow and the distinction between storage and provider verification.
- Exercised a real PTY at 80×24, 40×18 and 120×36, including live resizing in home, business fields and settings. Selection and content survived those resizes. The compact layout stayed usable; business editing, provider saving and recent-pair reuse all completed at 40×18.

## Minor friction

1. After saving a key from a filtered provider list, “Next: Connect agent” is guidance rather than an action. Esc clears the filter, then a second Esc returns home. This is consistent with the footer and never blocked me, but a direct next-step action could shorten the most common first-use path.
2. Creating a new environment or business returns to its list with the new row already marked “chosen”; another Enter is needed to return to the pair editor. The confirmation explains this, but the extra confirmation felt slightly redundant.
3. At 40 columns the masked provider preview wraps the closing part of `sealed(...)` onto another line. Long business values become ellipses and the Settings motion source becomes `command fl…`. All relevant actions remain visible; this is presentation friction rather than lost functionality.
4. The two intro cards use intentionally profane copy. It communicates consequences clearly, but its tone will not suit every new user. This did not interfere with completing any task.

## Blockers

None observed for the exercised tasks. No change of implementation was needed during this audit.

## Coverage and limits

Completed: initial help and two intro cards; initial home; provider search/save/replacement cancellation; Codex-only append and byte/mode checks; business-name edits; creation of two businesses and two environments; staged-switch cancellation; exact pair activation/reuse and cancellation; global action search; Settings and local Check setup; Help and a help answer; screen resizing across all requested sizes.

Not completed or claimed: live provider credential validation, provider websites, actual agent launch/task execution, clipboard Copy for this task, every provider/field, Copy current environment, invalid-name edge cases, delete/rename paths, installer/update execution, music/audio, plain mode, default animation, light/no-color themes, terminal restoration assertions, screen-reader accessibility, or exhaustive Back-route combinations. Motion was disabled by the isolated fixture environment. Screen captures use a terminal emulator and simple image renderer; native terminal-app visual appearance was not separately checked.

A few harness sends initially batched keystrokes across screen changes, which the CLI did not consistently carry across. I resumed with screen-by-screen events; this was not scored as a user-facing defect. The first noninteractive `--help` call inherited the normal shell environment; all interactive/verification calls used the temporary HOME and explicit CODEX_HOME/COPILOT_HOME. No ordinary credential storage was opened, no provider access was used, and no source code was changed.

Evidence: frozen `first-impressions.md`; 100 numbered text/PNG terminal frames; `actions.jsonl`; `file-verification.json`; `pair-verification-a.json`; `pair-verification-b.json`. Screenshots 003, 047 and 075 were also visually inspected. Synthetic input strings are intentionally present in the action log; no real credentials were used.
