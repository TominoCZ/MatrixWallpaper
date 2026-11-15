"""Render every named state of the effect off-screen and audit each frame.

    ./run.sh shots          every shot, plus the contact sheet .dev/shots/sheet.png
    ./run.sh shots rain     the shots whose name starts with "rain", with their own sheet
    ./run.sh shots =rain    only the shot named "rain"

The exit code is the number of faulty shots. A green audit is not a good-looking frame: open
the PNGs and look.
"""

import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtQuick import QQuickItem

import rain

OUT = rain.ROOT / ".dev/shots"
TICK = 200  # far enough in that every column has a drop somewhere
LIT = bytes(1 if value > 40 else 0 for value in range(256))


def fixture() -> Path:
    return rain.bands(OUT / "fixture-bands.png", (1280, 720))


def dark_fixture() -> Path:
    return rain.bands(OUT / "fixture-dark.png", (1280, 720), shade=204)  # a fifth as bright


def screen_size() -> tuple[int, int]:
    size = rain.app.primaryScreen().size()
    return size.width(), size.height()


# name -> (window size, image, properties). A missing image skips the shot.
SHOTS = {
    "rain": lambda: ((1280, 720), fixture(), {}),
    "rain-green": lambda: ((1280, 720), None, {}),
    "rain-big": lambda: ((1280, 720), fixture(), {"cellHeight": 40}),
    "rain-small": lambda: ((480, 270), fixture(), {}),
    "rain-odd-size": lambda: ((1003, 409), fixture(), {"trailFloor": 0.5}),  # 83.6 x 20.45 cells
    "glide-none": lambda: ((1280, 720), fixture(), {"glide": 0, "cellHeight": 40}),
    "glide-full": lambda: ((1280, 720), fixture(), {"glide": 1, "cellHeight": 40}),
    "glide-falling": lambda: ((1280, 720), fixture(), {"glide": 2, "cellHeight": 40}),
    "floor-none": lambda: ((1280, 720), fixture(), {"trailFloor": 0}),
    "floor-half": lambda: ((1280, 720), fixture(), {"trailFloor": 0.5}),
    "lift-none": lambda: ((1280, 720), dark_fixture(), {"lift": 0}),
    "lift-half": lambda: ((1280, 720), dark_fixture(), {"lift": 0.5}),
    "lift-full": lambda: ((1280, 720), dark_fixture(), {"lift": 1}),
    "tune-glow": lambda: ((1280, 720), fixture(), {"cellHeight": 32, "glow": 1, "_maxLit": 0.5}),
    "tune-glow-small": lambda: ((1280, 720), fixture(), {"glow": 0.7, "glowSize": 0.5, "_maxLit": 0.5}),
    "tune-glow-big": lambda: ((1280, 720), fixture(), {"cellHeight": 32, "glow": 0.7, "glowSize": 1.5, "_maxLit": 0.6}),
    "tune-drops-1": lambda: ((1280, 720), fixture(), {"drops": 1, "trailFloor": 0}),
    "tune-drops-4": lambda: ((1280, 720), fixture(), {"drops": 4, "trailFloor": 0}),
    "tune-trail-short": lambda: ((1280, 720), fixture(), {"trailLength": 0.4, "trailFloor": 0}),
    "tune-trail-quick": lambda: ((1280, 720), fixture(), {"trailCurve": 3, "trailFloor": 0}),
    "tune-trail-bright": lambda: ((1280, 720), fixture(), {"trailCurve": 0.4, "trailFloor": 0}),
    "photo": lambda: (screen_size(), rain.current_wallpaper() or "", {}),
    "photo-glow": lambda: (screen_size(), rain.current_wallpaper() or "", {"glow": 0.6, "_maxLit": 0.5}),
    "photo-lift-none": lambda: (screen_size(), rain.current_wallpaper() or "", {"lift": 0}),
    "photo-lift-most": lambda: (screen_size(), rain.current_wallpaper() or "", {"lift": 0.75}),
    "photo-lift-full": lambda: (screen_size(), rain.current_wallpaper() or "", {"lift": 1}),
    "photo-floor-none": lambda: (screen_size(), rain.current_wallpaper() or "", {"trailFloor": 0}),
    "photo-floor-half": lambda: (screen_size(), rain.current_wallpaper() or "", {"trailFloor": 0.5}),
}

# The settings page as Plasma's dialog would show it: name -> (window size, cfg_ properties).
CONFIG = rain.ROOT / "package/contents/ui/config.qml"
DEFAULTS = {"cfg_CellHeight": 20, "cfg_Speed": 400, "cfg_TrailFloor": 0.1, "cfg_Lift": 0.5, "cfg_Glide": 2,
            "cfg_Drops": 1, "cfg_TrailLength": 1, "cfg_TrailCurve": 1, "cfg_Glow": 0.1, "cfg_GlowSize": 1}
PAGES = {
    "settings": lambda: ((760, 1000), {**DEFAULTS, "cfg_Image": str(fixture())}),
    "settings-green": lambda: ((760, 1000), {**DEFAULTS, "cfg_Image": "", "cfg_Glide": 0, "cfg_CellHeight": 24, "cfg_Glow": 0.6}),
    "settings-narrow": lambda: ((520, 1250), {**DEFAULTS, "cfg_Image": str(fixture())}),
}


