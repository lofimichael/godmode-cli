# Unprimed first impressions

> Archived review record from 2026-11-17. Personal checkout paths are generalized. Referenced PTY captures, binaries and temporary fixtures remain session evidence and are not included here. Findings and scores describe the reviewed build, not the current candidate.

Observed executable before reading any source or previous reviews. The agent-facing `godmode help` explains saved keys, the profile, provider setup, run scoping, and security; the multi-setup workflow appears only in the final three lines (Active setup, active --command). It does not yet tell me how to create two businesses or key environments.

At 80x24, initial warning/brand screen fills most of the terminal. Footer `Enter I understand · Esc exit` led me to type `I understand` and Enter; it moved forward (typing was apparently unnecessary). The next branding screen needs another Enter. Main menu is clean and compact. `Business: Automatic · Keys: default` is visible directly below the logo, and the first row `Active setup / Switch business / keys` looks like the right destination. `Automatic` is not self-explanatory yet: I cannot tell whether it selects a business from my folder, key environment, or something else.

Main menu at 80x24: Active setup, Providers, Agents, Business details, Doctor, Update, Help / FAQ, Music, Done. Footer: ↑↓ move · Enter open · s switch · Esc quit. The fixed global switch shortcut is promising. The two first-run introductory screens cost two confirmations; the main menu exposes all target destinations without scrolling.

Harness note excluded from UX findings: initial temporary GODMODE_HOME was created with mode 0755; executable correctly rejected it as insecure. It was chmodded 0700. The first launch attempt had redirected stdin, was correctly rejected, and was rerun with a real PTY.
