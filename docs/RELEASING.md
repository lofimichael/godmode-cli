# Build and release

Contributors need Rust 1.96, Python 3 for shlex compatibility fixtures, and a POSIX shell. End users of a prebuilt binary do not need those development tools.

Keep the design centered on one editable `.env.godmode` file. New features must not make agents depend on this executable to read or use saved credentials, or require provider registration for arbitrary key names.

## Local checks

```sh
cargo fmt --all -- --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
python3 tests/gen_shlex_vectors.py > target/shlex_vectors.json
cmp tests/shlex_vectors.json target/shlex_vectors.json
sh tests/install.sh
sh tests/install-update.sh
cargo build --release --locked
python3 tests/pty_smoke.py target/release/godmode
python3 tests/pty_setup.py target/release/godmode
```

Test the UI with synthetic values and explicit isolated `--config-dir` and `--state-dir` paths, including narrow terminal sizes, bracketed paste and cancellation. Do not use a real credential store for development. Running the build path is enough; installing over another `godmode` is unnecessary.

The [installation guide](INSTALLATION.md) documents the self-contained Godmode home, legacy detection, PATH handoff and side-by-side installation. Installer tests use synthetic executables and temporary home directories; they never install into the developer's home directory.

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

Each archive contains `godmode`, `install.sh`, `LICENSE`, `README.md`, `READTHIS.NFO` and `docs/`. Keep `install.sh` in the checksum-covered archive: it becomes the installed `godmodeup` command and updates alongside the executable. A separate `SHA256SUMS` covers the archives. The final job uses only the repository-scoped workflow token to create a **draft** GitHub release; it refuses to replace an existing release. Release publication is a separate maintainer action. There is no crates.io publish, automatic version bump, Apple signing or notarization step.

Before handing off a release, run its bootstrap in a temporary home, then run the installed `godmodeup` twice. Verify the installed bytes, previous-binary backup, shell PATH integration, and unchanged credentials. Check the CLI in light and dark terminal themes.

The workflow is a packaging implementation, not evidence that any release or target has been tested remotely. Record the actual build results when a release is run. Source and checksums should be distributed through the intended repository; hashes alone do not authenticate a compromised publisher.

## Cargo distribution

A crates.io package is a useful source-install option for people who already have Rust. This repository has not published one. Its package name is `godmode`, with a binary of the same name; `godmode-cli` on crates.io belongs to an unrelated project.

Before any authorized publication, inspect `cargo package --list`, verify the archive contains no private files, and run `cargo package --locked` to build the packaged source. Test `cargo install --path . --locked --root /an/isolated/temporary/home` and run the resulting binary's setup. Publishing makes the packaged source public even if the GitHub repository stays private; it is a separate maintainer action. No publish command is run by the release workflow.

The release installer provides the prebuilt path without a Rust toolchain. Keep both routes on the same interactive `setup` behavior.
