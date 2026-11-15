# PLAN.md — the design

The design of record: how MatrixWallpaper works and why. Change it when a decision changes, and
say why (here, or in the plan's notes).

It refers to `next.md` (the handoff between working sessions), `open.md` (what is unresolved)
and a plan of record with notes. Those are the author's private working files and are not in
the public repository; "the owner" throughout is the author.

---

## 0. Two-minute orientation

MatrixWallpaper is a **wallpaper plugin for KDE Plasma 6**: a `Plasma/Wallpaper` package
(`package/`) that Plasma loads into the desktop in place of its image wallpaper. It draws
Matrix-style falling glyphs, and every glyph takes the colour the wallpaper image has at that
glyph's cell, so the picture shows through the rain.

It is not a separate program, has no daemon and no compiled code: QML plus one fragment shader.

Three decisions carry everything else:

1. **The whole effect is one fragment shader, a pure function of (cell, tick)** (§4.2). One quad,
   one draw call, two texture lookups per pixel, no state on the CPU or the GPU.
2. **The clock advances once per displayed frame** (§4.3): the rain fades and falls smoothly at
   the screen's refresh rate (240 Hz here), in step with vsync. The owner chose this over a
   stepped, `cmatrix`-like rain that would redraw a tenth as often.
3. **It lives inside plasmashell as a wallpaper plugin** (§4.1), so icons, widgets and the
   wallpaper dialog keep working, and "the current wallpaper" is read from Plasma itself.

Since 2026-11-15 it is the wallpaper on the owner's desktop (Plasma 6.6.6, Wayland,
5120×1440). At a true 240 frames a second it costs plasmashell about 25 % of one core and the machine
about 6 W more than a photo; pausing when covered and a cheaper mode are M3.

## 1. Goals and non-goals

- **Goals:**
  - A live Matrix rain as the desktop wallpaper on Kubuntu (Plasma 6, Wayland), coloured per cell
    from the wallpaper image the desktop had.
  - As cheap as it can be made: all per-pixel work on the GPU, nothing per glyph on the CPU, one
    draw call per frame, nothing at all when the desktop is covered (M3).
  - Every claim about cost backed by a measurement (M3), on the owner's machine: RTX 3080 Ti,
    one 5120×1440 screen at 240 Hz.
- **Non-goals (for now):**
  - Other desktops or compositors. A wallpaper plugin is Plasma-only by nature.
  - Following a slideshow or picture-of-the-day as it changes (open.md O4): the image is copied
    once, when the wallpaper is applied.
  - Running without a GPU. Qt's software renderer cannot run a shader effect.

## 2. How it works

```
image file ──► Image (decoded once, ~1 texel per cell) ──┐
glyph string ─► Row of Text (drawn once into a texture) ──┼─► ShaderEffect ─► desktop
shown frames ─► tick (a number, grows with time) ─────────┘    rain.frag
```

The screen is a grid of cells (`cellHeight` px high, 16 by default, 0.6 of that wide, fitted to
the screen: §4.11). `tick` counts the rows the fastest drops have fallen. For each pixel the shader:

1. finds its cell, and where it is inside the cell;
2. works out how bright the cell is: each column has two drops, each with its own speed, length
   and gap, all derived from a hash of the column number. A drop's head is at row
   `tick × speed + start`, wrapped, a fractional number; the cell's brightness falls off with
   its distance above the head, the cell under the head fades in as the head arrives, and
   nothing gets darker than `trailFloor` (§4.8);
3. picks the cell's glyph: a hash of the cell and of a per-cell clock, so glyphs swap now and then;
4. looks up that glyph's pixel in the glyph texture, and the cell's colour in the image texture,
   brightened by `lift` (§4.9);
5. outputs colour × brightness × glyph. Where the head is, the colour is mixed towards white,
   fading back over one row.

Nothing is remembered between frames: the same tick always gives the same frame. That is what
makes it cheap (no simulation, no feedback buffer) and what makes it testable (render a tick,
assert on the pixels).

