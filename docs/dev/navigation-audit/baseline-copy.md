# Installed v0.19.2: independent copy and layout baseline

> Archived review record from 2026-11-17. Personal checkout paths are generalized. Referenced PTY captures, binaries and temporary fixtures remain session evidence and are not included here. Findings and scores describe the reviewed build, not the current candidate.

Reviewed 2026-11-17. Binary: `~/.godmode/bin/godmode`; `--version` returned `godmode 0.19.2`. This review did not use the current source candidate or other review reports.

## Method and boundaries

I began with the installed binary's normal TUI and CLI help. I exercised 80×24 and 40×18 PTYs with isolated HOME/GODMODE_HOME, synthetic business data, one synthetic credential value, and synthetic existing Codex/Claude instruction files. No provider link was opened, no provider access was checked, and no updater was run. I did not append instructions to any real agent file or change product code. Doctor did inspect the installed executable's existing updater receipt; that is distinct from the isolated configuration being reviewed.

After recording first impressions, I inspected read-only copies of `internal/ui/{view,model,input,management,intro}.go` and `internal/core/core.py` from original commit `9f5f9ee` to explain visible wording and behavior. Findings distinguish observed behavior from that source confirmation.

Captures are reconstructed terminal cell grids, not GUI screenshots. They support text, wrapping, ordering, and viewport findings; I did not evaluate color contrast. Initial captures used an unusually long macOS temporary directory. I reran important narrow views with a short home and then a resolved `/private/tmp` path. Conclusions below do not treat extra wrapping from the original long test path or `/tmp` symlink as normal-product defects. The earliest 80-column capture also predates a terminal-emulator scrolling fix; use the later resolved capture as the authoritative 80-column evidence.

## Findings, in priority order

### P1 — A permission problem is presented first as a broken active selection file

**Observed:** when GODMODE_HOME already existed with mode 0755, even `godmode help` exited 2 with:

> godmode: Cannot read active.json. Repair the active selection file, or select both --env NAME and --context NAME (--context - uses the environment profile). The profile directory must be yours and mode 0700.

The directory was a new synthetic test directory; there was no corrupt selection file. With a fresh, non-existing home, help worked. The final sentence identifies the actual permission issue, but the first two proposed remedies send the reader toward a nonexistent file or advanced scope syntax. The same failure prevents the introductory agent guide from being read.

**Source confirmation:** `selection_saved()` in committed `internal/core/core.py:1200` wraps every `Profile.read()` ValueError in this active.json message.

**Impact:** a recoverable local permissions issue looks like profile corruption and makes the proposed repair harder than the cause. Prioritize specific underlying cause and a directly relevant recovery action. This finding does not claim that every first install fails: it required a pre-existing directory with disallowed permissions.

### P1 — Narrow provider guidance spends its entire initial reading area on a URL

**Observed at 40×18 with a normal-length, tilde-rendered storage path:** GitHub entry shows “Visit GitHub's token page,” followed by five wrapped URL fragments. The actual token-creation steps are below the initial viewport. The counter reads `1–6 of 14 · ↓ more`. The lower area correctly keeps the file destination, masked addition, input, and Escape control visible.

At 80×24 the full URL still consumes four lines, but both action steps are visible. The long query string includes permission names and expiration parameters. It has far greater visual weight than the instructions the person must follow on the provider website.

**Impact:** the narrow experience asks users to scroll through implementation detail before reaching the steps that help them complete the task. A short descriptive link label, with the full URL available on demand, would retain the action while giving the steps room. This finding is about reading order, not a claim that the URL or permissions are incorrect.

### P2 — Business/profile vocabulary and routing require extra interpretation

**Observed route:** Home “Business details” → page “Business” → “Edit profile” → page “Profile” → individual field. The same feature is called business details, business, and profile across consecutive screens. “Switch business” and “New business” sit in the intermediate page.

