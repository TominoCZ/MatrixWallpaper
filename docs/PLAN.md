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
5120×1440). At a true 240 frames a second it costs plasmashell about a fifth of one core (the
rain itself 5 %, the rest is the desktop window being redrawn) and the machine about 6 W more
than a photo, and 1 % while a fullscreen window (a game) has the focus. Nothing degrades over time: the clock stays exact for years (§4.14) and a
per-frame memory leak in NVIDIA's driver is worked around (§4.15).

## 1. Goals and non-goals

- **Goals:**
  - A live Matrix rain as the desktop wallpaper on Kubuntu (Plasma 6, Wayland), coloured per cell
    from the wallpaper image the desktop had.
  - As cheap as it can be made: all per-pixel work on the GPU, nothing per glyph on the CPU, one
    draw call per frame.
  - Nothing gets worse the longer it runs: frame rate, smoothness, memory.
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
| `package/contents/config/main.xml` | The settings and their defaults: `Image`, `CellHeight`, `Speed`, `TrailFloor`, `Lift`, `Glide`, `Glow`, `GlowSize`, `Drops`, `TrailLength`, `TrailCurve`, `LogFrameRate`. |
| `package/contents/ui/main.qml` | What Plasma loads: a `WallpaperItem` that hands the settings to `MatrixRain` and pauses it while a fullscreen window has the focus (§4.16). |
| `package/contents/ui/config.qml` | The settings page in Plasma's desktop dialog: picture, glyph size, speed, trail floor, lift, glide, and a live preview that is `MatrixRain` itself (§4.17). |
| `package/contents/ui/MatrixRain.qml` | The effect: frame clock, image texture, glyph texture, the shader's inputs. Plain QtQuick, no KDE imports. |
| `package/contents/shaders/rain.frag` | The rain. `rain.frag.qsb` is its baked form, the file Qt loads; both are in the repository. |
| `scripts/rain.py` | Loads `MatrixRain.qml` outside Plasma: hidden window + `grab(tick)` for shots and checks; run directly, the live preview. |
| `scripts/shots.py` | Renders the named states of the rain and of the settings page to `.dev/shots/` and audits each frame. |
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
   Plasma. Reason: that is the only code the tooling cannot see. The one exception is the
   fullscreen pause (§4.16), which needs Plasma's window list; check it in plasmashell.
4. **No tool is fetched from the internet and run without the owner saying so.** Reason: the
   owner's rule (and their permission setup enforces it); see §4.6.
5. **System settings outside the project are the owner's call** (the EGL workaround of §4.15
   included): describe them, apply them only when asked.

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
what a photo does. Of that quarter core the rain itself is about 5 %: measured in a window
outside Plasma at 240 fps, the same at 320×200 and 1280×720. The rest is Qt Quick redrawing
everything else in the desktop window each frame (icons, widgets); it fell from 25 % to 19 %
when the owner's desktop went from many icons to one folder. A wallpaper cannot keep the rest
of its window from being redrawn; drawing fewer frames is the only lever, which is why it
pauses under fullscreen windows (§4.16).

The clock reaches the shader in two parts so that it stays exact for years (§4.14).

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

### 4.13 The light slides through the glyphs (`Glide`, now Motion: §4.19)

With 240 real frames a second the rain still did not feel like it (owner, 2026-11-15), because
nothing on screen moved: a glyph never changes place, it only gets brighter and darker, so the
eye saw a cell fade in every 33 ms, not motion. With `Glide` 1 (the default) a pixel's place on
the drop's way is its own height, not its cell's row: the light front and the white head are a
soft band that travels down the screen two pixels per frame, through the glyphs. With `Glide`
0 each glyph lights up as a whole, as before. One `mix()` in the shader.

The owner on seeing it: "seems very smooth now". `./run.sh set Glide 0` and `1` compare the
two live.

### 4.14 The clock stays exact however long it runs

