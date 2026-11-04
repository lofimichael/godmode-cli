# Picard mode

Godmode can display the original image and play the audio from [picard.ytmnd.com](https://picard.ytmnd.com/). Each is requested separately. The standalone commands do not load your credentials.

```sh
godmode picard link   # print the original site URL
godmode picard open   # open that site in your browser
godmode picard show   # show the original image in the terminal; p starts audio
godmode picard play   # play the original YTMND excerpt on repeat, foreground
godmode picard stop   # ask this state directory's Godmode player to stop
```

On the provider board: `i` opens the picture, `p` starts/stops audio and `v` opens the source. In the picture view, `t` switches between fit and tile; `i` or Esc returns to the board. In standalone `picard show`, q, Esc or Ctrl-C exits. Quitting either session stops its own player.

Loading remains cancellable with Esc; q or Ctrl-C quits. In `picard play`, Ctrl-C or `picard stop` stops loading/playback. Use the same `--state-dir` for play and stop if you override it. Opening the website is separate: Godmode's stop command controls its own audio child, not a browser's media player. It does not close another terminal's picture view.

## The picture

`show` uses the original **436 x 574 JPEG portrait**, fetched from the asset identified in YTMND's [site 508 metadata](https://picard.ytmnd.com/info/508/json). The original page tiled this still photograph and placed layered text over it, as the [January 21, 2005 archived page](https://web.archive.org/web/20050121191446id_/http://picard.ytmnd.com/) also shows. The terminal view offers a fitted portrait or repeated tiles. It does not reproduce the browser's text overlay or run its scripts.

The source image was fetched and inspected on 2026-11-04:

- [Original JPEG](https://users.content.ytmnd.com/f/8/c/f8cd26d2ab99e2f44562fb050d74c9a2.jpg), 58,375 bytes.
- SHA-256: `5f35ea6e9fb61e7091da79b8c6086fff53f5aefacf778ad076214fcf6b0455bf`.

The renderer resamples the actual image into terminal cells. A half-block character supplies two colour samples per cell, assuming a cell approximately twice as tall as it is wide. `COLORTERM=truecolor`/`24bit` or a `TERM` ending in `-direct` selects RGB; otherwise it uses the fixed xterm 256-colour palette. `NO_COLOR` selects ASCII luminance shading. Resizing the terminal changes the available resolution. Nonstandard font proportions can change the apparent aspect ratio.

This works through the existing Ratatui renderer without an image-viewer dependency or terminal-specific image escape protocol. It is a modern terminal rendering of a period image, not period ASCII art. Kitty and iTerm2 provide their own graphics protocols, but support cannot be assumed across Terminal.app, SSH sessions and other terminals. The portable cell renderer is the implemented path; native pixel protocols are not claimed. [Kitty graphics protocol](https://sw.kovidgoyal.net/kitty/graphics-protocol/), [iTerm2 inline images](https://iterm2.com/documentation-images.html).

The JPEG is checked against its exact size and hash before decoding, with independent dimension and allocation limits. It is cached privately at `<state-dir>/picard/image/picard-f8cd26d2.jpg`. Image and audio use separate cache locks, so loading the picture does not interrupt control of an existing player. A cached picture can be viewed offline without curl. Redirected output is refused before making a request or creating state; use `picard link` in a script.

## What actually plays

The original YTMND page uses an approximately **7.976-second excerpt** from **The Picard Song by DarkMateria**, not the full track. Godmode loops that same excerpt. YTMND's community history dates the page to April 25, 2004 and credits the page to ShittyMcShit. That is a later community chronology, not a claim that Godmode independently recovered a 2004 creation log. [YTMND history](https://wiki.ytmnd.com/Picard_Song).

The source recording was fetched and inspected on 2026-11-04:

- Original asset: [YTMND WAV](https://users.content.ytmnd.com/d/0/3/d0330b0d03957ad58853427a6513e793.wav).
- PCM WAV, mono, 22,050 Hz, 16-bit; 351,860 bytes.
- SHA-256: `d69a477ba3b9a8d454512db12b2ce3da05ec72ffa36d7ab313b0ed8aff764db8`.

The source JPEG and recording are **not included** in Git, the executable or release archives. The project's MIT license covers its own code, not the song, television samples, YTMND artwork or branding. The source remains credited and directly linked; no lyrics or borrowed logos are reproduced.

## Local requirements and storage

The first request for either source asset needs `curl` and an Internet connection. Image display uses the built-in JPEG decoder. For audio, macOS uses its built-in `/usr/bin/afplay`. Linux uses an existing `paplay`, `aplay`, `ffplay` or `mpv`, in that order; Godmode does not install an audio stack. The source link remains usable without any native player. Backends supporting a volume argument are requested at half gain; `aplay` uses the device's level. Godmode does not change system volume.

An explicit play request downloads only the fixed HTTPS source above, with a 20-second timeout and 1 MiB bound, checks its size and SHA-256, and saves it as:

```text
<state-dir>/picard/picard-d0330b0d.wav
```

The directory is mode 0700 and the file mode 0600. Subsequent plays validate the cache and can work offline. YTMND receives the ordinary download request and its network metadata. There is no telemetry, credential access or credential-bearing request. A corrupt or changed recording is refused rather than silently substituted. Stop playback before removing this dedicated cache if you want it downloaded again.

The transient controller owns the player process and a private local `p.sock` control socket. It never stores a PID for a future process to kill, never uses `pkill`, and never registers a daemon, startup item or scheduled job. Only one controller per state directory runs at once. The cache remains after stopping; the active socket is removed.
