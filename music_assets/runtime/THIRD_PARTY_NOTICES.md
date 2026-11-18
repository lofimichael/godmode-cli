# Godmode music runtime sources and assets

This is the selected source/runtime material copied for Michael's private local
Godmode music installation. It contains no music catalog, OOTRS collection,
recordings, ROM, downloaded archive, GUI converter, or prebuilt executable.

## Original code

`synthesize.py`, `experiments/render_synth.c`, and `oot-instruments.json` were
copied from Michael Kirsanov's Darunia CLI on 2026-11-17. The original MIT notice
is retained in `COPYING-DARUNIA.txt`. Its scope does not grant rights to upstream
tools, music, samples, or recordings. The renderer retains the whole-song
instrument preflight: one unsupported instrument selects piano for every channel.

## Separate converter

SEQ64 is pinned to `47500ab1bbf93eeaad35806ff6a13163cc11538a`:
https://github.com/sauraen/seq64/tree/47500ab1bbf93eeaad35806ff6a13163cc11538a

Its seven console source/header files and Zelda ABI are retained with upstream
source notices, README, and GPL text in `vendor/seq64`. Source headers permit
GPL version 3 or later. Godmode's `CMakeLists.txt` is an adapted minimal build
recipe and marks its changes. The converter is compiled as a separate process,
not linked into Godmode's native UI.

JUCE is pinned to `69795dc8e589a9eb5df251b6dd994859bf7b3fab`:
https://github.com/juce-framework/JUCE/tree/69795dc8e589a9eb5df251b6dd994859bf7b3fab

The actual module headers identify JUCE 7.0.5. `juce_core`, `juce_events`, and
`juce_audio_basics` use ISC notices. `juce_data_structures` offers GPLv3 as its
open-source option. Their complete module sources and embedded third-party
notices are retained. The upstream top-level notice is `vendor/juce/LICENSE.md`.
This build uses the GPL option for the separate SEQ64 executable.

## Renderer headers

TinySoundFont and TinyMidiLoader are pinned to
`853a0a171759f1ddba0de1442133a75912bbeffa`:
https://github.com/schellingb/TinySoundFont/tree/853a0a171759f1ddba0de1442133a75912bbeffa

`tools/tsf.h` retains its MIT notice, Bernhard Schelling 2017-2025 and SFZero's
Steve Folta 2012 attribution. `tools/tml.h` retains its separate zlib notice,
Bernhard Schelling 2017, 2018, 2020. No header modifications were made.

## Locally copied instrument assets

`tools/florestan-subset.sf2` is the 531,786-byte example asset in the pinned
TinySoundFont source. Its embedded `ICOP` field reads `Public Domain`; its
embedded comments point to the Florestan author sites. No separate font-specific
permission document was found in the inspected source. The original metadata is
preserved; the renderer header's MIT license is not assigned to the samples.
SHA-256: `1d890349a4bf0ae8d932000f0157633c03b81e127e479e069238ff382db44a32`.

The three mapped community OoT banks were copied from Michael's existing local
Darunia installation under his explicit instruction to make Godmode self-contained:

| File | Bytes | SHA-256 |
|---|---:|---|
| 03 Main Orchestra.sf2 | 1667242 | aa4513d863c4c3b2ef92f4f4d0df8b7408c13f21003f58e4b40f90eb09dd7444 |
| 20 Battle 2.sf2 | 1714544 | d5a06256be61c67594ffcf409e3095571f5bf5dcda9e709433aced5d7f233066 |
| 22 Ending Orchestra 2.sf2 | 1681152 | e7693145ecf37f4d887d6a68e6bd98e1128be27cbfd3f5803b52626855fdc26a |

Source archive pointer: https://www.mediafire.com/file/9pei4yktfd24fdo/OoT_Soundfonts.zip/file
Pinned archive SHA-256: `bd947fd6523b99875ff984083a0b6b945c5a1cb3999a86f70771f75e024d8f7b`.
The inspected archive contains no license-like text file, and these three fonts
contain no embedded copyright/license field. Their asset redistribution rights
have not been established. This private/local copy does not assert such rights;
no public release of these assets was requested or performed. No other bank from
the larger pack is included.

FFmpeg, mpv, CMake, and C/C++ compilers are external installed tools, not bundled
binaries. Setup performs no network requests or package installations.
