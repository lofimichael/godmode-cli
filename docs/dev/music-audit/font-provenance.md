# Music font and notice inventory

Inspected 2026-11-17. Read-only inspection of `/Users/michael/Documents/GitHub/darunias-cli`, plus narrow primary-source lookups. No secret files read; no assets changed or downloaded. This note is an implementation inventory, not a determination about third-party sample rights.

## Recommendation for the authorized private migration

Copy the working renderer and library headers with their existing notices. Copy the existing `florestan-subset.sf2` intact as the fallback: 531,786 bytes (519 KiB) is already a practical small runtime font and avoids inventing a new font-reduction step. The existing renderer must select the preset named `Piano`; this font stores it at bank 0/program 2, not program 0.

If retaining Darunia's current automatic OoT-first behavior, copy exactly the three mapped bank fonts below plus `oot-instruments.json`. Total fonts including fallback are 5,594,724 bytes (5.34 MiB). The currently installed directory contains many more fonts than the mapping uses. Do not copy the other banks, 32,749,950-byte source ZIP, raw samples, cached WAVs, recordings, or broad build directories merely to make the runtime work.

Original MIT renderer code, MIT `tsf.h`, zlib `tml.h`, and the separately invoked GPL converter/source can be carried with their respective notices and build/source material. Keep the converter as its own executable and retain its source/build recipe; the other inventory is checking the precise SEQ64/JUCE source subset. Do not label every dependency or sample as MIT.

The source inventory has enough evidence to implement the user's authorized private/local transfer now, including all four fonts in the self-contained runtime bundle. The small fallback's embedded notice says `Public Domain`; no separate license statement for the exact sample subset was independently located. The OoT package has no discovered license text. Preserve that factual distinction in an internal third-party notice rather than claiming new redistribution authority. If the product is later distributed with assets, revisit the asset manifest then; that is outside this private-copy task. No user-facing warning or new permission gate is needed for the requested local migration.

## Verified local files

| File in Darunia | Bytes | SHA-256 |
| --- | ---: | --- |
| `tools/florestan-subset.sf2` | 531,786 | `1d890349a4bf0ae8d932000f0157633c03b81e127e479e069238ff382db44a32` |
| `tools/oot-soundfonts/03 Main Orchestra.sf2` | 1,667,242 | `aa4513d863c4c3b2ef92f4f4d0df8b7408c13f21003f58e4b40f90eb09dd7444` |
| `tools/oot-soundfonts/20 Battle 2.sf2` | 1,714,544 | `d5a06256be61c67594ffcf409e3095571f5bf5dcda9e709433aced5d7f233066` |
| `tools/oot-soundfonts/22 Ending Orchestra 2.sf2` | 1,681,152 | `e7693145ecf37f4d887d6a68e6bd98e1128be27cbfd3f5803b52626855fdc26a` |

The three OoT files total 5,062,938 bytes. Their actual hashes match `oot-instruments.json`. All four files' RIFF INFO metadata was parsed directly during this inspection. The fallback has 17 real presets; the first is Piano. Unused presets occupy some of its already small size; no piano-only derivative was needed or produced.

## Exact provenance and notices

- `experiments/setup-synthesis.sh` fetches `tsf.h`, `tml.h`, and `examples/florestan-subset.sf2` from TinySoundFont commit `853a0a171759f1ddba0de1442133a75912bbeffa`.
- Florestan RIFF INFO: `INAM=florestan-subsetttt.sf2`, `ISFT=Awave v4.8:SFEDT v1.28:`, `ICOP=Public Domain`, `ICMT=http://go.to/florestan` followed by `http://nandoflorestan.cjb.net`. These are observed embedded labels, not a separate audit of the originating recordings.
- The pinned upstream README describes the example SoundFont and labels the library MIT. Its root LICENSE is a software MIT notice. Neither retrieved text separately explains the provenance of the exact `florestan-subset.sf2` samples.
- The primary author website, Nando Florestan's SoundFonts page, is still indexed with the author's discussion of his old SoundFonts, but direct page retrieval failed (HTTP 400). No additional exact-font license statement was established from it. No mirror's claim was promoted into primary evidence.
- `tools/tsf.h` embeds MIT text: Bernhard Schelling 2017–2025, based on SFZero / Steve Folta 2012. Preserve the header intact. The pinned repository root LICENSE gives an older copyright range (2017–2023); keep both if including the upstream root notice rather than silently rewriting it.
- `tools/tml.h` embeds the **zlib** license, with Bernhard Schelling 2017, 2018, 2020. Preserve it intact and mark source modifications if any. It is not MIT despite the umbrella repository license summary.
- Darunia's root `LICENSE` is Michael Kirsanov's MIT notice for original Python/C code and documentation, explicitly excluding third-party music/samples/tools/catalog data.
- `tools/seq64-source/LICENSE.txt` contains GPL version 3. SEQ64 is used as a separate executable. The companion runtime-source inventory confirms GPLv3-or-later source notices and pinned JUCE 7.0.5: core/events/audio_basics ISC, data_structures with an explicit GPLv3 alternative. Retain the source/build material and notices described there.

