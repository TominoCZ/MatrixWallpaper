"""The effect outside Plasma, on the system's Qt (the one plasmashell runs on).

`view()` loads MatrixRain.qml into a window that is never shown and `grab()` renders one tick
of it to an image: that is what the shots and the checks are built on. Run as a script, it is
the live preview: the rain in a window, coloured from the current wallpaper image.
"""

import re
import sys
from pathlib import Path

from PyQt6.QtCore import QRect, Qt, QUrl, qInstallMessageHandler
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PyQt6.QtQuick import QQuickView

ROOT = Path(__file__).resolve().parent.parent
QML = ROOT / "package/contents/ui/MatrixRain.qml"
BANDS = [QColor("red"), QColor("lime"), QColor("blue"), QColor("white")]

app = QGuiApplication(sys.argv)
messages: list[str] = []  # everything Qt warned about, e.g. a shader that did not load


def _on_message(_kind, _context, text: str) -> None:
    messages.append(text)
    print(text, file=sys.stderr)


qInstallMessageHandler(_on_message)


def current_wallpaper() -> str | None:
    """The image Plasma's image wallpaper shows on the first desktop that has one."""
    config = Path.home() / ".config/plasma-org.kde.plasma.desktop-appletsrc"
    if not config.exists():
        return None
    group = r"^\[Containments\]\[\d+\]\[Wallpaper\]\[org\.kde\.image\]\[General\]\n"
    found = re.search(group + r"(?:(?!\[).*\n)*?Image=(.+)$", config.read_text(), re.M)
    return found.group(1).removeprefix("file://") if found else None


def bands(path: Path, size: tuple[int, int], vertical: bool = True, shade: int = 0) -> Path:
    """A fixture image: four equal bands of red, green, blue and white, darkened by `shade` (0 to 255)."""
    image = QImage(*size, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    for i, colour in enumerate(BANDS):
        w, h = size[0] // 4, size[1] // 4
        painter.fillRect(QRect(i * w, 0, w, size[1]) if vertical else QRect(0, i * h, size[0], h), colour)
    painter.fillRect(image.rect(), QColor(0, 0, 0, shade))
    painter.end()
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(path))
    return path


def view(width: int, height: int, image: str | Path | None = None, **props) -> QQuickView:
    """MatrixRain at this size, standing still (`running` off) unless asked otherwise."""
    window = QQuickView()
    window.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    window.resize(width, height)  # before the source: a hidden window gets no resize event
    props.setdefault("running", False)
    if image:
        props["image"] = QUrl.fromLocalFile(str(image))
    window.setInitialProperties(props)
    window.setSource(QUrl.fromLocalFile(str(QML)))
    if window.status() != QQuickView.Status.Ready:
        raise SystemExit("\n".join(error.toString() for error in window.errors()))
    while not window.rootObject().property("ready"):  # the image is decoded on another thread
        app.processEvents()
    return window


def grab(window: QQuickView, tick: int) -> QImage:
    window.rootObject().setProperty("tick", tick)
    return window.grabWindow()


def mean_rgb(image: QImage, rect: QRect) -> tuple[float, float, float]:
    """The average colour of a part of a frame, 0 to 255 per channel."""
    part = image.copy(rect).convertToFormat(QImage.Format.Format_RGBX8888)
    data = part.constBits().asstring(part.sizeInBytes())
    return tuple(sum(data[channel::4]) / (part.width() * part.height()) for channel in range(3))


if __name__ == "__main__":
    preview = view(1280, 720, current_wallpaper(), running=True)
    preview.setTitle("MatrixWallpaper preview")
    preview.setFlag(Qt.WindowType.Window)
    preview.show()
    sys.exit(app.exec())
