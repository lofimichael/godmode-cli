# GODMODE identity

GODMODE uses original block lettering, magenta and cyan terminal colors, and blunt language about account access. Its intro says: “GODMODE gives your agents the goddamn keys.” The profile and credential facts follow it, including spending, live changes and deletion.

The source voice is Craig Brozefsky's June 27, 1999 post, [SCWM, Pot and the GPL](https://www.nongnu.org/ratpoison/inspiration.html). Its hacker diction includes “goddamn,” “rodent,” and “hacking.” The original argues for keyboard control and fewer distractions. Godmode borrows that directness; its lettering and copy are original.

## Lettering and motion

The intro uses six rows of block lettering when they fit. A two-row wordmark and then a text name serve smaller terminals. A brief row reveal appears only in color terminals. The account-use statement stays visible during the reveal. Enter accepts it. `--no-motion`, `GODMODE_NO_MOTION=1`, `--plain` and `NO_COLOR` suppress the reveal.

The native terminal UI uses Bubble Tea v2 and Lip Gloss v2. The full account-use statement and its Enter action must fit before Enter can proceed. A smaller terminal removes decoration first. A terminal too small for those words cannot advance.

## Home

Profile, Providers and Agents have wider meters and numeric counts. A larger header carries the wordmark and total. Rows gain blank space when the window can hold it. Short windows keep the section names and counts.

Leaving Profile focuses Providers. Leaving Providers focuses Agents. Leaving Agents focuses Help / FAQ. Help returns to its own row. Music returns to the home menu. Escape from the home returns to the shell.

## Sources

| Source | Applied behavior |
| --- | --- |
| [Ratpoison inspiration](https://www.nongnu.org/ratpoison/inspiration.html), 1999-06-27 | Blunt hacker diction, keyboard control, concentration |
| [Evil Martians: CLI progress](https://evilmartians.com/chronicles/cli-ux-best-practices-3-patterns-for-improving-progress-displays), 2024-04-15 | Counts accompany bars; instant file writes do not need invented loading work |
| [GitHub CLI accessibility](https://github.blog/engineering/user-experience/building-a-more-accessible-github-cli/), 2025-05-02 | Static plain mode, terminal-owned colors, readable status without color |

The complete earlier research remains in [CLI experience](CLI_EXPERIENCE.md).
