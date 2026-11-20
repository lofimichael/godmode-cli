# Stripe accounts and sandboxes

Use a named Godmode environment for each Stripe account and sandbox you work on. Give deployments their own Stripe configuration so code can check the target before a write.

| Detail | Where to keep it |
| --- | --- |
| Legal name, address, public contact | [Profile](PROFILE.md) |
| API keys for the selected loadout | [Godmode key environment](CONTEXTS.md) |
| Expected `acct_…`, test or live mode, resource IDs | Project deployment configuration |
| Webhook signing secret | The endpoint's runtime secret store |

## Select the account and sandbox

1. In the Stripe Dashboard, select the account and sandbox. General sandboxes have isolated data and settings. The `sk_test_` or `rk_test_` prefix alone cannot identify a sandbox. [Stripe accounts](https://docs.stripe.com/get-started/account/multiple-accounts), [Sandboxes](https://docs.stripe.com/sandboxes).
2. Create a key environment and open the Stripe key editor.

   ```sh
   godmode env create acme-test
   godmode --env acme-test --context - loadout stripe
   ```

3. Save the test key you need. For a restricted key, give it the permissions needed for the task. [Stripe API keys](https://docs.stripe.com/keys).

## Check the target before changing it

Have the consuming tool retrieve the authenticated account and compare its ID with the configured account. Check the sandbox and the `livemode` field on relevant resources. Confirm the deployment destination before writing. An organization key also needs explicit account routing and an API version. [Retrieve an account](https://docs.stripe.com/api/accounts/retrieve), [Organization keys](https://docs.stripe.com/keys/organization-api-keys).

With the Stripe CLI installed, map the stored test key to `STRIPE_API_KEY` to make a read-only request.

```sh
godmode --env acme-test --context - run \
  STRIPE_API_KEY=STRIPE_TEST_SECRET_KEY -- stripe balance retrieve
```

The balance response tests access to that endpoint. Confirm account and sandbox separately before making changes.

## Keep webhook secrets with their endpoints

Each endpoint has its own secret, including test and live endpoints at the same URL. Stripe CLI forwarding uses another secret. Install the matching secret on the receiver, verify the signature against the raw request body, then send a test event and check the receiver's result. [Stripe webhooks](https://docs.stripe.com/webhooks).

## Reuse facts and verified resources

Reuse a business profile across test and live. Scope product, price, customer and webhook IDs to their Stripe account and sandbox. Before creating a resource, check saved IDs and search existing resources. Use idempotency keys for retries. [Stripe idempotency](https://docs.stripe.com/api/idempotent_requests).
