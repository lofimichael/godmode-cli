# Godmode

Enter your details and credentials once so your agents can use them. Godmode is a local onboarder: **Your details**, **Credentials**, **Agent instructions**, **Done**. Everything is optional.

Your name, business and contact facts live in a small editable `profile.json`. Pick a provider with the arrow keys, follow its short instructions, and paste a key or drag a credential JSON file behind a mask. Before saving, the CLI shows the intended credential-file edit with your value masked as `sealed(sk_•••••123)`. New credentials are sealed; older plain files stay plain until you choose to seal them.

One readable Python command, local files, no service or synchronization. The provider defaults intentionally favor broad useful access for trusted agents. Your task and existing project rules define how they use it.

Agents use keys through it, one command at a time:

```sh
godmode list                                  # key names
godmode set NAME                              # onboard or replace a credential
godmode set ACME_AUTH_JSON --stdin < credential.json
godmode run CLOUDFLARE_API_TOKEN -- npx wrangler whoami
godmode help                                  # the guide agents need
godmode profile                               # optional personal/business details
godmode profile get business_name             # read one saved fact
godmode provider google                       # setup, access, verification and recovery
godmode agents                                # one-time agent discovery hint
```

**Saved means stored, not verified.** Use only the credentials your task needs; the provider list is a catalog, not a checklist of required keys. Any name ending in `_JSON` accepts a JSON object, including a reusable OAuth grant exported by an official provider tool. Credential files, OAuth client configuration and permissions policies are different; use the type your consuming tool expects. See [Google's examples](docs/GOOGLE.md).

For everyday discovery, copy the short `godmode agents` hint once into your agent's normal user instructions. The CLI prints the locations and preserves existing rules. Agents fetch current help and the relevant provider guide when needed. No personal facts are templated into agent rules. See [agent setup and conventions](docs/AGENT_SETUP.md) and [profile fields](docs/PROFILE.md).

The consuming provider tool handles ordinary token refresh. If a credential is revoked or expired, the agent guides the provider's official OAuth or key-replacement flow, saves the replacement through `godmode set`, and verifies the intended operation. Outages, quotas and missing permissions need their own remedies. A returned replacement refresh credential must also be saved; `run` does not write updates back. Godmode does not implement provider login, refresh, health checks or background services.

Plain-text keys in `~/.config/godmode/.env.godmode` are detected at setup, with an offer to move them to `~/.godmode` and seal them (`godmode migrate` does the same).

![Interactive setup using a synthetic key](docs/images/setup.gif)

## Install

macOS/Linux, Python 3.9+. Requires [GitHub CLI](https://cli.github.com/) signed in with access to this private repo.

```sh
gh api -H 'Accept: application/vnd.github.raw+json' \
  repos/lofimichael/godmode-cli/contents/install.sh | sh -s -- --path
```

Installs into `~/.godmode/`, adds its commands to your shell, and starts setup. Existing `~/.config/godmode/` keys stay where they are until you choose to move them.

Update and run from a new terminal:

```sh
godmodeup
godmode
```

[Installation](docs/INSTALLATION.md) · [Profile](docs/PROFILE.md) · [Agent setup](docs/AGENT_SETUP.md) · [Providers](docs/PROVIDERS.md) · [Security](docs/SECURITY.md) · [Picard](docs/PICARD.md) · [Development](docs/RELEASING.md)
