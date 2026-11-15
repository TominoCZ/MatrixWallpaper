import QtQuick
import org.kde.plasma.plasmoid

// What Plasma loads. It only hands the settings to MatrixRain, which has no KDE imports so
// that the same file also loads in the preview and the checks (scripts/rain.py).
WallpaperItem {
    id: root

    // The setting holds a path as Plasma's image wallpaper stores it; "#", "?" or "%" in a
    // file name would otherwise be read as parts of a URL.
    function toUrl(path) {
        return path.startsWith("/") ? "file://" + path.split("/").map(encodeURIComponent).join("/") : path;
    }

    MatrixRain {
        anchors.fill: parent
        image: root.toUrl(root.configuration.Image)
        cellHeight: root.configuration.CellHeight
        speed: root.configuration.Speed
        trailFloor: root.configuration.TrailFloor
        lift: root.configuration.Lift
        glide: root.configuration.Glide
        logFrameRate: root.configuration.LogFrameRate
    }
}
