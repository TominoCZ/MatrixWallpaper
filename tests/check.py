"""The checks: render real frames off-screen and assert what the effect promises.

Needs a GPU and the system's PyQt6 (docs/deps.md). Run with ./run.sh check.
"""

import sys
import time
from pathlib import Path
from xml.etree import ElementTree

from PyQt6.QtCore import QRect
from PyQt6.QtGui import QImage

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
    window = rain.view(480, 240, trailFloor=0, cellHeight=20, drops=2, glow=0)  # 40 x 12 cells of 12 x 20 px
    assert black_cells(rain.grab(window, 200)) > 100, "with no floor, cells between the drops should be black"
    window.rootObject().setProperty("trailFloor", 0.3)
    assert black_cells(rain.grab(window, 200)) == 0, "with a floor, no cell may go black"


def check_lift_brightens_and_keeps_the_hue() -> None:
    dark = rain.bands(TMP / "dark.png", (1280, 720), shade=204)  # a fifth as bright
    window = rain.view(1280, 720, dark, lift=0, trailFloor=0.25, drops=2, glow=0, trailCurve=1)
    red_band = QRect(30, 0, 260, 720)
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
    # Glide off: with it, a head glyph entering at the top slides in and is rightly drawn in part.
    frame = rain.grab(rain.view(500, 250, trailFloor=1, cellHeight=20, glyphs="0123456789", glide=0, glow=0), 200)
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
    window = rain.view(480, 240, trailFloor=0, cellHeight=20, glyphs="|", glide=0, glow=0)
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
    window = rain.view(480, 240, trailFloor=0, cellHeight=20, glow=0, drops=2)
    for start in (100, 1e9):
        frames = [rain.grab(window, start + step / 10) for step in range(10)]
        smooth = sum(len({rain.mean_rgb(f, QRect(x, 0, 12, 240)) for f in frames}) == 10 for x in range(0, 480, 12))
        assert smooth >= 30, f"at tick {start:g} only {smooth} of 40 columns change with every tenth of a row"


