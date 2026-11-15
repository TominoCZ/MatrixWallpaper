import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Dialogs
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// The wallpaper's page in Plasma's desktop settings. Plasma gives it a cfg_<Key> for each
// setting in ../config/main.xml it finds here, and saves them on Apply. LogFrameRate has no
// control (it is for ./run.sh perf); here it makes the preview log its frame rate too.
Kirigami.FormLayout {
    id: page
    // Lines the labels up with the rest of the dialog; only Plasma's dialog provides it.
    twinFormLayouts: typeof parentLayout === "undefined" ? [] : parentLayout

    // Plasma hands every wallpaper page these two; unused here, declared so it does not log a warning.
    property var configDialog
    property var wallpaperConfiguration

    property string cfg_Image
    property alias cfg_CellHeight: cellHeight.value
    property alias cfg_Speed: speed.value
    property alias cfg_TrailFloor: trailFloor.value
    property alias cfg_Lift: lift.value
    property real cfg_Glide
    property bool cfg_LogFrameRate
    property alias cfg_Drops: drops.value
    property alias cfg_TrailLength: trailLength.value
    property real cfg_TrailCurve: 1
    property alias cfg_Glow: glow.value
    property alias cfg_GlowSize: glowSize.value

    component Hint: QQC2.Label {
        Layout.maximumWidth: Kirigami.Units.gridUnit * 24
        wrapMode: Text.Wrap
        font: Kirigami.Theme.smallFont
        opacity: 0.75
    }

    // The rain with this page's settings, before they are applied. Glyphs and speed are as on
    // the desktop; the whole picture is fitted into the frame.
    Rectangle {
        Kirigami.FormData.label: "Preview:"
        // As wide as the form allows, up to 30 grid units, and the shape of the screen.
        Layout.fillWidth: true
        Layout.preferredWidth: Kirigami.Units.gridUnit * 30
        Layout.maximumWidth: Kirigami.Units.gridUnit * 30
        implicitHeight: Math.max(Kirigami.Units.gridUnit * 4, Math.round(width * Screen.height / Screen.width))
        color: "black"
        border.color: Kirigami.Theme.disabledTextColor

        MatrixRain {
            id: preview
            objectName: "preview"
            anchors.fill: parent
            anchors.margins: 1
            image: page.cfg_Image
            cellHeight: page.cfg_CellHeight
            speed: page.cfg_Speed
            trailFloor: page.cfg_TrailFloor
            lift: page.cfg_Lift
            glide: page.cfg_Glide
            drops: page.cfg_Drops
            trailLength: page.cfg_TrailLength
            trailCurve: page.cfg_TrailCurve
            glow: page.cfg_Glow
            glowSize: page.cfg_GlowSize
            logFrameRate: page.cfg_LogFrameRate
            logName: "MatrixWallpaper preview"
        }
    }

    RowLayout {
        Kirigami.FormData.label: "Picture:"
        QQC2.TextField {
            Layout.preferredWidth: Kirigami.Units.gridUnit * 20
            text: page.cfg_Image
            placeholderText: "None: classic green"
            onEditingFinished: page.cfg_Image = text.trim()
        }
        QQC2.Button {
            text: "Choose…"
            icon.name: "document-open"
            onClicked: picker.open()
        }
    }
    Hint { text: "The rain takes its colours from this picture. Use an image file, not a folder." }

    FileDialog {
        id: picker
        title: "Choose the picture the rain takes its colours from"
        nameFilters: ["Images (*.jpg *.jpeg *.png *.webp *.avif *.jxl *.bmp *.gif *.tif *.tiff)", "All files (*)"]
        currentFolder: page.cfg_Image.startsWith("/")
            ? preview.toUrl(page.cfg_Image.substring(0, page.cfg_Image.lastIndexOf("/") + 1)) : ""
        onAccepted: page.cfg_Image = decodeURIComponent(selectedFile.toString().replace(/^file:\/\//, ""))
    }

    RowLayout {
        Kirigami.FormData.label: "Glyph size:"
        QQC2.SpinBox {
            id: cellHeight
            from: 4
            to: 64
        }
        QQC2.Label { text: "px high" }
    }
    Hint { text: "Smaller glyphs give a finer picture; below about 14 they get thin and dim." }

    RowLayout {
        Kirigami.FormData.label: "Speed:"
        QQC2.SpinBox {
            id: speed
            from: 0
            to: 3000
            stepSize: 20
        }
        QQC2.Label { text: "px per second" }
    }
    Hint { text: "For the fastest drops; the slowest fall at a third of it. 0 stops the rain." }

    RowLayout {
        Kirigami.FormData.label: "Picture between drops:"
        QQC2.Slider {
            id: trailFloor
            Layout.preferredWidth: Kirigami.Units.gridUnit * 12
            from: 0
            to: 1
            stepSize: 0.05
        }
        QQC2.Label { text: Math.round(trailFloor.value * 100) + " %" }
    }
    Hint { text: "How bright glyphs stay where no drop is. 0 lets trails fade to black, as in the film." }

    RowLayout {
        Kirigami.FormData.label: "Brighten dark pictures:"
        QQC2.Slider {
            id: lift
            Layout.preferredWidth: Kirigami.Units.gridUnit * 12
            from: 0
            to: 1
            stepSize: 0.05
        }
        QQC2.Label { text: Math.round(lift.value * 100) + " %" }
    }
    Hint { text: "Dark parts gain the most and keep their colour. 100 % gives every glyph full brightness." }

    QQC2.CheckBox {
        Kirigami.FormData.label: "Motion:"
        text: "Light slides down through the glyphs"
        checked: page.cfg_Glide > 0.5
        onToggled: page.cfg_Glide = checked ? 1 : 0
    }
    Hint { text: "Off: each glyph lights up as a whole, one cell at a time." }

    Kirigami.Separator {
        Kirigami.FormData.isSection: true
        Kirigami.FormData.label: "Tuning"
    }

    RowLayout {
        Kirigami.FormData.label: "Head glow:"
        QQC2.Slider {
            id: glow
            Layout.preferredWidth: Kirigami.Units.gridUnit * 12
            from: 0
            to: 1
            stepSize: 0.05
        }
        QQC2.Label { text: glow.value > 0 ? Math.round(glow.value * 100) + " %" : "off" }
    }
    RowLayout {
        Kirigami.FormData.label: "Glow size:"
        enabled: glow.value > 0
        QQC2.Slider {
            id: glowSize
            Layout.preferredWidth: Kirigami.Units.gridUnit * 12
            from: 0.2
            to: 1.5
            stepSize: 0.05
        }
        QQC2.Label { text: glowSize.value.toFixed(2) + " glyphs" }
    }
    Hint { text: "A soft light around the head of each drop, in its colour, spilling into the gaps between glyphs." }

    RowLayout {
        Kirigami.FormData.label: "Drops per column:"
        QQC2.SpinBox {
            id: drops
            from: 1
            to: 4
        }
    }

    RowLayout {
        Kirigami.FormData.label: "Trail length:"
        QQC2.Slider {
            id: trailLength
            Layout.preferredWidth: Kirigami.Units.gridUnit * 12
            from: 0.25
            to: 2
            stepSize: 0.05
        }
        QQC2.Label { text: "× " + trailLength.value.toFixed(2) }
    }

    RowLayout {
        Kirigami.FormData.label: "Trail fade:"
        QQC2.Label { text: "stays bright" }
        // Logarithmic, so that "even" (1) is in the middle: 0.25 at the left end, 4 at the right.
        QQC2.Slider {
            Layout.preferredWidth: Kirigami.Units.gridUnit * 10
            from: -2
            to: 2
            stepSize: 0.1
            value: Math.log2(page.cfg_TrailCurve)
            onMoved: page.cfg_TrailCurve = Math.round(Math.pow(2, value) * 100) / 100
        }
        QQC2.Label { text: "fades quickly" }
    }
    Hint { text: "In the middle (1) a trail fades evenly from the head to its end." }
}
