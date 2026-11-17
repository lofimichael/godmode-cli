# Godmode intro

17 November 2026.

The first-run intro and `godmode intro` use two short native cards: the consequences of giving an agent credentials, followed by what the user can do with that access. Enter advances immediately. Escape and Ctrl-C restore the terminal. No timer grants access or prevents input.

"Your accounts. Your consequences." names the responsibility without promising an approval gate. The acknowledgement records that the intro was seen; it does not authorize an agent task or enforce its limits.

The visual identity uses the existing original NFO lettering, a red-to-amber warning gradient, a purple-to-cyan power gradient, a feathered diagonal sheen, and a small moving connector. The intro repeats a 96-frame cycle at the 40 ms tick cadence until the user advances or exits. Moving elements leave the visible area before the cycle repeats, avoiding a jump across the logo or rail. The statement and labels remain readable on every frame; there is no simulated scan, fake progress or privilege claim.

The renderer uses the pinned [Lip Gloss](https://github.com/charmbracelet/lipgloss) style/layout API and [Bubble Tea](https://github.com/charmbracelet/bubbletea) event loop. It adds no runtime dependency. Letter cells are grouped by style to reduce ANSI bytes. The full looping frame measured about 0.25 ms on the development M1 Max; that measurement is a local benchmark, not a cross-machine guarantee. Intro motion stops when the intro closes; management screens do not inherit its continuous tick.

Still art appears immediately with `--no-motion`. `NO_COLOR` preserves the full statement and actions without styling or animation. The 40×18 layout uses a compact logo and vertical capability diagram; 80×24 uses full lettering and the horizontal diagram. Both light and dark terminal themes use distinct readable color sets. Windows too small to show the consequences cannot acknowledge them.

Renderer tests cover repeated cycles, an identical wrap boundary, immediate Enter after many cycles, unchanged logo cells, and bounded line widths at 40, 80, 110 and 160 columns. Real terminal resize and repaint checks remain necessary: valid frame strings alone cannot prove a terminal has painted or cleared them correctly.

`scripts/record-v019.py` captures actual native PTYs in synthetic homes. It records both cards, motion, reduced motion, light mode, no-color, and the active-setup screens. It does not load ordinary credentials or contact a provider. Still images use the terminal's observed cells, not a mock layout.
