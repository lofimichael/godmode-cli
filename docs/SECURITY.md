# What happens to a pasted value

Menus are chosen with the arrow keys and never take a value: a paste into a menu is ignored and not shown. The terminal does not echo for the whole setup session, so text that arrives between two screens is dropped unseen. A paste that is too large or holds a NUL byte is read to its end before it is refused, so none of it can reach your shell.

1. The terminal reads it with echo disabled. A value pasted into an empty field is shown as its first and last three characters around five dots (`sk_•••••123`); values shorter than 24 characters show fewer, never more than a quarter of the value, and values under 8 characters show only dots. Pasting again replaces the value rather than appending to it. Typed or edited values show one dot per character and no ends, because otherwise each character would pass through the visible end while you type. A bracketed paste does not save until you press Enter.
2. Above the input, a preview titled "What will be executed on your machine" shows a shell command with the same effect on the file, updated as you paste: `printf '%s\n' 'KEY=…' >> ~/.godmode/.env.godmode` for a new key (with a leading line break when the file lacks a final one, and CRLF when the file uses it), `sed -i 's/^KEY=.*/KEY=…/' …` for a key saved on one ordinary line, and a line-numbered `sed` that also deletes extra lines when the key is indented, exported or listed more than once. The kind of command depends only on the file, never on the value, so it reveals nothing about hidden characters. Notes say when a line is rewritten, duplicates are removed, or a line keeps a CRLF ending. Run with the real value, these commands produce the same bytes as Godmode; the test suite checks that for LF files. Godmode makes the edit itself; no shell runs and nothing is sent. If the value cannot be saved (for example multiline text that is not JSON), the preview says why and Enter does nothing. After a successful save the screen is erased and one receipt line stays: `Saved KEY=sk_•••••123`. A few keys have a paste rule in providers.json: spaces are removed from a Gmail app password, and a Higgsfield key copied as `ID:SECRET` is split between its two entries. The preview always shows the value after the rule, as it will be stored. The rules follow the key at any prompt; `godmode set KEY --stdin` saves its input as given. Keys marked `"secret": false` in providers.json, such as the Gmail address, are shown as you type them; a paste into them is still masked, and the prompt for a custom key's name ignores pastes, so a secret pasted into the wrong field is never displayed in full.
3. The storage helper validates the key name, quotes the value, and replaces that key's assignment in `.env.godmode`.
4. A private temporary file is atomically renamed over the original. Unrelated lines are preserved.

That is the credential flow. No provider login, remote verification, telemetry, synchronization, database, daemon or command runner participates. The installed script is readable Python source; its file writer is [godmode_store.py](../lib/godmode_store.py), and its input handling is [godmode_terminal.py](../lib/godmode_terminal.py). Readability helps inspection; it is not a security guarantee.

## The file

`.env.godmode` is ordinary plaintext with shell-compatible quoting. Nano and your agents can use it without this CLI. No value is evaluated as shell code. Existing ownership, mode 0600, regular-file type and symlink checks apply before reads or writes. New directories are private. Git checkouts must ignore the credential file and must not track it.

An existing file is read again before saving; a directory lock coordinates cooperating CLI writers, and a changed file aborts the save. There are no persistent writer-lock or acknowledgement files. The new-home notice is shown before interactive creation. `set KEY --stdin` is an explicit noninteractive write; credentials are never accepted as positional arguments.

The file is limited to 1 MiB. A pasted multiline JSON object is compacted to one line; names ending in `_JSON` also require an object. Other values cannot contain control characters. Provider names and links are static help, not a validation or authorization system. There are no token-prefix rules or provider-specific credential factories.

The populator writes one assignment per line. Existing multiline or unfinished shell quoting is left untouched with a `godmode edit` instruction; nano can edit that file directly. Newly pasted JSON is compacted to a single line.

Mode 0600 keeps other ordinary users out. Programs running as you, privileged processes, backups and a compromised machine can still read the file. Python does not guarantee erasing every copy of a value from process memory. Use appropriate provider scopes and revoke exposed keys with the provider.

## Optional external actions

A provider page opens only when you press Enter on an empty key prompt; with a value entered, Enter saves instead. The browser opener is started in the background, so a slow browser cannot hold the prompt. The browser and nano receive a small ordinary process environment, not a loaded credential inventory. Nano displays the file's values while editing.

Picard is a separate, explicitly requested media feature. Its code never opens the credential file. It downloads only its pinned image/audio assets and starts only its own foreground player. See [Picard](PICARD.md).

The updater downloads release code and verifies its checksum. It updates only managed files unless replacement is explicitly requested. A checksum checks bytes against the published digest; it cannot protect against a compromised publisher. Shell-profile changes require `--path`. Credentials, operating rules and OAuth grants are never migrated by an update.

For a problem report, use synthetic keys. Do not include real credentials, OAuth grants or unredacted recordings. The MIT license is in [LICENSE](../LICENSE).
