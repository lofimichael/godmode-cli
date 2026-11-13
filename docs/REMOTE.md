# Use Godmode on another machine

Godmode's profile and credentials are local files. You can copy them with `scp`
to a development machine you trust and run the same CLI there. Install Godmode
on that machine first using the [installation guide](INSTALLATION.md); you do not
need to copy executables, shell setup, media caches or sockets.

The normal home is `~/.godmode`, not `~/godmode`. Check the actual files on the
source machine:

```sh
godmode profile path
godmode path
```

The profile and credentials can live in different directories. In particular,
legacy credentials may still be in `~/.config/godmode` while the profile is in
`~/.godmode`. These commands print paths, not their contents.

## Copy your details

This example uses the SSH host alias `clouddevmachine` and a new remote home,
`~/.godmode-cloud`, so an existing Godmode setup stays intact. Replace the alias
with your own host. Verify its SSH host identity through your normal trusted
channel before copying anything.

Run this on the source machine after saving a profile. The `mkdir` must succeed;
if that directory already exists, choose a different new name throughout these
examples instead of copying over it.

```sh
ssh clouddevmachine 'umask 077; mkdir "$HOME/.godmode-cloud"' &&
  scp -p "$(godmode profile path)" clouddevmachine:.godmode-cloud/profile.json
```

Only `profile.json` travels. It is plain JSON and may contain private contact
details; choose a host and account that should have those details. If you have
not created a profile, skip its copy and create the empty remote home with the
`ssh` command alone.

## Also give that machine your credentials

Copying `.env.godmode` together with `seal.key` grants the remote account access
to the entire copied credential inventory. Sealing does not prevent that account
or its programs from using the keys. Use this when you intend that machine's
agents to have the same provider access. For a smaller inventory, enroll only
the needed credentials there with `godmode set` instead.

For sealed credentials, copy both files from the directory reported by
`godmode path`. Do not print or open either file. Run this once after creating
the remote home above; it stops if either destination file already exists:

```sh
godmode_key_file=$(godmode path)
godmode_key_dir=$(dirname "$godmode_key_file")
ssh clouddevmachine '
  test -d "$HOME/.godmode-cloud" &&
  test ! -L "$HOME/.godmode-cloud" &&
  test ! -e "$HOME/.godmode-cloud/.env.godmode" &&
  test ! -L "$HOME/.godmode-cloud/.env.godmode" &&
  test ! -e "$HOME/.godmode-cloud/seal.key" &&
  test ! -L "$HOME/.godmode-cloud/seal.key"
' &&
  scp -p "$godmode_key_file" "$godmode_key_dir/seal.key" \
    clouddevmachine:.godmode-cloud/
```

Old plain-text stores have no `seal.key`. You can first run `godmode migrate`
locally to move and seal them, then run `godmode path` again and use the block
above. Migration changes the local store; read the [migration details](SECURITY.md)
and update any plaintext consumers to `godmode run` first. If you deliberately
keep the old format, copy only the `.env.godmode` file into the empty destination.
Do not mix a credential file with a different store's `seal.key`.

## Use and check the copy

On the remote machine:

```sh
export GODMODE_HOME="$HOME/.godmode-cloud"
godmode profile path
godmode path
godmode list
godmode agents
```

`godmode list` shows saved names. Verify the provider operation you actually
need through `godmode run NAME... -- command`; a copied file is not a provider
access check. The destination directory must be owned by your remote user and
mode 0700; the copied profile, credential file and sealing key must be regular
files owned by that user and mode 0600. The examples create a private directory
and use `scp -p` to retain the source files' modes. Godmode rejects unsafe file
paths and permissions.

Set `GODMODE_HOME` in that machine's shell configuration if you want to keep using
this home, or pass `godmode --home "$HOME/.godmode-cloud"` for individual commands.
Copy the `godmode agents` discovery hint into your agent's existing instructions
as described in [agent setup](AGENT_SETUP.md). Agent instructions themselves are
separate from the profile and keys.

These are independent copies. Changes do not synchronize, and removing a copied
file does not revoke a provider credential. OAuth grants remain subject to their
provider's expiry, refresh and device rules; follow the relevant `godmode provider`
guide if the new machine needs official sign-in or replacement credentials.
Provider-owned CLI logins or OAuth caches outside these files need their own
supported migration or sign-in; copying Godmode does not carry them along.

OpenSSH's [`scp` manual](https://man.openbsd.org/scp) documents encrypted transfer
over SSH, `-p` mode preservation, and the fact that recursive `-r` copies follow
symbolic links. Explicit file copies keep this handoff small and inspectable.
