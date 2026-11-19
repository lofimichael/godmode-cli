# Free CLI and legacy licenses

You can install and use Godmode on any number of computers you own or control. The CLI works locally without an account, activation, or membership. The [Godmode Free Source-Available License](../LICENSE) permits inspection, local use, and private modification, and restricts redistribution. Member packs and hosted services have separate terms.

## Earlier purchases

Valid earlier grants retain their original terms. A paid Early Access purchase under [Terms 1.1](https://godmode.build/licenses/godmode-1.1.txt) included perpetual local use and future local CLI updates. Use your original purchase terms for the scope of any other grant. Current CLI updates preserve existing receipts.

## Legacy receipts

Use these commands if you have a previously issued signed receipt.

| Command | Action |
| --- | --- |
| `godmode license status` | Show the receipt’s update coverage and evaluation expiry, if applicable. Add `--json` for metadata and the local path. |
| `godmode license check` | Verify the receipt offline. A valid receipt returns exit code 0 with no output. |
| `godmode license path` | Print the path to the receipt. |
| `godmode license activate` | Enter a previously issued purchase key at the hidden prompt. Use `--stdin` for input from a protected pipe or file. |
| `godmode license deactivate` | Release an activation. Godmode removes the local receipt after the service confirms and preserves your provider keys and profile. |

For an offline restore, import a private backup:

```sh
godmode license import --stdin < /private/backup/license.json
```

Import restores the signed installation ID in a fresh Godmode home. If there is already an installation ID, it must match the one in the receipt.

### Files and network access

Godmode stores the signed receipt and deactivation token in `~/.godmode/license.json` and the random installation ID in `~/.godmode/installation.json`. Keep backups of the receipt private. A signed perpetual receipt can still verify offline after server-side revocation.

Activation sends the purchase key, installation ID, platform, and CLI version to the licensing service. Deactivation sends the license ID, installation ID, and deactivation token. The service can ask for a legacy preview password, which can be supplied with `GODMODE_PREVIEW_PASSWORD`. Key and password input are kept out of command arguments and the local receipt.
