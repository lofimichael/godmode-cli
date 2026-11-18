# Separate final-build checkpoint

Binary SHA-256: `0da6fa2c7384285accffb7540fd87686818783a8d90e096324adaa163307e9e9`

This is a follow-up smoke/regression checkpoint, **not a second blind first-use audit**. The candidate-3 first impressions and 8.5/10 judgment were frozen before this checkpoint. No implementation source, design documents or prior audit reports were consulted. The temporary fixture was copied from the candidate-3 synthetic fixture, then the Codex/Claude instruction fixtures were restored to their original bytes so the final build could perform a fresh Codex append. The original candidate-3 fixture was not modified.

Observed result: **no blockers in the final-build tasks exercised here.** The bounded 8.5/10 navigation assessment still fits; the successful detour checks add confidence, without establishing exhaustive coverage.

## Repeated core actions

- Started at 80×24 with existing synthetic keys/profiles. The home screen correctly said Connect your agent and selected Connect agent because the copied fixture's instruction files had been reset.
- Used global action search to reach Cloudflare from Connect agent, saved a synthetic replacement, then entered and cancelled another replacement. Returned through action search to the original Connect agent screen. Independent `run` verification confirmed the saved value survived the cancelled replacement.
- Selected Codex only, resized its append preview to 40×18, paged to the end, and appended. Original CRLF bytes and mode 0600 were preserved, one Godmode block existed, and the command path pointed to the final binary. Claude's bytes remained exact and its rule file was absent.
- Edited business B's name at 40×18, with confirmation.
- Cancelled a recent-pair review, then reused A and B. Final CLI checks confirmed A retained its original synthetic key/profile and B used the newly saved key/profile.
- Found Settings and Help through global actions. Read the first-use help answer. Resized the business screen to 120×36 and saw the correct full A value.

## Back-navigation detours

1. Business details, selected Legal name → Ctrl-K → Settings → **Back menu item** → action search → Esc → Business details, still selected Legal name.
2. Business details for B → `s` → Recent setups → review A → Esc. B remained active.
3. Reopen A review → apply → **Recent setups Back item** → Switch setup → **Switch setup Back item** → original Business details screen, still selected Legal name, now correctly scoped to A. Resizing and opening Business name showed “Synthetic Business A”, not stale B data.
4. Reused B afterward and verified the exact active B pair and its values through the CLI.

The final checkpoint produced 44 numbered text/PNG terminal frames plus `actions.jsonl` and `verification.json`. Frame names describe intended actions; frame 002 is Connect agent because the final home selected that next step automatically, and the following `/cloudflare` correctly opened the global action finder.

Limits: did not repeat brand-new intro, environment/business creation, every Settings/help page or the local Check setup command on this build. Those were exercised only on candidate 3. No live provider/agent execution, clipboard, animations, plain mode, installer/update or destructive operations were exercised on either build. The same minor narrow-screen wrapping and menu-depth friction remain acceptable within this scope. No implementation was changed.
