"""The checks: render real frames off-screen and assert what the effect promises.

Needs a GPU and the system's PyQt6 (docs/deps.md). Run with ./run.sh check.
"""

import sys
import time
from pathlib import Path
from xml.etree import ElementTree

from PyQt6.QtCore import QRect

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import rain  # noqa: E402

TMP = rain.ROOT / ".dev/check"
RED, GREEN, BLUE = 0, 1, 2


def dominant(frame, rect: QRect, channel: int) -> bool:
    """Is this part of the frame lit, and clearly in one colour channel?"""
    rgb = rain.mean_rgb(frame, rect)
    return rgb[channel] > 1 and all(rgb[channel] > 2 * v for c, v in enumerate(rgb) if c != channel)


def check_colour_follows_image() -> None:
    # 16:9 image in a 16:9 window: nothing is cropped, so each quarter of the frame is one band.
    frame = rain.grab(rain.view(1280, 720, rain.bands(TMP / "bands.png", (1280, 720))), 200)
    for i, channel in enumerate((RED, GREEN, BLUE)):
        assert dominant(frame, QRect(i * 320 + 30, 0, 260, 720), channel), f"band {i} is not its image colour"
    r, g, b = rain.mean_rgb(frame, QRect(3 * 320 + 30, 0, 260, 720))
    assert r > 1 and abs(r - g) < 0.2 * r and abs(r - b) < 0.2 * r, "the white band is not grey"


def check_image_is_cropped_not_squeezed() -> None:
    # Square image with horizontal bands in a 2:1 window: only its middle half shows, so the
    # top of the frame is the green band and the bottom the blue one.
    image = rain.bands(TMP / "rows.png", (800, 800), vertical=False)
    frame = rain.grab(rain.view(1200, 600, image), 200)
    assert dominant(frame, QRect(0, 30, 1200, 240), GREEN), "top half should show the green band"
    assert dominant(frame, QRect(0, 330, 1200, 240), BLUE), "bottom half should show the blue band"


def check_no_image_is_green() -> None:
    frame = rain.grab(rain.view(640, 360), 200)
    assert dominant(frame, QRect(0, 0, 640, 360), GREEN), "without an image the rain should be green"


def black_cells(frame, width: int = 12, height: int = 20) -> int:
    """How many whole cells of a frame have nothing lit in them."""
    return sum(
        rain.mean_rgb(frame, QRect(x, y, width, height)) == (0, 0, 0)
        for y in range(0, frame.height(), height)
        for x in range(0, frame.width(), width)
    )


def check_trail_floor_keeps_every_glyph_lit() -> None:
    window = rain.view(480, 240, trailFloor=0, cellHeight=20)  # 40 x 12 cells of 12 x 20 px
    assert black_cells(rain.grab(window, 200)) > 100, "with no floor, cells between the drops should be black"
    window.rootObject().setProperty("trailFloor", 0.3)
    assert black_cells(rain.grab(window, 200)) == 0, "with a floor, no cell may go black"


def check_lift_brightens_and_keeps_the_hue() -> None:
    dark = rain.bands(TMP / "dark.png", (1280, 720), shade=204)  # a fifth as bright
    window, red_band = rain.view(1280, 720, dark, lift=0), QRect(30, 0, 260, 720)
    as_is = rain.mean_rgb(rain.grab(window, 200), red_band)[RED]
    window.rootObject().setProperty("lift", 1)
    lifted = rain.grab(window, 200)
    gain = rain.mean_rgb(lifted, red_band)[RED] / as_is
    assert gain > 3, f"full lift should bring a fifth-bright image near full brightness, gained x{gain:.1f}"
    assert dominant(lifted, red_band, RED), "lift changed the hue"


def check_defaults_match_the_settings_file() -> None:
    # Plasma takes its defaults from main.xml, the preview and these checks from MatrixRain.qml.
    window = rain.view(320, 200)  # kept in a name: the root object dies with its window
    root = window.rootObject()
    entries = ElementTree.parse(rain.ROOT / "package/contents/config/main.xml").findall(".//{*}entry")
    assert entries, "no settings found in main.xml"
    for entry in entries:
        key, default = entry.get("name"), entry.findtext("{*}default") or ""
        ours = root.property(key[0].lower() + key[1:])
        ours = ours.toString() if hasattr(ours, "toString") else ours  # the image is a URL
        assert str(ours).lower() == default or float(ours) == float(default), f"{key}: {ours!r} here, {default!r} in main.xml"


