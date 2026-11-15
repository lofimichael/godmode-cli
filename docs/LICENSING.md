# Godmode licenses

A Godmode purchase licenses the local CLI. Provider credentials remain on your
machine. The license service receives a purchase key, a random installation ID,
your operating system and CPU, and the Godmode version. It receives no provider
keys, business profile, hardware fingerprint, or agent instructions.

```sh
godmode license activate
godmode license status
```

Key entry is hidden. For automation, pipe the purchase key to
`godmode license activate --stdin`; never put it in command arguments.
The private site also asks for its password. Automated activation can receive
that password through `GODMODE_PREVIEW_PASSWORD`. It is not written to disk or
passed to provider commands. A release accepts only its compiled HTTPS origin
and signing key; redirects are refused.

Activation saves `~/.godmode/license.json` with mode 0600. This contains an
Ed25519-signed entitlement and a separate token that can release the activation.
The purchase key and site password are not saved. `installation.json` holds a
random UUID so interrupted activation can retry without consuming another slot.
`--home DIR` and `GODMODE_HOME` select another Godmode home.

Every ordinary command checks the saved signature locally. A perpetual receipt
has no expiry or recurring network check. It names the highest licensed major
version. A future major upgrade can require another entitlement; an already
licensed version continues working offline.

Preview evaluation receipts expire seven days after issuance. Their signed
expiry is checked offline; reactivation does not extend the server's evaluation
window. They record no purchase or upgrade credit. Paid receipts have no expiry.

Help, FAQ, source, build information, version, path, saved key names, and license
commands remain available without activation. Failed verification changes no
provider credentials or profile data. Keep your previous executable when
upgrading. The existing installed v0.15.1 executable stays unchanged until you
choose to replace it.

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

The Python engine invokes its containing native executable for verification.
Direct Python entry exposes inspection and help; ordinary use requires the
native command. Build it with `scripts/build-native.sh` from the supplied source.

Tests use a separate executable and a synthetic signing key that production
builds do not trust. `scripts/build-license-test.sh` produces that test candidate;
`scripts/build-native.sh` produces the normal licensed candidate. Never distribute
the test executable as a release.
