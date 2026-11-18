# Self-contained music runtime inventory

Inspected and implemented 2026-11-17. Source: `/Users/michael/Documents/GitHub/darunias-cli`. Following Michael's explicit direction, the separate optional Music Pack includes the minimal source/runtime material and the existing three mapped OoT fonts for his private local installation.

## Recommended boundary

Godmode can own an offline source bundle and compile its private runtime with `godmode music setup --songs DIR`. No Darunia checkout, Git fetch, downloaded music catalog, game ROM, or downloaded recording is needed. Existing FFmpeg and mpv remain external executables; compilation additionally uses C/C++ and CMake. All four dependencies are currently installed on this Mac.

The source bundle contains original adapter/renderer/mapping, the exact console converter source and ABI, four required JUCE modules, TinySoundFont/TinyMidiLoader, four required font files, and notices. SEQ64 remains a separate GPL executable, not a linked component of the native Godmode UI. No installed prebuilt binary is copied: the setup compiles the converter and renderer locally.

## Smallest verified source set

| Component | Exact required content | License/provenance evidence |
|---|---|---|
| Original synthesis adapter | `synthesize.py` (~16 KB) | Repository MIT, Michael Kirsanov 2026; scope explicitly excludes third-party assets |
| Original renderer | `experiments/render_synth.c` (~8 KB) | Same MIT; preserves full-MIDI preflight and whole-song fallback |
| Original mapping | `oot-instruments.json` (~4 KB) | Original project mapping; includes bank/font hashes and program-to-preset names |
| SEQ64 | `CommandLine.hpp/.cpp`, `Common.hpp`, `SeqFile.hpp/.cpp`, `MainConsole.cpp`, `JuceHeaderConsole.hpp`; GPL notice; one `abi/4 - Zelda.xml` (~45 KB) | Pinned commit `47500ab1bbf93eeaad35806ff6a13163cc11538a`; GPLv3 README, GPLv3-or-later source headers; [primary README](https://github.com/sauraen/seq64/blob/47500ab1bbf93eeaad35806ff6a13163cc11538a/README.md) |
| JUCE | Complete `juce_core`, `juce_events`, `juce_audio_basics`, `juce_data_structures` modules, with embedded notices and top-level notice | Pinned commit `69795dc8e589a9eb5df251b6dd994859bf7b3fab`. Actual headers say **7.0.5**, despite SEQ64 README saying JUCE 6. First three modules ISC; [data structures explicitly offers GPLv3](https://raw.githubusercontent.com/juce-framework/JUCE/69795dc8e589a9eb5df251b6dd994859bf7b3fab/modules/juce_data_structures/juce_data_structures.h). |
| TinySoundFont | `tsf.h` (~92 KB) with its license block | MIT; pinned `853a0a171759f1ddba0de1442133a75912bbeffa`; [primary license](https://raw.githubusercontent.com/schellingb/TinySoundFont/853a0a171759f1ddba0de1442133a75912bbeffa/LICENSE) |
| TinyMidiLoader | `tml.h` (~20 KB) with its license block | Its header says zlib, not MIT; retain its exact notice |
| Baseline piano | `florestan-subset.sf2`, 531,786 bytes | Primary asset metadata: `ICOP=Public Domain`, author-site pointers in `ICMT`. TinySoundFont includes it as an example font. No separate asset-specific permission text was found in the inspected pinned source; retain this precise provenance statement rather than applying the code's MIT license to samples. |

The implemented bundle contains **464 files; 11,535,965 uncompressed bytes; 6,789,624 compressed ZIP bytes**, including piano, the three mapped OoT fonts, a minimal replacement build recipe, and notices. No build products are bundled. The generated music-only readable Python engine is 9,258,328 bytes; it belongs to the separate opt-in Music Pack and is excluded from the core CLI.

The actual existing SEQ64 executable is **2,528,096 bytes**, arm64 Mach-O. Its linked dependencies are Apple system frameworks, libc++, libSystem, and libobjc. The old `tools/seq64` directory's ~20 MB includes build products and is not the necessary runtime size.

## Fonts and local migration

The original installed OoT fonts occupy ~28 MB, but the current map uses only three banks: `03 Main Orchestra.sf2`, `20 Battle 2.sf2`, and `22 Ending Orchestra 2.sf2` (5,062,938 bytes together). Michael explicitly authorized copying the necessary existing assets to preserve OoT-by-default playback in his self-contained private installation. These three files are included; the rest of the pack is excluded. The inspected archive/source provides no asset redistribution license, and the notice records that fact without asserting one. No public release was requested or performed.

`music setup --songs DIR` builds from bundled materials and installs the same three fonts automatically. Runtime mapping still makes the entire song piano if one required instrument is unsupported. No instrument-mode flag, Darunia checkout, network request, or asset download is required.

## Setup design

1. Validate the songs folder and build executables before writes; acquire the existing music/cache lifetime lock.
2. Load bundled manifest and data, enforce member count/size/path bounds, validate SHA-256, and extract into a private temporary directory under music state. Refuse links and nonregular files.
3. Compile the original renderer and a separate console-only SEQ64 using a small owned build recipe. Preserve C++17, disable browser/curl features, and carry over the working macOS Objective-C++ treatment for JUCE core/events plus required Apple frameworks. Linux uses threads/dl and ordinary C++.
4. Keep only the required ABI beside the converter. Retain the corresponding source and notices inside the owned runtime bundle.
5. Verify executable output and a deterministic synthetic render before atomically publishing the runtime and config. Failed setup leaves the existing config/runtime/cache unchanged. Repeated setup verifies and reuses an intact runtime.
6. Continue using the existing `_music_config`, render receipts, cache checks, file signatures, detached session, and native UI contract. Replace Darunia-link language with owned-engine setup language; legacy `init` can remain a compatibility route.
7. The source/native builders include assets only when music is enabled. `--without-music` and native `nomusic` must exclude source blobs, extraction/setup functions, notices/assets specific to music, and transport code.

Observed new macOS cold setup: **13.146 seconds**; repeated full-integrity reuse: **0.108 seconds**; owned runtime: **13,972,742 bytes**. Setup roundtripped generated MIDI through SEQ64 and verified nonzero renderer PCM. Cancellation testing confirmed compiler descendants are reaped, unrelated processes survive, staging is removed, and existing configuration is retained. Linux build behavior remains unexercised. Evidence: `.context/music-audit/verification/owned-runtime-setup.json`.
