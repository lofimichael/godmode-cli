#!/usr/bin/env python3
"""Run engine regression tests with the native license boundary explicitly mocked.

The test fixture alters a copy of source in memory. Production code has no
runtime flag/environment variable that disables verification. Native/crypto
tests exercise actual signed licenses separately.
"""
import sys
from pathlib import Path

script = sys.argv[1]
sys.argv = sys.argv[1:]
source = Path(script).read_text(encoding='utf-8')
boundary = '    require_license(argv, home)\n'
if source.count(boundary) != 1:
    raise SystemExit('The engine test fixture needs an explicit license boundary.')
source = source.replace(boundary, '    pass  # Native verifier mocked by engine regression test.\n')
exec(compile(source, script, 'exec'), {'__name__': '__main__', '__file__': script})
