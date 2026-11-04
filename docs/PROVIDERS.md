# Add a provider

You can save any valid key immediately with `godmode set ACME_ACCOUNT_ADMIN_TOKEN`. A registry entry is optional; it adds a named row, setup guidance and value metadata to the terminal interface.

Generate a starting point:

```sh
godmode providers-template > ./providers.toml
GODMODE_REGISTRY="$PWD/providers.toml" godmode providers
```

Edit that new file locally, then either keep using `GODMODE_REGISTRY` or place it at `<config-dir>/providers.toml`. An explicit environment path takes precedence over the default overlay. Never put credentials in a registry file. Do not redirect the template over an existing overlay you want to preserve.

```toml
schema = 1

[[provider]]
id = "acme"
name = "Acme"
purpose = "Manage the operator's Acme projects"
console = "https://example.com/settings/tokens"
docs = "https://example.com/docs/authentication"
notes = ["Use the account that owns your projects."]

[[provider.key]]
name = "ACME_ACCOUNT_ADMIN_TOKEN"
kind = "secret"
required = true
usage = "Create projects and manage their configuration"
scope = "Account access with project administration permissions"
steps = ["Open the token page", "Create a token for the required scope", "Paste the token into Godmode"]
format = "Opaque token issued by Acme"
verify = "Use the authenticated client to read the account identity"
```

Providers merge by `id`. Reusing an existing ID replaces its entire entry; a new ID appends a provider. IDs are lowercase slugs, and key names must be unique across the merged catalog. The schema rejects unknown fields. Console and documentation links must be HTTPS. Guidance is data: the CLI does not execute setup steps, verification hints or commands from a catalog.

Key metadata:

| Field | Meaning |
| --- | --- |
| `name` | Literal environment-variable name; include scope or environment where useful |
| `kind` | Display description, usually `secret`, `public` or `identity` |
| `required` | Needed for this provider's intended workflow; no provider is mandatory |
| `usage`, `scope` | What the credential enables and the permissions to select |
| `steps` | Short instructions for obtaining it |
| `format` | A human-readable hint; avoid undocumented fixed lengths |
| `prefixes` | Optional format hints, not proof of authentication |
| `forbid_prefixes` | Prefixes refused for this key, such as live credentials under a test name |
| `json` | When true, accept a raw JSON object and compact it before storage |
| `verify` | Read-only manual verification guidance; never executed by Godmode |

Avoid storing derivable account IDs or duplicating product runtime keys merely to fill a form. Keep reusable account credentials local, and send product-specific runtime credentials directly to the product's own secret store when operating that product.

## Bundled guides

The bundled [registry](../registry/providers.toml) covers the following providers. Documentation links were reviewed on 2026-11-03. Their interfaces and permission models can change; confirm the exact account and scope in the provider before relying on a credential.

| Provider | Official documentation |
| --- | --- |
| GitHub | [Personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) |
| Cloudflare | [Create API tokens](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/) |
| Vercel | [Access tokens](https://vercel.com/docs/accounts/access-tokens) |
| Supabase | [Personal access tokens](https://supabase.com/docs/guides/platform/personal-access-tokens) |
| Stripe | [API keys](https://docs.stripe.com/keys) |
| PostHog | [Personal API keys](https://posthog.com/docs/api/personal-api-keys) |
| Notion | [Internal connections](https://developers.notion.com/guides/connections-and-tokens/internal-connections) |
| Gmail | [App passwords](https://support.google.com/accounts/answer/185833) |
| Google | [Ads service accounts](https://developers.google.com/google-ads/api/docs/oauth/service-accounts), [Search Console authorization](https://developers.google.com/webmaster-tools/v1/how-tos/authorizing) |
| Higgsfield | [Authentication](https://docs.higgsfield.ai/docs/authentication) |
| Zernio | [Quickstart](https://docs.zernio.com/quickstart) |
| Prodigi | [Print API](https://www.prodigi.com/print-api/docs/) |

Search Console user OAuth grants belong in a separate state store; see [Google setup](GOOGLE.md). A Gmail app password does not provide Google SSO, Gmail API or Workspace administration access.
