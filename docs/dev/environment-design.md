# Environment design

Godmode needs to equip one person working across their own products and client accounts without making that person run a credential control plane.

## Complete files are the unit of selection

`.env.godmode` remains the default. `--env NAME` selects `.env.godmode.NAME`. A named file is complete: an absent value never resolves through another file. Since 0.19, `godmode use` and Active setup save a default environment/business pair in `active.json`. Flags override shell variables, which override the saved pair. There is no working-directory detection or automatic migration. Each running Godmode process keeps its resolved selection; each new unscoped invocation follows the saved default. Agents must capture `godmode active --command`, use a copied scoped note, or pin shell selectors to remain independent of later switches. See [Active setup](ACTIVE_SELECTION.md).

`env create NAME --copy SOURCE` makes a create-only snapshot. It preserves the source's exact bytes, including comments and sealed tokens, using the same home's seal key. Source and destination validation, a writer lock, snapshot checks, private permissions and Git guards apply. No decrypted value is printed or copied through a shell argument. Clone semantics are explicit: subsequent source edits and rotations do not propagate.

Copying preserves every source credential, including live credentials if present. An empty file is the better starting point for a client whose accounts should be separate. Files in one home are not a security boundary against a process running as that user.

This approach deliberately accepts credential duplication. A copy is inspectable and understandable. Automatic layered inheritance would make a missing client key ambiguous and require explaining precedence. Sharing by reference can be added later as an explicit operation if repeated rotation becomes a demonstrated problem; existing complete files must never silently become overlays.

## Business facts have a separate owner

The default business profile stays in its existing location. A named environment without an explicit business has its own empty profile. `--context acme` selects one reusable Acme profile across any number of environments. Copying credentials does not copy legal facts.

Existing context aliases remain compatible and resolve once within the selected file. Their optional name translation is separate from environment selection. A missing alias target fails. Mapped edits preview and change the actual saved name. Removing an alias restores the ordinary name inside the same file.

The global agent-file addition remains generic and append-only. The copied task note names the selected environment, business and paths. A client-specific selection never becomes a global instruction for every subsequent project.

## Provider checks belong at the point of mutation

A filename does not prove a key's account, sandbox, permissions or payment capability. Godmode supplies selected values to the existing command. It does not wrap every provider API, own refresh sessions or turn a local label into spend authorization. Other inherited shell variables and provider-native login stores remain available to the child process.

For Stripe, the project must pin the expected account ID and mode, verify authenticated identity before mutations, and scope resource receipts to account, environment and deployment. An enabled business's sandbox still produces test payments. Both legacy test mode and general sandboxes use test-prefixed keys; the prefix cannot distinguish two sandboxes. Organization keys need explicit `Stripe-Context` and API versions and are not a default for one project.

Each webhook endpoint has a distinct signing secret. The website now has separate test/live secret slots; live mode never inherits the old test slot. Provisioning validates the exact deployment, paginates resource discovery, refuses ambiguous adoption, and records the secret-install checkpoint. A failed secret install cannot become success merely because an endpoint already exists on retry. A saved endpoint or secret slot does not prove delivery; a signed event and resulting state provide that proof.

## Status replaces setup scoring

The native home starts with Active setup, followed by Providers, Agents and Business details. It shows actual fields, keys and installed notes rather than scoring optional business information as unfinished work. Navigation returns to the selected section. NFO lettering, color and focus remain; short windows reserve action and navigation space before decoration.

Doctor checks local file safety, sealed-value readability, alias targets, business data, agent notes and the managed updater without network requests or mutations. It authenticates raw stored values separately from aliases. A stored key is not reported as provider-verified. Update exits the UI cleanly, checks the sibling updater and executable against the install receipt, and invokes the existing checksum-validating release flow without provider credentials.

## Evidence and sources

Local fixtures exercise independent files, clone preservation, mapped writes, concurrent selections, unsafe files, stale previews, update receipts, non-disclosure, verified membership access and webhook mode boundaries. The release receipt records the exact completed checks and deployed verification; source review alone is not production proof.

- [Stripe: multiple separate accounts](https://docs.stripe.com/get-started/account/multiple-accounts)
- [Stripe: sandboxes](https://docs.stripe.com/sandboxes)
- [Stripe: API keys](https://docs.stripe.com/keys)
- [Stripe: restricted API keys](https://docs.stripe.com/keys/restricted-api-keys)
- [Stripe: organization API keys](https://docs.stripe.com/keys/organization-api-keys)
- [Stripe: webhooks](https://docs.stripe.com/webhooks)
- [Stripe: idempotency](https://docs.stripe.com/api/idempotent_requests)
- [Evil Martians: interfaces for developer tools](https://evilmartians.com/chronicles/devs-in-mind-how-to-design-interfaces-for-developer-tools)

Reviewed November 17, 2026; updated for 0.19 active selection.
