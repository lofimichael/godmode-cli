# What happens to a pasted value

1. The terminal reads it with echo disabled and displays only a mask. A bracketed paste does not save until you press Enter.
2. The storage helper validates the key name, quotes the value, and replaces that key's assignment in `.env.godmode`.
3. A private temporary file is atomically renamed over the original. Unrelated lines are preserved.

That is the credential flow. No provider login, remote verification, telemetry, synchronization, database, daemon or command runner participates. The installed script is readable Python source; its file writer is [godmode_store.py](../lib/godmode_store.py), and its input handling is [godmode_terminal.py](../lib/godmode_terminal.py). Readability helps inspection; it is not a security guarantee.

## The file

`.env.godmode` is ordinary plaintext with shell-compatible quoting. Nano and your agents can use it without this CLI. No value is evaluated as shell code. Existing ownership, mode 0600, regular-file type and symlink checks apply before reads or writes. New directories are private. Git checkouts must ignore the credential file and must not track it.

An existing file is read again before saving; a directory lock coordinates cooperating CLI writers, and a changed file aborts the save. There are no persistent writer-lock or acknowledgement files. The new-home notice is shown before interactive creation. `set KEY --stdin` is an explicit noninteractive write; credentials are never accepted as positional arguments.

The file is limited to 1 MiB. A pasted multiline JSON object is compacted to one line; names ending in `_JSON` also require an object. Other values cannot contain control characters. Provider names and links are static help, not a validation or authorization system. There are no token-prefix rules or provider-specific credential factories.

The populator writes one assignment per line. Existing multiline or unfinished shell quoting is left untouched with a `godmode edit` instruction; nano can edit that file directly. Newly pasted JSON is compacted to a single line.

Mode 0600 keeps other ordinary users out. Programs running as you, privileged processes, backups and a compromised machine can still read the file. Python does not guarantee erasing every copy of a value from process memory. Use appropriate provider scopes and revoke exposed keys with the provider.

## Optional external actions

Provider pages open only after you choose their browser action. The browser and nano receive a small ordinary process environment, not a loaded credential inventory. Nano displays the file's values while editing.

Picard is a separate, explicitly requested media feature. Its code never opens the credential file. It downloads only its pinned image/audio assets and starts only its own foreground player. See [Picard](PICARD.md).

The updater downloads release code and verifies its checksum. It updates only managed files unless replacement is explicitly requested. A checksum checks bytes against the published digest; it cannot protect against a compromised publisher. Shell-profile changes require `--path`. Credentials, operating rules and OAuth grants are never migrated by an update.

For a problem report, use synthetic keys. Do not include real credentials, OAuth grants or unredacted recordings. The MIT license is in [LICENSE](../LICENSE).
