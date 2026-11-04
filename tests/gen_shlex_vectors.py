#!/usr/bin/env python3
"""Generate shlex parity vectors. The Rust tokenizer must match Python's
shlex.split(value, comments=True, posix=True) exactly: same tokens, or an
error when Python raises ValueError. Run from the repo root:
    python3 tests/gen_shlex_vectors.py > tests/shlex_vectors.json
"""
import json, shlex, sys

RAW = [
    "", "   ", "abc", "  abc  ", "a b", "a\tb", "'a b'", '"a b"', "'it'\"'\"'s'", "'it'\\''s'",
    "a'b", 'a"b', "'unterminated", '"unterminated', "a\\ b", "a\\b", "\\'", "'a\\b'", '"a\\b"', '"a\\"b"',
    '"a\\$b"', '"a\\\\b"', "'a\\'", "abc # comment", "abc#notcomment", "#whole", " # whole", "'#quoted'", '"#quoted"',
    "a 'b c' d", "sk_test_123", "github_pat_ABC_def", "ghp_x", "name@example.com", "/path/with spaces/x",
    "{\"type\":\"service_account\",\"private_key\":\"-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n\"}",
    "'{\"type\":\"service_account\",\"private_key\":\"-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n\"}'",
    '"{\\"type\\":\\"service_account\\"}"', "a=b", "a==b", "=", "'='", "a;b", "a|b", "a&b", "$HOME", "'$HOME'", '"$HOME"',
    "`cmd`", "a*b", "a?b", "~user", "a\u00e9b", "'\u00e9 \u4e2d'", "a\\\nb", "'a\nb'", "a\\\\", "a\\", "''", '""',
    "'' ''", "a''b", 'a""b', "'a'b'c'", "\"a\"b\"c\"", "x  #  y", "x\t#y", "'x' # y", "'x'# y", "'x'#y", "\"x\"#y",
    "\\#x", "'a' 'b'", "a 'b", "a \"b", "a\\'b", "'a' b\\ c", "tab\there", "nl\nhere", "cr\rhere", "trail ", " lead",
    "u2028\u2028x", "zero\x00byte", "quote'in'middle", "dq\"in\"middle", "mixed 'sq' \"dq\" bare", "\\\\'", "'\\\\'",
    "x\\#y", "'x\\#y'", "\"x\\#y\"", "a#b c", "a #b c", "'a #b' c", "ab\\ #c", "\\\"", "'\\\"'", "\"\\'\"",
]
out = []
for raw in RAW:
    try:
        toks = shlex.split(raw, comments=True, posix=True)
        out.append({"raw": raw, "tokens": toks})
    except ValueError as e:
        out.append({"raw": raw, "error": str(e)})
json.dump(out, sys.stdout, indent=1, ensure_ascii=False)
sys.stdout.write("\n")
