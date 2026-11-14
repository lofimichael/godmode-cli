# Providers

`godmode provider` lists the bundled providers, and `godmode provider SLUG`, such as `godmode provider google`, prints one provider's key types, setup pages, account scope, checks, recovery steps and official links. It reads no keys and contacts nothing.

`godmode setup SLUG` opens one provider's keys. Each key has one screen with its page and at most three steps. Enter on the empty field opens the page; paste the key and press Enter to save it. Save only the keys your work uses; the list is a catalog, not a checklist.

`godmode setup` lists every provider with its saved state. `/` filters names and descriptions. Escape clears the search; a second Escape leaves the list. Tab shows the selected row's full details. A key's default preview shows its destination file and masked assignment; Tab shows the shell equivalent.

`godmode --plain setup` uses numbered choices. Enter reviews a typed or pasted value; a second Enter saves it. Provider instructions and validation are the same in both modes.

The instructions come from [providers.json](../providers.json) ([schema](dev/CATALOG.md)) and were checked against each provider's public documentation on 2026-11-13. No signed-in account was tested. Follow the provider's current documentation where it differs.

## How agents use a provider

The bundled steps favor broad account access, so the user does not repeat setup for each task. A key grants technical access; the user's task grants authority. A saved key is not permission to spend money, publish, delete or change unrelated settings.

1. Read `godmode provider SLUG`, confirm the intended account and operation, and check the official tool's help or API documentation.
2. Run `godmode list` for saved names. Save a missing key with `godmode set NAME`, or ask the user to run `godmode setup SLUG`.
3. Pass only the needed names with `godmode run NAME... -- command`. The command must read those variables itself; Godmode does not configure an SDK, choose an account, enable an API or turn JSON into a credential file.
4. Run a read first to confirm identity, scope and target, then do the authorized operation and check the actual result. A saved key or a successful token check does not prove a deployment or write access.

Any other name works without registration:

```sh
godmode set ACME_ACCOUNT_ADMIN_TOKEN
godmode set ACME_OAUTH_JSON --stdin < /private/path/grant.json
godmode run ACME_ACCOUNT_ADMIN_TOKEN -- your-provider-command
```

`your-provider-command` stands for a real installed tool. Do not invent provider subcommands.

## Credential types

Any name ending in `_JSON` holds a JSON object. Save the type the consuming tool expects. [Google credentials](GOOGLE.md) shows Google's formats.

| What is stored | Normal use | When it needs replacing |
| --- | --- | --- |
| Static API token, key or app password | The tool uses the stored value directly. | Expiration, revocation, loss, compromise or a required rotation. |
| Service-account JSON key | The provider's auth library gets short-lived access tokens from the private key. | The key is disabled, deleted, invalid or due for rotation. Access-token expiry alone is routine. |
| User OAuth refresh grant | A compatible client gets and refreshes access tokens for the consenting user. | The grant is revoked, expired or unusable, or the provider requires a new sign-in. |
| OAuth client JSON | Identifies the application during its sign-in flow. | The client configuration changes. It is not a saved login. |
| Permission policy JSON | Describes roles and resources. | Update it through the provider. It is not a login. |

## Refresh and recovery

Provider tools and libraries refresh short-lived access tokens themselves. Godmode has no login, refresh service or daemon, and an expired access token alone needs no action.

When a key is rejected, read the error first. A wrong account, missing scope, resource access, billing limit, disabled API or outage each has its own fix. If the key itself is revoked, expired or lost, use the provider's official replacement or sign-in flow and save the result under the same name with `godmode set NAME --stdin`. `godmode run` never writes changes back: if a tool returns a new refresh grant, save it the same way. Keep a working provider-owned login cache where it is.

Some rotations invalidate the old value at once; others allow overlap, so verify a new key before retiring a valid old one. Saving a replacement changes only this machine's key file, not deployments, other machines or provider caches. Stop only at a real sign-in, MFA, account-owner or provider-review step, tell the user that exact step, and continue other work. Each provider's recovery steps are in `godmode provider SLUG`.
