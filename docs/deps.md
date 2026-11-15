# deps.md — what a machine needs to run MatrixWallpaper

Everything that has to be installed on the system. Package names are for Kubuntu 26.04.
**Keep this file current:** a change that calls a new program, loads a new library or relies on
a new service adds a row here in the same change.

## Required

| Dependency | Package | Used for | Without it |
|---|---|---|---|
| KDE Plasma 6 desktop | `plasma-workspace` (part of Kubuntu) | Loads the wallpaper package; brings Qt 6 Quick with it. Built against 6.6.6 / Qt 6.10.2. | Nothing to load it: this is a Plasma plugin, not a program. |
| A GPU with working OpenGL or Vulkan drivers | the vendor's driver | The whole effect is a fragment shader. | Qt's software renderer skips shader effects: a black desktop. |
| `kpackagetool6` | `kpackagetool6` | `./run.sh install` | Copy `package/` to `~/.local/share/plasma/wallpapers/io.github.tominocz.matrixwallpaper/` by hand. |
| `qdbus6` | `qdbus-qt6` | `./run.sh apply`, `revert`, `set` and `perf` (Plasma scripting over D-Bus) | Pick "Matrix Wallpaper" in the desktop's wallpaper settings instead; the image setting then stays empty and the rain is green, and no setting can be changed. |

## Optional

| Dependency | Package | Used for | Without it |
|---|---|---|---|
| A font with half-width katakana | `fonts-noto-cjk` (part of Kubuntu) | The glyphs of the rain | Those cells show the font's "missing glyph" box or nothing; digits and signs still fall. |

## Development only (not shipped)

| Dependency | Package | Used for |
|---|---|---|
| Python 3 with PyQt6 and its Qt Quick module | `python3-pyqt6`, `python3-pyqt6.qtqml`, `python3-pyqt6.qtquick` | `./run.sh` (preview), `./run.sh shots`, `./run.sh check`, `scripts/readme.py`. Must be the distribution's build, on the system Qt; see PLAN.md §4.6. |
| `qsb`, Qt's shader baker | `qt6-shader-baker` | `./run.sh build`, only after editing `rain.frag`; the baked `rain.frag.qsb` is in the repository, so installing and running need no baker. |
| ffmpeg | `ffmpeg` | `scripts/readme.py`, the README's moving picture. |
| `nvidia-smi` | comes with the NVIDIA driver | `./run.sh perf` adds GPU load and power when it is there. |
