# Godmode 0.19.0

17 November 2026.

Godmode now remembers an active business profile and key environment. Choose **Active setup** from home, or run `godmode use --env NAME --context NAME`. New commands use the saved pair. `godmode active` reports it; `godmode active --command` returns a fully scoped prefix for an agent task. Use `--context -` for the environment's own profile.

Command flags override shell selectors, which override the saved pair. Existing processes retain their selection. Copied agent instructions pin both axes, including defaults; children launched by `godmode run` inherit that scope. Switching only writes nonsecret selection metadata and preserves existing key and profile files. Missing selected targets produce an actionable error instead of falling through to another business.

The first interactive launch and `godmode intro` have two Lip Gloss scenes: a red warning, then a violet/cyan empowerment screen. Both respond immediately to Enter. Animated sheen and connector motion finish naturally; reduced-motion, no-color, light backgrounds and compact terminals remain usable.

Guided screens show the selected business and keys, with a full-width focus row and brief navigation accents. Backend operations run outside Bubble Tea's input loop, with a delayed loading indicator for work that actually takes time. Large-paste checks retain edits. Writes stay serialized, stale responses are ignored, and Ctrl-C interrupts a waiting backend after restoring the terminal. Updated model snapshots do not share mutable state with the rendered screen.

[Selection decision](ACTIVE_SELECTION.md), [intro direction](INTRO_DIRECTION.md), and [performance review](PERFORMANCE_REVIEW.md) contain the source research and measurement boundaries. The local measurements describe this Mac, not a cross-platform performance guarantee. macOS ARM64 is exercised locally; the other release targets are cross-compiled and inspected.

The CLI remains free and accountless under its existing source-available license. Membership, billing, provider credentials and agent files are not changed by this release.
