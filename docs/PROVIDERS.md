# Provider help

Run `godmode` and pick a provider with the arrow keys (typing a name jumps to it). Each key has one screen: what to create, the page to create it on, and at most three steps to take there. Enter opens the page while the field is empty; paste the key and Enter saves it. Esc goes back. A provider with several keys shows them as a second list. `godmode setup stripe` starts at one provider. Save only the keys you need; a saved count records storage, not working access or required setup.

Any other key works without registration, from `Another key` in the list or directly:

```sh
godmode set ACME_ACCOUNT_ADMIN_TOKEN
```

`godmode edit` opens nano for manual changes or removing keys.

The bundled provider list is static help in [providers.json](../providers.json). It does not authenticate, validate account permissions, enroll OAuth, or impose token-prefix rules. Never put credentials in this help file.

## When a key stops working

Check the provider's error first: missing permission, a wrong account, and expiry are different problems. For an expired or revoked credential, use the provider's replacement or sign-in flow, then overwrite the same Godmode entry:

```sh
godmode setup github                   # opens the provider's setup guidance
godmode set GH_TOKEN                   # paste a replacement behind a mask
godmode set EXAMPLE_OAUTH_JSON --stdin < /path/to/new-grant.json
godmode run GH_TOKEN -- gh repo list   # the consuming tool checks access
```

For GitHub, Vercel, Supabase, Notion, PostHog and Zernio, create a replacement token in the linked provider page. Cloudflare and Stripe also offer token/key rotation; follow the provider's instructions about when the old value stops working. Verify the new value in its consumer before retiring the old one when the provider allows overlap. Updating Godmode does not update other machines, deployments or provider-owned credential caches.

Gmail needs a new app password; Higgsfield needs both halves of the new key; Prodigi uses separate sandbox and live keys. Google JSON files have different roles: follow [Google credentials](GOOGLE.md) for service account keys, OAuth clients and saved grants. Godmode does not refresh any of them itself.

