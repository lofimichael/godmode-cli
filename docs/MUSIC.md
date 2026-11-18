# GODMODE BEATZ

`godmode music` opens the optional Music Pack's local library, queue, and player.
Browse without interrupting the current track. Closing the interface leaves
music playing; `godmode music stop` stops playback and unfinished synthesis.

Godmode's core includes the pack installer and command router. The separate pack
contains the player interface, synthesis source, instruments, and original
jingles. Installing the pack does not require a Darunia checkout or include a
song library.

## Install the local preview

The Music Pack is currently a local preview. Its remote release manifest at
`https://godmode.build/packs/music/latest.json` is planned but has not been
published. Use the supplied companion executable and its SHA-256:

```sh
godmode music install --file /path/to/godmode-music --sha256 SHA256
```

Replace `SHA256` with the supplied 64-character checksum. The installer checks
the artifact's checksum, platform, and pack protocol before installing it under
`GODMODE_HOME/packs/music` (`~/.godmode/packs/music` by default). No music assets
are extracted and no synth is compiled just by installing or opening Godmode.

`godmode music install` keeps an installed pack or reinstalls the previously
selected local preview when its file and checksum still match. On a fresh home
without that local source, it attempts the planned remote release and currently
reports that the download is unavailable. The local preview command above is
the working installation route.

