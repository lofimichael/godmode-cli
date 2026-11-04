# Picard

```sh
godmode picard link
godmode picard open
godmode picard show
godmode picard play
godmode picard stop
```

The source is [picard.ytmnd.com](https://picard.ytmnd.com/), with audio by DarkMateria. `link` prints the URL and `open` opens it. Nothing plays during setup. The [optional media helper](../lib/godmode_picard.py) never loads a credential file or receives a Store.

`show` downloads the original JPEG only when requested, verifies its pinned SHA-256 and renders a static terminal picture. macOS uses its existing `sips` command to decode the image, followed by a small bounded BMP reader and half-block renderer. Other systems can use an already-installed `chafa`; otherwise the command points you to the original site. `NO_COLOR`, `CLICOLOR=0` and `TERM=dumb` select ASCII output. This rendering adapts the original image to terminal cells; it is not period ASCII artwork. The previous full-screen picture viewer and tiling controls are removed.

`play` loops the original approximately eight-second YTMND excerpt, not the full DarkMateria track. It uses an existing `afplay`, `ffplay` or `aplay` in the foreground. Ctrl-C stops it; a second terminal can use `stop`. The controller owns and reaps its player. It never finds players by name or kills an arbitrary PID. Cross-terminal stopping uses a private Unix socket.

Downloads use curl only on request, are bounded to 1 MiB and checked against the original pinned hashes. Source image and audio are not bundled. Cache files are mode 0600 in private directories under `~/.godmode/state/picard`. `--state-dir DIR` or `GODMODE_STATE_DIR` selects another state root; give `stop` the same root as `play`. An explicit `--home` defaults media state to that home's `state` directory.

YTMND receives the media download request. No credential inventory is read or sent. The MIT license for this project's code does not cover the original image or recording. See [the culture research](CULTURE.md) for historical context.
