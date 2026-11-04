# Storage and authority

The credentials you store here may allow agents to create and delete infrastructure, spend money, publish, send mail and commit as you. Check those permissions at the provider. Godmode records the keys you choose; it does not sandbox the programs using them or enforce a spending limit.

The credential inventory is plaintext. Mode 0600 prevents other ordinary users from reading the file; it does not prevent your own user, unrestricted agents, privileged processes, backups or a compromised machine from accessing it. Select appropriate provider scopes, protect the host and revoke exposed credentials at their source. Saving a live key is not authorization to spend money or publish.

## What the CLI does

- Stores one flat `.env.godmode`, with shell-compatible quoting and no evaluation of shell expressions.
- Preserves unrelated content during edits and checks ownership, permissions, file type, size and symlink components.
- Serializes cooperating writers and replaces the file atomically; temporary credential files are private.
- Requires an acknowledgment before mutations. Acknowledgment is a local receipt, not an enforceable authorization boundary.
- Prints names and local states. Masked input has no reveal control, and parsing errors suppress credential content.
- Makes no provider API calls and sends no telemetry. Provider verification guidance is for a separate manual operation. Explicit Picard picture/audio requests download pinned media from YTMND; the standalone commands do not read credentials, and no credentials are sent. Browser links open only on command.

Use `doctor` for offline file checks. Its success does not demonstrate that a provider accepts a token, that the token belongs to the intended account, or that a requested operation is authorized. Provider-specific prefix hints are not authentication. Wrong-environment prefixes declared in the catalog are refused; arbitrary providers can declare their own metadata.

The CLI reads at most 1 MiB of credential input and refuses oversized credential files. Ordinary values cannot contain control characters. Keys marked `json = true` accept a JSON object and compact it to one line before quoting.

## Child processes and other applications

`run` passes only the selected stored credentials plus a small basic process environment to a child. The child is an ordinary process running as you: it can access your files, make network requests, print secrets, write logs or start more processes. Its output is not filtered. This command reduces accidental environment sharing; it does not confine the child.

Do not run an untrusted command merely because its environment is restricted. Avoid putting credentials directly into argv or shell history. Use masked input, stdin or a private file when importing them.

## Existing installations

The installer refuses an existing executable unless replacement is explicitly requested with `--force`, and always refuses a symlink destination. It verifies a supplied SHA-256 digest before installation and makes no network requests. Checksums establish integrity relative to the supplied digest, not publisher identity.

The CLI does not install hooks, edit shell profiles, replace operating rules, synchronize credentials or enroll OAuth sessions. Test with explicit configuration and state directories when evaluating it alongside an existing installation.

## Reporting a problem

For a suspected credential leak, revoke or rotate the affected key with its provider first. Share a minimal reproduction using synthetic values. Never include your credential file, real tokens, OAuth grants, authorization URLs or unredacted terminal recordings in an issue.

MIT license warranty and liability terms are in [LICENSE](../LICENSE).

## Picard media

Picard mode is optional. It downloads the pinned source image or recording only when that item is requested and caches it under the CLI state directory. Neither source asset is bundled in the executable or release archive. The image is decoded with size limits and rendered as terminal cells; it does not run page scripts or emit downloaded terminal control sequences. The local player is an owned child process; stopping it does not search for or kill arbitrary audio processes. Playback ends when its foreground controller or provider board exits. External `picard stop` uses a private local control socket, not a remembered process ID. See [PICARD.md](PICARD.md) for the source and current playback requirements.
