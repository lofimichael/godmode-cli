# Navigation review records

These Markdown records preserve the evidence used in the [navigation audit](../NAVIGATION_AUDIT.md). They are AI-agent walkthroughs and source research, not a human usability study. The research reviewer and baseline reviewers worked independently; first impressions preceded source or design inspection. Numeric scores are subjective judgments with the scope stated in each report.

| Record | Scope |
| --- | --- |
| [Research](research.md) | Ten CLI/TUI precedents, primary sources, and separate design inferences |
| [First-use first impressions](baseline-first-impressions.md) | Frozen before deeper inspection |
| [First-use baseline](baseline-first-use.md) | Installed 0.19.2; empty setup and one synthetic provider |
| [Returning-user first impressions](baseline-returning-first-impressions.md) | Frozen before deeper inspection |
| [Returning-user baseline](baseline-returning.md) | Installed 0.19.2; two businesses and environments |
| [Copy/layout baseline](baseline-copy.md) | Installed 0.19.2; 80×24 and 40×18 |
| [Candidate 1 review](candidate-1-review.md) | Fixed unreleased build; includes the narrow-screen save blocker |
| [Candidate 2 review](candidate-2-review.md) | 8/10; narrow save and selected-agent tasks completed at all three tested sizes |
| [Independent fresh review](fresh-review.md) | 8/10; 80×24 and 40×18; two businesses, key environments and selected-agent append |
| [Candidate 3 fresh review](candidate-3-fresh-review.md) | 8.5/10; core tasks, recent pairs and three viewport sizes; no blocker in the exercised scope |
| [Candidate 3 returning/copy review](candidate-3-returning-review.md) | 8/10; improved copy and recent pairs, with reproduced wrong-provider Back defect |
| [Final blind first impressions](final-fresh-first-impressions.md) | Frozen before the last independent walkthrough |
| [Final fresh checkpoint](final-fresh-checkpoint.md) | Retained 8.5/10; final-hash Back, scope, key and chosen-agent checks |
| [Final returning/copy checkpoint](final-returning-review.md) | 9/10; final-hash fixes verified, remaining minor copy recorded |
| [Backend validation handoff](backend-validation.md) | Implementer-reported operation boundaries and focused test results |

Only selected Markdown reports are retained. No executables, raw ANSI streams, credential stores, screenshots, clipboard contents, or temporary home inventories are committed here. Working paths are generalized; capture filenames in reports are historical evidence references rather than promised repository artifacts.

Both final reviewer handoffs are recorded as separate final-hash checkpoints. Do not rewrite the baseline, earlier candidate or fresh-review judgments to match later fixes. The audit identifies the final frozen source candidate separately; no public release or installation was performed by this work.
