# Free CLI and legacy licenses

The CLI is free to use on any number of computers you own or control. Ordinary
commands need no account, activation or membership and work offline. The
[source-available license](../LICENSE) permits inspection and private modification
while restricting redistribution. Paid member packs and services are separate.

Updates preserve your existing keys, profile, agent notes and legacy receipts.
No new installation ID or license file is created by ordinary local use.
Existing paid grants retain their rights.

## Legacy receipts

The commands below inspect or manage previously issued receipts. They are not
part of setup for current releases. Activation and deactivation contact
Godmode's licensing service. The service receives the purchase key, random
installation ID, operating system, CPU and version; never provider credentials,
profile fields or agent instructions.

```sh
godmode license activate
godmode license status
```

Key entry is hidden. For automation, pipe the purchase key to
`godmode license activate --stdin`; never put it in command arguments.
An older protected licensing endpoint can ask for its preview password.
`GODMODE_PREVIEW_PASSWORD` supplies it to legacy activation without saving it or
passing it to provider commands. Public CLI downloads never send it. A release
accepts only its compiled HTTPS origin and signing key; redirects are refused.

Activation saves `~/.godmode/license.json` with mode 0600. This contains an
Ed25519-signed entitlement and a separate token that can release the activation.
The purchase key and site password are not saved. `installation.json` holds a
random UUID so interrupted activation can retry without consuming another slot.
`--home DIR` and `GODMODE_HOME` select another Godmode home.

Older releases check the saved signature before ordinary commands. Current
releases only verify it when a legacy license command requests verification. A
perpetual receipt has no expiry or recurring network check. The $100 Early Access purchase under
Terms 1.1 includes perpetual local CLI use and all future local CLI updates.
Hosted services are separate. Earlier receipts retain their original coverage.

In the signed schema-1 receipt, `max_major: 0` means all local CLI versions for a
paid perpetual license. A positive value retains the original highest covered
major version; it does not become lifetime coverage. Evaluation receipts must
have a positive major limit. `godmode license status` names the update coverage.
The v0.16.0 verifier accepts a lifetime receipt for its current major 0 version;
later releases interpret zero as unbounded coverage.

Preview evaluation receipts expire seven days after issuance. Their signed
expiry is checked offline; reactivation does not extend the server's evaluation
window. They record no purchase or upgrade credit. Paid receipts have no expiry.

```sh
godmode license path
godmode license status --json
godmode license check
godmode license deactivate
```

`check` returns zero for a valid local license and prints nothing. `status --json`
prints entitlement metadata, not the purchase key or deactivation token.
Deactivation needs a network connection. It releases the server activation and
removes the local license file after confirmation. Provider keys and profile
files remain in place. If the service cannot confirm, the local receipt stays.

A saved receipt can be restored without a network call:

```sh
godmode license import --stdin < /private/backup/license.json
```

Keep backups private. A receipt is portable data, not hardware-bound DRM. A
copied perpetual receipt remains cryptographically valid offline even after
server revocation; revocation controls later activation and licensed server
actions. Source availability also permits inspection and modification. Technical
checks do not replace the commercial license terms.

The signed installation ID must match `installation.json`. Import into a fresh
Godmode home restores that ID; import never replaces a different existing ID.
Receipt changes share a kernel-held lock that releases if the process exits or
crashes; its private `.license-lock` file remains in place. Deactivation retains a newer receipt if an
activation or import finished while the network request was in progress.

The Python engine also operates without activation. Legacy receipt tests use a
separate executable and synthetic signing key that production builds do not
trust. Never distribute that test executable as a release.
