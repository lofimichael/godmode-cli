# Providers

Run `godmode provider` to browse the catalog. Read a provider’s guide before adding it to your loadout.

```sh
godmode provider cloudflare
godmode loadout cloudflare
```

## Add a provider

1. Open **Provider keys** in Godmode or run `godmode loadout PROVIDER`. Choose the credential you need.
2. Press **Ctrl-O** to open the provider page when the field has a link. Follow the instructions for your account, project and environment.
3. Paste the value and check the masked preview and destination. **Enter** saves. **Tab** shows edit details and **Esc** cancels the edit.

For numbered menus, run `godmode --plain loadout`. In a plain credential field, use **Tab** to review, then **Enter** to save. You can read the bundled steps, verification and recovery instructions anytime with `godmode provider PROVIDER`.

## Choose a provider

| Provider | What your agent can do | Where to get the credential |
| --- | --- | --- |
| GitHub | Open pull requests, triage issues and manage Actions in selected repositories. | [Fine-grained token](https://github.com/settings/personal-access-tokens/new) |
| Cloudflare | Deploy a website on Workers, configure DNS or manage D1 and R2 with the relevant permissions. | [User API tokens](https://dash.cloudflare.com/profile/api-tokens) |
| Vercel | Deploy a web app, check a preview and connect a domain. | [Account tokens](https://vercel.com/account/settings/tokens) |
| Supabase | Inspect hosted Postgres projects, configure Auth or deploy Edge Functions. | [Personal access tokens](https://supabase.com/dashboard/account/tokens) |
| Stripe | Test checkout in a sandbox or work with real payments. A secret key runs server-side requests. A publishable key belongs in the client. | [Sandbox keys](https://dashboard.stripe.com/test/apikeys) · [Live keys](https://dashboard.stripe.com/apikeys) |
| PostHog | Query product usage and manage feature flags in a project. Use the account region that holds its data. | [US personal keys](https://app.posthog.com/settings/user-api-keys?preset=mcp_server) · [EU personal keys](https://eu.posthog.com/settings/user-api-keys) |
| Notion | Find notes, edit pages and add database entries using your workspace permissions. | [Personal access tokens](https://app.notion.com/developers/tokens) |
| Gmail | Read mail over IMAP or send it over SMTP. Save the mailbox address and its app password. | [Google app passwords](https://myaccount.google.com/apppasswords) |
| Google | Research Ads keywords or inspect Search Console performance. Grant the service-account email access to the customer or property. | [Cloud service accounts](https://console.cloud.google.com/projectselector/iam-admin/serviceaccounts) · [Google credentials](GOOGLE.md) |
| Higgsfield | Generate images and video clips using your API account. Paste the same credential into the ID and secret fields. | [API keys](https://open.higgsfield.ai/api-keys) |
| Zernio | Schedule posts and check their status after connecting a social account to a profile. | [API keys](https://zernio.com/dashboard/api-keys) |
| Prodigi | Quote print jobs and test order submission. Submitting a live order can trigger paid printing and shipping. | [Sandbox API settings](https://sandbox-beta-dashboard.pwinty.com/settings/api) · [Live API settings](https://dashboard.prodigi.com/settings/api) |

## How agents use a provider

1. Read `godmode provider PROVIDER` and run `godmode list` to find saved names.
2. Look up the environment variable the installed tool expects. Pass only the keys it needs with `godmode run`, using `VARIABLE=SAVED_KEY` to rename a key for the command.
3. Make a read-only request to check the account, resource and permissions. Keep writes within the task the user authorized and verify their result at the provider.

The GitHub CLI can report the signed-in account using your saved `GH_TOKEN`.

```sh
godmode run GH_TOKEN -- gh api user --jq .login
```

With the Python package `higgsfield-client` installed, check a previous generation by substituting its request ID below. The aliases supply the two names the SDK reads. If your shell already defines the SDK’s combined `HF_KEY`, clear it for this command because it takes precedence.

```sh
env -u HF_KEY godmode run HF_API_KEY=HIGGSFIELD_API_KEY_ID \
  HF_API_SECRET=HIGGSFIELD_API_KEY_SECRET -- python3 -c \
  'import sys, higgsfield_client as hf; print(type(hf.status(sys.argv[1])).__name__)' REQUEST_ID
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
