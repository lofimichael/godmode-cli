# Remote machines

Set up Godmode on a remote machine or copy a specific environment over SSH. A copied key file and its matching `seal.key` give that machine access to every key in that file. For a machine that needs just a few keys, install Godmode there and add those keys with `godmode setup`.

## Copy the default environment to a fresh home

Use a remote account you trust. Replace `devbox` with its SSH host. First create a private destination and install there without opening setup:

```sh
ssh devbox 'umask 077 && mkdir "$HOME/.godmode-remote" &&
  curl -fsSL https://get.godmode.build | bash -s -- --home "$HOME/.godmode-remote" --no-setup &&
  test -x "$HOME/.godmode-remote/bin/godmode"'
```

Continue only after this succeeds. If the directory already exists, choose a new destination. The matching seal key is shared by all environments in its home.

On the source machine, use `godmode --env default --context - path` to confirm the default key file location. If you use legacy plain-text keys, [migrate them first](INSTALLATION.md#upgrading-from-09-or-earlier). For the standard home:

```sh
scp -p ~/.godmode/.env.godmode ~/.godmode/seal.key devbox:.godmode-remote/
```

Copy the optional profile separately if you want those business facts on the remote machine. You can use this step by itself after installing when the remote machine only needs the profile:

```sh
scp -p ~/.godmode/profile.json devbox:.godmode-remote/
```

`scp -p` preserves the required file mode of 0600. Check the saved names on the remote host:

```sh
ssh devbox '~/.godmode-remote/bin/godmode --home ~/.godmode-remote --env default --context - list'
```

Use `--home ~/.godmode-remote` for subsequent commands on that machine, or set `GODMODE_HOME` there. Run `godmode agents` with that home to connect the remote agent.

## Copy a named environment

Use the path from `godmode env show NAME` to copy `.env.godmode.NAME` and its matching `seal.key` into a fresh home. Select it with `--env NAME --context -` to use its own profile. Copy business details only if needed. See the [file locations](CONTEXTS.md#inspect-the-files).

The remote copy is a snapshot. Update rotated keys on each machine, and use the provider tool's own login flow for any separate login cache it needs.
