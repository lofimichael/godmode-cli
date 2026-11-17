# Godmode 0.19.2

17 November 2026.

Fixes the intro animation leaving pieces of the logo at the left edge in terminals that map line feeds to carriage-return/line-feed. The fault was reproduced with the same shapes and positions as the Conductor screenshot by enabling output newline mapping during an actual PTY session. Relative cursor movement now uses explicit cursor-down controls instead of assuming that a line feed preserves the column. Scrolling and ordinary newline output keep their existing behavior.

The intro now repeats a smooth 96-frame cycle, approximately 3.84 seconds per loop. Enter changes scenes immediately. The transition keeps one clock; it does not start another stream of ticks. Reduced-motion and no-color modes remain static, and intro ticks stop when the user leaves.

The vendored renderer patch and focused regression are documented in `vendor/PATCHES.md`. Active setup, credential storage, paid access and distribution boundaries are unchanged.

Validation: all Go packages passed with the race detector, along with three explicit vendored-renderer regressions. Twenty-four native Python checks passed using the demo environment, including two real-PTY newline-mapping cases held for 8.2 seconds each with unchanged logo cells and restored terminal flags. The recorder verified 22 screenshots and 11 PTY checks, including a nine-second loop run, both intro scenes, light/dark, compact/wide, reduced-motion, no-color, and terminal restoration.
