# Setup recording

The README animation is made from a scripted session of the actual native command
in a pseudo-terminal. It shows choosing a provider with the arrow keys, the
key's steps, the file and masked value preview, and the saved result. Tab
reveals the shell equivalent. `pyte` interprets the ANSI
output, including its colors and emphasis; Pillow draws the resulting terminal
cells. The frame holds are chosen for readability and total at most ten
seconds. It is not a desktop recording or a mock interface.

```sh
sh scripts/build-native.sh --output target/godmode-native
python3 -m venv target/demo-venv
target/demo-venv/bin/python -m pip install -r scripts/demo-requirements.txt
target/demo-venv/bin/python scripts/record-demo.py --binary target/godmode-native
```

Add `--intro` and an `--output` path to record the single welcome and the
home screen instead. This uses a separate empty temporary home, writes only
`intro.seen`, and checks that no profile or keys were created.

`scripts/record-tour.py --output target/visual-tour` currently builds and records
the Python compatibility interface, including profile, agent preview, provider
search, narrow home and key errors. It uses the same optional recording
environment and synthetic data. Its captures are not evidence of the native UI.

The default output is `docs/images/setup.gif`. Pass `--binary` for the native
build: the recorder's default input path remains `target/godmode`. `--output` and `--font`
can override the inputs/destination. On macOS the script uses the installed Menlo
font; on Linux it tries DejaVu Sans Mono or Liberation Mono. Fonts are not bundled.
Use `--theme light` to inspect the same ANSI output on a light terminal palette;
`--frames-dir PATH` also saves the recorded states as PNGs. These are representative
terminal themes; Godmode uses the user's terminal colors and default background.

The recording uses a temporary HOME, config and state directory and a deliberately
synthetic Cloudflare token. The temporary file is created before recording so
the short animation can focus on entering a key. First-run confirmation and
cancellation are exercised separately by `tests/test_simple_cli.py`. Input stays masked.
It never loads the ordinary Godmode configuration, launches a browser, requests Picard media, authenticates with a
provider, or changes an installed executable. The raw terminal transcript remains
in memory and is checked for accidental credential echo. The script verifies the
synthetic save, clean terminal exit, GIF frame durations and looping before reporting
success. Provider access is not verified by this demo.
