"""The README's pictures: a painted sunset, a few seconds of the rain it turns into, and a
real-size piece of the desktop screenshot.

    python3 scripts/readme.py      (needs ffmpeg, for the animation)

Writes docs/images/source.jpg, rain.webp and desktop-detail.png. Run it again when the look
changes: a stale picture misleads. The sunset is painted here so that the moving picture does
not depend on anybody's own wallpaper; docs/images/desktop.png is the author's own screenshot
and is only cut, never made, here.
"""

import shutil
import subprocess
import sys

from PyQt6.QtCore import QPointF, QRect, QRectF
from PyQt6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPolygonF, QRadialGradient

import rain

IMG = rain.ROOT / "docs/images"
TMP = rain.ROOT / ".dev/readme"
WIDTH, HEIGHT = 1280, 480
FPS, SECONDS = 30, 3
# Shown a little bolder than the defaults (0.25 and 0.5) so that a small picture reads.
SETTINGS = {"trailFloor": 0.4, "lift": 0.75}
DETAIL = QRect(1560, 40, 1600, 640)  # of desktop.png: the widgets' lower edge and the rain under them


def gradient(line: QLinearGradient | QRadialGradient, stops: dict[float, str]):
    for at, colour in stops.items():
        line.setColorAt(at, QColor(colour))
    return line


def ridge(heights: list[float], base: float) -> QPolygonF:
    """A mountain range: peaks at these heights (fractions of the picture), down to `base`."""
    step = WIDTH / (len(heights) - 1)
    points = [QPointF(i * step, h * HEIGHT) for i, h in enumerate(heights)]
    return QPolygonF([QPointF(0, base * HEIGHT), *points, QPointF(WIDTH, base * HEIGHT)])


def sunset() -> QImage:
    image = QImage(WIDTH, HEIGHT, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    horizon = 0.7 * HEIGHT
    sky = {0: "#1b2a8a", 0.45: "#7a3bb8", 0.78: "#ff5a8a", 1: "#ffb04a"}
    painter.fillRect(QRectF(0, 0, WIDTH, horizon), gradient(QLinearGradient(0, 0, 0, horizon), sky))
    sun = QPointF(0.62 * WIDTH, 0.6 * HEIGHT)
    glow = gradient(QRadialGradient(sun, 0.45 * HEIGHT), {0: "#fff6c0", 0.3: "#ffd060", 1: "#00ffc04d"})
    painter.fillRect(QRectF(0, 0, WIDTH, horizon), glow)
    water = {0: "#ffb04a", 0.3: "#d0489a", 1: "#1b2a8a"}
    painter.fillRect(QRectF(0, horizon, WIDTH, HEIGHT - horizon), gradient(QLinearGradient(0, horizon, 0, HEIGHT), water))
    painter.setPen(QColor(0, 0, 0, 0))
    painter.setBrush(QColor("#5a3aa8"))
    painter.drawPolygon(ridge([0.6, 0.42, 0.55, 0.38, 0.52, 0.47, 0.62, 0.5, 0.66], 0.7))
    painter.setBrush(QColor("#22225e"))
    painter.drawPolygon(ridge([0.52, 0.62, 0.5, 0.66, 0.6, 0.68, 0.64, 0.58, 0.48], 0.72))
    painter.end()
    return image


def main() -> None:
    if not shutil.which("ffmpeg"):
        sys.exit("readme.py: ffmpeg is not installed (sudo apt install ffmpeg)")
    IMG.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True)
    sunset().save(str(IMG / "source.jpg"), quality=90)
    window = rain.view(WIDTH, HEIGHT, IMG / "source.jpg", **SETTINGS)
    root = window.rootObject()
    rows_per_frame = root.property("speed") / root.property("cellHeight") / FPS
    for frame in range(FPS * SECONDS):
        rain.grab(window, 200 + frame * rows_per_frame).save(str(TMP / f"{frame:03d}.png"))
    encode = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(TMP / "%03d.png")]
    subprocess.run([*encode, "-c:v", "libwebp_anim", "-loop", "0", "-quality", "70", str(IMG / "rain.webp")], check=True)
    if (IMG / "desktop.png").exists():
        QImage(str(IMG / "desktop.png")).copy(DETAIL).save(str(IMG / "desktop-detail.png"))
    for path in sorted(IMG.iterdir()):
        print(f"{path.relative_to(rain.ROOT)}  {path.stat().st_size / 1024:.0f} kB")


if __name__ == "__main__":
    main()