Found on 2026-11-15 when the owner asked for a check that nothing degrades over time. The clock
reached the shader as one 32-bit float, wrapping at 2²⁰ rows. A float's resolution coarsens as
it grows: after 5 hours of running, frames 1/30 of a row apart gave only 6 different images out
of 10 (the motion moved in 1 px steps), after 9 hours 2 px steps, then the wrap jumped.

Now `MatrixRain.qml` keeps the clock as a double and hands the shader `tickHigh` (whole 128s of
rows) and `tickLow` (the rest, with the fraction). The shader's `elapsed(m)` works out the clock
modulo a whole number `m` exactly from those, and everything that depends on time is made to
repeat after a whole number of rows: each drop's speed is a whole number of 32nds of a row per
tick (0.31 to 1, was any value from 0.3 to 1), so its place repeats after 32 of its periods; each
cell swaps its glyph every whole number of ticks (4 to 40). The look is unchanged. The clock now
wraps at 2³¹ rows, 2.3 years at the default speed. `check_it_fades_smoothly_for_years` checks
the motion at the start and after 10⁹ rows; it failed on the old clock.

`elapsed()` is exact while `m` is below 65536, i.e. while a column's period (up to 2.7 times the
rows on screen) times 32 stays under it: up to about 750 rows, so cells of 2 px on a 1440 px
screen. `CellHeight` has a minimum of 4.

Also hardened for long runs: a system clock set back no longer makes the frame time negative
(the gap must be positive to count), the frame counter is a double, and the frame-rate check
hides and shows its window to prove the clock starts again by itself (screen off, lock screen).

### 4.15 The NVIDIA driver leaks memory per presented frame

Found the same day: plasmashell's memory grew by about 55 kB a second while the rain ran and by
about 12 kB/s with `Speed` 0, linearly, with no sign of levelling off over 6 minutes (about
200 MB an hour, several GB a day). Narrowed down in a window outside Plasma:

| Test at 240 fps | memory per frame |
|---|---|
| the rain | +232 bytes |
| a plain Rectangle on the same frame chain, no shader | +294 bytes |
| the same with a forced JavaScript `gc()` every 2000 frames | +237 bytes |
| Qt's threaded render loop | +281 bytes |
| Qt Quick on Vulkan instead of OpenGL | +42 bytes |
| a bare `QOpenGLWindow`, no Qt Quick at all | +230 bytes |
| the bare window with NVIDIA's older `libnvidia-egl-wayland` 1.1.21 | 0 bytes |
| the rain with `libnvidia-egl-wayland` 1.1.21 | +28 bytes (noise), CPU 6.1 % against 4.9 % |

So it is NVIDIA's new EGL Wayland library, `libnvidia-egl-wayland2`
(`/usr/share/egl/egl_external_platform.d/09_nvidia_wayland2.json`, driver 595.99.02), which takes
precedence over the older one when both are installed. Any Qt OpenGL program leaks the same per
presented frame; a static wallpaper presents almost none, so it never showed before.
`es2gears_wayland` grew only 25 bytes a frame, so it may depend on something Qt does (Qt
presents with swap interval 0 and throttles on frame callbacks itself); not investigated.

The workaround is to point plasmashell alone at the older library with the EGL loader's
`__EGL_EXTERNAL_PLATFORM_CONFIG_FILENAMES` variable, in a systemd drop-in for
`plasma-plasmashell.service` (README, "Known limits"). Rejected: Qt Quick on Vulkan for
plasmashell, a much larger change to the whole shell for the same result. The wallpaper itself
cannot choose the EGL library.

Applied on the owner's machine at their request (2026-11-15,
`~/.config/systemd/user/plasma-plasmashell.service.d/egl-wayland.conf`): plasmashell then loads
`libnvidia-egl-wayland.so.1.1.21`, still draws 240 frames a second at the same CPU, and its
memory stayed flat (+40 kB over 75 s, against +55 kB every second before).

### 4.16 Paused while a fullscreen window has the focus

