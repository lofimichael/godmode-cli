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
login = "https://example.com/login"
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

Providers merge by `id`. Reusing an existing ID replaces its entire entry; a new ID appends a provider. IDs are lowercase slugs, and key names must be unique across the merged catalog. The schema rejects unknown fields. `login`, `console` and `docs` links must be HTTPS. `login` is optional for older overlays; when omitted or empty, the console link is used for sign-in. Guidance is data: the CLI does not execute setup steps, verification hints or commands from a catalog.

Provider links:

| Field | Meaning |
| --- | --- |
| `login` | Account sign-in page; optional, with `console` as the fallback |
| `console` | Direct credential-management or API-key page |
| `docs` | Official setup or authentication documentation |

In interactive setup, `l` opens sign-in, `o` opens the key page and `d` opens documentation for the selected provider. The links are also displayed as text so you can copy them. Browsers open only after a keypress; entering a credential never opens a browser. If you prefer a plain command, `godmode guide PROVIDER` prints all three URLs and the setup instructions.

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

The bundled [registry](../registry/providers.toml) covers the following providers. Public sign-in and documentation entry points were checked on **2026-11-04**. This was a link review without signing in or submitting credentials; some provider pages require JavaScript. Interfaces and permission models can change, so confirm the account and scope in the provider before relying on a credential.

| Provider | Sign in | Official documentation |
| --- | --- | --- |
| GitHub | [GitHub login](https://github.com/login) | [Personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) |
| Cloudflare | [Dashboard login](https://dash.cloudflare.com/login) | [Create API tokens](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/) |
| Vercel | [Vercel login](https://vercel.com/login) | [Access tokens](https://vercel.com/docs/accounts/access-tokens) |
| Supabase | [Dashboard sign-in](https://supabase.com/dashboard/sign-in) | [Personal access tokens](https://supabase.com/docs/guides/platform/personal-access-tokens) |
| Stripe | [Dashboard login](https://dashboard.stripe.com/login) | [API keys](https://docs.stripe.com/keys) |
| PostHog | [US Cloud login](https://us.posthog.com/login) | [Personal API keys](https://posthog.com/docs/api/personal-api-keys) |
| Notion | [Notion login](https://app.notion.com/login) | [Internal connections](https://developers.notion.com/guides/connections-and-tokens/internal-connections) |
| Gmail | [Google Account sign-in](https://accounts.google.com/) | [App passwords](https://support.google.com/accounts/answer/185833) |
| Google | [Google Account sign-in](https://accounts.google.com/) | [Ads service accounts](https://developers.google.com/google-ads/api/docs/oauth/service-accounts), [Search Console authorization](https://developers.google.com/webmaster-tools/v1/how-tos/authorizing) |
| Higgsfield | [API platform login](https://open.higgsfield.ai/auth/sign-in?redirect_url=%2Fapi-keys) | [Authentication](https://docs.higgsfield.ai/docs/authentication) |
| Zernio | [Zernio sign-in](https://zernio.com/signin) | [Quickstart](https://docs.zernio.com/quickstart) |
| Prodigi | [Dashboard login](https://dashboard.prodigi.com/login) | [Print API](https://www.prodigi.com/print-api/docs/) |

PostHog's bundled entry uses US Cloud. If your project is hosted in the EU, use `https://eu.posthog.com/login` and its matching console URL in an overlay. The Higgsfield API console now lives at `open.higgsfield.ai`; its former `console.higgsfield.ai` entry redirects there. Login links lead to the provider's normal browser authentication and do not enroll an OAuth grant, supply a password, or verify the saved API key.

Search Console user OAuth grants belong in a separate state store; see [Google setup](GOOGLE.md). A Gmail app password does not provide Google SSO, Gmail API or Workspace administration access.
