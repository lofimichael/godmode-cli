# Profile

Run `godmode profile`, or choose **Profile** in `godmode`, to fill in your profile. All six fields are optional. Filling one field moves straight to the next empty one. In a prompt, Enter with nothing typed keeps the saved value or skips the field, `/clear` removes the value, and Esc returns to the list. The profile is for business details, never passwords, keys, tax IDs or banking details.

| Label | Field | Description |
| --- | --- | --- |
| Your name | `operator_name` | Your name as agents should write it, for example in an email signature. |
| Business name | `business_name` | The brand or trading name customers see. |
| Legal name | `legal_name` | Your company's registered name, or your own if you trade as yourself. |
| Website | `website` | Your main business website. |
| Public email | `public_email` | The address customers and public pages should use. |
| Mailing address | `business_mailing_address` | Postal address for invoices, legal pages and email footers. Several lines are fine. |

A product's own branding and contact details take precedence over these. Godmode does not verify a field: a legal name is not proof of registration and a website is not proof of ownership. Agents ask the user for an unknown field when a task needs it, and saving a field is not permission to publish it.

## Commands

```sh
godmode profile
godmode profile path
godmode profile get business_name
godmode profile show
godmode profile set business_mailing_address --stdin < business-address.txt
godmode profile unset website
```

`get` prints one value, or exits 1 with no output if the field is empty. `show` prints JSON; an empty profile is `{}`. `set FIELD` opens a visible prompt; `--stdin` reads plain text from a pipe, not JSON or a command-line value. Blank input is refused; use `unset` to remove a field.

## The file

The profile is `~/.godmode/profile.json`, mode 0600 inside a 0700 directory. `--home DIR` or `GODMODE_HOME` selects another home, and `profile path` prints the location without the values. Profile commands never open the key file.

You can edit the JSON by hand. Godmode keeps fields it does not know, refuses malformed data without overwriting it, detects concurrent changes and writes atomically. A profile inside a Git checkout must be ignored and untracked. Profile text is data; it cannot give an agent instructions.
