#!/usr/bin/env bash
# MatrixWallpaper, a live wallpaper for KDE Plasma 6. The first argument picks what to do:
#   ./run.sh               live preview in a window, coloured from the current wallpaper image;
#                          does not touch the desktop
#   ./run.sh check         run the checks
#   ./run.sh shots [name]  render every state off-screen to .dev/shots/ and audit it
#   ./run.sh build         bake the shader (needs qsb, see docs/deps.md)
#   ./run.sh install       install or upgrade the package for this user
#   ./run.sh apply         switch every desktop to it, with the image each one shows now
#   ./run.sh revert        switch every desktop back to Plasma's image wallpaper
#   ./run.sh perf [secs]   what the running wallpaper costs and how many frames it really shows
#   ./run.sh set KEY VALUE change a setting of the running wallpaper, e.g. set CellHeight 14
#                          (keys: package/contents/config/main.xml)
set -euo pipefail
cd "$(dirname "$0")"
id=io.github.tominocz.matrixwallpaper
frag=package/contents/shaders/rain.frag

# Bake the shader when its source is newer than the baked file (or always, with `force`).
# File times mean little after a clone, so without qsb this only warns: the baked file in the
# repository matches its source unless you edited the source.
bake() {
  [[ ${1:-} == force || $frag -nt $frag.qsb ]] || return 0
  local qsb=${QSB:-$(command -v qsb || echo /usr/lib/qt6/bin/qsb)}
  if [[ ! -x $qsb ]]; then
    echo "run.sh: qsb is not installed (sudo apt install qt6-shader-baker); using the baked shader as it is. If you edited $frag, it is stale." >&2
    [[ ${1:-} == force ]] && exit 1
    return 0
  fi
  "$qsb" --glsl "100 es,120,150" -o "$frag.qsb" "$frag"
}
# Run a Plasma desktop script (https://develop.kde.org/docs/plasma/scripting/api/).
plasma() { qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "$1"; }

case "${1:-}" in
  "") bake; exec python3 scripts/rain.py ;;
  check) bake; shift; exec python3 tests/check.py "$@" ;;
  shots) bake; shift; exec python3 scripts/shots.py "$@" ;;
  build) bake force ;;
  install)
    kpackagetool6 --type Plasma/Wallpaper --upgrade package >/dev/null 2>&1 && echo "Upgraded $id; restart plasmashell to load it." ||
      kpackagetool6 --type Plasma/Wallpaper --install package ;;
  apply)
    plasma "for (const d of desktops()) {
      d.currentConfigGroup = ['Wallpaper', 'org.kde.image', 'General'];
      const image = d.readConfig('Image');
      d.currentConfigGroup = ['Wallpaper', '$id', 'General'];
      d.writeConfig('Image', image);  // before the switch, so the plugin starts with its image
      d.wallpaperPlugin = '$id';
    }" ;;
  revert) plasma "for (const d of desktops()) d.wallpaperPlugin = 'org.kde.image';" ;;
  set)
    grep -q "<entry name=\"${2:-}\"" package/contents/config/main.xml || { echo "run.sh: no setting '${2:-}'; there are:$(grep -o '<entry name="[^"]*' package/contents/config/main.xml | sed 's/.*"/ /' | tr -d '\n')" >&2; exit 2; }
    value=${3?run.sh: set $2 needs a value}; value=${value//\\/\\\\}; value=${value//\'/\\\'}
    plasma "for (const d of desktops()) if (d.wallpaperPlugin == '$id') {
      d.currentConfigGroup = ['Wallpaper', '$id', 'General'];
      d.writeConfig('$2', '$value');
    }" ;;
  perf)
    shell=$(pgrep -x plasmashell | head -1); kwin=$(pgrep -x kwin_wayland | head -1); since=$(date +%T)
    "$0" set LogFrameRate true >/dev/null  # the wallpaper reports its own frame rate to the log
    # top's first sample is an average since the process started: skipped
    LC_ALL=C top -b -n $((${2:-8} + 1)) -d 1 -p "$shell,$kwin" | LC_ALL=C awk -v s="$shell" -v k="$kwin" '
      $1 == s && a++ { cpu_s += $9 } $1 == k && b++ { cpu_k += $9 }
      END { printf "plasmashell %.1f %% of one core, kwin_wayland %.1f %%\n", cpu_s / (a - 1), cpu_k / (b - 1) }'
    command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=utilization.gpu,power.draw --format=csv,noheader | sed 's/^/whole GPU /'
    "$0" set LogFrameRate false >/dev/null
    journalctl --user -u plasma-plasmashell --since "$since" --no-pager -o cat | grep "MatrixWallpaper:" ||
      echo "no frame rate in the log: is the wallpaper applied, and plasmashell restarted since the last install?" ;;
  *) sed -n '2,13p' "$0" >&2; exit 2 ;;
esac
