# Profile

Save optional business details for your agent to reuse. Open **Business details** in `godmode`, or run `godmode profile`. Enter on an empty input keeps the saved value or skips the field. Use `/clear` to remove a saved value.

| Field | Use |
| --- | --- |
| `operator_name` | Your name as it should appear in a signature |
| `business_name` | The trading name customers see |
| `legal_name` | The registered company or sole trader name |
| `website` | The business website |
| `public_email` | The address to use for public contact |
| `business_mailing_address` | Postal address for invoices or footers. Line breaks are allowed. |

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
