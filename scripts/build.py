#!/usr/bin/env python3
"""Assemble ordinary Python source into one readable installable script."""
import argparse
import ast
import json
from pathlib import Path
import pprint
import re

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'target/godmode')
    args = parser.parse_args()
    version = (ROOT / 'VERSION').read_text().strip()
    sections = ['#!/usr/bin/env python3\n# Godmode ' + version + ': readable source, no bundled interpreter or dependencies.\n'
                'import sys\nif sys.version_info < (3, 9):\n    sys.exit("Godmode needs Python 3.9 or newer. No files changed.")\n']
    for name in ['godmode_store.py', 'godmode_terminal.py', 'godmode_picard.py']:
        path = ROOT / 'lib' / name
        sections.append('\n# --- ' + name + ' ---\n' + path.read_text())
    source = (ROOT / 'godmode.py').read_text()
    kept = [line for line in source.splitlines()
            if not line.startswith('#!') and not line.lstrip().startswith('from godmode_')
            and not line.startswith('sys.path.insert(')]
    source = '\n'.join(kept) + '\n'
    data = pprint.pformat(json.loads((ROOT / 'providers.json').read_text()), width=100, sort_dicts=False)
    source = source.replace('PROVIDERS = None  # The build script inserts the plain provider data here.',
                            'PROVIDERS = ' + data)
    source = re.sub(r"^VERSION = '[^']*'$", lambda _: 'VERSION = ' + repr(version), source, count=1, flags=re.M)
    sections.append('\n# --- command line and static provider guidance ---\n' + source)
    script = '\n'.join(sections)
    ast.parse(script)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(script)
    args.output.chmod(0o755)
    print(str(args.output))


if __name__ == '__main__':
    main()
