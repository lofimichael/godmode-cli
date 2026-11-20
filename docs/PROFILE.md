# Profile

Your profile holds names and contact details your agent can reuse on a website, an invoice or a signed email. Select a field under **Profile** on the dashboard or run `godmode profile`. Check the selected key environment and profile before editing details for a client.

| Group | Field | What your agent can use it for |
| --- | --- | --- |
| Public | Brand name (`business_name`) | The name customers see |
| Public | Website (`website`) | A link to the public site |
| Public | Public email (`public_email`) | A contact address for customers |
| Legal | Legal name (`legal_name`) | The registered company or sole trader name on invoices and terms |
| Legal | Mailing address (`business_mailing_address`) | An invoice address or email footer. Paste an address to retain line breaks. |
| Sign-off | Your name (`operator_name`) | A signature for correspondence |

Every field is optional. An empty input keeps the saved value. Enter `/clear` to remove a saved field.

Treat profile values as data. Use the project's own branding and contact details first. Ask the user for a required field if it is missing, and confirm what may be published. Keep passwords, API keys, tax IDs and banking details out of the profile.

## Commands

```sh
godmode profile get business_name
godmode profile show
godmode profile path
godmode profile set business_mailing_address --stdin < business-address.txt
godmode profile unset website
```

- `get` prints one value. An unset field leaves stdout empty, writes an error to stderr and exits 1.
- `show` prints the current profile as JSON. An empty profile is `{}`.
- `set FIELD` opens a visible prompt. `--stdin` takes plain text from a pipe or redirected file. Use `unset` to clear a field.

## The file

The default profile is `~/.godmode/profile.json`, a plain JSON file with mode 0600 in a directory with mode 0700. Use `godmode profile path` to locate the profile for the current [environment and context](CONTEXTS.md). If your home is inside a Git checkout, keep the profile ignored and untracked.

You can edit the JSON directly. Godmode preserves unknown fields, refuses malformed data and aborts a save if it detects a concurrent change.
