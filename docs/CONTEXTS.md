# Businesses and environments

Client work needs its own keys and business details. An environment selects a complete key file. A business context selects reusable business facts.

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

`--context acme` selects the same business profile in both environments. Without a context, a named environment has its own empty profile. Copying keys does not copy business facts.

## Give an agent the selection

Each command selects its own files. Two agents can work for different businesses at once.

```sh
godmode --env acme-test --context acme agents --print
godmode --env acme-test --context acme help
godmode --env acme-test --context acme run \
  STRIPE_SECRET_KEY=STRIPE_TEST_SECRET_KEY -- your-command
```

Copy the note into the agent's task. The Agents menu keeps this note visible after all agents are connected. Installed global instructions stay generic; a client selection belongs to that client's task.

The menu's selection lasts for that menu session. It does not change other terminals. `run` adds the requested keys to the child process; other variables and native provider logins already in the shell remain available.

## Inspect the files

Names and paths reveal the selection without exposing values.

```sh
godmode env list --json
godmode env show acme-test
godmode --env acme-test --context acme doctor --json
```

```text
~/.godmode/
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
