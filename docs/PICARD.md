# Picard mode

An optional detour to [picard.ytmnd.com](https://picard.ytmnd.com/). No autoplay. Your credentials are not involved.

```sh
godmode picard link   # print the original site URL
godmode picard open   # open that site in your browser
godmode picard play   # play the original YTMND excerpt on repeat, foreground
godmode picard stop   # ask this state directory's Godmode player to stop
```

On the provider board: `p` starts/stops audio; `v` opens the source. `p` or Esc cancels loading. Quitting the board stops its player. In the foreground command, Ctrl-C or `picard stop` stops loading/playback. Use the same `--state-dir` for play and stop if you override it. Opening the website is separate: Godmode's stop command controls its own audio child, not a browser's media player.

## What actually plays

The original YTMND page uses an approximately **7.976-second excerpt** from **The Picard Song by DarkMateria**, not the full track. Godmode loops that same excerpt. YTMND's community history dates the page to April 25, 2004 and credits the page to ShittyMcShit. That is a later community chronology, not a claim that Godmode independently recovered a 2004 creation log. [YTMND history](https://wiki.ytmnd.com/Picard_Song).

The source recording was fetched and inspected on 2026-11-04:

- Original asset: [YTMND WAV](https://users.content.ytmnd.com/d/0/3/d0330b0d03957ad58853427a6513e793.wav).
- PCM WAV, mono, 22,050 Hz, 16-bit; 351,860 bytes.
- SHA-256: `d69a477ba3b9a8d454512db12b2ce3da05ec72ffa36d7ab313b0ed8aff764db8`.

The recording is **not included** in Git, the executable or release archives. The project's MIT license covers its own code, not the song, television samples, YTMND artwork or branding. The source remains credited and directly linked; no lyrics or borrowed logos are reproduced.

## Local requirements and storage

First playback needs `curl` and an Internet connection. macOS uses its built-in `/usr/bin/afplay`. Linux uses an existing `paplay`, `aplay`, `ffplay` or `mpv`, in that order; Godmode does not install an audio stack. The source link remains usable without any native player. Backends supporting a volume argument are requested at half gain; `aplay` uses the device's level. Godmode does not change system volume.

An explicit play request downloads only the fixed HTTPS source above, with a 20-second timeout and 1 MiB bound, checks its size and SHA-256, and saves it as:

```text
<state-dir>/picard/picard-d0330b0d.wav
```

The directory is mode 0700 and the file mode 0600. Subsequent plays validate the cache and can work offline. YTMND receives the ordinary download request and its network metadata. There is no telemetry, credential access or credential-bearing request. A corrupt or changed recording is refused rather than silently substituted. Stop playback before removing this dedicated cache if you want it downloaded again.

The transient controller owns the player process and a private local `p.sock` control socket. It never stores a PID for a future process to kill, never uses `pkill`, and never registers a daemon, startup item or scheduled job. Only one controller per state directory runs at once. The cache remains after stopping; the active socket is removed.
