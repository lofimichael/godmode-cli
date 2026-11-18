# CLI framework decision

Research and implementation audit date: November 14, 2026. The current source
implements the selected Go interface and embedded Python engine. This document
distinguishes code inspection from release verification and performance tests.

## Decision and current implementation

**Go with Bubble Tea v2 and Lip Gloss v2 owns Godmode's default interactive
experience. The existing Python credential/profile implementation remains the
embedded file engine.** Direct commands and plain mode use that engine.

The visual experience takes priority over preserving the old Python interface.
Bubble Tea's event/update/view model and Lip Gloss's styling support the NFO
welcome, typography, brief animation and responsive previews. The native home,
provider, key, profile, agent and FAQ views live in `internal/ui`.

The native executable embeds the assembled readable Python source. During an
interactive session, Go owns input and rendering; one session-owned Python
subprocess handles bounded JSON-line requests over private pipes. Its in-memory
preview IDs retain snapshots until a save or cancellation. The Python engine
reads/writes the store, validates edits, computes masked key previews and checks
for concurrent file changes. The existing Python terminal code remains embedded
for plain mode and compatibility routes; the native default no
longer uses it for the main guided interface.

A full Go rewrite would require reproducing the credential store's
encryption compatibility, shell parsing, comment preservation, ownership,
locking and atomic replacement. Reimplementing those systems does not make the
interface prettier. Keep them behind a narrow adapter now; consider moving them
only with independent format/behavior compatibility evidence later.

This architecture retains the existing Python 3.9+ prerequisite. A single
installed native executable does **not** mean a standalone native runtime.
Embedding source does not make the binary directly readable either.
`godmode source` emits the exact embedded core; `godmode build-info` reports its
hash, compiler and Go modules. The separate `-source.tar.gz` release archive
contains matching Go/Python sources, build scripts and vendored dependencies.
Native archives contain the executable, documentation, build metadata and license
notices. No Python interpreter is bundled.

`go.mod` pins Bubble Tea 2.1.1, Lip Gloss 2.1.0, x/ansi 0.11.9 and x/term 0.2.2;
`go.sum` and `vendor/modules.txt` record the dependency set. `scripts/build-native.sh`
uses Go 1.26.7, `-mod=vendor` when the vendor tree is present, `CGO_ENABLED=0`,
`-trimpath`, no VCS metadata and an empty build ID. It assembles the core before
building. `scripts/package-native.py` requires the vendor tree and produces four
native target archives plus the complete source archive. Building requires the
pinned Go toolchain; installing a native archive does not.

## What was inspected locally

- `lib/godmode_terminal.py`: hidden input, a 1 MiB paste bound, fragmented paste
  parsing, cancellation, signal handling, resize/reflow, masked previews and
  explicit plain mode. Current cleanup flushes unread terminal input.
- `lib/godmode_store.py`: the existing writer is a separate concern from the
  renderer. Retain its validation, locking and atomic-write behavior.
- `scripts/build.py`: assembles the standard-library Python engine, including
  provider data and the bridge. It checks Python 3.9 and installs no packages.
- `cmd/godmode/main.go`, `internal/core/core.go`, `lib/godmode_bridge.py`:
  native routing, isolated Python execution, private protocol and session state.
- `go.mod`, `vendor/modules.txt`, `scripts/build-native.sh` and
  `scripts/package-native.py`: pinned dependencies, build flags and archive contents.
- `godmode.py`, `README.md`, `docs/dev/CLI_EXPERIENCE.md`: guided and direct
  routes, sparse copy, local storage, literal previews and static output.

Comparisons below are engineering judgments, not measured speed, memory,
accessibility or security results. The implementation audit read current code;
it did not rerun behavioral suites or certify a published release.

## Verified package snapshot

Versions come from the publishers' package registries or official release APIs,
not search-result summaries. Requirements refer to these versions, not every
older release. Dependency counts are declared direct dependencies, not a
resolved transitive audit or final binary size.

