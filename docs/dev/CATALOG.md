# Provider catalog

[providers.json](../../providers.json) is the only source of provider instructions. The native build embeds it in the Python file engine inside the executable.

A provider has `id` (used by `setup` and `provider`), `name`, a short menu `about`, a default `console` page, and `key` entries. Its printable agent guide has:

- `access`: credential identity, permissions, account/resource selection and relevant limits.
- `verify`: a list of useful checks and supported operation guidance. These are instructions, never commands Godmode runs.
- `recover`: a list of provider-owned refresh, replacement and re-enrollment instructions.
- `docs`: a list of official reference objects with `title` and HTTPS `url`.
- `ready`: Optional. A list of key-name lists; the provider counts as ready when any list is fully saved. Without it, all keys are required.

Each key has:

- `name`: the stored variable. `label`: the short name in the menu. `kind`: a descriptive credential type; it does not validate or enforce permissions.
- `goal`: the first line of its screen. `steps`: at most three one-line steps, with page labels between `**` shown bold. `note`: one optional line under them.
- `console`: a different page from the provider's, or `null` when none is needed.
- `prompt`: a custom input label. `"secret": false`: show typed input, as for an address; pasted input stays masked.
- `file`: accept a dragged key file. `format`: `google-service-account` checks the standard Google key shape, not live access.
- `drop`: characters removed from interactive input. `split`: `[":", 0]` keeps the first part and `[":", 1]` keeps the rest. Interactive `godmode set NAME` uses these rules too; `--stdin` saves its input without them.

Never put keys, account-specific facts or personal operating policy in the catalog. Keep onboarding steps here rather than copying them into separate documents. After editing it, rebuild with `sh scripts/build-native.sh` and reinstall the new native executable. That build runs `scripts/build.py` to refresh the embedded engine and catalog first.
