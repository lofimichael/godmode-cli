# Get started

Save one provider key, give your coding agent a task note, and verify access with a read-only request.

## 1. Install Godmode

On macOS or Linux with Python 3.9 or later, run:

```sh
curl -fsSL https://get.godmode.build | bash
. "$HOME/.godmode/env"
godmode --version
```

Sourcing the generated `env` file puts Godmode on the current shell’s PATH. See [Installation](INSTALLATION.md) to add it to future shells or review the script before running it.

## 2. Open your loadout

Run `godmode` to see providers and profile details together. Select a provider to add or replace a key, or select a profile field to edit it. Profile fields are optional. The examples in the editors show the format to use.

### Save a provider key

This example uses GitHub and assumes `gh`, the GitHub CLI, is installed. Read the provider guide, then open the credential editor:

```sh
godmode provider github
godmode loadout github
godmode list
```

Follow the guide to create a token with only the access your task needs. Press Ctrl-O in the credential field to open GitHub. Paste the token, review the masked edit, and press Enter to save. In `--plain` mode, press Tab to review first. Expect `GH_TOKEN` in the list. A saved name confirms local storage.

For another provider, run `godmode provider` to find its slug or see [Provider keys](PROVIDERS.md).

## 3. Give your agent a task

```sh
godmode agents --print
```

Paste the printed note into your current agent chat. It pins the selected environment and profile. Ask the agent to follow the note and make a read-only check:

> Read the Godmode provider guide for GitHub. Use the saved token to tell me which GitHub account it belongs to. Do not print the token.

The underlying request is:

```sh
godmode run GH_TOKEN -- gh api user --jq .login
```

Expect a GitHub login. Check that it matches the intended account. Confirm access to your specific repository separately.

## Next steps

- [Save agent instructions](AGENT_SETUP.md) for future sessions.
- [Add profile details](PROFILE.md) for tasks that need a name, URL, or contact email.
- [Choose an environment and profile](CONTEXTS.md) before working with multiple accounts or sets of keys.
- Run `godmode doctor` to check local files. Run `godmode help` for agent guidance.
