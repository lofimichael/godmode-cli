# Setup recording

The README animation is made from a scripted session of the actual release binary
in a pseudo-terminal. `pyte` interprets its ANSI output; Pillow draws the resulting
terminal cells. The frame holds are chosen for readability and total at most ten
seconds. It is not a desktop recording or a mock interface.

```sh
cargo build --release --locked
python3 -m venv target/demo-venv
target/demo-venv/bin/python -m pip install -r scripts/demo-requirements.txt
target/demo-venv/bin/python scripts/record-demo.py
```

The default output is `docs/images/setup.gif`. `--binary`, `--output` and `--font`
can override the inputs/destination. On macOS the script uses the installed Menlo
font; on Linux it tries DejaVu Sans Mono or Liberation Mono. Fonts are not bundled.

The recording uses a temporary HOME, config and state directory and a deliberately
synthetic GitHub token. Input stays masked. It never loads the ordinary Godmode
configuration, launches a browser, requests Picard media, authenticates with a
provider, or changes an installed executable. The raw terminal transcript remains
in memory and is checked for accidental credential echo. The script verifies the
synthetic save, clean terminal exit, GIF frame durations and looping before reporting
success. Provider access is not verified by this demo.