Replacement references: [Cloudflare rotation](https://developers.cloudflare.com/fundamentals/api/how-to/roll-token/), [Stripe rotation](https://docs.stripe.com/keys#rolling-keys), [Notion expiry](https://developers.notion.com/guides/connections-and-tokens/personal-access-tokens). Other provider links are below.

## What the on-screen steps give you

The steps favor broad provider presets for this private operator toolkit. Routes and labels were checked against public documentation, and in several cases open-source dashboard code, on **2026-11-12**; credential-type and replacement guidance was reviewed on **2026-11-13**. Nothing was checked from a signed-in dashboard, so labels and available choices can differ. These are requested permissions: the provider still applies your account's roles, plan, resource access and policies. Saving a value proves none of those.

| Key | On-screen route | Narrower choice |
| --- | --- | --- |
| `GH_TOKEN` | Fine-grained token from a pre-filled link: write on Administration, Contents, Workflows, Actions, Secrets, Variables, Environments, Issues and Pull requests, for the selected resource owner's repositories. The link requests 366 days; organization policy can restrict it. | Choose **Only select repositories**. To drop repository deletion and settings rights, remove `administration=write` from the link and add the **Repository creation** permission. |
| `CLOUDFLARE_API_TOKEN` | User token built from **Read All Resources**, changing permissions to Edit where available. Confirm the account/zone resources and required services in the summary. | The documented pre-filled link below selects Workers scripts and routes, KV, R2, D1, Queues, DNS and zone settings. Limit the accounts/zones and set a token expiration in the provider form. |
| `VERCEL_TOKEN` | **Full Account**: your personal account and every team you belong to. | Under **Scope** choose one team, then **All Projects**. |
| `SUPABASE_ACCESS_TOKEN` | Legacy token: your account's full access across organizations and projects, with **Never** selected for expiry. This is a management token, not a database password or project runtime key. | A scoped token: **Generate new token**, pick the organization and the **Full access** preset, or set permissions one by one. |
| `STRIPE_TEST_SECRET_KEY` | The sandbox's standard secret key: full access to test data. | **Create restricted key** and set Write only on what agents use. |
| `STRIPE_TEST_PUBLISHABLE_KEY` | The sandbox's publishable key. It is safe in browser code. | None. |
| `STRIPE_LIVE_SECRET_KEY` | A new standard secret key: full access to live data and money movement. Add it only when live charges are authorized. | **Create restricted key**; choosing the agent-access use adds Stripe's approval rules for refunds, cancellations and payouts. |
| `STRIPE_LIVE_PUBLISHABLE_KEY` | The live publishable key. | None. |
| `POSTHOG_PERSONAL_API_KEY` | PostHog's pre-filled **MCP Server** preset requests broad private API access. Review its organization/project selection and scopes; use the key on the matching US, EU or self-hosted instance. | Open the page without `?preset=mcp_server`, choose one organization and only the scopes agents use. |
| `NOTION_API_KEY` | Personal access token: acts as you across the workspace, expires within a year. | An internal connection at `app.notion.com/developers/connections`: it sees only pages you share with it and does not expire. |
| `GMAIL_USER` | The address agents sign in with. Not a secret. | Use a dedicated mailbox. |
| `GMAIL_APP_PASSWORD` | IMAP and SMTP access to that mailbox where allowed by its account settings. Needs 2-Step Verification. Interactive entry removes the spaces Google shows. | Use a dedicated mailbox, or a separate OAuth implementation with the needed Gmail API scopes. |
| `GOOGLE_ADS_SERVICE_ACCOUNT_JSON` | A service account key with no Cloud roles. It can do nothing in Ads until its email is added under Admin > Access and security. Enable the Google Ads API in the project first. | Add the email with Read only access, or to one client account instead of a manager account. |
| `GOOGLE_SEARCH_CONSOLE_SERVICE_ACCOUNT_JSON` | A Search service account key, with the Search Console API enabled in its project and its email granted property access. Replacing a key does not require a new service account. User OAuth is a separate supported consumer choice; see [Google credentials](GOOGLE.md). | Grant access only to the properties and operations needed; Restricted user access is suitable only for operations that allow it. |
| `HIGGSFIELD_API_KEY_ID`, `HIGGSFIELD_API_KEY_SECRET` | One credential pair for your account. Model availability is checked separately by Higgsfield. Its `ID:SECRET` copy can be pasted into both interactive entries; each keeps its half. | Turn on **Set expiration date** when available. Replace both halves together. |
| `ZERNIO_API_KEY` | Default key: read and write, all profiles. | In the same panel choose **Read Only**, pick profiles, or restrict resource groups. |
| `PRODIGI_SANDBOX_API_KEY` | The account's one sandbox key. Sandbox orders are not printed or charged. | None; there is one key per environment. |
| `PRODIGI_API_KEY` | The account's one live key. Orders placed with it are printed, shipped and billed. | None. |

### Cloudflare's pre-filled link

Cloudflare documents [API token template URLs](https://developers.cloudflare.com/fundamentals/api/how-to/account-owned-token-template/) that open the Create Token form already filled in. This one uses only documented permission keys; after it opens, select **Continue to summary**, then **Create Token**:

```
https://dash.cloudflare.com/profile/api-tokens?permissionGroupKeys=%5B%7B%22key%22%3A%22workers_scripts%22%2C%22type%22%3A%22edit%22%7D%2C%7B%22key%22%3A%22workers_kv_storage%22%2C%22type%22%3A%22edit%22%7D%2C%7B%22key%22%3A%22workers_r2%22%2C%22type%22%3A%22edit%22%7D%2C%7B%22key%22%3A%22d1%22%2C%22type%22%3A%22edit%22%7D%2C%7B%22key%22%3A%22queues%22%2C%22type%22%3A%22edit%22%7D%2C%7B%22key%22%3A%22account_settings%22%2C%22type%22%3A%22read%22%7D%2C%7B%22key%22%3A%22workers_routes%22%2C%22type%22%3A%22edit%22%7D%2C%7B%22key%22%3A%22dns%22%2C%22type%22%3A%22edit%22%7D%2C%7B%22key%22%3A%22zone%22%2C%22type%22%3A%22read%22%7D%2C%7B%22key%22%3A%22zone_settings%22%2C%22type%22%3A%22edit%22%7D%5D&accountId=%2A&zoneId=all&name=godmode
```

It was not tested after Cloudflare's November 2026 redesign of the token form, and it cannot pre-fill Email Routing rules, Email Sending or Workers Observability, which have no documented keys. To make Enter open it, set `console` for `CLOUDFLARE_API_TOKEN` in providers.json to this link and shorten its steps.

## Provider data

Each provider in [providers.json](../providers.json) has an `id` (the word used by `godmode setup <id>`), a `name`, a short `about` shown beside it in the list, a `console` page, and `key` entries. The installed script carries a copy of this data: after changing it, rebuild with `scripts/build.py` and reinstall. A key has:

- `name`: the variable written to the file. `label`: its name in a list of keys.
- `goal`: the first line of its screen. `steps`: at most three one-line steps, with page labels between `**` shown bold. `note`: one optional line under them.
- `console`: its own page when it differs from the provider's; `null` when it has none.
- `prompt`: a different input label. `"secret": false`: show the value as it is typed, for an address (a paste is still masked).
- `file`: a key file dragged onto the prompt is read from its path. `format`: `google-service-account` checks the standard Google key shape.
- `drop`: characters removed from a paste. `split`: `[":", 0]` keeps the part before the first colon, `[":", 1]` the part after. These rules apply wherever the key is entered at a prompt, including `godmode set NAME`; `godmode set NAME --stdin` saves its input as given.

## Sign-in and documentation links

Public sign-in and documentation entry points for the bundled providers, checked on **2026-11-04** (Notion and Prodigi links on 2026-11-12). This was a link review without signing in or submitting credentials; some provider pages require JavaScript. Interfaces and permission models can change, so confirm the account and scope in the provider before relying on a credential.

| Provider | Sign in | Official documentation |
| --- | --- | --- |
| GitHub | [GitHub login](https://github.com/login) | [Personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) |
| Cloudflare | [Dashboard login](https://dash.cloudflare.com/login) | [Create API tokens](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/) |
| Vercel | [Vercel login](https://vercel.com/login) | [Access tokens](https://vercel.com/docs/accounts/access-tokens) |
| Supabase | [Dashboard sign-in](https://supabase.com/dashboard/sign-in) | [Personal access tokens](https://supabase.com/docs/guides/platform/personal-access-tokens) |
| Stripe | [Dashboard login](https://dashboard.stripe.com/login) | [API keys](https://docs.stripe.com/keys) |
| PostHog | [US Cloud login](https://us.posthog.com/login) | [Personal API keys](https://posthog.com/docs/api/personal-api-keys) |
| Notion | [Notion login](https://app.notion.com/login) | [Personal access tokens](https://developers.notion.com/guides/connections-and-tokens/personal-access-tokens), [Internal connections](https://developers.notion.com/guides/connections-and-tokens/internal-connections) |
| Gmail | [Google Account sign-in](https://accounts.google.com/) | [App passwords](https://support.google.com/accounts/answer/185833) |
| Google | [Google Account sign-in](https://accounts.google.com/) | [Ads service accounts](https://developers.google.com/google-ads/api/docs/oauth/service-accounts), [Search Console authorization](https://developers.google.com/webmaster-tools/v1/how-tos/authorizing) |
| Higgsfield | [API platform login](https://open.higgsfield.ai/auth/sign-in?redirect_url=%2Fapi-keys) | [Authentication](https://docs.higgsfield.ai/docs/authentication) |
| Zernio | [Zernio sign-in](https://zernio.com/signin) | [Quickstart](https://docs.zernio.com/quickstart) |
| Prodigi | [Dashboard login](https://dashboard.prodigi.com/login) | [Print API](https://www.prodigi.com/print-api/docs/) |

PostHog's link, `app.posthog.com`, sends you to the US or EU cloud you last signed in to. The Higgsfield API console lives at `open.higgsfield.ai`. Opening a page leads to the provider's normal browser sign-in; it does not enroll an OAuth grant, supply a password, or verify the saved key.

Search Console user OAuth grants use a separate key name and a consumer that understands them; see [Google credentials](GOOGLE.md). A Gmail app password does not provide Google SSO, Gmail API or Workspace administration access.
