# Independent returning-user navigation audit

> Archived review record from 2026-11-17. Personal checkout paths are generalized. Referenced PTY captures, binaries and temporary fixtures remain session evidence and are not included here. Findings and scores describe the reviewed build, not the current candidate.

Baseline: installed Godmode 0.19.2, 2026-11-17. No prior design/review/history read. Initial normal help and terminal screens preceded source access; only the PTY helper was read while auditing. The review used synthetic data under a new isolated HOME/GODMODE_HOME. No real keys were read or printed, no product source was changed during the baseline, and no release/install occurred. Opening the Update menu did invoke the updater; it reported already up to date and exited.

Overall judgment: **6.5/10 for a returning user managing two businesses.** Most operations are easy to locate and state is consistently visible. The most costly gaps are switching a pair through an immediately persisted mixed state, nonpersistent errors from external screens, and hidden overflow choices at 80x24. This is one agent's observed usability evaluation, not human-user research.

## First impressions

Saved independently in `first-impressions.md`. Main menu is compact and clear at 80x24: all nine top-level destinations fit, active Business/Keys appears just below the logo, and `s switch` is visible. `Automatic` does not explain what selects the business. `godmode help` is primarily agent-facing and only mentions active setup near the end; later `godmode --help` was much better for a human and explicitly listed env/context/use/active.

## Findings, in priority order

1. **Switching two related selections is not one transaction (observed).** In `30-switch-pair.txt` through `34-north-pair-selected.txt`, switching south-business/south to north-business/north requires entering Key environment, choosing north, then entering Business profile and choosing north-business. After the first save the header reads `Business: south-business · Keys: north`; the selection is already persisted. The header is honest, but the user cannot stage the desired pair or cancel the overall switch. Inference: another newly started command during this interval could pick a business/key combination the user did not intend as a finished setup. Fix: stage both choices on one Switch setup page, show the proposed pair, and make `Use this setup` the single save.

2. **Music failures disappear into the main menu (observed).** At 110x36, choosing Music exits the full-screen interface, prints an error, then immediately recreates the main menu with Active setup selected. The final screen is indistinguishable from a successful return. Raw `75-music-resolved-path.ansi` contains `godmode: Darunia is not linked. Run godmode music init SYNTH_FOLDER --songs TRACK_FOLDER.` but `75-music-resolved-path.txt` no longer contains it. A first attempt through macOS's /var alias similarly printed a symlink-path error and hid it. The missing local music setup is expected in the isolated profile; losing the actionable next step is the navigation defect. Fix: show the error and resumable command in a persistent Music setup/error screen.

3. **Overflow is unexplained in the Providers list at 80x24 (observed).** `37-provider-open.txt` shows thirteen named providers, with Prodigi at the bottom. `Another key`, `Open a GitHub issue`, and Back are below the visible area, with no `more` or range indicator. Searching `/gmail` reveals these actions in `47-provider-search.txt`. Doctor already has the better pattern (`1–15 of 21 · ↓ more`, `67-doctor.txt`). Fix: reserve a row for count/overflow, or make Add another key a fixed action at the top/bottom.

4. **Creation returns to different places (observed).** New environment -> Empty -> name -> Environments with new row selected (`04`–`06`, `07`–`09`). New business -> name -> Business settings with Edit profile selected (`12`–`14`, `19`–`20`). I expected both to return to their chooser and briefly navigated to the wrong place when creating the second business. Fix: choose one consistent return rule and show a clear `Created ...` result. Optional environment copy step is reasonable; return destination inconsistency is avoidable.

5. **Help / FAQ does not explain everyday navigation or scope (observed).** `63-help-faq.txt` lists seven questions about sealing, absent providers, token locations, source, network calls, releases and agent appends. None explain Automatic, environments versus businesses, switch behavior, recovering partial setup or keyboard usage. `--help` does explain command scopes. Fix: add `How do businesses and key environments work?` and a short navigation/shortcut guide; explain Automatic inline on its chooser.

6. **Update is an immediate operation, not a detail page (observed).** From main menu, Enter on Update leaves the TUI and runs the updater; `71-update-confirm.txt` shows `Godmode 0.19.2 is up to date.` and process exit 0. `Install latest` does disclose the action, so this is a consistency/predictability gap rather than a false label. Fix: an Update page can show installed version and an explicit Check/install action, and return to its prior place after completion.

## What worked

- Header showed the selected business and key environment in every normal screen, including secret entry. `godmode active --command` returned the same north/north scope. Explicit synthetic scoped runs matched the correct distinct keys for both environments (`synthetic-scope-verification.json`); no real account access was tested.
- Provider add and replacement were direct: open GitHub, paste, Enter save; open its saved row again, paste replacement, Enter. File/change preview and masked value were visible. Saved status means local storage, not verified account access.
- Interrupted Gmail setup was especially good: 1/2 status on provider list (`52`), reopening focused App password automatically (`53`), saving completed 2/2 and selected Back (`59`). Repair did not require reentering the mailbox address.
- Doctor is read-only, uses clear OK/WARN labels, supports PgDn, and gives a fully scoped agent repair command (`67`–`68`). It was honest that zero agent files contained instructions.
- Backtracking generally kept location/selection and Esc exited cleanly from main with restored terminal flags. `s switch` is a convenient main-menu shortcut; it was not available on profile screens, whose footers did not advertise it.
- 110x36 main layout remained readable (`72-wide-main.txt`); more space grows the logo and leaves substantial blank space without pushing primary destinations away.

## Navigation cost

Counts are logical key presses (text entry/paste excluded), from the stated start; rapid combined Esc sequences in the harness were excluded because terminal escape decoding can coalesce them.

| Task | Observed route | Approximate cost |
| --- | --- | --- |
| Switch both populated selections from main | s, Enter key chooser, Up+Enter north, Down+Enter business chooser, Up+Enter north-business, Esc main | 9 presses; 4 screens; mixed state after first selection |
| Create empty environment from main | Active setup, key chooser, New environment, Empty, name, create | ~7–10 presses depending current row, plus name |
| Create business from main | Business details, New business, name/create | ~8 presses plus name; returns to Business settings |
| Add first provider from main | Down+Enter Providers, Enter GitHub, paste, Enter | 4 presses + paste |
| Replace GitHub from its provider row | Enter, paste, Enter | 2 presses + paste |
| Repair partial Gmail from filtered provider row | Enter (missing field auto-selected), Enter password, paste, Enter | 3 presses + paste |
| Find FAQ from fresh main | Down x6, Enter | 7 presses; answer another Enter |
| Find Doctor from fresh main | Down x4, Enter | 5 presses; one PgDn for lower results at 80x24 |
| Find Update from fresh main | Down x5, Enter | 6 presses; immediately runs updater and exits |
| Find Music from fresh main | Down x7, Enter | 8 presses; error disappears on return in isolated setup |

## Evidence and limits

Numbered `.txt` screens reconstruct the recorded ANSI terminal stream; corresponding `.ansi` files preserve exact output. `actions.jsonl` records exact sent input and dimensions, though some early action labels reflect expected destinations rather than what actually appeared. A small custom terminal emulator was corrected for scrolling/deletion after initial harness runs. Do not treat incidental reconstructed residue/missing letters as application rendering defects; none were scored above. No browser/provider authentication, network key validation, audio playback, or actual update install was exercised. Temporary isolation was corrected to mode0700, and later to a resolved macOS path for the Music check. These harness constraints are not counted as product defects.
