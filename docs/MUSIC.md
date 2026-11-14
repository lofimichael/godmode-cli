# Music

`godmode music` plays local tracks through [Darunia's CLI](https://github.com/lofimichael/darunias-cli). The bars follow the WAV's frequency levels. `q` or Escape closes the visualizer and stops playback. Ctrl-C stops music in every display mode.

```sh
godmode music init /path/to/darunias-cli --songs /path/to/local/music
godmode music
godmode music list 'Chrono Trigger'
godmode music play 'Chrono Trigger/Corridors of Time.ootrs'
godmode music play 'Chrono Trigger/Corridors of Time.ootrs' --seconds 30
```

The song picker supports `/` search. Tracks are local `.ootrs` files. The default render lasts three minutes; `--seconds` accepts 1–3600 seconds. Sound plays on the computer running Godmode.

Darunia must already have its synthesis tools and local SoundFonts. Its [setup instructions](https://github.com/lofimichael/darunias-cli/blob/main/docs/SYNTHESIS.md) cover those dependencies. Godmode does not install them, fetch songs, or call Darunia's network player.

## Cache

```sh
godmode music status
godmode music play 'Chrono Trigger/Corridors of Time.ootrs' --render-only
godmode music clear
```

Synthesized WAVs live in `GODMODE_HOME/state/music/cache` (`~/.godmode/state/music/cache` by default). Darunia checks the sequence, sound settings, tools, and fonts before reusing a render. The cache keeps a SHA-256 receipt for each WAV. `clear` removes this cache and keeps the source songs, synth install, and Godmode settings. It refuses to run during playback or synthesis.

## Display

`--no-motion` plays without animation. `godmode --plain music` uses static text. `NO_COLOR=1` keeps the visualizer in monochrome. Playback uses an installed `afplay`, `ffplay`, or `aplay`. macOS and FFmpeg playback start at 35% volume.

The visualizer reads PCM samples from the current point in the WAV and measures logarithmically spaced frequency bands. It does not record a microphone or the system audio output.

## Source and removal

The adapter is [lib/godmode_music.py](../lib/godmode_music.py). It uses Python's standard library and launches the local synth as a separate process with a small environment that excludes Godmode's keys. Initialization records the synth script's SHA-256. A changed script requires review and another `music init`.

```sh
godmode music clear
godmode music forget
scripts/build-native.sh --without-music
```

`forget` removes the local Darunia link. `--without-music` omits the adapter from the built executable. Profile, provider, agent, and key commands remain available. No music files, SoundFonts, converters, or Darunia source are bundled with Godmode.

Darunia's original code is MIT-licensed. Its license does not grant rights to compositions, arrangements, recordings, samples, or upstream tools. SEQ64 is GPL-3.0; TinySoundFont is MIT. The separate local installation retains those licenses. Sources: [Darunia license](https://github.com/lofimichael/darunias-cli/blob/main/LICENSE), [synthesis dependencies](https://github.com/lofimichael/darunias-cli/blob/main/docs/SYNTHESIS.md).
