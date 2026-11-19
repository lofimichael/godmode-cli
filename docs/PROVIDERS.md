# Providers

Use `godmode provider` to list bundled providers. Add a slug to see its key names, setup links, account requirements and recovery steps.

```sh
godmode provider google
godmode setup google
```

## Add a key

1. In `godmode`, open **Provider keys** and select a provider and key. Use `/` to filter the provider list, or open the provider directly with `godmode setup PROVIDER`.
2. Press Enter on an empty key field to open its setup link, when available. Create or copy the key in the provider's dashboard.
3. Paste the value, review the destination and masked preview, then press Enter to save. Tab shows the shell equivalent. Esc cancels an unsaved edit.

For numbered menus, use `godmode --plain setup`. Press Enter to review the value, then Enter again to save. The bundled guides come from [providers.json](../providers.json).

## How agents use a provider

1. Read `godmode provider PROVIDER` and run `godmode list` to find saved names.
2. Look up the environment variable the installed tool expects. Pass only the keys it needs with `godmode run`, using `VARIABLE=SAVED_KEY` to rename a key for the command.
3. Make a read-only request to check the account, resource and permissions. Keep writes within the task the user authorized and verify their result at the provider.

The GitHub CLI can report the signed-in account using your saved `GH_TOKEN`.

```sh
godmode run GH_TOKEN -- gh api user --jq .login
```

You can choose your own saved key name. Run `godmode set ACME_API_TOKEN` for the masked prompt, or import a credential from a private file.

```sh
godmode set ACME_OAUTH_JSON --stdin < /private/path/grant.json
```

## Credential types

| Type | Use |
| --- | --- |
| API token, API key or app password | The tool sends the value to the provider. |
| Service-account key | The provider library uses the private key to obtain short-lived access tokens. |
| User OAuth refresh grant | The authorized client obtains access tokens for the consenting user. |
| OAuth client configuration | Identifies the app during sign-in. |
| Permission policy | Defines which identities may use a resource. |

A name ending in `_JSON` requires a JSON object. Match the consuming tool's format. For service accounts, user grants and application credentials, see [Google credentials](GOOGLE.md).

## Refresh and recovery

The provider tool or library handles routine access-token refresh. Keep its existing login cache if it manages the grant. If the provider returns a replacement credential that you store in Godmode, save it explicitly with `godmode set NAME` or `godmode set NAME --stdin`. A command launched with `godmode run` has no write-back step.

When a request fails, check account, resource, scope and service status before rotating. Use the provider's official sign-in or replacement flow for an expired or revoked credential. Verify the new key with the intended tool and update each machine or deployment that uses it.
