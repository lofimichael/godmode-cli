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

## 2. Save a provider key

This example uses GitHub and assumes `gh`, the GitHub CLI, is installed. Read the provider guide, then open masked setup:

```sh
godmode provider github
godmode setup github
godmode list
```

Follow the guide to create a token with only the access your task needs. Paste it into the masked prompt, review the edit, and confirm the save. Expect `GH_TOKEN` in the list. A saved name confirms local storage.

For another provider, run `godmode provider` to find its slug or see [Provider keys](PROVIDERS.md).

## 3. Give your agent a task

```sh
godmode agents --print
```

Paste the printed note into your current agent chat. It pins the selected environment and business. Ask the agent to follow the note and make a read-only check:

> Read the Godmode provider guide for GitHub. Use the saved token to tell me which GitHub account it belongs to. Do not print the token.

The underlying request is:

```sh
godmode run GH_TOKEN -- gh api user --jq .login
```

Expect a GitHub login. Check that it matches the intended account. Confirm access to your specific repository separately.

## Next steps

- [Connect an agent](AGENT_SETUP.md) to load instructions in future sessions.
- [Add business details](PROFILE.md) for tasks that need a name, URL, or contact email.
- [Choose an environment and business](CONTEXTS.md) before working with multiple accounts or sets of keys.
- Run `godmode doctor` to check local setup. Run `godmode help` for agent guidance.
