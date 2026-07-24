# kcd-pak-action

[![CI][ci-badge]][ci-url]

GitHub Action that packages a **Kingdom Come: Deliverance** (KCD1 & KCD2) loose-file mod into
game-ready `.pak` files plus a release `.zip`.

Both games use the same CryEngine pak format, so this works for either. It follows the standard
KCD mod layout (Data/, Localization/, Data/Levels).

## Why not just rename a 7-Zip / WinRAR archive?

Because it won't load. CryPak **rejects the per-file
modification-time metadata** that 7-Zip / WinRAR / WinZip add by default - the ZIP *extra fields*
`0x000A` (NTFS time) and `0x5455` (`UT` extended timestamp). This action writes paks with Python's
`zipfile`, which adds none of those fields, so they load. Windows Explorer's built-in
"Compressed (zipped) folder" works for the same reason.

> Note: the "0 compression" advice you may have seen is a red herring - Store *and* Deflate
> both load; the timestamp metadata is the actual gate. 7-Zip fails even at 0 compression.

## Quick start

In your **mod** repo, add `.github/workflows/release.yml`. A minimal single-job version follows;
see [`examples/consumer-release.yml`](examples/consumer-release.yml) for a hardened two-job one
with least-privilege permissions:

```yaml
name: Release mod
on:
  push:
    tags: ["v*"]
permissions:
  contents: write
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - id: pak
        uses: tkhquang/kcd-pak-action@v1
        with:
          mod-dir: LootBeacon/src     # folder containing mod.manifest
          compress: deflate           # or 'store'
      - uses: softprops/action-gh-release@3bb12739c298aeb8a4eeaf626c5b8d85266b0e65 # v2.6.2
        with:
          files: ${{ steps.pak.outputs.archive }}
          generate_release_notes: true
```

Push a tag like `v1.4.3` and a `.pak` release is built and published automatically.

## Inputs

| Input      | Default   | Description |
|------------|-----------|-------------|
| `mod-dir`  | `.`       | Mod source folder - must contain `mod.manifest`. |
| `out-dir`  | `dist`    | Where the packaged mod folder + release zip are written. |
| `compress` | `deflate` | `deflate` (smaller) or `store` (0 compression). |

Run `actions/checkout` before this action so `mod-dir` exists in the workspace.

## Outputs

| Output    | Example                        | Description |
|-----------|--------------------------------|-------------|
| `archive` | `dist/loot_beacon-v1.4.3.zip`  | The release zip. |
| `mod-dir` | `dist/loot_beacon`             | Deploy-ready mod folder. |
| `modid`   | `loot_beacon`                  | From `mod.manifest`. |
| `version` | `1.4.3`                        | From `mod.manifest`. |

`archive` and `mod-dir` are absolute paths (native form on Windows runners); the examples show
only the trailing part. If you pass an absolute or parent-relative `out-dir`, they resolve there.

## Folder -> pak mapping

Given a source folder with `mod.manifest` (`<modid>loot_beacon</modid>`):

```text
Data/**  (except Data/Levels/**)   ->  Data/<modid>.pak         (Data/ prefix stripped)
Localization/<Lang>/**             ->  Localization/<Lang>.pak
Data/Levels/<level>/**             ->  Data/Levels/<level>/<modid>.pak
mod.manifest, mod.cfg              ->  kept LOOSE (not packed)
```

Existing `.pak` files in the source are skipped (they are build outputs, not source) with a
warning. Symlinks are skipped rather than followed.

Result (deploy-ready - drop the `<modid>/` folder into the game's `Mods/`):

```text
dist/loot_beacon/
  mod.manifest
  mod.cfg                        (only if your mod has one)
  Data/loot_beacon.pak
  Localization/English_xml.pak
dist/loot_beacon-v1.4.3.zip
```

## Monorepo (multiple mods in one repo)

```yaml
jobs:
  release:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        mod: [LootBeacon/src, AnotherMod/src]
    steps:
      - uses: actions/checkout@v4
      - uses: tkhquang/kcd-pak-action@v1
        with:
          mod-dir: ${{ matrix.mod }}
      - uses: actions/upload-artifact@v4
        with:
          name: pak-${{ strategy.job-index }}
          path: dist/**
```

## Use locally (no GitHub account needed)

You can build the `.pak` files on your own computer. The only thing you need is **Python 3.8 or
newer** (a free download). No Bash, no build tools.

### 1. Install Python

Download Python from <https://www.python.org/downloads/> and install it. On Windows, tick
**"Add python.exe to PATH"** on the first setup screen. macOS and most Linux systems already
include Python.

### 2. Download this tool

On the repository page, click **Code -> Download ZIP**, then unzip it. You now have a folder named
`kcd-pak-action`. (If you know Git, `git clone` works too.)

### 3. Open a terminal in that folder

- **Windows:** open the `kcd-pak-action` folder, hold **Shift**, right-click an empty spot, and
  choose **"Open in Terminal"** (or "Open PowerShell window here").
- **macOS:** open Terminal, type `cd` followed by a space, drag the `kcd-pak-action` folder onto
  the window, and press Enter.
- **Linux:** right-click the folder and choose "Open Terminal Here".

Check Python is ready (it should print a version like `Python 3.12`):

```text
python --version
```

On macOS and Linux, use `python3` instead of `python` in every command below.

### 4. Build your mod

Run the command below, replacing the path with your mod folder (the one that contains
`mod.manifest`). Keep the quotation marks:

```text
python scripts/pak_kcd_mod.py "C:\Users\You\Desktop\YourMod\src"
```

Tip: you can drag the mod folder onto the terminal window to paste its full path.

### 5. Install it in the game

The finished mod appears in a new `dist` folder inside `kcd-pak-action`, as `dist/<modid>/` (for
example `dist/loot_beacon/`). Copy that `<modid>` folder into your game's `Mods` folder, usually:

```text
...\steamapps\common\KingdomComeDeliverance2\Mods\
```

Then enable the mod in the in-game mod manager (or your `mod_order.txt`).

### Extra options

Send the output somewhere else by adding a second path:

```text
python scripts/pak_kcd_mod.py "C:\path\to\YourMod\src" "C:\path\to\output"
```

Build with no compression (only if a mod specifically needs it):

```text
python scripts/pak_kcd_mod.py "C:\path\to\YourMod\src" --compress store
```

## Versioning

`@v1` is a moving compatibility tag: update it on each backward-compatible release. Consumers who
want an immutable reference should pin a full commit SHA instead. To cut a release, tag `v1.0.0`
and point `v1` at it:

```bash
git tag v1.0.0 && git push origin v1.0.0
git tag -f v1 v1.0.0 && git push -f origin v1
```

## Credits & license

Thanks to the Kingdom Come: Deliverance modding community for documenting the pak format and the
CryPak modification-time quirk. This action is an independent implementation in Python.
Released under the BSD Zero Clause License (0BSD) - see [LICENSE](LICENSE).

[ci-badge]: https://github.com/tkhquang/kcd-pak-action/actions/workflows/ci.yml/badge.svg
[ci-url]: https://github.com/tkhquang/kcd-pak-action/actions/workflows/ci.yml