| Library | Current version inspected | License | Runtime/build floor and dependency facts |
| --- | --- | --- | --- |
| Rich | 15.0.0 | MIT | Python >=3.9; two ordinary direct dependencies: markdown-it-py and Pygments. Optional Jupyter dependencies excluded. [Metadata](https://pypi.org/pypi/rich/15.0.0/json) |
| prompt_toolkit | 3.0.53 | BSD-3-Clause | **Python >=3.10**; one declared dependency, wcwidth. Adopting it would raise Godmode's current 3.9 floor; it is not selected. [Metadata](https://pypi.org/pypi/prompt_toolkit/3.0.53/json), [license](https://github.com/prompt-toolkit/python-prompt-toolkit/blob/3.0.53/LICENSE) |
| Textual | 8.2.8 | MIT | Python >=3.9,<4; six ordinary direct requirements, including Rich, Markdown parsers, platformdirs and typing-extensions. Optional syntax extras add Tree-sitter packages. [Metadata](https://pypi.org/pypi/textual/8.2.8/json) |
| Bubble Tea | 2.1.1 | MIT | Go 1.26.0 declared; eight direct module requirements and nine indirect entries in the tagged manifest. Some entries serve development/testing; this is not runtime linkage count. [Release](https://github.com/charmbracelet/bubbletea/releases/tag/v2.1.1), [manifest](https://github.com/charmbracelet/bubbletea/blob/v2.1.1/go.mod), [license](https://github.com/charmbracelet/bubbletea/blob/v2.1.1/LICENSE) |
| Lip Gloss | 2.1.0 | MIT | Go 1.26.7 declared; ten direct module requirements. Together with Bubble Tea, use the higher toolchain floor and a resolved shared graph. [Manifest](https://github.com/charmbracelet/lipgloss/blob/v2.1.0/go.mod), [license](https://github.com/charmbracelet/lipgloss/blob/v2.1.0/LICENSE) |
| Huh | 2.0.3 | MIT | Go 1.25.8 declared; depends on Bubbles, Bubble Tea and Lip Gloss plus other modules. It is a forms layer, not a tiny standalone prompt dependency. [Manifest](https://github.com/charmbracelet/huh/blob/v2.0.3/go.mod), [license](https://github.com/charmbracelet/huh/blob/v2.0.3/LICENSE) |
| Ratatui | 0.30.2 | MIT | Rust >=1.88.0; modular crates and feature-selected backends. Defaults include widgets, Crossterm, layout cache, macros and underline color. [Registry](https://crates.io/api/v1/crates/ratatui/0.30.2), [manifest](https://github.com/ratatui/ratatui/blob/ratatui-v0.30.2/ratatui/Cargo.toml) |
| Crossterm | 0.29.0 | MIT | Rust >=1.63.0; raw terminal/events layer. Default features include bracketed paste and events; use Ratatui's higher Rust floor for the combination. [Registry](https://crates.io/api/v1/crates/crossterm/0.29.0), [source](https://github.com/crossterm-rs/crossterm) |
| Ink | 8.0.0 | MIT | Node >=22, React >=19.3.0 peer; 23 declared direct dependencies, including React reconciler and Yoga layout. Devtools/type peers are separate and not all mandatory at runtime. [Metadata](https://registry.npmjs.org/ink/8.0.0), [source](https://github.com/vadimdemedes/ink) |
| Clack prompts | 1.9.0 | MIT | Node >=20.12.0; four direct dependencies including `@clack/core` 1.6.0. [Metadata](https://registry.npmjs.org/@clack/prompts/1.9.0), [source](https://github.com/bombshell-dev/clack) |

For example, search results still described Ink 7.x during this research while
the publisher's registry returned 8.0.0. A floating `latest` install is not a
reproducible decision. These are evidence snapshots, not future update pins.

## Comparison against Godmode's goals

The chosen visual direction outweighs preserving the current UI implementation.
Storage correctness, explicit writes and accessible output remain requirements.
The matrix distinguishes a Go UI migration from a full language rewrite; those
are different amounts of work and risk.

| Candidate | Experience fit | What must be rebuilt | Distribution / inspectability | Decision |
| --- | --- | --- | --- | --- |
| **Bubble Tea + Lip Gloss UI, embedded Python core** | Preferred visual/event foundation | Native UI and core adapter implemented | Native artifact plus existing Python; separate complete source archive | **Implemented default** |
| Entirely Go | Same preferred UI | UI, file parser, crypto compatibility, profile/store operations and migration | Native-only deployment; compiled artifact needs source/build receipts | Defer storage rewrite |
| Python + prompt_toolkit | Capable custom inline/full-screen rendering | UI, with no process boundary | Python >=3.10 and vendored sources; smaller dependency graph | Alternative, not selected |
| Existing stdlib Python | Can draw the art but owns all terminal machinery | Continued growth of private terminal framework | Most directly readable current artifact | Retain as fallback/compatibility path |
| Python + Rich only | Strong styled output, insufficient input engine | Existing raw input machinery remains | Python plus Markdown/highlighting dependencies | Does not solve the right layer |
| Python + Textual | Rich app/widget/animation system | UI app model | More Python dependencies; readable source | More application machinery than needed |
| Rust + Ratatui/Crossterm | Excellent cell rendering | UI plus operations or another process boundary | Native artifacts; Rust graph/toolchain review | More migration cost without a UI advantage here |
| TypeScript + Ink | Strong React rendering and screen-reader primitives | UI plus operations or another process boundary | Node/React/Yoga graph or bundled runtime | No existing React reuse to offset cost |
| TypeScript + Clack | Strong focused installer prompts | UI and custom stage | Node plus prompt dependencies | Less suited to the requested expressive stage |

### Python

**prompt_toolkit** is an input/render engine, not merely a readline replacement.
Its custom layouts fit a staged NFO intro, focused key fields and narrow/wide
previews. It avoids rewriting the store or piping keys between languages. Its
ordinary widget appearance is not the desired Godmode art direction; keep the
custom row/fragment renderer if this alternative is revisited. The responsible
distribution would vendor the engine and wcwidth as source with pinned hashes,
licenses and an update receipt, rather than run pip on first launch. This would
change the installed artifact from one script to a source distribution.
[Custom applications](https://python-prompt-toolkit.readthedocs.io/en/master/pages/full_screen_apps.html),
[application API](https://python-prompt-toolkit.readthedocs.io/en/master/pages/reference.html#prompt_toolkit.application.Application).

Password masking is not a complete secret policy. A PromptSession normally has
history, while `is_password=True` masks rendering. Use an explicit no-history
implementation, no completion/suggestions, no external editor and no clipboard
integration for credentials. Keep paste completion separate from submission.
[Prompt/history documentation](https://python-prompt-toolkit.readthedocs.io/en/master/pages/asking_for_input.html),
[history API](https://python-prompt-toolkit.readthedocs.io/en/master/pages/reference.html#prompt_toolkit.history.DummyHistory).

**Rich** is excellent for styled static output, code and live displays. It does
not replace the raw input problem. Adding it alone leaves the hardest part of
Godmode's terminal layer intact; combining it with prompt_toolkit creates two
rendering systems to coordinate. Its automatic non-TTY behavior and color
detection are useful references. `NO_COLOR` removes colors but retains some
styles; it is not a screen-reader mode. [Console behavior](https://rich.readthedocs.io/en/stable/console.html).

**Textual** supplies layout, reactive state, widgets, CSS, animation and testing
tools. It has explicit `none/basic/full` animation levels and a separate smooth
scroll setting. It is the best Python option if Godmode becomes a multi-pane
application. Here its app structure and dependency graph exceed the need for a
few focused views. Do not claim its password widget or animation toggle makes
the whole app screen-reader accessible. [Animation](https://textual.textualize.io/guide/animation/),
[motion settings](https://textual.textualize.io/api/constants/).

### Go

**Bubble Tea + Lip Gloss** best matches an expressive native TUI: state updates,
timed messages, scoped drawing and good composition. Bubbles has password/hidden
echo modes and paste messages. Bubble Tea supplies terminal restoration and
panic recovery, but application errors must still avoid printing secret-bearing
values. Huh offers an explicit accessible mode that switches forms to standard
prompts; custom intro and diff views still need their own plain path.
[Bubble Tea](https://github.com/charmbracelet/bubbletea),
[text input source](https://github.com/charmbracelet/bubbles/blob/v2.0.0/textinput/textinput.go),
[Huh accessibility](https://github.com/charmbracelet/huh#accessibility).

An entirely native rewrite could remove the target machine's Python requirement;
the selected Go UI with embedded Python core retains it. Both need
per-OS/architecture release artifacts and a compiled artifact users cannot read
directly. Publish corresponding source, locked modules, license inventory, build
recipe and verification hashes. The current build disables Cgo.
Huh and Bubbles are not dependencies of this app;
Godmode uses its own views and input adapter on Bubble Tea and Lip Gloss.
The tagged Bubble Tea 2.1.1 release fixes a terminal size-report vulnerability;
“established framework” does not mean the dependency audit disappears.
[Release note](https://github.com/charmbracelet/bubbletea/releases/tag/v2.1.1).

### Rust

**Ratatui + Crossterm** provides excellent cell-level rendering, charts and
backend control with native distribution. It would work well for a sophisticated
dashboard. Ratatui deliberately leaves application/event architecture to the
developer; it is not a ready-made credential form system. Input editing,
accessible sequential prompts and Godmode's domain behavior remain work.
Feature selection can narrow the graph, but it cannot eliminate dependency and
toolchain review. Rust's ownership is helpful for lifecycle reasoning; it does
not automatically erase strings, prevent logging secrets or replace storage
tests. The migration cost exceeds the benefit of rendering a modest number of
terminal cells. [Backends and event model](https://ratatui.rs/concepts/backends/),
[Crossterm](https://github.com/crossterm-rs/crossterm).

### JavaScript / TypeScript

**Ink** offers React components, layout, animation and explicit screen-reader
support with an ARIA subset. It is a serious option, not an inaccessible toy.
Its rendering model suits teams already sharing React UI logic. Godmode shares
none, so Node/React/Yoga, transpilation and the larger package graph add cost
without code reuse. Keep secret values away from debugging tools, snapshots,
logging and component inspection. Node single-executable support can remove a
separate Node install, but bundling the runtime does not remove that runtime's
audit or platform packaging cost. [Ink accessibility and lifecycle](https://github.com/vadimdemedes/ink#screen-reader-support),
[Node executable packaging](https://nodejs.org/api/single-executable-applications.html).

**Clack** is the best narrow JavaScript choice for a friendly installer with
focused prompts. It supports masked passwords, cancellation signals and Unicode
fallbacks. Its opinionated prompt flow fits setup better than a custom NFO stage.
Adding Ink for the latter would recreate the two-renderer problem. A dedicated screen-reader mode was not established by the
documentation inspected; do not infer it from no-color support.
[Prompts](https://bomb.sh/docs/clack/packages/prompts/),
[lower-level core](https://bomb.sh/docs/clack/packages/core/).

## UI architecture, independent of framework

1. **One state model, two renderers.** Use simple view data for title, short
   instruction, selectable rows, proposed edits and receipt. The plain renderer
   prints complete static information and uses sequential prompts. It must not
   replay every animated frame into scrollback.
2. **Keep content literal.** Big ego-first NFO art belongs in the welcome.
   Operational views use a filename, `-` old value, `+` new value and one action.
   Mask keys before producing any display model. Profile/instruction edits show
   actual user-readable changes. Color reinforces signs; signs carry meaning.
3. **Separate capabilities.** Color, Unicode, cursor control and motion
   are distinct settings. Plain mode is static. Reduced motion keeps useful
   final states and removes flicker, sweeps and moving bars. Direct commands
   remain complete and pipeable. A terminal does not provide a universally
   reliable browser-style reduced-motion signal; offer an explicit setting.
4. **One terminal owner.** Do not mix Rich Live, a prompt_toolkit Application,
   another TUI and a child process's terminal output. Background work returns
   bounded events. Cancellation closes the app, stops owned child processes and
   restores echo, cursor and paste modes. SIGKILL cannot run application cleanup.
## Implemented operation boundary and acceptance

`cmd/godmode/main.go` selects the Go UI for interactive guided routes with a TTY.
Plain mode, a dumb/missing terminal, non-TTY use and direct commands use the
embedded Python engine. The direct runner preserves streams and environment,
returns the child exit status and relays INT, TERM and HUP. The UI client passes
an allowlisted environment and discards Python stderr so tracebacks cannot print
request contents. Source enters on descriptor 3; stdin remains available for key
input or the private protocol. Python starts with `-I -S` to ignore environment
module paths and site startup hooks.

### Private core interface

The adapter uses one bounded JSON request and response line per operation over
one session-owned subprocess. It is not a background daemon or network service.
There is no separately versioned public protocol: UI and engine ship in the same
binary. The request cap is 8 MiB, the native response cap is 2 MiB, and submitted
credential values have a separate 1 MiB UTF-8 limit. Calls are serialized; a
30-second timeout closes and kills the engine. Closing the UI closes stdin,
waits up to one second, then kills and reaps a child that has not exited.

| Operation | Request | Response / effect |
| --- | --- | --- |
| `state` | None; home chosen at engine startup | Catalog, field definitions, profile values, saved-key states, local progress and intro state; never stored raw secret values |
| `key_plan` | Key name | Opaque preview ID, field guidance and target metadata; core retains the store digest |
| `key_check` | Preview ID, proposed value and pasted flag | Validation and masked display data; core records the candidate digest; no write |
| `key_save` | Preview ID, same proposed value and pasted flag | Requires a checked candidate, validates again, calls the existing store with the expected file digest, invalidates the preview, returns a masked receipt |
| `profile_save` | Field and value/clear instruction | Uses the profile snapshot retained by `state`; existing profile writer rejects changed files |
| `agents_plan` / `agents_apply` | Plan request, then accepted opaque ID | Exact append/path preview; core retains file snapshots and applies guarded appends |

Other private actions accept the intro, mark/copy the agent note, return FAQ
entries or open a requested provider URL. They are UI implementation details,
not additional public commands.

An empty key entry that opens a provider URL and a key paste that only previews
remain distinct actions. The core decides key validity and masking, and returns
structured data rather than pre-styled ANSI strings. Go adds visual styling
without interpreting shell fragments or constructing credential assignments.

For key writes the frontend temporarily holds newly entered secret bytes and
sends them to the child on a private pipe. The implementation does not put them
in argv, environment variables or temporary files. The core never returns
stored plaintext credentials to the UI. Keep logs/error paths free of submitted
values and do not serialize the entire model for debugging.
Clearing a field reduces lifetime but is not a guarantee of managed-memory
zeroization in either Go or Python.

The source pipe avoids executable temporary files and leaves stdin independent.
The operation engine is noninteractive. It does not run a Python prompt under
the Go renderer. No dynamically downloaded code or package installation is needed. After an uncertain write,
refresh/reopen state rather than blindly repeating a mutation.

### Release checks

Exercise the welcome, provider choice, one fake-key edit, profile edit and
agent-note append in temporary homes.
No real credential inventory is required to prove these paths. Keep the
existing Python behavior tests and add meaningful cross-boundary checks for
plan/apply drift, schema errors, cancellation and direct-command compatibility.

Then verify the behaviors that a framework cannot promise for Godmode: a pasted
newline never saves; a cancelled/oversized fragmented paste cannot become shell
input; hidden text is absent from output and logs; Ctrl-C, Escape, HUP and TERM
restore terminal state; real resizes preserve the full preview; `NO_COLOR`,
ASCII, 40-column and wide layouts remain legible; plain mode works with a screen
reader; owned children stop on exit. Keep validation and the
atomic writer independent of the UI and preserve direct command output.

Measure the packaged Go candidate against the current build for startup time,
installed binary/source size, animation CPU and idle CPU. Publish the exact
embedded core, Go source and dependency inventory. Select native release
artifacts by supported OS/architecture, verify hashes and preserve an updater
rollback. Retain the Python floor in installer checks; do not advertise removal
of the Python dependency. Verify `godmode source` matches the embedded source
hash and that ordinary setup remains functional.

Bubble Tea now owns the default interactive experience, while file operations
remain in the Python engine. The acceptance checks above remain verification
requirements, not results asserted by this architecture audit. Release evidence
belongs in the verification/release records. Rewriting encryption and file
formats in Go remains a separate decision requiring compatibility evidence.