def check_settings_page_covers_every_setting() -> None:
    # Plasma hands the page a cfg_<Key> for each setting it declares and reads them back on
    # Apply. Each must be there and survive the trip through its control (LogFrameRate has none).
    keys = [e.get("name") for e in ElementTree.parse(rain.ROOT / "package/contents/config/main.xml").findall(".//{*}entry")]
    values = {"Image": "/tmp/a picture #1.jpg", "CellHeight": 18, "Speed": 300, "TrailFloor": 0.4, "Lift": 0.6, "Glide": 2,
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
    window = rain.view(640, 360, rain.bands(TMP / "big-bands.png", (6000, 3000)), trailFloor=0.5, cellHeight=20, glow=0)
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
    window = rain.view(640, 360, trailFloor=0, cellHeight=20, glow=0, drops=2, trailCurve=1)
    root = window.rootObject()

    def light(**props) -> float:
        for key, value in props.items():
            root.setProperty(key, value)
        # Averaged over four moments: one frame may hold few drops. Longer trails also lengthen
        # the gap before a drop comes round again, so their gain is well below proportional.
        total = sum(brightness(rain.grab(window, tick)) for tick in (100, 200, 300, 400))
        for key in props:  # back to the defaults for the next measurement
            root.setProperty(key, {"glow": 0, "drops": 2, "trailLength": 1, "trailCurve": 1}[key])
        return total

    assert light(glow=1) > 1.3 * light(glow=0), "head glow does not add light"
    assert light(drops=4) > 1.5 * light(drops=1), "more drops per column do not light more"
    assert light(trailLength=2) > 1.3 * light(trailLength=0.5), "longer trails do not light more"
    assert light(trailCurve=3) < 0.7 * light(trailCurve=0.5), "a quick trail fade is not darker than an even one"


def head_unevenness(**props) -> float:
    """Follow one drop's head for half a second at 240 fps, as an eye would: the spread of its
    per-frame steps over their mean. Tracked is the centre of the white in its column (the head
    is white, its trail coloured), weighted linearly as the eye roughly does."""
    import numpy as np  # only this check needs it

    window = rain.view(640, 360, trailFloor=0, drops=1, speed=400, glow=0, **props)
    root = window.rootObject()
    cell_width, step = 640 / root.property("columns"), 400 / root.property("cellHeight") / 240

    def whiteness(tick):
        frame = rain.grab(window, tick).convertToFormat(QImage.Format.Format_RGBX8888)
        return np.frombuffer(frame.constBits().asstring(frame.sizeInBytes()), np.uint8).reshape(360, 640, 4)[:, :, :3].min(axis=2) / 255

    first = whiteness(200)  # a column whose head is in the top third, so it stays on screen
    column = max(range(root.property("columns")), key=lambda c: first[:120, int(c * cell_width):int((c + 1) * cell_width)].max())
    x0, x1 = int(column * cell_width), int((column + 1) * cell_width)
    centres = []
    for frame in range(120):
        white = whiteness(200 + frame * step)[:, x0:x1].max(axis=1)
        centres.append((white * np.arange(360)).sum() / max(white.sum(), 1e-9))
    steps = np.diff(centres)
    return steps.std() / abs(steps.mean())


def check_look_alike_heads_never_neighbours() -> None:
    # Measured look-alike katakana (16 to 30 px). Neighbouring rows draw from places of different
    # parity, so each group must sit at places of one parity, or a falling head can morph into a
    # glyph that looks the same and seem to freeze. Signs and look-alike digits must never be heads.
    window = rain.view(64, 64)
    root = window.rootObject()
    order = root.property("glyphs")
    for group in ("ｦｳｵｻｿﾂﾃﾅﾎﾗﾘﾜ", "ｴｺﾆﾕ", "ｱｽﾇ", "ｾﾔ", "27"):
        parities = {order.index(g) % 2 for g in group}
        assert len(parities) == 1, f"look-alikes {group} are split between the two halves"
    heads = order[: int(root.property("headCount"))]
    assert not any(g in heads for g in "035689:.=*+-<>"), "a look-alike digit or a sign can be a falling head"
    assert all(g in heads for g in "1247"), "the distinct digits 1 2 4 7 should be heads too"


def check_falling_heads_never_shrink_to_a_dot() -> None:
    # Glyphs "0", "1" and ".": a falling head passing a "." cell must show a tall glyph instead,
    # or it looks as if it vanished. Tracked: the white (the head; its trail is coloured) in each
    # column with a head, frame by frame; its least over half a second against its typical.
    import numpy as np

    window = rain.view(640, 360, trailFloor=0, cellHeight=24, glide=2, glyphs="01.", notHeads=".", drops=1, glow=0)
    root = window.rootObject()
    width, step = 640 / root.property("columns"), 400 / 24 / 240

    def white(tick):
        frame = rain.grab(window, tick).convertToFormat(QImage.Format.Format_RGBX8888)
        return np.frombuffer(frame.constBits().asstring(frame.sizeInBytes()), np.uint8).reshape(360, 640, 4)[:, :, :3].min(axis=2) / 255

    first = white(200)
    columns = [c for c in range(root.property("columns"))
               if 0.2 * 360 < first[:, int(c * width):int((c + 1) * width)].max(axis=1).argmax() < 0.6 * 360][:6]
    masses = np.array([[white(200 + f * step)[:, int(c * width):int((c + 1) * width)].sum() for c in columns]
                       for f in range(0, 120, 4)])
    worst = (masses.min(axis=0) / np.median(masses, axis=0)).min()
    assert worst > 0.5, f"a falling head shrank to {worst:.0%} of its usual white: it showed a short glyph"


def check_falling_heads_move_evenly() -> None:
    # Motion 2 exists for an eye following a drop: its head must move by the same amount every
    # frame. With the head on the grid (motion 0) it moves in steps, which this must tell apart.
    assert head_unevenness(cellHeight=24, glide=2) < 0.15, "falling heads do not move evenly"
    assert head_unevenness(cellHeight=24, glide=0) > 0.3, "the measure cannot tell steps from even motion"


def check_no_glyph_repeats_its_neighbour_above() -> None:
    # Every glyph fully lit, in the green fallback (a head's whitening leaves green alone), cell
    # by cell: two cells above each other with the same pixels show the same glyph.
    import numpy as np  # only this check and the motion check need it

    window = rain.view(640, 360, trailFloor=1, cellHeight=20, glide=0, glow=0)
    for tick in (100, 200, 300):
        frame = rain.grab(window, tick).convertToFormat(QImage.Format.Format_RGBX8888)
        green = np.frombuffer(frame.constBits().asstring(frame.sizeInBytes()), np.uint8).reshape(360, 640, 4)[:, :, 1]
        cells = green[:360, :636].reshape(18, 20, 53, 12)  # 18 rows x 53 columns of 12 x 20 px
        same = int((cells[1:] == cells[:-1]).all(axis=(1, 3)).sum())
        assert same == 0, f"{same} glyphs repeat the one above them at tick {tick}"


def check_faster_drops_leave_longer_trails() -> None:
    # Like light fading on a screen: a glyph fades over time once the head has passed, so a drop
    # that falls faster leaves a longer trail. Per column: the head's speed from two frames a tick
    # apart, and how many cells above it are lit; the two must rise together.
    import numpy as np

    # Tall, with trails at half length, so that most trails end on screen and can be measured.
    window = rain.view(640, 1440, trailFloor=0, cellHeight=20, glide=0, drops=1, trailCurve=1, trailLength=0.5, glow=0)
    columns, rows = window.rootObject().property("columns"), window.rootObject().property("rows")

    def cells(tick):
        frame = rain.grab(window, tick).convertToFormat(QImage.Format.Format_RGBX8888)
        a = np.frombuffer(frame.constBits().asstring(frame.sizeInBytes()), np.uint8).reshape(1440, 640, 4)
        a = a[: rows * 20, : columns * 12].reshape(rows, 20, columns, 12, 4).astype(float)
        return a[..., :3].min(axis=-1).max(axis=(1, 3)), a[..., 1].max(axis=(1, 3))  # whiteness, green

    speeds, lengths = [], []
    for start in (100, 300, 500, 700, 900, 1100):
        white0, green = cells(start)
        white1, _ = cells(start + 6)
        for c in range(columns):
            h0, h1 = white0[:, c].argmax(), white1[:, c].argmax()
            if white0[h0, c] < 100 or white1[h1, c] < 100 or not 0 < h1 - h0 <= 6 or h0 > rows - 7:
                continue  # no head here, or it left the screen
            lit = 0
            while h0 - lit - 1 >= 0 and green[h0 - lit - 1, c] > 30:
                lit += 1
            if h0 - lit - 1 >= 0:  # the trail's end is on screen
                speeds.append((h1 - h0) / 6)
                lengths.append(lit)
    r = np.corrcoef(speeds, lengths)[0, 1]
    assert len(speeds) >= 15 and r > 0.4, f"faster drops do not leave longer trails (correlation {r:+.2f} over {len(speeds)} drops)"


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
