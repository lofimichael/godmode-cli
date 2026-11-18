#!/usr/bin/env python3
"""Assemble ordinary Python source into one readable installable script."""
import argparse
import ast
import json
import hashlib
from pathlib import Path
import pprint
import re

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'target/godmode')
    parser.add_argument('--without-music', action='store_true', help='omit the optional local music adapter')
    parser.add_argument('--verify', type=Path, metavar='SCRIPT', help='compare a script with a rebuild; write nothing')
    args = parser.parse_args()
    version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    sections = ['#!/usr/bin/env python3\n# Godmode ' + version + ': readable source, no bundled interpreter or dependencies.\n'
                'import sys\nif sys.version_info < (3, 9):\n    sys.exit("Godmode needs Python 3.9 or newer. No files changed.")\n']
    modules = ['godmode_store.py', 'godmode_profile.py', 'godmode_context.py', 'godmode_environment.py', 'godmode_selection.py', 'godmode_maintenance.py', 'godmode_terminal.py', 'godmode_picard.py', 'godmode_bridge.py']
    if (ROOT / 'lib/godmode_identity.py').exists():
        modules.append('godmode_identity.py')
    if not args.without_music and (ROOT / 'lib/godmode_music_pack.py').exists():
        modules.append('godmode_music_pack.py')
    for name in modules:
        path = ROOT / 'lib' / name
        module = '\n'.join(line for line in path.read_text(encoding='utf-8').splitlines()
                           if not line.lstrip().startswith('from godmode_')) + '\n'
        sections.append('\n# --- ' + name + ' ---\n' + module)
    source = (ROOT / 'godmode.py').read_text(encoding='utf-8')
    kept = [line for line in source.splitlines()
            if not line.startswith('#!') and not line.lstrip().startswith('from godmode_')
            and not line.startswith('sys.path.insert(')]
    source = '\n'.join(kept) + '\n'
    data = pprint.pformat(json.loads((ROOT / 'providers.json').read_text(encoding='utf-8')), width=100, sort_dicts=False)
    source = source.replace('MUSIC_INCLUDED = None  # The native/source builder sets this optional feature flag.',
                            'MUSIC_INCLUDED = ' + repr(not args.without_music))
    source = source.replace('PROVIDERS = None  # The build script inserts the plain provider data here.',
                            'PROVIDERS = ' + data)
    source = re.sub(r"^VERSION = '[^']*'$", lambda _: 'VERSION = ' + repr(version), source, count=1, flags=re.M)
    sections.append('\n# --- command line and static provider guidance ---\n' + source)
    script = '\n'.join(sections)
    ast.parse(script)
    if args.verify:
        expected = script.encode('utf-8')
        actual = args.verify.read_bytes()
        if actual != expected:
            parser.exit(1, 'Source differs from the script. No files changed.\n')
        print('Source matches: SHA-256 ' + hashlib.sha256(actual).hexdigest())
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(script, encoding='utf-8')
    args.output.chmod(0o755)
    print(str(args.output))


if __name__ == '__main__':
    main()
