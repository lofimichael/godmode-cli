# Business contexts

Different businesses need different payment accounts and legal details. A context
keeps those facts separate while reusing your shared provider keys.

## Create a context

```sh
godmode context create acme
godmode --context acme profile
```

The context starts with an empty business profile. Your default profile stays
unchanged. `--context acme profile get FIELD` and `profile set FIELD --stdin`
also select that business.

## Choose different keys

Save each credential once under its own name, then map the provider's expected
key name to it:

```sh
godmode set ACME_STRIPE_SECRET_KEY
godmode context map acme STRIPE_SECRET_KEY ACME_STRIPE_SECRET_KEY
godmode --context acme run STRIPE_SECRET_KEY CLOUDFLARE_API_TOKEN -- your-command
```

That command receives Acme's Stripe key and the shared Cloudflare key. Unmapped
names use the shared store. A mapped key that is missing or unreadable stops the
command; Godmode never substitutes the shared Stripe key.

`VAR=NAME` still changes the environment variable a tool receives. Context
mappings apply to `NAME` once; mappings do not chain.

## Inspect or change a context

```sh
godmode context list
godmode context show acme
godmode --context acme help
godmode context unmap acme STRIPE_SECRET_KEY
```

`show` prints key names and the profile path, never credential values. `unmap`
restores the shared key for that name. Save keys with ordinary `godmode set`;
context selection supports `profile`, `run`, `list` and `help`.

Every command selects its context explicitly. There is no global active switch,
so agents working for different businesses can run at the same time. Tell the
agent which context to use for all profile reads and provider commands in its
task. A context changes which saved keys are supplied; it is not a sandbox or
provider permission boundary.

## Files

```text
~/.godmode/
  .env.godmode                 shared sealed credentials
  profile.json                 default business profile
  contexts/acme/
    context.json               key-name mappings only
    profile.json               Acme's business facts
```

Context directories are mode 0700; files are mode 0600. They must be owned by you
and cannot be symlinks. Context edits never copy or rewrite saved credentials.
Deleting a context removes its mappings and profile, not provider accounts or
the shared keys.