## OoT retrieval path and asset boundary

`experiments/install-oot-soundfonts.py` reads `oot-instruments.json`, verifies the already installed three named banks, and otherwise uses a local archive or parses the MediaFire download-page anchor. Downloads are HTTPS, size capped, and checked against archive SHA-256 `bd947fd6523b99875ff984083a0b6b945c5a1cb3999a86f70771f75e024d8f7b`. It writes only manifest basenames after per-bank hash verification and stages each file before replacement.

The current upstream community instrument guide still links that exact MediaFire archive and describes combined/per-bank fonts as a testing aid, with a pitch-accuracy caveat. It does not provide an asset license statement in the inspected passage. The existing local `build/oot-soundfonts.zip` contains 135 archive members and no filename matching README, LICENSE, COPYING, NOTICE, `.txt`, or `.md`. The three mapped fonts' INFO fields identify `Polyphone` as the writing tool and contain no `ICOP` field.

The combined `00 ALL.sf2` is larger than the three needed fonts (5,881,670 bytes) and has a different preset numbering scheme. Swapping it in would require mapping changes and verification without saving runtime size here.

## Suggested internal NOTICE text

Godmode's music runtime includes original Darunia integration code under Michael Kirsanov's MIT license, TinySoundFont under its embedded MIT notice, TinyMidiLoader under its embedded zlib notice, and the separately invoked SEQ64 converter with its GPL source and dependency notices. Each retained source file preserves its upstream notice.

The fallback `florestan-subset.sf2` is the example font from TinySoundFont commit `853a0a171759f1ddba0de1442133a75912bbeffa`. Its embedded copyright field reads `Public Domain`; its comment identifies the historic Florestan websites. The OoT bank fonts 03, 20, and 22 were copied from Michael's existing local Darunia installation for this private setup. They originate from the community pack linked by LuigiXHero's instrument guide. Their metadata names Polyphone as the writing tool; no separate license text was found in the inspected archive. These asset observations do not extend the MIT software license to samples or music. The four asset identities and hashes are recorded in this bundle's manifest.

## Primary-source links

- [Pinned TinySoundFont README](https://raw.githubusercontent.com/schellingb/TinySoundFont/853a0a171759f1ddba0de1442133a75912bbeffa/README.md)
- [Pinned TinySoundFont license](https://raw.githubusercontent.com/schellingb/TinySoundFont/853a0a171759f1ddba0de1442133a75912bbeffa/LICENSE)
- [Pinned example font](https://github.com/schellingb/TinySoundFont/blob/853a0a171759f1ddba0de1442133a75912bbeffa/examples/florestan-subset.sf2)
- [Nando Florestan's SoundFonts page](https://dev.nando.audio/pages/soundfonts.html) (index observed; direct fetch unsuccessful)
- [Community author instrument guide](https://raw.githubusercontent.com/LuigiXHero/OoT-Randomizer-Music-Pack/master/OoT%20Instrument%20List%20and%20Custom%20Music%20Tips.md)
- [Original linked OoT SoundFonts download page](https://www.mediafire.com/file/9pei4yktfd24fdo/OoT_Soundfonts.zip/file)

## Memory used only as an inspection pointer

`MEMORY.md:114-138` and `rollout_summaries/2026-11-14T12-49-28-oDNX-darunias_cli_oot_default_whole_song_piano_fallback.md` pointed to the three-bank mapping and whole-song fallback policy (rollout `01a1da1b-0c10-7943-83ec-f1503531c0b5`). Current files, hashes, embedded notices, and setup behavior above were verified afresh.
