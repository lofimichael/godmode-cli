# Godmode 0.14.0

Godmode uses one welcome screen, independent setup bars, provider search, compact file edits, and static numbered prompts. The Python standard library remains its only runtime dependency.

## Checks

| Check | Result |
| --- | --- |
| Full Python suite | 181 tests passed on Python 3.9.6 and 3.14.5 |
| Final profile resize regression | All 38 onboarding tests passed on both versions; two-column entry cannot save until the form is visible |
| Static terminal mode | 27 terminal tests passed, including an 8×12 welcome and masked review, invalid menu numbers, paste rejection, and terminal restoration |
| Installer and updater suites | Passed, including checksums, managed updates, previous executable, shell files, and concurrency |
| Shell syntax and ShellCheck | Passed |
| Actual 0.13.0 → 0.14.0 archive upgrade | Synthetic keys, profile, intro marker, and agent instructions stayed byte-for-byte identical; the saved key still reached a child command; previous executable reports 0.13.0 |
| Layout sweep | 330 width/height combinations across intro, name, base prompts, searchable menus, and required previews completed without unexpected exceptions |
| Added-text secret scan | Two synthetic test fixtures; no provider token or private-key matches |
| Git whitespace check | Passed |

The profile resize tests were added after the full-suite run. Both final profile suites include them. All terminal and upgrade checks use temporary homes and synthetic data.

## Screens

The screenshots contain output from the real program in a pseudo-terminal. `scripts/record-demo.py` records first use and key saving. `scripts/record-tour.py` records profile, agent, search, error, and narrow-window states. Optional Pillow and pyte dependencies belong only to these recording tools.

![Profile](../images/visual/profile.png)

![Exact agent note and target files](../images/visual/agents.png)

![Provider search](../images/visual/search.png)

![Narrow home](../images/visual/narrow.png)

![Narrow error](../images/visual/error.png)

![Agent preview on a light terminal](../images/visual/agents-light.png)

## Measurements

| Measure | 0.13.0 | 0.14.0 |
| --- | ---: | ---: |
| Welcome screens | 3 | 1 |
| Welcome titles and prose | 158 words | 25 words |
| Enter presses in welcome | 3 | 1 |
| Providers needed to fill the provider portion | 3 | 1 |
| Runtime packages | 0 | 0 |

The word count excludes diagrams, storage paths, and keyboard controls. Human newcomer task completion and screen-reader speech output have not been measured.
