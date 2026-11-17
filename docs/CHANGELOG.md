# Release notes

## v0.18.0

November 16, 2026

- Named `.env.godmode.NAME` files keep complete key sets separate. Create empty files or copy an existing file without overwriting it.
- Reuse one business profile across environments. Every command selects its own files; menu selections stay in that session.
- The status screen gives Business, Providers, Agents and Environments equal weight, with Doctor and Update actions.
- Agent instructions remain visible and copyable after installation. Copied task notes include the selected files; global agent notes stay generic.
- `godmode doctor --json` checks local files and the updater. `godmode update` uses the recorded installer and verifies release downloads.

Read [Businesses and environments](CONTEXTS.md) and [Stripe accounts and sandboxes](STRIPE_ENVIRONMENTS.md).