**The image.** Plasma's image wallpaper keeps its picture in its own settings group. `./run.sh
apply` reads it through Plasma's scripting interface, switches the desktop to this plugin and
writes the path into this plugin's `Image` setting. Plasma's own setting is left alone, so
`./run.sh revert` brings the old wallpaper back. The image is decoded at about one texel per
cell, on Qt's image thread, so one lookup already gives the cell's average colour; cropping to
the screen (as "scaled and cropped" does) is two numbers passed to the shader.

## 3. Architecture

| File | Does |
|---|---|
| `package/metadata.json` | Tells Plasma this is a wallpaper, and its id `io.github.tominocz.matrixwallpaper`. |
| `package/contents/config/main.xml` | The settings and their defaults: `Image`, `CellHeight`, `Speed`, `TrailFloor`, `Lift`, `Glide`, `LogFrameRate`. |
| `package/contents/ui/main.qml` | What Plasma loads: a `WallpaperItem` that hands the settings to `MatrixRain`. Nothing else. |
| `package/contents/ui/MatrixRain.qml` | The effect: frame clock, image texture, glyph texture, the shader's inputs. Plain QtQuick, no KDE imports. |
| `package/contents/shaders/rain.frag` | The rain. `rain.frag.qsb` is its baked form, the file Qt loads; both are in the repository. |
| `scripts/rain.py` | Loads `MatrixRain.qml` outside Plasma: hidden window + `grab(tick)` for shots and checks; run directly, the live preview. |
| `scripts/shots.py` | Renders the named states to `.dev/shots/` and audits each frame. |
| `scripts/readme.py` | Makes the README's pictures in `docs/images/` (needs ffmpeg). |
| `tests/check.py` | Asserts on rendered frames: colour follows the image, crop, fallback, trail floor, lift, no glyph cut at an edge, it fades smoothly, the light slides through glyphs with glide, the clock runs at the display's frame rate and stops at speed 0, it moves, it keeps no state; and that the defaults in `MatrixRain.qml` equal those in `main.xml`. |
| `run.sh` | Entry point: preview, `check`, `shots`, `build`, `install`, `apply`, `revert`, `set`, `perf`. |

**Safety rules.**

1. **Never change Plasma's own wallpaper settings.** `apply` only reads `org.kde.image`'s group
   and writes this plugin's. Reason: `revert` must always give the owner their desktop back.
2. **Nothing but `apply`, `revert` and `set` touches the live desktop**, and only when the owner runs
   them or asks for it in that session. Preview, shots and checks run in their own (hidden) windows. Reason: a broken shader on
   the real desktop is a black screen behind every window.
3. **`main.qml` stays a thin wrapper.** Anything in it cannot be rendered or checked outside
   Plasma. Reason: that is the only code the tooling cannot see.
4. **No tool is fetched from the internet and run without the owner saying so.** Reason: the
   owner's rule (and their permission setup enforces it); see §4.6.

## 4. Decisions

### 4.1 A Plasma wallpaper plugin, not a standalone program

Chosen: a `Plasma/Wallpaper` package, QML only.

Rejected: **a standalone program drawing on a layer-shell background surface** (C++/Rust with
OpenGL or Vulkan). It would have full control of rendering, but plasmashell's desktop is itself
an opaque surface on that layer: the program would either hide the icons and widgets or be
hidden by them. It would also need its own autostart, multi-screen handling and settings
window, all of which Plasma gives a plugin for free. Rejected: **a C++ wallpaper plugin**
(custom scene-graph node): a build system and a compiled module for nothing the shader effect
cannot do.

Revisit if measurements (M3) show that being inside plasmashell costs something a shader cannot
fix, e.g. plasmashell's own frame pacing.

### 4.2 One stateless fragment shader

Chosen: every pixel computed from (cell, tick) in `rain.frag`.

Rejected: **one QML item per glyph**: at 5120×1440 with 20 px cells that is about 30 000 text
items animated from the GUI thread. Rejected: **a particle simulation with a feedback
framebuffer** (the usual "trails fade" trick): it needs state, two render targets, and cannot
skip frames or be rendered at an arbitrary tick for a check.

Cost of the choice: effects that need memory (a glyph that lingers after an irregular event)
have to be expressed as hashes of time. So far nothing wanted needs more.

### 4.3 The clock runs with the display, not in steps

Chosen by the owner (2026-11-15: "a smooth and high framerate would be great, vsync ideally",
then "i do want 240 fps"): the rain advances once per frame the display shows, and the shader
works with a fractional tick, so trails fade and heads arrive smoothly at the refresh rate.

**How.** `MatrixRain.qml` listens to its window's `frameSwapped` signal and advances `tick`
there. The changed tick makes the scene dirty, Qt draws at the next vsync, and that frame
advances the tick again: a chain that runs exactly as fast as frames are shown. When no frame
is shown (window not exposed, or `Speed` 0) the chain stops and nothing is drawn; `kick()` asks
for one frame to start it again. The frame time is a smoothed `Date.now()` difference, because
JavaScript only has whole milliseconds and a 240 Hz frame is 4.17 ms.

**Why not `FrameAnimation`** (first built, 2026-11-15): plasmashell draws on its GUI thread,
Qt's *basic* render loop (it has no `QSGRenderThread`), and there Qt's animations tick from a
16 ms timer whatever the display does. Measured in a test window: 62.5 triggers a second under
the basic loop against 239.8 frames swapped; 239.5 under the threaded loop. The first "smooth"
version therefore ran at 60 fps on the 240 Hz screen and the owner saw it.
`check_clock_runs_with_the_display` now fails on that (63 fps against 240).

**Measured inside plasmashell** (the wallpaper logs its own frame count when `LogFrameRate` is
on, which is what `./run.sh perf` reads): about 240 frames a second (225 to 252 per two-second window), 0.5 to 1.5 late frames a
second, worst gap usually 7 to 10 ms. So the display rate is really reached.

**Rejected earlier:** a `Timer` stepping the tick 24 times a second, the desktop redrawn only on
a step. Cheapest, but it looks like `cmatrix`, in steps.

**Cost on the owner's desktop**, plasmashell's share of one core: photo 1 %, 24 steps a second
5 %, 62.5 fps 12 %, 240 fps 25 %. The compositor stays at 8 to 9 % throughout (it presents at
240 Hz anyway) and power goes from about 89 W to 94.5 W. With `Speed` 0 the wallpaper costs
what a photo does. Most of the 25 % is probably the whole desktop window (icons, widgets)
being redrawn each frame on the GUI thread, not the shader; not yet measured (M3).

The tick wraps at 2²⁰ rows (about 12 hours at the default speed) because the shader holds it in
a 32-bit float, whose steps would otherwise grow coarse; the wrap is one visible jump. Marked
`ponytail:` in `MatrixRain.qml`.

### 4.4 Textures: image at one texel per cell, glyphs drawn at run time

- **Image:** decoded with `sourceSize` = the grid size, which Qt does once on its loader thread.
  Sampling the full-size image at each cell's centre would cost the same per pixel but hold
  tens of megabytes of texture and give one arbitrary pixel's colour per cell instead of the
  cell's average.
- **Glyphs:** a hidden `Row` of `Text` items rendered once into a layer texture, one cell per
  glyph, at the nominal cell size and sampled without filtering (§4.11). No atlas file to generate or ship, and font and glyph set stay settings. Rejected: a
  pre-baked PNG or distance-field atlas, which adds a build step for no gain at a fixed size.

### 4.5 The shader is written for the lowest common GLSL

`rain.frag` uses floats only (no `texelFetch`, no integer hashing) and is baked for GLSL 100 es,
120 and 150 plus SPIR-V, the GLSL versions of Qt's own `qsb --qt6` preset. One source then works whichever
graphics backend plasmashell runs on. The hash is Dave Hoskins' `hash12` (no `sin`), so the
pattern is the same on every GPU. Its inputs are kept small because it degrades on large ones.

### 4.6 Tooling runs on the system's Qt; qsb comes from the distribution

- **Preview, shots and checks** use the system Python with the distribution's PyQt6
  (`python3-pyqt6.qtquick`). That is the same Qt 6.10.2 plasmashell runs on, so a frame grabbed
  by the tooling was drawn by the code that will draw the desktop. This is why the project does
  not use `uv`, unlike the owner's Python projects: a PyPI Qt would be a different build.
- **`qsb`**, which bakes the shader, is only needed after editing `rain.frag`; the baked file is
  in the repository. The proper source is the `qt6-shader-baker` package (needs `sudo`, not
  installed yet: open.md O2). Running PySide6's copy from PyPI through `uvx` was tried and
  denied by the owner's permission setup, and is not to be retried. Until the package is
  installed, the `qsb` binary inside the installed Krita snap works: it links against the
  system's `libQt6ShaderTools` 6.10.2, so the baking is done by the system library
  (`QSB=/snap/krita/current/usr/lib/qt6/bin/qsb ./run.sh build`).

### 4.7 The package id, the licence

`io.github.tominocz.matrixwallpaper`, after the owner's GitHub name. It is also the name of the
settings group, so changing it after the first `apply` orphans the saved settings.

MIT (owner, 2026-11-15: "a project for fun, I don't care very much what people do with it"), the
same as PipeBoard. The public repository is `github.com/TominoCZ/MatrixWallpaper`.

### 4.8 The background is a floor under the trail, not a second layer

The owner's idea (2026-11-15), in answer to "black, or the wallpaper dimmed, behind the glyphs":
limit how dark a trail may get. A cell's brightness is `max(trailFloor, drop brightness)`, so
with a floor above 0 every glyph stays on screen at that brightness and the image stays readable
as a mosaic of characters, with the drops running through it brighter. `TrailFloor` is a
setting, 0 to 1: 0 is the film's black, the default is 0.25.

It costs one `max()` and no extra texture lookup. Rejected: drawing the dimmed photo itself
under the glyphs, which is a second full-resolution texture and stops looking like text.

Because the shader has no memory, the floor applies to every cell from the first frame, not
only where a drop has already passed. Making glyphs appear only once a drop has reached them
would need state or a start time; not asked for.

### 4.9 Dark images are lifted, not multiplied

A cell's colour is scaled by `value^-lift`, where value is its brightest channel. `Lift` is a
setting, 0 to 1: at 0 a glyph is as bright as the image is there; at 1 every glyph has full
brightness in its image's hue (the film's look, in the picture's colours, but the picture's
light and shade are gone); the default is 0.5. Dark cells gain the most, the hue does not move
and nothing can clip, whatever the image.

Rejected: a plain multiplier, which needs a different value for every picture and burns out
the bright parts of the ones it suits. Measured on a fixture a fifth as bright as full: lift 0.5
doubles the light (×2.05), lift 1 brings it to ×4.4.

### 4.10 Defaults live in two places

Plasma reads the defaults from `main.xml`; the preview, shots and checks read the property
defaults in `MatrixRain.qml`. They must be equal or the preview stops showing what the desktop
will. `check_defaults_match_the_settings_file` fails when they drift.

### 4.11 The grid is fitted to the screen

Asked for by the owner (2026-11-15): the right edge cut its glyphs in half (5120 px is 426.67
cells of 12 px). The grid is now the nearest whole number of columns and rows, spread over
exactly the screen: 427 columns of 11.99 px here, so the last column ends at the screen's edge
like the first begins at it.

The glyph texture keeps its nominal cell size and is sampled to the nearest texel, so glyphs
stay sharp; the price is one pixel column dropped or doubled every hundred cells or so (four
places across this screen). Rejected: whole 12 px cells centred with a black strip each side
(not edge to edge), and a cell width that divides the screen (10 or 16 px here, and different
on every screen).

### 4.12 Speed is in pixels, cells are small

The owner's idea (2026-11-15): the rain can only move a cell at a time, so big cells at a fixed
rows-per-second look steppy however many frames are drawn; make the font smaller and let the
stepping rate follow. `Speed` is therefore pixels per second for the fastest drops (default
480; the slowest fall at 0.3 of it), and the shader's tick is in rows, so rows per second =
`Speed` / `CellHeight`: 24 at 20 px, 30 at 16 px, 40 at 12 px. The default cell height went
from 20 to 16 px (10 px wide: 512 × 90 cells on the owner's screen). Once glide had made the
motion smooth the owner tried 20 px again and went back to 16.

Below about 14 px the glyphs get thin and the rain dimmer (antialiased strokes carry less
light); compared at 20, 16, 14, 12 and 10 px on the owner's wallpaper.

### 4.13 The light slides through the glyphs (`Glide`)

With 240 real frames a second the rain still did not feel like it (owner, 2026-11-15), because
nothing on screen moved: a glyph never changes place, it only gets brighter and darker, so the
eye saw a cell fade in every 33 ms, not motion. With `Glide` 1 (the default) a pixel's place on
the drop's way is its own height, not its cell's row: the light front and the white head are a
soft band that travels down the screen two pixels per frame, through the glyphs. With `Glide`
0 each glyph lights up as a whole, as before. One `mix()` in the shader.

The owner on seeing it: "seems very smooth now". `./run.sh set Glide 0` and `1` compare the
two live.

## 5. The look

What the owner asked for: "a live cmatrix-like animation where each letter takes the color of
the image at that grid position of the letter".

First pass, as built: every glyph at least a quarter lit (`TrailFloor`, §4.8); dark images
lifted halfway to full brightness (`Lift`, §4.9); half-width katakana, digits and a few signs in the system's monospace font; 16 px cells fitted to the screen (§4.11); two drops per column
falling at 144 to 480 px a second (`Speed`, §4.12); brightness falling linearly up the trail; the head
mixed 60 % towards white; the light sliding through the glyphs (`Glide`, §4.13) at the
display's frame rate (§4.3). Without an image the rain is `#00ff41`.