def check_grid_ends_at_the_edges() -> None:
    # 500 x 250 px is 41.67 x 12.5 cells of 12 x 20 px: the grid must still end on a cell boundary
    # all round.
    # With every glyph fully lit, a cut glyph shows as lit pixels in the outermost line. Digits
    # only: they keep clear of their cell's border, which "|" does not.
    frame = rain.grab(rain.view(500, 250, trailFloor=1, cellHeight=20, glyphs="0123456789"), 200)
    edges = {"left": QRect(0, 0, 1, 250), "right": QRect(499, 0, 1, 250), "top": QRect(0, 0, 500, 1), "bottom": QRect(0, 249, 500, 1)}
    for name, line in edges.items():
        assert rain.mean_rgb(frame, line) == (0, 0, 0), f"glyphs are cut off at the {name} edge"


def half_lit_cells(frame, width: int = 12, height: int = 20) -> int:
    """Cells whose top is lit while their bottom is still dark: the light front is inside them."""
    count = 0
    for y in range(0, frame.height(), height):
        for x in range(0, frame.width(), width):
            top = rain.mean_rgb(frame, QRect(x, y + 2, width, 4))[GREEN]
            bottom = rain.mean_rgb(frame, QRect(x, y + height - 6, width, 4))[GREEN]
            count += top > 8 and bottom < top / 5
    return count


def check_light_glides_through_glyphs() -> None:
    # "|" has ink from the top of its cell to the bottom, so only the light can make one half
    # of a cell darker than the other.
    window = rain.view(480, 240, trailFloor=0, cellHeight=20, glyphs="|", glide=0)
    assert half_lit_cells(rain.grab(window, 200.5)) == 0, "with glide 0 a glyph must be lit as a whole"
    window.rootObject().setProperty("glide", 1)
    gliding = half_lit_cells(rain.grab(window, 200.5))
    assert gliding >= 5, f"with glide 1 the front should be inside some glyphs, found {gliding}"


def check_it_fades_smoothly_for_years() -> None:
    # Ten frames a tenth of a row apart. A column with a drop in it must look different in every
    # one of them; a rain that moves in steps changes once or twice in that time. Checked at the
    # start and after about a year of running (1e9 rows at 30 rows a second): a clock held in
    # one 32-bit float loses its fraction as it grows, and after five hours the motion went
    # coarse.
    window = rain.view(480, 240, trailFloor=0, cellHeight=20)
    for start in (100, 1e9):
        frames = [rain.grab(window, start + step / 10) for step in range(10)]
        smooth = sum(len({rain.mean_rgb(f, QRect(x, 0, 12, 240)) for f in frames}) == 10 for x in range(0, 480, 12))
        assert smooth >= 30, f"at tick {start:g} only {smooth} of 40 columns change with every tenth of a row"


def check_settings_page_covers_every_setting() -> None:
    # Plasma hands the page a cfg_<Key> for each setting it declares and reads them back on
    # Apply. Each must be there and survive the trip through its control (LogFrameRate has none).
    keys = [e.get("name") for e in ElementTree.parse(rain.ROOT / "package/contents/config/main.xml").findall(".//{*}entry")]
    values = {"Image": "/tmp/a picture #1.jpg", "CellHeight": 18, "Speed": 300, "TrailFloor": 0.4, "Lift": 0.6, "Glide": 0,
              "LogFrameRate": True, "Drops": 3, "TrailLength": 1.5, "TrailCurve": 2.0, "Glow": 0.5, "GlowSize": 1.0}
    assert set(keys) == set(values), f"settings and test values differ: {sorted(set(keys) ^ set(values))}"
    window = rain.load(rain.ROOT / "package/contents/ui/config.qml", 700, 600, {f"cfg_{k}": v for k, v in values.items()})
    page = window.rootObject()
    for key, value in values.items():
        got = page.property(f"cfg_{key}")
        assert got == value or (isinstance(value, float) and abs(got - value) < 1e-6), f"cfg_{key}: set {value!r}, page has {got!r}"


