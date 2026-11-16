# Godmode 0.17.0

The local CLI works without an account, activation or membership. Public release
downloads use HTTPS without a shared preview password. The source-available
license allows free personal and commercial local use and private modification;
redistribution remains restricted. Member playbooks and services are separate.

Business contexts keep each business profile separate and map selected provider
key names to existing saved credentials. Unmapped keys remain shared. Each
command chooses its context explicitly, so concurrent agents can use different
businesses without changing one another's selection.

```sh
godmode context create acme
godmode --context acme profile
godmode set ACME_STRIPE_SECRET_KEY
godmode context map acme STRIPE_SECRET_KEY ACME_STRIPE_SECRET_KEY
godmode --context acme run STRIPE_SECRET_KEY CLOUDFLARE_API_TOKEN -- your-command
```

A missing mapped key stops the command. Context files contain business facts and
key-name mappings; credentials remain in the existing sealed store. The default
profile, existing keys, agent notes and legacy license receipts stay unchanged.

Legacy receipt inspection and management remain available. Paid rights already
granted under earlier terms remain in force. Neither native nor Python ordinary
commands require or refresh those receipts.

The installer still checks archive size and SHA-256, refuses redirects and
unrecorded replacements, and keeps the previous executable for rollback.
