# Businesses and environments

Client work needs its own keys and business details. An environment selects a complete key file. A business context selects reusable business facts.

## Select the active setup

Open **Active setup** in `godmode`. Choose the key environment and business profile once. New commands use that pair, including `godmode profile get FIELD`, `godmode list` and `godmode run`.

```sh
godmode use --env acme-test --context acme
godmode active
godmode profile get business_name
```

The choices must already exist. With `godmode use acme-test` or `godmode use --context acme`, the omitted choice retains its currently resolved value, including any shell override; the complete resulting pair is saved. Pass both flags to save an exact pair. No keys or business fields are copied. Choose **Automatic** for the selected environment's own profile:

```sh
godmode use --env default --context -
```

The active pair is saved in `active.json` in the Godmode home. Existing installations keep their default files until you choose a different setup. A missing saved file or business produces an error instead of falling back to another account.

## Copy a key file

A copy keeps the providers you already use while letting you replace a few keys.

```sh
godmode env create acme-test --copy default
godmode --env acme-test setup stripe
```

This creates `.env.godmode.acme-test` beside `.env.godmode`. Every source key is copied. Later changes stay in the file you edit; rotations do not spread to copies. The source file is untouched. Existing destinations are refused.

For a client who needs only their own keys, start empty:

```sh
godmode env create client-test
godmode --env client-test setup
```

A missing key stays missing. Named files never borrow keys from the default file. A name such as `acme-live` does not change a key's Stripe account or mode.

## Reuse one business profile

Test and live environments can share one business address and legal name.

```sh
godmode context create acme
godmode --context acme profile
godmode env create acme-live
godmode --env acme-test --context acme profile
godmode --env acme-live --context acme setup stripe
```

`--context acme` selects the same business profile in both environments. With the Automatic business profile (`--context -`), a named environment has its own empty profile. Copying keys does not copy business facts.

## Give an agent the selection

Pin the pair at the start of a task. Two agents can then work for different businesses while you change the saved default.

```sh
godmode --env acme-test --context acme agents --print
godmode --env acme-test --context acme help
godmode --env acme-test --context acme run \
  STRIPE_SECRET_KEY=STRIPE_TEST_SECRET_KEY -- your-command
```

Copy the note into the agent's task. The Agents menu keeps this note visible after all agents are connected. Installed global instructions stay generic; a client selection belongs to that client's task.

Menu selections become the saved default for new commands. Already running Godmode sessions keep their current pair. A new unscoped command in another terminal uses the saved default, so copy a scoped task note or pin the shell for work that must stay on one account.

```sh
export GODMODE_ENV=acme-test
export GODMODE_CONTEXT=acme
# Start your agent in this shell.
```

Explicit `--env` / `--context` options win, then shell variables, then the saved active pair. Each axis resolves separately. `GODMODE_CONTEXT=-` selects the environment's own profile. Use `unset GODMODE_ENV GODMODE_CONTEXT` to follow the saved default again.

`godmode active --command` prints the exact scoped command prefix. `godmode active --json` reports names, paths and where each choice came from. `run` pins both selections in its child environment and supplies only the requested saved keys. Other inherited variables and native provider logins remain available. The new setup does not change another tool's own login or grant permission to use it.

## Inspect the files

Names and paths reveal the selection without exposing values.

```sh
godmode env list --json
godmode env show acme-test
godmode --env acme-test --context acme doctor --json
```

```text
~/.godmode/
  active.json                    saved environment/business names
  .env.godmode                    default keys
  .env.godmode.acme-test          independent test keys
  .env.godmode.acme-live          independent live keys
  seal.key                       shared local seal key
  profile.json                   default business facts
  environments/acme-test/
    profile.json                 facts when no context is selected
  contexts/acme/
    context.json                 optional key-name mappings
    profile.json                 reusable Acme facts
```

Existing legacy homes are detected. `--home DIR` selects a different home explicitly. `godmode path` shows the selected key file.

## Reuse a saved key name

Aliases keep older setups working without copying values inside one file.

```sh
godmode context map acme STRIPE_SECRET_KEY ACME_STRIPE_KEY
godmode --env acme-test --context acme run STRIPE_SECRET_KEY -- your-command
```

The mapping resolves once inside the selected file. Missing mapped keys stop the command. Unmapped names use that same file. `context unmap acme STRIPE_SECRET_KEY` restores the ordinary name in that file. Mapped edits show and change the actual saved name.

## Repair a missing selection

`godmode env list` and `godmode context list` remain available if a selected file was moved. Select an existing pair to repair the default:

```sh
godmode use --env default --context -
```

A malformed or unsafe `active.json` is refused. Explicitly supplying both selections lets a task continue without reading that file. Correct the JSON or move the damaged file aside yourself before saving a replacement. Godmode never silently clears unreadable selection metadata.
