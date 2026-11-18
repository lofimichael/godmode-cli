# Backend handoff

> Archived review record from 2026-11-17. Personal checkout paths are generalized. Referenced PTY captures, binaries and temporary fixtures remain session evidence and are not included here. Findings and scores describe the reviewed build, not the current candidate.

Modified only product files `lib/godmode_bridge.py` and `tests/test_ui_bridge.py`.

- `selection_save`: required string `environment`/`context`; empty context or `-` means Automatic. Validates and saves the full pair once through existing `set_active_selection`, refreshes current store/profile, invalidates key and agent preview IDs, returns normal state. Invalid pair leaves prior active selection intact.
- `environment_create` / `context_create`: optional boolean `select` defaults true for old callers. `false` creates the resource without changing active.json or current preview IDs; returns normal state with original pair. Invalid select type fails before creation.
- `state.preferences`: `{motion: true|false}`, default true with no file writes. A malformed/unsafe local file adds `preferences_error` while normal state stays available.
- `preferences_save`: required boolean `motion`, returns normal state. Writes local nonsecret `ui.json` using the existing Profile read/snapshot/lock/atomic-replace/mode rules (0600 file, 0700 home). Unknown fields are preserved. Malformed, duplicate-key, wrong-type, unsafe-mode and symlink files are refused; normal CLI startup does not read this file.

Validation exercised:

- UI bridge: 18 tests passed.
- Active selection: 16 tests passed.
- Environments: 11 tests passed.
- Contexts: 8 tests passed.
- `git diff --check`: passed.

No product install, release, commit or real user-home writes. Source tests used temporary isolated homes with synthetic credentials.

Additional reviewed-target selection:

- `agents_apply` accepts optional `targets`, a nonempty unique list of exact displayed `path` strings from the pending targets in that plan. Omission keeps apply-all behavior.
- Invalid, unknown, duplicate, nonstring, empty, absolute-path substitutions, and already-added targets are rejected before any writer call or plan invalidation. A corrected request can reuse the preview.
- Valid selection filters the original server-held snapshots and uses the same append writer. Unselected existing bytes and file metadata remain untouched; unselected missing agent folders remain absent.
- Validation after this change: 22 bridge tests and 17 agent-append tests passed; `git diff --check` passed.