Home shows `Business: Automatic · Keys: default`, while Active setup offers “Key environment” and “Business profile.” Its explanation is “New commands use this choice. Shell settings and flags override it.” At 80×24 the Business page explains that Automatic follows the selected environment's profile. That explanation is absent at 40×18; source confirms it is conditional on height ≥20.

**Impact:** the default single-business task carries the vocabulary and an extra routing decision needed for multiple setups. The scope labels are visible, which is valuable, but their meaning is not initially evident. Use one user-facing name consistently and make Automatic's effective meaning available at narrow sizes. This does not imply environments or business contexts should be removed.

### P2 — The profile introduction hides fields before any editing starts

**Observed at 40×18:** the Profile page spends five wrapped lines on:

> Full sites that take payments usually require a business profile, terms of service and a privacy policy. Agents use these details to fill them in.

Only Your name, Business name, Legal name, and Website are initially visible; Public email and Mailing address require movement. There is no visible count of hidden list rows or “more” indicator on this list. The header's `0/6 optional fields` helps establish the total but does not explain which entries are off-screen. At 80×24 all six are visible.

**Impact:** a general explanation about payment sites dominates a simple optional-details editor. The user may also wonder whether saving these fields creates legal documents. The copy is a contextual claim rather than a description of the current editing action. A shorter immediate purpose and secondary explanation would reduce the burden without making the editor denser.

### P2 — Search-empty feedback points toward a feature request before query recovery

**Observed:** entering `/zzzz` in Providers shows “No providers match,” then “Don't see a provider you want? Open a GitHub issue! We'll get on it,” followed by Another key, Open a GitHub issue, and Back. No row is visibly selected in that initial state. Footer wording remains `↑↓ move · / search · Enter open · Esc back`.

Escape actually clears the search first and restores the list. This useful recovery is not named by the footer, which says Back. The screen conflates an unsuccessful filter with a missing provider integration.

**Impact:** the reader is sent toward external support for what may be a typo. Show query-specific empty-state guidance and make “clear search” discoverable before suggesting a request. Another key is a useful existing fallback and should be explained before the external issue route.

### P2 — Agent preview is honest, but its primary action is advertised before it is available

**Observed with synthetic existing Codex/Claude files:** Agents shows separate “These files will be created” and “These files will be modified” groups, paths, and `+19 −0`; the note follows as added lines. This makes the write scope unusually concrete. At 80×24 the initial counter was `1–14 of 30`; the complete note and “Copy for this task” section extend below the viewport.

At 40×18, pressing Enter immediately produced “Scroll through the full diff before adding the note.” The footer had already offered `Enter append`. The feedback itself takes more rows, reducing the visible preview area. The narrow long-path test exaggerated this; the gating and action-label mismatch are independent of that path length.

**Impact:** users discover a prerequisite by attempting the apparently available action. State the review requirement before the first Enter press and distinguish pending review from available append. Retain the exact file groups, additions, and preservation intent. This review did not bypass the review gate or claim an append succeeded.

### P2 — Technical masked receipts occupy too much of the narrow confirmation area

**Observed:** a synthetic GitHub value was accepted and saved locally; no network verification occurred. Draft input and receipts stayed masked. At 40×18 `+ Add GH_TOKEN=sealed(••••…)` wrapped across three lines; `Ctrl-U` split across two footer lines. After save, `Saved GH_TOKEN=sealed(••••…)` used three lines and stayed visible on returning home. The provider list then initially showed only GitHub, Cloudflare, and Vercel.

The list correctly says “saved” and “1 key stored,” not connected or verified. This is a positive accuracy distinction.

**Impact:** the receipt devotes its scarce space to placeholder syntax instead of the outcome. A compact “GitHub credential saved locally” with technical details available separately would preserve literal meaning. The opaque placeholder does not add useful identification once the named provider/key is known.

### P3 — First-run key wording can look like a typing instruction