The owner (2026-11-15): "all I would need is detecting a fullscreen window in focus, like a
fullscreen game, borderless or not", if it is cheap; and first, whether the system already does
it. It does not: with the owner's fullscreen application up for four minutes the wallpaper kept
drawing 240 frames a second, so KWin keeps sending frames to a covered desktop. (Plasma's image
wallpaper pauses its animated pictures with its own `MaximizedWindowMonitor`; that is code in
that plugin, not something other wallpapers get.)

Built in `main.qml`, because it needs Plasma's `org.kde.taskmanager`: a `TasksModel` limited to
this screen (the desktop window's geometry, as the image wallpaper does) watches the active
window. The rain's `running` is off while that window is fullscreen, or its geometry covers its
whole screen (a borderless game that does not set the fullscreen state). It reacts to
`activeTaskChanged` and `dataChanged`, so it costs nothing between window events. Measured with a
fullscreen test window: 0 frames a second while it had the focus, back to 240 at once after;
plasmashell 1 % of a core while paused against 20 % running.

What it deliberately ignores: a maximized window (the owner asked for fullscreen only; with a
visible panel it does not cover the screen), and a fullscreen window that has lost the focus.
With an auto-hiding panel a maximized window does cover the screen and pauses the rain, which is
invisible then anyway. The tooling cannot check this code outside Plasma (§3 rule 3); it was
checked in plasmashell. A frame-rate cap was left out: the owner wants 240.

### 4.17 The settings page

`config.qml`, the page Plasma shows under "Configure Desktop and Wallpaper", follows Plasma's own
wallpaper pages: a `Kirigami.FormLayout` with one `cfg_<Key>` property per setting, which Plasma
fills from the configuration and saves on Apply. Image (a path field and a file chooser), glyph
size, speed, the two sliders and the glide checkbox; `LogFrameRate` stays off the page (it is for
`./run.sh perf`). Each field has one line saying what it does.

On top is a live preview, and it is simply `MatrixRain` with the page's values, so it shows the
real thing before Apply: glyph size and speed as on the desktop, the whole picture fitted into a
frame of the screen's shape that shrinks with the dialog. The page has no Plasma imports
(Kirigami and Qt Quick Controls only), so the harness loads it like any QML file.

`MatrixRain.image` became a path (or URL) string, converted in one place (`toUrl`), so the page,
`main.qml` and the harness all pass what the setting holds.

Checked by `check_settings_page_covers_every_setting` (every setting but `LogFrameRate` is on the
page and survives the round trip through its control; it fails when a setting is added to
`main.xml` and not to the page) and three shots, `settings`, `settings-green` and
`settings-narrow`, audited for Qt warnings, any visible item reaching past the window, and a
preview that shows the green fallback although a picture is set. Both audits were seen to fail:
a fixed-width preview overflowed the narrow window, and grabbing before the layout had settled
showed the fallback.

Tried in Plasma's real dialog by the owner (2026-11-15): "seems to work". With `LogFrameRate`
on, the preview logs its own frame rate (as "MatrixWallpaper preview:", which `./run.sh perf`
ignores): a steady 120 frames a second in the dialog. Plasmashell draws all its windows on one
thread, so with the dialog open it and the desktop share the display's 240; outside Plasma two
windows in one process showed the same halving. Apply saved the values.

Changing the glyph size used to flash the rain green for a few frames, in the preview and on the
desktop: a new size means the picture is decoded again, and the `Image` the shader draws from
was empty while it reloaded. Now a second, hidden `Image` (`decoding`) decodes each new picture
or size and hands it to the one the shader uses (`colours`) only when done; `colours` takes it
from Qt's image cache at once. `check_glyph_size_change_keeps_the_picture` uses a 6000×3000
picture so that decoding takes longer than a frame (with a small one the race hid the bug); it
failed on the old code.

Two harness lessons from it: a hidden window lays itself out only when it is drawn, so a shot
must draw, wait for pictures, and draw again until nothing changes; and fixture pictures are
written to a temporary name and swapped in, because a view still loading the previous copy read
a half-written file. `MatrixRain.ready` now waits for the picture itself (ready or failed): it
used to say ready in the moment between the source being set and its loading starting.

### 4.18 Tuning knobs, and the head glow

The owner chose four parts of the look to tune by eye (2026-11-15), most of all the glow. Each is
a setting with a control in a "Tuning" section of the settings page, so the live preview shows
it before Apply; the defaults keep the look as it was (glow off):

- **Drops per column** (`Drops`, 1 to 4): the drops are a loop over seeds 7·i; seeds 0 and 7 are
  the two of before.
- **Trail length** (`TrailLength`, ×0.25 to ×2): scales the 8-rows-to-70 %-of-the-screen range.
- **Trail fade** (`TrailCurve`): the trail's light is (1 − distance from the head / length)^curve.
  The slider is logarithmic so that 1 (even) is in its middle.
- **Head glow** (`Glow`, `GlowSize`): a halo around each head in the cell's colour, whitened a
  little, added on top of the glyphs so it lights the gaps between them. Its falloff
  (1 − d²/r²)² reaches exactly zero at the radius, and each pixel looks at the heads of two
  columns either side, with the radius held to what those cover, so no seam shows at a column
  edge.

The clipped "|" (it reached past its cell in this font) is no longer among the glyphs.

The glow is the costly part: each pixel works out ten drops instead of two. On the owner's
screen (5120×1440, 240 fps) plasmashell's GPU share went from 30–38 % to 43–45 % and board power
by up to 30 W, measured by switching it on and off three times. The planned fix: render each
column's drop positions once per frame into a small floating-point texture and let every pixel
look them up.

### 4.19 Motion for an eye that follows a drop

The owner (2026-11-15): at glyph sizes 20–30 a drop followed by eye did not look smooth, at 4
and 64 it did. Measured by following drops' white heads frame by frame at 240 fps (spread of
the per-frame steps over their mean, median of up to eight drops; `check_falling_heads_move_evenly`
keeps the measure): with glyphs fixed and only the light moving, the white an eye follows
hopped glyph to glyph, at exactly the rate the head passed glyph rows: 8–17 Hz at 20–30 px, the
band the eye reads as judder (60–90 Hz at 4 px is fused, 3–4 Hz at 64 px reads as structure).