Playback needs [mpv](https://mpv.io/). Synth setup also needs Python 3.9+, a C/C++
compiler, CMake, and FFmpeg. On macOS, with Homebrew and the Command Line Tools
already available:

```sh
brew install mpv ffmpeg cmake
godmode music setup --songs /path/to/local/music
godmode music
```

On Linux, install those tools through your package manager. Setup checks for the
required tools, verifies the included files, builds the converter and renderer,
checks their output, and links your existing `.ootrs` folder. It reuses a valid
runtime on subsequent setup calls. Keep source songs outside Godmode's managed
pack and `state/music` folders. Godmode does not install dependencies on startup
or fetch songs. Sound plays on the computer running Godmode.

## Browse and listen

| Control | Action |
| --- | --- |
| Up/down | Move selection; playback stays unchanged |
| Enter | Submit search, open a collection, or play the selected track |
| `/` | Search the library |
| Esc | Close search/help or return to the parent collection |
| Tab | Focus search results, or switch between library and queue |
| `a` | Add the selection to the queue |
| `c` | Open the selected track's collection; Esc returns to the previous view |
| `A` | Add that whole collection to the queue |
| `i` | Read the full selected title, collection, and path |
| Space | Pause or resume |
| `n` / `p` | Next / previous track |
| `<` / `>` | Seek backward / forward |
| `-` / `+` | Change player volume |
| `r` | Cycle repeat off, one track, or the whole queue |
| `s` | Toggle shuffle |
| `x` | Stop playback and preparation |
| `q` / Ctrl-C | Close the interface; playback continues |
| `?` | Show all controls |

The selected row and the playing track are separate. The persistent transport
area shows the current track, preparation/playback state, position, volume,
repeat, and shuffle. The library remains available while the synth prepares
audio. The queue is a snapshot: searching or navigating does not change it.

While typing a search, Enter or Tab focuses the results without starting audio.
Use `c` on a result to browse its soundtrack, or `A` to queue the soundtrack
directly. Ctrl-U clears the search input. Returning from the queue preserves
your query and selected result. Enter on a library track replaces the queue with
the visible tracks, starting at that row. The selected-track hint states this
before you play. Use `a` to append instead. Enter in the queue plays the chosen
queued track.

## Control from another terminal

```sh
godmode music list 'Chrono Trigger'
godmode music play 'Chrono Trigger/Corridors of Time.ootrs'
godmode music pause
godmode music resume
godmode music seek 15
godmode music volume 35
godmode music repeat all
godmode music shuffle on
godmode music next
godmode music queue
godmode music queue add 'Chrono Trigger/Corridors of Time.ootrs'
godmode music queue remove 2
godmode music status --json
godmode music stop
```

`play` starts a background session and returns. Reopen `godmode music` to control
the same session. One player owns each Godmode home; business/key selections do
not create different players. `godmode --home DIR music` selects a separate
music state root. Stop is safe to repeat and remains available if the synth is
missing. Stop preserves your queue and volume/repeat/shuffle settings; restored
sessions are always stopped. `godmode music queue clear` clears the queue
explicitly. Queue removal uses the one-based index shown by `music queue`.

`godmode --plain music` prints the text command guide instead of opening the
full-screen player. Headless commands do not require a full-screen terminal.

## Original jingles

```sh
godmode jingle list
godmode jingle play
godmode jingle play success --volume 25
godmode jingle play attention --json
```

The pack includes `ready`, `success`, and `attention`: short original tones
created procedurally, without sampled music. `play` defaults to `ready`, and
volume defaults to 35 on a 0–100 scale. Jingles need the installed pack and mpv;
they do not need synth setup or local tracks.

A jingle uses its own bounded player process and the default audio output. It
does not change the music queue, playback position, or saved volume. Ctrl-C
stops the jingle. A success message is printed only after its player exits
successfully; `--json` returns the played cue's name, duration, and volume.

## Synthesis and cache

```sh
godmode music play 'Chrono Trigger/Corridors of Time.ootrs' --seconds 30 --render-only
godmode music stop
godmode music clear
```

The default render lasts three minutes; `--seconds` accepts 1–3600 seconds.
The included Darunia-derived synth uses OoT mappings when the complete song is
supported, otherwise it renders the whole song with piano. It does not mix
fallback piano into an otherwise mapped song.

Synthesized WAVs live in `GODMODE_HOME/state/music/cache`. The synth fingerprints
the sequence, sound settings, tools, fonts, and duration before reusing a render.
Godmode verifies the WAV's SHA-256 receipt before playback. The cache currently
has no automatic size limit or eviction policy. Use `music clear` to remove
cached renders; it keeps source songs, the runtime, and settings. Stop playback
first because `clear` refuses to run while the player owns the cache.

On the measured Mac, the companion is about **15.2 MB** and its compiled runtime
adds **14.0 MB**: approximately **29.2 MB** before source songs, shared system
dependencies, and cached audio. A three-minute render adds roughly **32 MB**.
The local preview source artifact is also retained outside the managed pack so
it can be reinstalled. Cold synth setup took about **13 seconds**; verified reuse
took under a second including command startup. These are local measurements,
not cross-platform guarantees. See the [audit and samples](dev/MUSIC_AUDIT.md).

## Motion and timing

The spectrum uses PCM analysis of the rendered file at mpv's reported audio
position. Process-launch time is not the playback clock. Pause and seek use the
same player state as the visualization. This is file analysis, not microphone or
system-output recording; it does not measure speaker or Bluetooth latency.

Saved Motion settings and `--no-motion` disable animated visualization.
`NO_COLOR=1` removes color. No fake playback bars run during synthesis.

## Remove the pack

Close open music views and let setup finish or cancel it before removal:

```sh
godmode music remove
```

Removal stops the pack's playback and preparation, then removes its installed
companion, owned runtime, rendered cache, session files, and music configuration.
It preserves source songs outside those managed folders, shared Homebrew/system
dependencies, provider keys, business profiles, and other Godmode settings. The
small local-source record remains so `music install` can reinstall the same
preview if its original artifact is still available. Removal refuses to delete
a configured song folder inside the managed music directories; move it out
first. Active views or setup must close before the pack can be removed.

## Runtime boundary and provenance

The pack owns its Python adapter/session process, Go interface, private local
control socket, and `state/music` files. Interface clients send bounded semantic
commands. The pack does not import the credential store or receive provider
keys. Core Godmode forwards its home and shared motion preference. Music code,
instruments, and player UI are carried by the companion, separately from the
core executable.

The current private/local pack copies the necessary code and four instrument
fonts from Michael's existing Darunia installation with his authorization.
Original integration code retains its MIT notice; TinySoundFont is MIT,
TinyMidiLoader is zlib, and the separate SEQ64 converter and its dependencies
retain their source and license notices. The fallback font's embedded metadata
says `Public Domain`; the inspected OoT bank archive has no separate license
text. These recorded facts do not assert public distribution rights for samples
or songs. See [the retained notices](../music_assets/runtime/THIRD_PARTY_NOTICES.md)
and [asset manifest](../music_assets/manifest.json).
