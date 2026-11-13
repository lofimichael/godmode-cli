# Google credentials

The static credential inventory can hold service-account JSON for Google Ads or Search Console. Drag the downloaded key file onto the prompt (or paste its contents, or use `godmode set KEY --stdin < file.json`). Godmode checks it has the standard service-account shape, names the service account it found, compacts it and stores it sealed (as plain text while your keys are still in an older plain `~/.config/godmode` file; `godmode migrate` seals them). Use it with `godmode run GOOGLE_ADS_SERVICE_ACCOUNT_JSON -- command`. It does not contact Google, enable APIs, obtain access approval or verify account permissions.

For Ads, enable the API and obtain the appropriate access level in your Cloud project, then grant the service-account email access in the intended Ads account. Follow Google's [service-account setup](https://developers.google.com/google-ads/api/docs/oauth/service-accounts). Keep API use within your approved advertising purpose.

Search Console is separate. The application requests an OAuth token with the appropriate scope, and the authenticated principal needs access to the owned property. `webmasters.readonly` covers reporting; `webmasters` permits supported writes. See [Search Console authorization](https://developers.google.com/webmaster-tools/v1/how-tos/authorizing).

## Desktop OAuth stays outside the inventory

User OAuth enrollment requires browser consent and a configured desktop client. Use an appropriate OAuth client and Google's [desktop application flow](https://developers.google.com/identity/protocols/oauth2/native-app). This CLI does not implement that enrollment or refresh flow.

Keep the static desktop client JSON in a private, ignored local file, such as `~/.config/godmode/google-oauth-client.json`. Keep generated refresh grants in a separate private state directory, such as `~/.local/state/godmode/auth/google/`, with mode 0700 directories and 0600 files. Do not paste refresh grants into `.env.godmode`, provider catalogs, Git or cloud-sync folders. This separation is the Godmode storage convention; the OAuth implementation must still follow Google's requirements.

A configured Google CLI login is not automatically the identity used by another script or service account. Select and verify the intended profile or credential explicitly. Never infer Gmail API, Workspace administration or Ads account authority from a successful Google sign-in.
