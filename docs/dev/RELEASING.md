# Release

`scripts/build.py` joins `lib/*.py`, `providers.json` and `godmode.py` into one readable Python script. It does not compile, compress or download anything. The release number is in `VERSION`; the build writes it into the script.

## Check

```sh
python3 -m unittest discover -s tests -p 'test_simple*.py'
python3 scripts/build.py --output target/godmode
target/godmode --version
sh tests/install.sh
sh tests/install-update.sh
shellcheck -s sh install.sh tests/install.sh tests/install-update.sh
```

Tests use synthetic keys and temporary homes. Never run them against a real key file.

## Package

1. Set the version in the `VERSION` file and the `VERSION` constant in `godmode.py`, commit to main, then tag and push `vX.Y.Z`.
2. Build one universal archive and its checksum. `docs/dev` stays out of the archive.

   ```sh
   v=v$(cat VERSION)
   rm -rf target/package target/dist
   mkdir -p target/package/docs target/package/lib target/package/scripts target/dist
   cp target/godmode LICENSE README.md READTHIS.NFO install.sh godmode.py providers.json VERSION target/package/
   cp docs/*.md target/package/docs/ && cp -R docs/images target/package/docs/
   cp lib/*.py target/package/lib/ && cp scripts/build.py target/package/scripts/
   COPYFILE_DISABLE=1 tar -czf "target/dist/godmode-$v-unix.tar.gz" -C target/package \
     godmode LICENSE README.md READTHIS.NFO install.sh docs lib godmode.py providers.json VERSION scripts
   (cd target/dist && shasum -a 256 "godmode-$v-unix.tar.gz" > SHA256SUMS)
   ```

3. Create a private draft release with the archive, `SHA256SUMS` and `install.sh` as assets:

   ```sh
   gh release create "$v" "target/dist/godmode-$v-unix.tar.gz" target/dist/SHA256SUMS install.sh \
     --verify-tag --draft --title "Godmode $v"
   ```

4. Install it with `~/.godmode/bin/godmodeup --version vX.Y.Z`. A draft is visible only to a GitHub CLI login with access to the repository. godmodeup keeps the previous executable as `~/.godmode/bin/godmode.previous`.

The README uses authenticated GitHub CLI downloads for the private repository.
Public HTTPS downloads require a published release with `install.sh` attached.
