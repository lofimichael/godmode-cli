# Remote machines

Godmode's files stay on the machine where you saved them. To use them on a cloud or remote development machine you trust:

1. Install Godmode on the remote machine with the [install command](INSTALLATION.md), adding `--no-setup`.
2. On this machine, copy your profile and keys. This replaces those files on the remote machine.

   ```sh
   scp -p ~/.godmode/profile.json ~/.godmode/.env.godmode ~/.godmode/seal.key devbox:.godmode/
   ```

3. Run `godmode list` on the remote machine. It prints the names of the keys you copied.

Replace `devbox` with your SSH host. `-p` keeps the files' 0600 mode, which Godmode requires.

`.env.godmode` with `seal.key` gives that machine every key you saved. Copy only `profile.json` to share your profile without keys.

If `godmode path` prints a path under `~/.config/godmode`, run `godmode migrate` first.

The copies do not sync. Save a replaced key on each machine, and choose **Agents** in `godmode` on the remote machine to add the agent text there.