def check_glyph_size_change_keeps_the_picture() -> None:
    # A new glyph size means the picture is decoded again at the new grid. The frame right after
    # the change must still show it (the old decode), not the green fallback while it reloads.
    # A large picture, so that decoding it again takes longer than one frame, as a photo does.
    window = rain.view(640, 360, rain.bands(TMP / "big-bands.png", (6000, 3000)), trailFloor=0.5, cellHeight=20)
    root = window.rootObject()
    for height in (21, 14, 30):
        root.setProperty("cellHeight", height)
        assert dominant(rain.grab(window, 200), QRect(0, 0, 150, 360), RED), f"the picture dropped out when the glyph size became {height}"
        while not root.property("ready"):
            rain.app.processEvents()


def brightness(frame) -> float:
    return sum(rain.mean_rgb(frame, QRect(0, 0, frame.width(), frame.height())))


def check_tuning_knobs_do_what_they_say() -> None:
    # Each knob against its own opposite, on the same frame of the green rain with no trail floor.
    window = rain.view(640, 360, trailFloor=0, cellHeight=20)
    root = window.rootObject()

    def light(**props) -> float:
        for key, value in props.items():
            root.setProperty(key, value)
        frame = rain.grab(window, 200)
        for key in props:  # back to the defaults for the next measurement
            root.setProperty(key, {"glow": 0, "drops": 2, "trailLength": 1, "trailCurve": 1}[key])
        return brightness(frame)

    assert light(glow=1) > 1.3 * light(glow=0), "head glow does not add light"
    assert light(drops=4) > 1.5 * light(drops=1), "more drops per column do not light more"
    assert light(trailLength=2) > 1.5 * light(trailLength=0.5), "longer trails do not light more"
    assert light(trailCurve=3) < 0.7 * light(trailCurve=0.5), "a quick trail fade is not darker than an even one"


def check_it_moves_and_repeats() -> None:
    window = rain.view(640, 360)
    first, moved, again = rain.grab(window, 100), rain.grab(window, 101), rain.grab(window, 100)
    assert first != moved, "the frame did not change with the tick"
    assert first == again, "the same tick gave two different frames: the shader keeps state"


def check_clock_runs_with_the_display() -> None:
    # The one check that shows a window (small, for two seconds): frames only come to a window
    # that is on screen. It must advance once per display frame, not at Qt's 62.5 Hz animation
    # timer, and fall at `speed` pixels a second.
    window = rain.view(320, 200, running=True, speed=400, cellHeight=20)
    window.show()
    root, refresh = window.rootObject(), rain.app.primaryScreen().refreshRate()

    def spin(seconds: float) -> None:
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            rain.app.processEvents()

    spin(0.7)  # let it get on screen and the frame time settle
    frames, tick, began = root.property("frames"), root.property("tick"), time.perf_counter()
    spin(1.5)
    seconds = time.perf_counter() - began
    fps, rows = (root.property("frames") - frames) / seconds, (root.property("tick") - tick) / seconds
    root.setProperty("speed", 0)  # stands still, and draws nothing
    spin(0.3)
    idle = root.property("frames")
    spin(0.5)
    assert root.property("frames") - idle <= 2, "frames are still drawn at speed 0"
    root.setProperty("speed", 400)  # and starts again by itself
    spin(0.5)
    assert root.property("frames") - idle > 50, "the clock did not start again after speed 0"
    window.hide()  # as when the screen goes off or is locked: no frames, and none asked for
    spin(0.3)
    hidden = root.property("frames")
    window.show()
    spin(0.7)
    assert root.property("frames") - hidden > 50, "the clock did not start again after the window was hidden"
    window.close()
    assert fps > 0.9 * refresh, f"{fps:.0f} frames a second on a {refresh:.0f} Hz display"
    assert abs(rows - 20) < 2, f"fell {rows:.1f} rows a second, 400 px/s in 20 px rows is 20"


if __name__ == "__main__":
    checks = [value for name, value in list(globals().items()) if name.startswith("check_")]
    for check in checks:
        check()
        print(f"ok  {check.__name__}")
    assert not rain.messages, f"Qt warned: {rain.messages}"
    print(f"{len(checks)} checks passed")
