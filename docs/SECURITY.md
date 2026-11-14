# How Godmode handles keys

Values are encrypted in .env.godmode with a random key in seal.key.
Reading the file shows names, never values.
Any program running as you can still ask godmode for a key.
Anyone with both files has every key.
Godmode sends nothing over the network.

To report a vulnerability, see [SECURITY.md](../SECURITY.md).

## The key file

- Each value is stored as `sealed:v1:…`: encrypted with HMAC-SHA256 in counter mode and authenticated with a second HMAC-SHA256 tag. `seal.key` holds a random 32-byte key; each value gets a fresh nonce, and the key's name is bound into the tag, so a value cannot be moved to another name. The code is in [godmode_store.py](../lib/godmode_store.py).
- Sealing keeps values out of anything that reads the file as text: `cat`, `grep`, editors, agent transcripts and copies of the file alone. It is not a lock, and it does not sandbox programs or limit spending.
- `.env.godmode`, `seal.key` and `profile.json` must be regular files you own with mode 0600, in a directory you own that others cannot write. Godmode refuses a symlink at the home or any of these files, and checks ownership, type and mode before every read and write. New directories are 0700.
- The key file is limited to 1 MiB.
- A save reads the file again, takes a directory lock, writes a private temporary file and renames it over the original. Unrelated lines are kept, and a file changed by another program aborts the save.
- A Git checkout that holds the home must ignore `.env.godmode` and `seal.key` and must not track them.
- The file starts with a short header naming the commands to use. `STOP_AND_READ_ME_FOR_KEYS.md` beside it says the same to an agent that lists the folder; Godmode writes it once and never overwrites it.
- A sealed file keeps no comments or other text. `godmode migrate` seals a plain value added by hand and names any other line for you to delete; `godmode help` says how many remain.
- `godmode edit` opens the file in nano. A sealed file shows names and ciphertext there; use `godmode set` to change a value.
- Older plain-text files are covered in [Upgrading from 0.9 or earlier](INSTALLATION.md#upgrading-from-09-or-earlier).

## Entering a key

- The terminal reads it with echo off. A pasted value shows as its first and last three characters around five dots (`sk_•••••123`). Values shorter than 24 characters show fewer, never more than a quarter of the value, and values under 8 characters show only dots. Typed values show one dot per character. Pasting again replaces the value.
- Menus ignore pastes, and text that arrives between screens is dropped. A paste that is too large or holds a NUL byte is read to its end and refused, so none of it reaches your shell.
- The save preview shows the destination file and `Add NAME=…` or `Replace NAME=…`, with the value masked. Tab opens the shell equivalent: `printf` for a new key or `sed` for a saved one. The command depends on the file, never on the value. For a plain file, that command with the real value produces the same bytes; the tests check this. For a sealed file, `sealed(…)` represents encrypted data. Godmode writes the file itself; no shell runs.
- If a value cannot be saved, for example multiline text that is not JSON, the preview says why and Enter does nothing. After a save, one receipt line stays: `✓ Saved NAME=sealed(sk_•••••123)`.
- Some keys have a paste rule in providers.json: spaces are removed from a Gmail app password, and a Higgsfield key copied as `ID:SECRET` is split between its two entries. The preview shows the value after the rule. `godmode set NAME --stdin` saves its input as given.
- Keys marked `"secret": false`, such as the Gmail address, show typed input; a paste into them is still masked. The prompt for a custom key's name ignores pastes.
- A pasted multiline JSON object is compacted to one line. Names ending in `_JSON` require an object and accept a dragged file. Godmode reads one snapshot of that file and validates, previews and saves the same snapshot, and leaves the file in place; delete a downloaded key when no tool needs it.
- JSON gets syntax checks only. The two Google service-account keys also check Google's file shape (`"type": "service_account"`, `project_id`, `private_key_id`, a PEM `private_key`, a `…gserviceaccount.com` `client_email` and Google's `token_uri`).
- Values cannot contain control characters, and no value is evaluated as shell code. Keys are never accepted as command-line arguments.
- `--plain` or `GODMODE_PLAIN=1` uses static prompts. Input stays hidden until Enter displays a masked review; a second Enter submits it. Pasted newlines never submit a value.
- Python cannot guarantee that every copy of a value is erased from memory.

## How agents reach keys

- `godmode list` prints the names of saved keys, never values.
- `godmode run NAME... -- command` replaces itself with the command, adding only the named keys to its environment and their names to `GODMODE_KEYS`. It prints nothing. A missing or unreadable key stops it before the command starts, naming the key only. The exit status is the command's own.
- `godmode set NAME --stdin` saves a key from a pipe or file redirection.

## Other actions

- Profile input is visible and saved as plain JSON. Terminal control characters are escaped while you type and refused in saved fields; the mailing address allows line breaks.
- A provider page opens only when you press Enter on an empty key prompt. The browser opener runs in the background with a small ordinary environment, not your keys; nano gets the same.
- `godmode picard` downloads its pinned image and audio from YTMND only when asked, and never opens the key file. See [Picard](PICARD.md).
- The installer and `godmodeup` check each download's SHA-256 against `SHA256SUMS` and replace only files they installed. A checksum cannot protect against a compromised publisher. Shell startup files change only with `--path`, and updates never touch your profile or keys.
- In a problem report, use synthetic keys. Never include real keys, OAuth grants or unredacted recordings. Deleting a key here does not revoke it; revoke an exposed key at the provider.