**Observed:** the first screen presents `Enter I understand · Esc exit`, followed by a second introduction with `Enter open Godmode · Esc exit`. There is no text field. I initially interpreted the first phrase as something to type. Source inspection confirmed the first screen listens for the Enter key; it does not require typing “I understand.”

The warning and second splash fit both tested sizes, preserve spacing, and retain an exit route. This is a precise labeling ambiguity, not a claim that the brand voice should change. Formatting the keyboard name distinctly—for example `Enter: I understand`—would remove the ambiguity. Two screens precede the actual task menu; whether both are valuable is a product decision, not established by this review.

### P3 — Small help and status inconsistencies add avoidable noise

**Observed:** `godmode --help` usefully separates “For you,” “For agents,” “Files,” and “Options”; `godmode help` is a different, much longer agent-oriented guide. The human help documents this distinction. The FAQ answers concrete questions and explicitly says Doctor does not verify provider access.

The unknown-command error adds “Never put a key on the command line; pipe it with --stdin” even for the harmless input `godmode nonsense`. `godmode doctor` prints `1 optional fields` after saving one business field. At 40 columns, home compresses its footer to `↑↓ Enter · Esc quit`, dropping the action verbs and the switch shortcut.

**Impact:** the error combines recovery with an unrelated warning, the grammar is visibly mechanical, and narrow-screen instruction copy becomes less explicit precisely when the layout is harder to scan. These are polish issues below the task-flow problems above.

## What the baseline already does well

- At 80×24, menus have generous space, consistent left alignment, readable names, and a persistent business/key scope. The tool does not generally suffer from overly dense menus.
- Escape works across the tested provider, business, search, and help layers; returning home retains the prior selected item. In provider Details, Escape first returns to guidance rather than leaving the provider.
- Existing business values are shown above a prefilled editable value. The footer separately names draft clearing (`Ctrl-U`) and stored-value removal (`/clear`). Saving the synthetic name returned to the field list, advanced selection, and displayed “Saved Your name.”
- Provider records use storage terminology. The synthetic credential produced a local saved receipt without claiming functional provider access.
- Agent preview exposes created versus modified paths and additions/removals. An attempted premature append did not write the synthetic files.
- `--plain`, no-motion, command help, the agent guide, direct commands, and FAQ are discoverable in human help. I read plain FAQ output; I did not exhaustively exercise every plain interactive workflow.

## Evidence and copy inventory

Authoritative text captures:

- `copy-baseline-80-resolved.txt`: 80×24 home, providers, search-empty/recovery, agent preview, existing profile value, FAQ menu.
- `copy-baseline-40-short-path.txt`: 40×18 first run, home, provider guidance, business routing/fields, field editing/save, agent review gate. This capture still uses the `/tmp` alias; the additional resolved-path display in agent preview is a harness effect.
- `copy-baseline-40-token.txt`: 40×18 normal-length tilde path, synthetic credential draft/save, masked receipt.
- `copy-baseline-cli.txt`: Doctor, active scope, invalid-field/command errors, non-TTY setup response, and plain FAQ.

Additional first-pass captures (`copy-baseline-80.txt`, `copy-baseline-80-settings.txt`, `copy-baseline-40.txt`) record the initial exploration. Labels in scripted captures describe intended destinations and are not always actual page names; the visible title/content is authoritative. In particular, one intended “business draft” capture was still on the profile menu because that route contained an extra layer. That was corrected in the short-path run.

Committed source inventory used after first impressions: home copy and narrow status omissions in `view.go:103`; page titles/descriptions in `view.go:215`; field and key details in `view.go:380`; masked addition/input/footer in `view.go:471`; agent preview grouping in `view.go:613`; first-run text in `intro.go:181`; Enter-only first-run behavior in `model.go:507`; active-file error wrapping in `core.py:1200`. These references are to commit `9f5f9ee`, not the current working tree.

This is a baseline set of observed issues and strengths, with no requested or invented numeric rating. It does not establish novice success rates, provider-guide accuracy, accessibility conformance, color contrast, or successful external account access.