def lit_fraction(frame: QImage) -> float:
    """The share of pixels that are clearly not black (in the brightest channel)."""
    pixels = frame.convertToFormat(QImage.Format.Format_RGBX8888)
    data = pixels.constBits().asstring(pixels.sizeInBytes())
    return max(data[c::4].translate(LIT).count(1) for c in range(3)) / (frame.width() * frame.height())


def audit(frame: QImage, size: tuple[int, int], warnings: list[str], max_lit: float = 0.15) -> list[str]:
    faults = [f"Qt warned: {text}" for text in warnings]
    if (frame.width(), frame.height()) != size:
        faults.append(f"frame is {frame.width()}x{frame.height()}, asked for {size[0]}x{size[1]}")
    lit = lit_fraction(frame)
    if lit < 0.003:
        faults.append(f"almost nothing drawn ({lit:.2%} of the pixels lit)")
    if lit > max_lit:  # glyph strokes light at most 10% of a frame, even with every cell lit; whole cells, 21% and up
        faults.append(f"flooded ({lit:.0%} of the pixels lit): the glyph mask is not applied")
    return faults


def render_page(name: str) -> tuple[QImage, list[str]]:
    size, props = PAGES[name]()
    seen = len(rain.messages)
    window = rain.load(CONFIG, *size, props)
    root = window.rootObject()
    preview = root.findChild(QObject, "preview")
    # A hidden window lays its items out only when it is drawn, i.e. when grabbed, and the last
    # pass gives the preview its final width, which starts a new load of the picture at that
    # size. So: draw, wait for the picture, until a draw no longer changes the preview's grid.
    grid = None
    while grid != (grid := (preview.property("columns"), preview.property("rows"))):
        window.grabWindow()
        while preview.property("ready") is False:  # it loads on another thread
            rain.app.processEvents()
    preview.setProperty("tick", TICK)
    frame = window.grabWindow()
    frame.save(str(OUT / f"{name}.png"))
    faults = [f"Qt warned: {text}" for text in rain.messages[seen:]]
    if props.get("cfg_Image") and not preview.property("showsImage"):
        faults.append("the preview shows the green fallback although a picture is set")
    faults += [f"{name} reaches {edge}, outside the {size[0]}x{size[1]} window" for name, edge in outside(root, *size)]
    return frame, faults


def outside(item: QQuickItem, width: int, height: int):
    """Visible items that reach past the window's edges. What a clipping item (a text field
    scrolling a long path) holds inside is its own business and is not looked into."""
    for child in item.childItems():
        if not child.isVisible() or child.width() <= 0 or child.height() <= 0:
            continue
        box = child.mapRectToScene(QRectF(0, 0, child.width(), child.height()))
        if box.right() > width + 0.5 or box.bottom() > height + 0.5 or box.left() < -0.5 or box.top() < -0.5:
            yield child.metaObject().className(), f"{box.right():.0f},{box.bottom():.0f}"
        if not child.clip():
            yield from outside(child, width, height)


def render(name: str) -> tuple[QImage | None, list[str]]:
    if name in PAGES:
        return render_page(name)
    size, image, props = SHOTS[name]()
    if image == "" or (image and not Path(image).exists()):
        return None, []
    max_lit = props.pop("_maxLit", 0.15)  # a glow lights the gaps between glyphs too
    seen = len(rain.messages)
    frame = rain.grab(rain.view(*size, image, **props), TICK)
    frame.save(str(OUT / f"{name}.png"))
    return frame, audit(frame, size, rain.messages[seen:], max_lit)


def sheet(frames: dict[str, QImage], path: Path) -> None:
    """Every frame at 640 px wide, two to a row, with its name."""
    thumbs = {name: f.scaledToWidth(640, Qt.TransformationMode.SmoothTransformation) for name, f in frames.items()}
    row = max(t.height() for t in thumbs.values()) + 28
    page = QImage(2 * 650, row * ((len(thumbs) + 1) // 2), QImage.Format.Format_RGB32)
    page.fill(QColor("#202020"))
    painter = QPainter(page)
    painter.setPen(QColor("white"))
    for i, (name, thumb) in enumerate(thumbs.items()):
        x, y = (i % 2) * 650, (i // 2) * row
        painter.drawText(QRect(x + 4, y, 640, 24), Qt.AlignmentFlag.AlignVCenter, name)
        painter.drawImage(x, y + 24, thumb)
    painter.end()
    page.save(str(path))


def main(pick: str) -> int:
    names = [n for n in [*SHOTS, *PAGES] if (n == pick[1:] if pick.startswith("=") else n.startswith(pick))]
    if not names:
        sys.exit(f"no shot matches {pick!r}; there are: {', '.join(SHOTS)}")
    OUT.mkdir(parents=True, exist_ok=True)
    frames, faulty = {}, 0
    for name in names:
        frame, faults = render(name)
        if frame is None:
            print(f"- {name}: skipped, no image")
            continue
        frames[name] = frame
        faulty += bool(faults)
        print(f"{'✗' if faults else '✓'} {name}  {frame.width()}x{frame.height()}")
        for fault in faults:
            print(f"    {fault}")
    if len(frames) > 1:
        sheet(frames, OUT / (f"sheet-{pick}.png" if pick else "sheet.png"))
    print(f"{len(frames)} shots in {OUT.relative_to(rain.ROOT)}/, {faulty} faulty")
    return faulty


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
