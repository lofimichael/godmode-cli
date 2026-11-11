# Provider help

Choose a provider in `godmode`, or use `godmode setup github`. At each key prompt, Tab opens that key's page in your browser (Stripe live keys and the Prodigi sandbox key have their own), and `?` prints the step-by-step instructions with the full key-page, sign-in and documentation links. Esc returns to the provider list. Browsers open only when requested. A key's optional `console` field in providers.json overrides the provider page; `null` means it has none. `prompt` replaces the input label, and `"secret": false` shows a non-secret value, such as an email address, as typed.

Any key works without provider registration:

```sh
godmode set ACME_ACCOUNT_ADMIN_TOKEN
```

Paste the value at the masked prompt and check the preview of the line it writes. Enter on an empty prompt keeps an existing value. `godmode edit` opens nano for manual changes or removing keys.

The bundled provider list is static help in [providers.json](../providers.json). It does not authenticate, validate account permissions, enroll OAuth, or impose token-prefix rules. Runtime catalogs and overlays are no longer needed. Never put credentials in this help file.

## Bundled guides

The bundled [guidance](../providers.json) covers the following providers. Public sign-in and documentation entry points were checked on **2026-11-04**. This was a link review without signing in or submitting credentials; some provider pages require JavaScript. Interfaces and permission models can change, so confirm the account and scope in the provider before relying on a credential.

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
