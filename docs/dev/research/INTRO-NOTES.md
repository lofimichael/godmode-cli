# Intro notes

Historical research, not current behaviour.

These notes were written for the 0.12 first-run welcome.

## The domain-to-payments example

An authorized agent with configured accounts can register a domain, deploy a
Cloudflare Workers application to it, and integrate Stripe payments. The example
describes what an agent can accomplish using access Godmode supplies, not a bundled
one-click Godmode deployment command.

Cloudflare's Registrar API is currently beta and supports programmatic registration
with Registrar write permission, supported domains, configured billing, a default
payment method, registrant contact and acceptance of the registration agreement.
Check the current price and purchase authority before registration. Workers custom
domains can be configured through Wrangler or the API for an appropriate active
zone. [Registrar guide](https://developers.cloudflare.com/registrar/registrar-api/),
[Workers custom domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/).

Stripe integration can be developed and tested with keys; live services depend on
account activation and business verification. "Integrate Stripe payments" avoids
confusing ordinary payment integration with the separate Stripe Connect product.
[Stripe account setup](https://docs.stripe.com/get-started/account/set-up).

## Reference design and documentation direction

Claude Code's official quickstart moves from setup toward a first useful task, then
routes to deeper guidance. Its terminal documentation supports theme-aware,
keyboard-oriented interaction; these pages do not establish an exact visual design
to reproduce. [Quickstart](https://code.claude.com/docs/en/quickstart),
[terminal configuration](https://code.claude.com/docs/en/terminal-config).

Executor's documentation provides a clear opening definition, short first-use
steps, task-based navigation and a Markdown copy option. Its page source uses
restrained typography, dark surfaces and fine rules. These are useful presentation
patterns; Executor's hosted/local architecture, approval controls and credential
isolation claims are different from this CLI. Source inspection was performed;
a rendered browser audit was not available. [Executor docs](https://executor.sh/docs).

The recommendation is a maintained **Docs** section at `godmode.build/docs`, with
the existing Markdown and provider catalog as its source. That is a proposed public
destination, not a live site. Keep the structure small:

| Section | Pages |
| --- | --- |
| Start | What Godmode does; installation; first useful task |
| Setup | Profile; credentials; agent instructions |
| Providers | Catalog and guides generated from `providers.json` |
| Use | Domain → Workers → Stripe example; remote development |
| Reference | Commands; files; recovery; security |

Use a readable left navigation, copyable commands, stable page links and Markdown
available to agents. Reuse the CLI's wordmark and restrained accent colors.
Publish a static site from the same reviewed source when the public launch is
ready. A separate CMS, accounts system or community-editable wiki is unnecessary
for this manual. Search can follow when the page count warrants it.
