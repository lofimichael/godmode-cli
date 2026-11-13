# Google credentials

Run `godmode provider google` for the bundled Ads and Search Console setup pages, account prerequisites, verification steps and recovery references. Google credentials have different jobs; choose the format your consuming program supports.

| File or value | Purpose | Recognizable fields |
| --- | --- | --- |
| Service-account key JSON | Lets a program authenticate as that service account and obtain access tokens. | `"type": "service_account"`, `client_email`, `private_key` |
| Desktop OAuth client JSON | Identifies the app during user sign-in. It is not a saved login. | An `installed` object with `client_id` and client configuration |
| User OAuth refresh grant | Lets the authorized client obtain access tokens for the consenting user. | Often `"type": "authorized_user"`, `refresh_token` and client details; formats vary by tool |
| Access token | Authorizes API requests for a limited time. | A bearer token; it is not the durable refresh credential |
| IAM policy JSON | Assigns roles to identities on a Cloud resource. It cannot authenticate. | `bindings` containing roles and members |

Other Google credential formats exist. A JSON object by itself does not prove that it is a credential or can access a particular account. The file's role follows Google's [service-account model](https://docs.cloud.google.com/iam/docs/service-account-creds), [Desktop OAuth flow](https://developers.google.com/identity/protocols/oauth2/native-app), and [IAM policy format](https://docs.cloud.google.com/iam/docs/allow-policies).

## Save the credential your consumer needs

Complete Google's setup or sign-in flow, then save its resulting credential under the name your consumer reads:

```sh
godmode set GOOGLE_ADS_SERVICE_ACCOUNT_JSON --stdin < /private/path/key.json
godmode run GOOGLE_ADS_SERVICE_ACCOUNT_JSON -- python3 your_ads_script.py
```

`your_ads_script.py` represents your own consumer. The bundled Ads and Search Console entries accept service-account keys only. A Desktop client, user grant or IAM policy is not interchangeable with that key. For a user grant, choose a separate name such as `GOOGLE_SEARCH_CONSOLE_OAUTH_JSON` and import it with `godmode set NAME --stdin < /private/path/grant.json`.

These JSON variable names are Godmode conventions. A Google SDK does not automatically discover them. Your consumer must parse the variable and configure the official library, or provide the credential using that tool's supported private-file mechanism. `GOOGLE_APPLICATION_CREDENTIALS`, for example, expects a **file path**, not the JSON contents. The Python auth library supports loading a parsed service-account object with `Credentials.from_service_account_info`; use the library's API-specific scopes and authenticated transport rather than printing access tokens. [Python service-account credentials](https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.service_account.html), [Application Default Credentials](https://docs.cloud.google.com/docs/authentication/application-default-credentials).

Godmode stores and supplies values. It does not sign in, enable APIs, grant roles, refresh credentials or update a provider's own login cache. Keep credential downloads and caches private and out of Git. Preserve a working provider-owned credential store unless the task calls for migrating it.

## Refresh is usually routine

A service-account key and an OAuth refresh grant can both support unattended API calls. The consuming library obtains new access tokens when needed. An expired access token alone does not require a new private key, new OAuth client or user consent. Service-account private keys are long-lived unless an organization sets an expiry or the key is disabled or deleted. [Service-account credential lifecycle](https://docs.cloud.google.com/iam/docs/service-account-creds).

For user OAuth, request the access your workflow needs through the client's documented flow and retain the refresh grant. A valid refresh grant normally avoids repeated browser sign-in. Google can invalidate it after revocation, long inactivity, some password changes, token limits or policy changes. External OAuth apps in **Testing** normally receive refresh tokens that expire after seven days, with an exception for basic identity-only scopes. Use the appropriate consent-screen publishing configuration for ongoing use and complete any required verification. A production setting does not guarantee permanent access. [Google OAuth lifecycle](https://developers.google.com/identity/protocols/oauth2), [Desktop authorization and offline access](https://developers.google.com/identity/protocols/oauth2/native-app).

If refresh fails, inspect the error and subtype. Fix a scope, client or account-policy issue when that is the cause. If the underlying grant is invalid or Google requires renewed sign-in, run the consuming tool's official authorization flow, complete the human step, and import the replacement grant. If a library rotates or otherwise saves a replacement refresh credential, import that value explicitly; `godmode run` does not write it back.

For a failed service-account private key, replace the key on the **same service account**, verify the consumer, and retire the old key. This preserves the identity's existing account/property grants. Rotating the key is separate from routine access-token renewal. [Service-account key rotation](https://docs.cloud.google.com/iam/docs/key-rotation).

## Verify the intended identity and account

Account access is separate from authentication. Use `godmode provider google` for the current Ads project/API and Search Console property requirements. The consumer must select the intended credential and requested scope; a Google CLI login does not automatically become another program's identity.

For Ads, listing accessible customers shows direct access and may omit client accounts reached through a manager. Confirm the intended manager/client relationship before a report or mutation. For Search Console, list sites and check the exact URL-prefix or domain property and permission level. A successful token exchange does not establish those rights. [Ads account listing](https://developers.google.com/google-ads/api/docs/account-management/listing-accounts), [Search Console sites listing](https://developers.google.com/webmaster-tools/v1/sites/list).

For Gmail app-password use, read `godmode provider gmail`. That password is for supported mail clients and does not provide Gmail API access, Google SSO or Workspace administration. OAuth-based Gmail clients use their own provider authorization and refresh flow.
