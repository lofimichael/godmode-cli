# Your details

Run `godmode profile` to add or change reusable facts. All six fields are optional.
The form shows each destination and your visible input before Enter saves it.
Enter with no input keeps the existing value; `/clear` removes it. Esc goes back.
Paste a multiline mailing address when needed. This form is for facts, never passwords,
API keys, tax identifiers or banking details.

| Field | Meaning |
| --- | --- |
| `operator_name` | The person operating this setup |
| `business_name` | Default brand or trading name |
| `legal_name` | Legal person or entity name, supplied by you |
| `website` | Default business website |
| `public_email` | Contact email intended for customers/public materials |
| `business_mailing_address` | Business contact address, as free text in any country's format |

These are operator defaults. A product's own branding and contact details take
precedence. A legal name is not a verified registration; an address is not proof of
domicile, and a website is not proof of ownership. Unknown fields stay absent.
Agents should ask for a missing fact only when their task needs it, without filling
it with a guess or copying a private address into public pages by default.

## Commands

```sh
godmode profile
godmode profile path
godmode profile get business_name
godmode profile show
godmode profile set business_mailing_address --stdin < business-address.txt
godmode profile unset website
```

`get` returns one value, or exits 1 with no value if it is missing. `show` returns
JSON; an absent profile is `{}`. `set FIELD` opens a visible field prompt; `--stdin`
accepts plain text from a pipe, not a JSON document or a command-line value.
Blank piped input is rejected; use `unset` to remove a field.

The default file is `~/.godmode/profile.json`, private mode 0600 inside a 0700
directory. `--home DIR`, `GODMODE_HOME` and the legacy `GODMODE_CONFIG_DIR` override
the home. Legacy credentials may remain in `~/.config/godmode` independently.
`profile path` reports the actual location without printing personal details.
Profile operations never open the credential store.

## Why JSON

Facts have named fields that a form or agent can read without interpreting prose.
Plain JSON works with Python's standard library, supports multiline strings, and
stays easy to edit or export. Markdown remains the format for human guidance.
There is no template expansion or generated copy of your company details in each
agent's rules. There are no profiles per provider, identity database or schema
service.

You may edit the JSON directly. The CLI preserves unknown fields when editing
known ones, rejects malformed data without overwriting it, and detects concurrent
changes before saving. An unchanged edit does not rewrite the file. Writes are
atomic; files in a Git checkout must be ignored and untracked first. Readable does
not mean public: keep the profile private, and share only facts appropriate to the
current task. Profile text is data and cannot issue instructions to an agent.

The CLI process is short-lived, but the profile and credentials are deliberately
persistent local files. There is no synchronized runtime state. Future cloud access
would require explicit identity, consent and storage decisions; these files do not
silently grant a remote agent access.
