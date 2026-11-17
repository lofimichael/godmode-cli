# Stripe accounts and sandboxes

The wrong Stripe key can put a product, payment or webhook in the wrong account. Keep business facts, key files and deployment settings separate.

| Detail | Where it belongs |
| --- | --- |
| Legal name, address, public contact | Reusable business profile |
| API keys for one chosen setup | Named Godmode environment |
| Expected `acct_…`, test/live mode, price IDs | Project deployment configuration |
| Webhook signing secret | That endpoint's runtime secret store |

## Select the account and sandbox

Stripe accounts can share a legal entity while keeping their products and payments separate. Independently operating projects or businesses need separate accounts. A consultant's clients keep their own accounts. [Stripe account guidance](https://docs.stripe.com/get-started/account/multiple-accounts)

General sandboxes have separate data and settings. Legacy test mode shares some settings with live. Both use test-prefixed keys; `sk_test_` or `rk_test_` alone cannot identify the sandbox. [Sandbox guidance](https://docs.stripe.com/sandboxes), [API keys](https://docs.stripe.com/keys)

```sh
godmode env create acme-test
godmode --env acme-test setup stripe
godmode --env acme-test --context acme help
```

Select the intended account and sandbox in Stripe before saving its key. A verified business's sandbox still makes test payments. Real payments require its live keys and enabled payment capabilities.

## Check the target before changing it

A local filename is a label. The provider's response establishes where the key works.

The project script should read the authenticated account, compare its ID with the configured account, check test/live mode on resources, and verify the deployment destination before writes. A denied restricted key stops the operation; it does not justify trying a broader key. Prefer restricted keys with the permissions that the task needs. [Restricted keys](https://docs.stripe.com/keys/restricted-api-keys)

Organization keys require explicit account routing and API versions. Account keys are simpler for one project. [Organization keys](https://docs.stripe.com/keys/organization-api-keys)

## Keep webhook secrets with their endpoints

Each webhook endpoint has its own signing secret. Test and live endpoints can share a URL and still have different secrets. Stripe CLI forwarding has another secret. [Webhook signatures](https://docs.stripe.com/webhooks)

Use a separate deployment for each account and sandbox. Store its matching endpoint secret there. Verify the raw request signature, expected mode and project ownership before changing membership or order data.

A created endpoint does not prove delivery. Save the endpoint ID, install its secret, then send a signed event and confirm the receiver's result. If secret installation fails, repair that step before declaring the endpoint ready.

## Reuse facts and verified resources

Reuse the business profile across test and live. Copy a key file when you want a snapshot of shared providers. Keep product, price, customer and webhook IDs separate for each Stripe account and environment.

Provisioning should first retrieve saved IDs, validate their ownership and settings, and search all result pages before creating anything. Multiple matches require resolution. Idempotency keys protect retries; they are not a permanent registry. [Stripe idempotency](https://docs.stripe.com/api/idempotent_requests)
