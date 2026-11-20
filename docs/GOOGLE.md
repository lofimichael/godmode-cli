# Google credentials

Godmode bundles service-account key guides for Google Ads and Search Console. Run `godmode provider google` for the credential pages and the access each API requires.

## Save the credential your consumer needs

| Format | How to recognize it | What it does |
| --- | --- | --- |
| Service-account key | `"type": "service_account"`, `client_email`, `private_key` | Authenticates as a service account. |
| Desktop OAuth client | An `installed` object with `client_id` | Identifies the app during user sign-in. |
| User OAuth grant | Shape depends on the tool. Often `"type": "authorized_user"` and `refresh_token`. | Lets the approved client obtain access tokens for the user. |
| Access token | A short-lived bearer token | Authorizes API requests until it expires. |
| IAM policy | `bindings` containing roles and members | Configures resource permissions. |

For Ads, import a downloaded service-account key. The example assumes you have an Ads script that reads the named variable.

```sh
godmode set GOOGLE_ADS_SERVICE_ACCOUNT_JSON --stdin < /private/path/key.json
godmode run GOOGLE_ADS_SERVICE_ACCOUNT_JSON -- python3 your_ads_script.py
```

Use `GOOGLE_SEARCH_CONSOLE_SERVICE_ACCOUNT_JSON` for the bundled Search Console entry. Both bundled entries validate Google's service-account file shape. For a user grant, use the tool's own login cache or import the grant under a separate name such as `GOOGLE_SEARCH_CONSOLE_OAUTH_JSON`.

A consumer must parse the named JSON variable and configure its Google library. In Python, use `Credentials.from_service_account_info` with the API's scopes. `GOOGLE_APPLICATION_CREDENTIALS` expects a file path. [Python service-account credentials](https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.service_account.html), [Application Default Credentials](https://docs.cloud.google.com/docs/authentication/application-default-credentials).

## Verify the intended identity and account

- **Ads.** Enable the Ads API in the service account’s Cloud project and grant its email access to your Ads customer or manager. Check that project’s production access level. Keyword planning needs Basic access or Standard access that permits planning. List directly accessible customers. For a client reached through a manager, use the manager’s ID without hyphens as the `login-customer-id` header and the client’s ID in the request. [Ads service accounts](https://developers.google.com/google-ads/api/docs/oauth/service-accounts) · [Access levels](https://developers.google.com/google-ads/api/docs/api-policy/access-levels) · [List Ads accounts](https://developers.google.com/google-ads/api/docs/account-management/listing-accounts).
- **Search Console.** Enable the Search Console API in the project and ask a property owner to add the service-account email under **Settings → Users and permissions**. List sites to confirm the exact domain or URL-prefix property and your permission level. [Search Console sites listing](https://developers.google.com/webmaster-tools/v1/sites/list).
- **Gmail.** Run `godmode provider gmail` to connect a mail client with an app password. Use Google's OAuth flow for a Gmail API client. [Google OAuth](https://developers.google.com/identity/protocols/oauth2).

## Refresh

Google libraries handle routine access-token renewal. When a service-account private key needs replacing, create its replacement on the same service account, verify it, then retire the old key. [Service-account key rotation](https://docs.cloud.google.com/iam/docs/key-rotation).

A user OAuth grant can stop working after revocation, inactivity or policy changes. For an external app in **Testing**, refresh tokens normally expire after seven days unless the app only requests basic identity scopes. If Google asks for sign-in again, reconnect through the consuming tool's OAuth flow. Persist a replacement grant where that tool expects it. [Google OAuth lifecycle](https://developers.google.com/identity/protocols/oauth2), [Godmode recovery](PROVIDERS.md#refresh-and-recovery).
