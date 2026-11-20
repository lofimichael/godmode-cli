# How Godmode handles keys

Godmode stores provider keys on your machine. New key files store each value as authenticated ciphertext. Anyone with a key file and its matching `seal.key` can recover the values. Programs running as you can also request saved keys through Godmode, so only pass keys to commands you trust.

For vulnerability reports, see [SECURITY.md](../SECURITY.md).

## The key file

- Each value gets a fresh nonce. Godmode encrypts it with an HMAC-SHA256 keystream and authenticates the ciphertext and key name with a separate HMAC-SHA256 tag. See [the storage code](../lib/godmode_store.py).
- The key file and `seal.key` must be regular files you own with mode 0600. Godmode rejects symlinks at the home or private files. New directories use mode 0700, and each key file has a 1 MiB limit.
- Saves use a lock and atomic replacement, preserve unrelated lines and abort when a concurrent edit is detected. In a Git checkout, keep the key files and `seal.key` ignored and untracked.
- Use `godmode set NAME` to replace a value and `godmode path` to locate the selected file. Older plain-text stores can be sealed with [the migration workflow](INSTALLATION.md#upgrading-from-09-or-earlier).

## Entering a key

Interactive loadout shows a masked preview of a secret and the destination before a save. Provider-specific rules can normalize a pasted value, such as removing spaces from a Gmail app password. With `godmode set NAME --stdin`, use a pipe or file. The stored format still applies, including JSON validation for names ending in `_JSON`.

The native interface sends new values to the local file engine over a private pipe. The engine returns masks and save status to the UI. Keep secrets out of shell arguments and logs.

## How agents reach keys

Use `godmode list` for key names. Use `godmode run NAME -- command` to supply that key in a child's environment. The child inherits the usual environment and runs with your account's permissions. Missing or unreadable keys stop the command before launch.

Pass only the needed keys and avoid environment dumps and shell tracing around sensitive commands. Keep the key file, seal key and imported credential files out of agent inputs and logs. The user's task defines which provider operations are authorized.

## Other actions

| Action | What to expect |
| --- | --- |
| Profile and key commands | Local operation, including offline use. The profile is plain JSON. |
| Open a provider link | Opens the provider page in your browser. |
| Install or update | Downloads public release files unless you select an [offline install](INSTALLATION.md#install-offline). |
| Legacy license commands | Activation and deactivation contact `godmode.build`. See [Licensing](LICENSING.md). |
| `godmode run` | The child can access the network according to its own configuration. |

Revoke an exposed credential at the provider. Local edits only change the selected key file.

## Source and releases

`godmode source` prints the embedded Python file engine. `godmode build-info` lists the Go compiler, dependency versions and engine SHA-256. The release's separate source archive includes the Go interface, build scripts and vendored dependencies.

To compare an installed binary against reviewed source, check out the matching release commit and select the exact Go toolchain in `go.mod`. Confirm the selected compiler with `GOTOOLCHAIN=local go version`. Rebuild on the same OS and architecture as the installed binary.

```sh
GOPROXY=off GOSUMDB=off sh scripts/build-native.sh
cmp target/godmode-native "$(command -v godmode)"
godmode source > target/installed-core.py
python3 scripts/build.py --verify target/installed-core.py
```

The installer verifies the archive against `SHA256SUMS`. An independent rebuild from reviewed source gives you a separate comparison if the archive and its checksum share a publisher. See [Installation](INSTALLATION.md) for the release files and offline options.
