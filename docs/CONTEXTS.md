# Businesses and environments

A key environment selects one complete key file. A business context selects a named [profile](PROFILE.md) you can reuse across environments.

## Select the active setup

Open **Switch setup** in `godmode`, choose a **Key environment** and **Business profile**, then select **Use this setup**. From the shell, use `godmode use` after creating the environment and context:

```sh
godmode use --env acme-test --context acme
godmode active
```

`use` saves the pair in `active.json` for new commands. Open Godmode sessions keep the pair they started with. If you omit one flag, Godmode saves that choice's currently resolved value, including shell overrides. Choose **Automatic** or pass `--context -` to use the selected environment's own profile.

## Copy a key file

Start empty when you need a separate account or client:

```sh
godmode env create acme-test
godmode --env acme-test --context - setup stripe
```

To start with the keys from another file, use `godmode env create acme-test --copy default` in place of the first command. A copy takes a snapshot of every key. Key rotations and profile edits stay with the files you change. Godmode refuses an existing destination and keeps missing keys missing in the selected environment.

## Reuse one business profile

Create a named context for details shared by test and live setups:

```sh
godmode context create acme
godmode --env acme-test --context acme profile
godmode use --env acme-test --context acme
```

Use `--context acme` with a different environment to select those same facts. Under **Automatic**, each environment has its own profile.

## Give an agent the selection

Generate a scoped note to paste into the agent task. Use the same prefix for discovery and execution:

```sh
godmode --env acme-test --context acme agents --print
godmode --env acme-test --context acme help
godmode --env acme-test --context acme run \
  STRIPE_API_KEY=STRIPE_TEST_SECRET_KEY -- stripe balance retrieve
```

The final command requires the Stripe CLI and a saved test key. `godmode active --command` prints the prefix for the current pair. Installed global agent instructions are generic. Use the scoped note when an ongoing task needs a specific account.

Selection order applies separately to keys and business facts:

| Priority | Keys | Business |
| --- | --- | --- |
| 1 | `--env NAME` | `--context NAME` |
| 2 | `GODMODE_ENV` | `GODMODE_CONTEXT` |
| 3 | Saved environment | Saved context |
| 4 | `default` | Automatic |

Set both shell variables before launching an agent to carry the scope into that shell's processes. Use `unset GODMODE_ENV GODMODE_CONTEXT` to follow the saved pair again. `run` also passes the resolved selections to the child. Each provider tool still controls its own login and account.

## Inspect the files

```sh
godmode active --json
godmode env list --json
godmode env show acme-test
godmode context show acme
```

`active --json` includes the selected names, paths and selection sources. `godmode path` prints the active key-file path.

| Path under the Godmode home | Contents |
| --- | --- |
| `active.json` | Saved environment and business names |
| `.env.godmode` / `.env.godmode.NAME` | Default or independent named key file |
| `seal.key` | Shared seal key for these files |
| `profile.json` / `environments/NAME/profile.json` | Default or named environment's Automatic profile |
| `contexts/NAME/profile.json` | Reusable business facts |
| `contexts/NAME/context.json` | Context metadata, including optional key aliases |

## Reuse a saved key name

Use a context mapping when a tool will keep asking for the same variable. This example maps the Stripe CLI's input to a saved test key:

```sh
godmode context map acme STRIPE_API_KEY STRIPE_TEST_SECRET_KEY
godmode --env acme-test --context acme run STRIPE_API_KEY -- stripe balance retrieve
```

Aliases resolve once inside the selected file. A missing mapped key stops the command. An unmapped name uses its ordinary entry in that file. To remove the mapping, run `godmode context unmap acme STRIPE_API_KEY`.

## Repair a missing selection

Run `godmode env list` and `godmode context list` to see available choices, then save a valid pair. To return to the default environment and its own profile:

```sh
godmode use --env default --context -
```

If `active.json` is malformed or unsafe, supply both flags to scope a task while you repair the saved file. Correct its JSON or move the file aside before saving a replacement.
