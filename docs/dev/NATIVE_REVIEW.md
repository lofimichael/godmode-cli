# Independent native CLI review

Reviewed the Go entry point, native UI, private core client, Python JSON bridge, append-only agent writer, relevant profile/store writers, and native home/provider screenshots directly. No previous audit or design rationale was used. Every executed terminal session used a temporary home and synthetic values. No real credentials or agent files were read or changed.

## Findings and resolutions

**Medium: interrupted bracketed paste trapped cancellation. Resolved.** Before the fix, send `ESC[200~synthetic_partial_paste` to `godmode set TEST_TOKEN`, then Ctrl-C without the terminator. The process remained alive: ultraviolet buffered Ctrl-C inside paste content. The UI's 1 MiB check also ran only after the decoder accumulated a complete paste. `internal/ui/input.go` now bounds paste content before the decoder, recognizes Ctrl-C/Ctrl-D during incomplete pastes, refuses oversized completed pastes, and discards queued tail input before terminal restoration. The `Run` hook in `internal/ui/model.go` installs the guard and shutdown filter. New unit and real-PTY tests passed.

**Medium: editing a pasted public-address field removed its masking. Resolved.** `editKey` formerly reset `m.pasted=false` after any editing keystroke. With `GMAIL_USER` (`secret:false`), the backend could then render the full pasted value after a backspace or typed edit. The readable Python prompt retained paste provenance until the field emptied. The root agent separated sticky `fromPaste` provenance from the preview flag. The final native PTY suite's pasted-address edit/save check passed in this review run.

**Medium: valid U+FFFD characters were silently deleted from pasted credentials. Resolved by explicit refusal.** `vendor/github.com/charmbracelet/ultraviolet/terminal_reader.go:357-361` excludes decoded `utf8.RuneError`, including correctly encoded literal U+FFFD. Reproduced with an isolated native PTY: paste `synthetic_PRIVATE_�_VALUE_12345`, save, and compare the child environment without printing it. U+FFFD was absent (comparison exited 42). The input guard now explicitly refuses malformed UTF-8 and literal U+FFFD before that decoder; it never silently changes an accepted value. Ordinary Unicode remains accepted. Unit tests and real PTY checks for both refusal cases passed.

No unresolved high or medium finding remains from this bounded review.

## Exercised evidence

- Before fixes: `go test ./cmd/godmode ./internal/core ./internal/ui` and all 5 then-existing native PTY tests passed; the additional interrupted-paste and U+FFFD reproductions exposed gaps not covered by those tests.
- Final candidate rebuilt with `scripts/build-native.sh` after the UTF-8 fix.
- Final `go test -race ./internal/ui`: passed (2.262 seconds).
- Final `python3 -m unittest discover -s tests -p 'test_native_*.py' -v`: 16 passed (6.949 seconds): 6 native CLI PTY tests, 5 input-guard PTY tests, and 5 packaging tests included by the glob.
- Input PTYs cover incomplete-paste Ctrl-C and Ctrl-D, 20 ms delayed tail bytes, a fragmented oversized paste followed by Enter and queued data, complete CRLF paste requiring explicit Enter, ignored menu paste followed by Done and delayed tail bytes, and malformed UTF-8/literal U+FFFD refusal. Assertions check secret masking, no unintended saves, exit status, terminal flags, bracketed-paste disablement, and alternate-screen restoration.
- Five focused guard unit tests exercise fragmented boundaries, cancellation, bounds, ordinary key sequences, and exact ordinary Unicode preservation.

The teardown drain is deliberately bounded to 80 ms of quiet and 500 ms total; the tested 20 ms delayed tails stayed private. This is local code/runtime evidence, not provider-access or commercial validation.
