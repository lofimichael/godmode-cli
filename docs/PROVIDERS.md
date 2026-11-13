# Provider help

Use `godmode provider` to list the bundled providers, then `godmode provider google` (or another provider ID) to read its credential types, setup pages, account scope, useful access checks, recovery instructions and official references. This is static help: it does not read credentials, contact the provider or create a Godmode store.

Run `godmode` for interactive onboarding, or `godmode setup stripe` to open one provider. Each key has one screen with its creation page and at most three steps. Enter opens the page while the field is empty; paste the key and Enter saves it. Esc goes back. Save the keys your work uses. A saved count describes storage, not working access or required setup.

The single source for provider instructions is [providers.json](../providers.json), embedded in the installed executable. The public documentation behind the access and recovery guidance was reviewed on **2026-11-13**. No signed-in account or credential was tested. Provider labels, permissions and policies can change; follow the linked current official documentation when they differ.

## Give an agent usable access

A broad account token can reduce repeated setup for a trusted operator. The bundled defaults intentionally favor that capability, subject to the provider's role, resource and expiration policies. A credential grants technical access; the user's task supplies authority to act. Creating a token does not approve spending, publication, deletion or unrelated account changes.

An agent should:

1. Read `godmode provider SLUG`, identify the intended account and operation, and inspect its installed official tool's help or the linked API documentation.
2. Use `godmode list` to discover saved names. Obtain missing credentials through the provider's official flow and save them with `godmode set NAME`, or use the interactive setup screens.
3. Pass only the relevant names through `godmode run NAME... -- command`. The consumer must understand those variables; Godmode does not configure an SDK, choose an account, enable an API or translate JSON into a credential file automatically.
4. Perform a relevant read to confirm identity, scope and target, then carry out the authorized operation and verify the actual result. A stored key, successful token check or resource listing does not prove a deployment, permission to write or a completed customer outcome.

Any other credential name works without registration:

```sh
godmode set ACME_ACCOUNT_ADMIN_TOKEN
godmode set ACME_OAUTH_JSON --stdin < /private/path/grant.json
godmode run ACME_ACCOUNT_ADMIN_TOKEN -- your-provider-command
```

`your-provider-command` is a placeholder for a real installed consumer. Do not invent provider subcommands. Use its documentation to load the selected value without printing it. `godmode edit` opens nano for manual changes or removing entries; use `godmode set` to replace sealed values.

## Keep access working

| What is stored | Normal use | When it needs replacing |
| --- | --- | --- |
| Static API token, key or app password | The consumer uses the stored value directly. | Expiration, revocation, loss, compromise or a required rotation. |
| Service-account JSON key | The provider's auth library obtains short-lived access tokens from the private key. | The underlying key is disabled, deleted, invalid or due for rotation. Access-token expiry alone is routine. |
| User OAuth refresh grant | A compatible client obtains and refreshes access tokens for the consenting user. | The refresh grant is revoked, expired, unusable or the provider requires renewed sign-in. |
| OAuth client JSON | Identifies the application during its provider sign-in flow. | The client configuration changes; it is not a saved user login. |
| Permission policy JSON | Describes roles and resources. | Update it through the provider when authorized; it is not an authentication credential. |

Read the actual error before replacing anything. Wrong accounts, missing scopes, resource access, billing restrictions, disabled APIs and temporary outages have different remedies. Normal access-token refresh belongs to the consuming provider tool or library. Godmode has no refresh manager, login service or daemon.

When the underlying credential really needs recovery, use the provider's official replacement or authorization flow, then overwrite the same Godmode name. If a tool saves a new refresh grant, import the replacement explicitly; changing a child process's environment or token cache cannot update Godmode. Keep a working provider-owned cache in place unless intentionally migrating it. See [Google credentials](GOOGLE.md) for its JSON formats and consent requirements.

Provider-specific recovery lives in `godmode provider SLUG`. Some rotations invalidate the old value immediately; others allow overlap. Verify replacements before retiring a valid old credential when the provider supports it. Saving a replacement updates this local store only, not deployments, other machines or provider-owned caches. Stop only at an actual human sign-in, MFA, account-owner or provider-review gate; report the exact step needed and continue independent work.

## Maintain the catalog

A provider has `id` (used by `setup` and `provider`), `name`, a short menu `about`, a default `console` page, and `key` entries. Its printable agent guide has:

- `access`: credential identity, permissions, account/resource selection and relevant limits.
- `verify`: a list of useful checks and supported operation guidance. These are instructions, never commands Godmode runs automatically.
- `recover`: a list of provider-owned refresh, replacement and re-enrollment instructions.
- `docs`: a list of official reference objects with `title` and HTTPS `url`.

Each key has:

- `name`: the stored variable. `label`: the short name in the menu. `kind`: a descriptive credential type; it does not validate or enforce permissions.
- `goal`: the first line of its screen. `steps`: at most three one-line steps, with page labels between `**` shown bold. `note`: one optional line under them.
- `console`: a different page from the provider's, or `null` when none is needed.
- `prompt`: a custom input label. `"secret": false`: show typed input for an address; pasted input stays masked.
- `file`: accept a dragged key file. `format`: `google-service-account` checks the standard Google key shape, not live access.
- `drop`: characters removed from interactive input. `split`: `[":", 0]` keeps the first part and `[":", 1]` keeps the rest. Interactive `godmode set NAME` uses these rules too; `--stdin` saves normalized input without those paste transformations.

Never put credentials, account-specific facts or personal operating policy in this catalog. Keep onboarding steps here rather than copying them into separate provider documents. After editing the catalog, rebuild with `scripts/build.py` and reinstall so the executable contains the update.