`Glide` became a three-way **Motion** setting:

| Motion | | unevenness, 16–64 px |
|---|---|---|
| 0, steps | the light steps cell by cell | 0.49–0.71 |
| 1, smooth light over the glyphs (default) | everything on the grid; the head's highlight is a symmetric bump of light (σ 0.5 rows) with a soft front | 0.20–0.43 |
| 2, smooth falling heads | the head is a glyph of its own, falling at its exact position, drawn between texel rows so it moves by fractions of a pixel, over the fixed glyphs (only its strokes cover them); the trail lights up across its height | 0.06–0.14 |

Motion 1 cannot be made perfectly smooth: the light is, but it is visible only on glyph ink,
which is fixed and broken into shapes with gaps between rows, so the visible white stalls at
each gap. No highlight width got it below about 0.2 (σ 0.3 to 1.2 tried); switching glyph swaps
off helped a little. Only something that moves is perfectly smooth.

In motion 2 the head shows the character of the grid cell it passes (lined up with a cell it is
that glyph, on top of it) and crossfades evenly to the next cell's as it slides. A head with one
character for its whole fall measured 0.00–0.05; switching costs a little, and switching at once
cost as much as motion 1 (0.17–0.42), hence the even crossfade. The first falling version hid
the fixed glyphs in the head's row, which looked like a black box cutting off the tail.

A glyph never repeats the one above it: even rows draw from the glyphs at even places in the
set, odd rows from the odd ones, so the falling head always visibly changes and no trail shows
the same character twice in a row. Two rows apart a repeat is still possible (about 1 in 28).

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
  restart and no dialog; Plasma's dialog (§4.17) does the same with a preview.
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
- M3 — Measure, then optimise ✅ (paused while a fullscreen window has the focus; no frame cap)
- M4 — The look
- M5 — Settings in the wallpaper dialog ✅ (§4.17)
- M6 — Public release (MIT, github.com/TominoCZ/MatrixWallpaper)
