# Active setup: decision and verification

17 November 2026.

Godmode needs one convenient default for a person and an explicit, stable choice for an agent task. The selected pair is a complete key environment plus a business profile. It does not add another credential store or copy business facts.

## Research

| Official pattern | Useful lesson | Godmode choice |
| --- | --- | --- |
| [Conda activation](https://docs.conda.io/projects/conda/en/stable/dev-guide/deep-dives/activation.html) changes the parent shell through shell integration; a child executable alone cannot export back to it. | Activation affects a shell session, and reliable activation requires shell-specific machinery. | No mandatory shell hooks or evaluated output. A saved pair works immediately; environment variables can pin a shell when needed. |
| [uv project environments](https://docs.astral.sh/uv/concepts/projects/config/) distinguish project environments from an externally activated environment, with an explicit active-environment option. | A visible selection and explicit precedence matter more than copying one tool's activation vocabulary. | `godmode active` reports the resolved pair; no implicit project-directory discovery or execution is added. |
| [Kubernetes contexts](https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/) have a saved current context and a command override. | A persistent default is easy for humans; scripts need explicit scope. | Save the selected pair and keep flags authoritative. Task notes pin both axes. |
| [AWS CLI environment precedence](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-envvars.html) gives command options priority over environment variables, then configuration. | Familiar, inspectable precedence supports both interactive and automated use. | `--env` / `--context` > `GODMODE_ENV` / `GODMODE_CONTEXT` > saved pair > original defaults, separately for each axis. |

## Contract

- `godmode use --env acme-test --context acme` atomically saves both names in `active.json` inside the selected Godmode home. `use acme-test` takes the business from the currently resolved selection, including a shell override, and saves the complete resulting pair. Likewise, `use --context acme` retains the resolved environment. Pass both flags for an exact pair. Selection must resolve to existing named files and contexts before writing.
- `godmode active` prints the pair and a fully scoped command. `--command` prints only the prefix; `--json` returns names, paths and source metadata. It never prints credential or profile values.
- `--context -` means the environment's own profile, shown as **Automatic**. This sentinel cannot collide with old context names; a real business named `default` remains valid.
- The menu changes the saved default, then adopts it in that session. Existing processes keep their snapshot. New unscoped commands follow the saved default, including commands from another terminal.
- For long-running agent work, capture `godmode active --command`, copy the scoped task note, or export the two selector variables before starting the agent. Explicit task scope cannot be redirected by a later saved-default change.
- A child launched through `godmode run` inherits both selectors, including explicit defaults, and an explicitly selected home. Reserved Godmode selector variables cannot be replaced through a credential alias.
- Shell overrides remain authoritative for later commands. The menu exposes a stable `shell_override` indicator; `use` warns that saving does not unset the shell variables.
- A selected missing environment/context fails closed. Inventory/create commands remain usable for recovery. Complete explicit selectors bypass damaged saved metadata; unsafe or malformed JSON is never silently deleted or overwritten.
- State and writes use the existing safe file machinery: private directories, owned regular mode-0600 files, no symlinks or hardlinks, duplicate-key rejection, size bounds, atomic replacement and conflict detection. Credentials and business files remain intact.

## Native bridge

Existing `environment_select` and `context_select` actions save the complete pair and return a fresh snapshot. `environment_create` and `context_create` retain their existing create-and-select behavior, now saving the chosen pair. Every selection invalidates old key and agent previews.

State adds `selection_source`, `environment_source`, `context_source`, `startup_sources` and `shell_override`. `context` remains an empty string for Automatic; copied and external commands use `--context -` to pin it explicitly.

## Exercised checks

`tests/test_active_selection.py` covers readonly empty startup; persisted profile/key routing; unchanged existing file bytes and metadata; per-axis flag/shell/saved precedence; compatibility with a business named `default`; explicit default task notes; missing target refusal and repair; invalid-choice preservation; malformed/unsafe selection files; replacement of invalid semantic metadata with an explicit valid pair; nested command pinning after a different default is saved; shell-override warning; separate live bridge sessions with stale-preview rejection; and preservation of legacy key-home discovery.

The existing environment, context and bridge suites remain part of acceptance. These are synthetic local tests; selector names do not establish actual provider identity, permissions or payment mode.
