# Build and release

Contributors need Rust 1.96, Python 3 for shlex compatibility fixtures, and a POSIX shell. End users of a prebuilt binary do not need those development tools.

## Local checks

```sh
cargo fmt --all -- --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
python3 tests/gen_shlex_vectors.py > target/shlex_vectors.json
cmp tests/shlex_vectors.json target/shlex_vectors.json
sh tests/install.sh
cargo build --release --locked
python3 tests/pty_smoke.py target/release/godmode
```

Test the UI with synthetic values and explicit isolated `--config-dir` and `--state-dir` paths, including narrow terminal sizes, bracketed paste and cancellation. Do not use a real credential store for development. Running the build path is enough; installing over another `godmode` is unnecessary.

## CI and cost

`Check` runs formatting, Clippy, tests, shlex fixture parity, installer tests, a release build and a real-terminal onboarding smoke test on Linux and macOS. Public repositories run it on pushes and pull requests. Private repositories require `GODMODE_CI_ENABLED=true` as a repository variable, or an explicit manual dispatch.

Private GitHub-hosted runners draw from included compute and can then incur charges. Check the repository owner's Actions budget before enabling automatic jobs or dispatching the build matrix. [GitHub's runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners) documents current labels and billing behavior. No provider credentials are required by these workflows.

## Draft a release

1. Finish local checks, commit the intended files and merge them to `main`.
2. Set `Cargo.toml` and `Cargo.lock` to the intended version. Create and push an existing `vX.Y.Z` tag on the checked commit.
3. Manually dispatch **Build draft release** with that tag. Pushing a tag alone does not start a release.
4. Inspect the draft's archives, checksums and workflow results. Test each intended distribution before publishing the draft.

The workflow refuses a tag that differs from the package version or does not point to a commit on `main`. It builds and tests four native targets:

| Target | Runner |
| --- | --- |
| `aarch64-apple-darwin` | `macos-15` |
| `x86_64-apple-darwin` | `macos-15-intel` |
| `x86_64-unknown-linux-musl` | `ubuntu-24.04` with `musl-tools` |
| `aarch64-unknown-linux-musl` | `ubuntu-24.04-arm` with `musl-tools` |

Each archive contains `godmode`, `install.sh`, `LICENSE`, `README.md`, `READTHIS.NFO` and `docs/`. A separate `SHA256SUMS` covers the archives. The final job uses only the repository-scoped workflow token to create a **draft** GitHub release; it refuses to replace an existing release. Release publication is a separate maintainer action. There is no crates.io publish, automatic version bump, Apple signing or notarization step.

The workflow is a packaging implementation, not evidence that any release or target has been tested remotely. Record the actual build results when a release is run. Source and checksums should be distributed through the intended repository; hashes alone do not authenticate a compromised publisher.
