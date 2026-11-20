# Remote machines

Set up Godmode on a remote machine or copy a specific environment over SSH. A copied key file and its matching `seal.key` give that machine access to every key in that file. For a machine that needs just a few keys, install Godmode there and add those keys with `godmode loadout`.

## Copy the default environment to a fresh home

Use a remote account you trust. Replace `devbox` with its SSH host. Create a private destination and run the direct installer with `--install-only`.

```sh
ssh devbox '
  umask 077
  remote_godmode="$HOME/.godmode-remote"
  mkdir "$remote_godmode" &&
  curl -fsSL https://godmode.build/install.sh -o "$remote_godmode/install.sh" &&
  sh "$remote_godmode/install.sh" --home "$remote_godmode" --install-only
'
```

Continue only after this succeeds. If the directory already exists, choose a new destination. The matching seal key is shared by all environments in its home.

On the source machine, use `godmode --env default --context - path` to confirm the default key file location. If you use legacy plain-text keys, [migrate them first](INSTALLATION.md#upgrading-from-09-or-earlier). This example copies from the standard home.

```sh
scp -p ~/.godmode/.env.godmode ~/.godmode/seal.key devbox:.godmode-remote/
```

Copy the optional profile separately. If the remote machine only needs business details, use this step by itself after installing.

```sh
scp -p ~/.godmode/profile.json devbox:.godmode-remote/
```

`scp -p` preserves the required file mode of 0600. List the key names to check the copy.

```sh
ssh devbox '~/.godmode-remote/bin/godmode --home ~/.godmode-remote --env default --context - list'
```

Use `--home ~/.godmode-remote` for subsequent commands on that machine, or set `GODMODE_HOME` there. Run `godmode agents` with that home to connect the remote agent.

## Copy a named environment

Use the path from `godmode env show NAME` to copy `.env.godmode.NAME` and its matching `seal.key` into a fresh home. Select it with `--env NAME --context -` to use its own profile. Copy business details only if needed. See the [file locations](CONTEXTS.md#inspect-the-files).

The remote copy is a snapshot. Update rotated keys on each machine, and use the provider tool's own login flow for any separate login cache it needs.
