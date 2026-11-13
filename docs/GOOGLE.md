# Google credentials

Google uses several JSON files. Choose the one your program expects:

| File | What it does | How to recognize it |
| --- | --- | --- |
| Service account key | Lets a program act as that service account. | `"type": "service_account"`, `client_email`, `private_key` |
| Desktop OAuth client | Identifies the app that asks you to sign in; it is not a saved login. | An `installed` object containing `client_id` |
| User OAuth grant | Lets a program obtain access tokens for the user who consented. | Usually `"type": "authorized_user"`, with `refresh_token` and client details |
| IAM policy | Describes who has permission on a Cloud resource; it is not a credential. | `bindings` containing roles and members |

Other Google credential formats exist. A valid JSON object alone does not establish what it can access. See Google's [credential types](https://docs.cloud.google.com/docs/authentication), [Desktop OAuth flow](https://developers.google.com/identity/protocols/oauth2/native-app), and [IAM policy format](https://docs.cloud.google.com/iam/docs/policies).

## Save and use a credential

Use Google's setup or sign-in flow first. Save the resulting credential under the name your program reads:

```sh
godmode set GOOGLE_ADS_SERVICE_ACCOUNT_JSON --stdin < /path/to/key.json
godmode run GOOGLE_ADS_SERVICE_ACCOUNT_JSON -- python3 your_ads_script.py
```

The bundled Ads and Search Console key entries accept service account keys only. For a user grant, use a separate name such as `GOOGLE_SEARCH_CONSOLE_OAUTH_JSON`; your program must support that format and read that variable. You can import it with the same `set NAME --stdin < file.json` command. Do not put a Desktop client or IAM policy into a service account key entry.

Godmode stores and supplies the value. It does not sign in, enable APIs, grant permissions, refresh tokens, or update Google's own login cache. Sealed storage prevents casual text reads; existing plain files remain plain until migrated. Keep credential downloads and provider-owned caches private and out of Git.

## Replace only what stopped working

- **Service account key:** create a new key on the same service account, save it under the same Godmode name, and verify the consumer before retiring the old key. Its short-lived access tokens are obtained by Google's auth library; the private key itself is not refreshed. Keys do not expire by default, but an organization policy can set expiry. [Key lifecycle](https://docs.cloud.google.com/iam/docs/service-account-creds), [rotation](https://docs.cloud.google.com/iam/docs/key-rotation).
- **User OAuth grant:** let the consuming Google library refresh access tokens. If Google requires consent again, repeat the provider's sign-in flow and import the new grant. A grant supplied through an environment variable cannot write an updated refresh token back to Godmode; if the consumer saves a replacement, import that replacement explicitly. [OAuth lifecycle](https://developers.google.com/identity/protocols/oauth2).
- **Desktop client:** reuse the existing client for sign-in unless Google or your app configuration requires a replacement. Changing the client is not a token refresh.
- **Gmail app password:** generate another in Google Account settings and replace `GMAIL_APP_PASSWORD`. Google revokes app passwords after an account password change. This password provides IMAP/SMTP access, not Gmail API or Google SSO. [App passwords](https://support.google.com/accounts/answer/185833).

## Account access is separate

For Ads, enable the API and obtain the appropriate API access level in the selected Cloud project, then grant the service-account email access in the intended Ads account. For Search Console, enable its API and give the selected identity access to each property. Keep existing Ads and Search identities/projects separate when replacing their credentials. [Ads setup](https://developers.google.com/google-ads/api/docs/oauth/service-accounts), [Search Console authorization](https://developers.google.com/webmaster-tools/v1/how-tos/authorizing).

A Google CLI login is not automatically the identity used by another program. Select the intended credential explicitly. A permission error may need account, scope, API or property access fixed; replacing a key does not grant those permissions.
