# Contributing to Godmode

Open a pull request against CLI `main`. Describe what changed and what you
verified. Use the [development checks](dev/TESTING.md) to test your changes.

## Releasing the CLI

Keep `VERSION` unchanged for routine contributions. Increase it only for an
intentional release. Follow the [release runbook](dev/RELEASING.md) for the
matching source updates and release notes.

1. Merge the version bump into CLI `main`. GitHub Actions tests and packages
   that commit, creates the matching tag, publishes the GitHub release, and
   opens a distribution PR in `godmode-build`.
2. Review the distribution PR as the customer rollout decision. Once its
   checks pass and it merges, Cloudflare deploys website `main`.
3. Check the [live release manifest](https://godmode.build/releases/latest.json)
   before reporting that the version is available. Its version is what users
   receive from `get.godmode.build` and `godmodeup` by default.