Not settled, for M4: the trail curve, how many drops, the head, how often glyphs swap, and
which `TrailFloor` and `Lift` the owner likes on the real desktop.

## 6. Preview tooling

- `./run.sh` shows the rain live in a window, coloured from the current wallpaper image.
- `./run.sh set KEY VALUE` changes a setting of the running desktop wallpaper at once, with no
  restart: the way to try a cell size or speed by eye until the settings page exists (M5).
- `./run.sh perf` prints what the running wallpaper costs (plasmashell and compositor CPU, GPU,
  power) and its real frame rate, late frames and worst gap, read from plasmashell's log.
- `./run.sh check` shows one small window for about three seconds (the frame-rate check: frames
  only come to a window that is on screen); everything else is off-screen.
- `./run.sh shots` renders every state in `scripts/shots.py` to `.dev/shots/<name>.png` plus
  `sheet.png`; `./run.sh shots rain` renders one group, `./run.sh shots =rain` one shot. Each
  frame is audited: Qt warnings while rendering (a shader that did not load), the frame size,
  almost nothing lit, too much lit (the glyph mask missing; glyph strokes are at most 10 % of a frame). The exit code is the number of
  faulty shots. Each of these has been seen to fail once (plan notes, 2026-11-15).
- The `photo*` shots render the owner's current wallpaper at the screen's real size, at several
  trail floors and lifts; they are skipped on a machine without one. `floor-*` and `lift-*` are
  the same variants on the fixtures (`lift-*` on a fixture a fifth as bright).

Add a shot for every new state or variant of the look. When a visual problem is reported, first
add the shot that shows it. A green audit is not a good-looking frame: open the PNGs.

## 7. Milestones

The plan of record, with every finding and decision in its notes, is in the author's local
working files (`.ponytail/plans/`, not in the repository). In short:

- M1 — Project setup ✅
- M2 — First run inside Plasma ✅
- M3 — Measure, then optimise
- M4 — The look
- M5 — Settings in the wallpaper dialog
- M6 — Public release (MIT, github.com/TominoCZ/MatrixWallpaper)
