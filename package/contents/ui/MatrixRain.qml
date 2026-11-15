import QtQuick

// The whole effect: one quad over the screen and one fragment shader (../shaders/rain.frag).
// Nothing here runs per frame except the clock; every pixel is worked out on the GPU
// from (cell, tick), so there is no particle state to keep on the CPU.
Item {
    id: root

    property string image                   // a file path or a URL; empty: classic green
    property int cellHeight: 20
    property real speed: 400                // pixels per second for the fastest drops; the slowest do a third
    property real trailFloor: 0.1          // 0: trails fade to black; above: every glyph stays this bright
    // The glyphs that may be falling heads first (katakana and the digits 2 1 7 4), in an order that
    // keeps look-alikes at places of the same parity (measured at 16 to 30 px: ｦｳｵｻｿﾂﾃﾅﾎﾗﾘﾜ, ｴｺﾆﾕ,
    // ｱｽﾇ, ｾﾔ, 27): neighbouring rows draw from places of different parity, so a falling head never
    // morphs into a glyph that looks like the one it was. No "|": in this font it reaches past the
    // cell and was cut off.
    property string glyphs: "ｦｴｳｺｵﾆｻﾕｿｱﾂｽﾃﾇﾅｾﾎﾔﾗｶﾘｷﾜｹｼﾀﾈﾊﾋﾏﾐﾑﾒﾓ2174035689:.=*+-<>"
    property string fontFamily: "monospace"
    property color fallback: "#00ff41"
    property real lift: 0.5                 // 0: the image's own brightness; 1: full brightness in each cell's hue
    property real glide: 2                  // motion: 0 steps; 1 smooth light on the grid; 2 the head falls as its own glyph
    property int drops: 1                   // drops per column, 1 to 4
    property real trailLength: 1            // trail lengths scaled by this
    property real trailCurve: 1             // 1: trails fade evenly; more: quickly after the head
    property real glow: 0.1                   // halo around each head, 0 for none
    property real glowSize: 1             // its radius in glyph heights (at most what two columns cover)
    property real headWidth: 0.5            // motion 1: width of the head's highlight in rows (not a setting)
    property real headFade: 0               // motion 2: 0 the head's character crossfades evenly; up to 0.5, quicker
    property bool logFrameRate: false       // write the measured frame rate to the log every 2 s
    property string logName: "MatrixWallpaper"  // how its log lines start; ./run.sh perf reads "MatrixWallpaper:"
    property bool running: true
    property real tick: 0                   // the rain's clock, in rows fallen by the fastest drops
    property real frames: 0                 // frames shown since the start, for measuring the frame rate

    readonly property int cellWidth: Math.round(cellHeight * 0.6)
    // The nearest whole number of cells, spread over exactly the screen: no cell is cut at an
    // edge. A cell is then up to half a pixel off its nominal size in total across the screen.
    readonly property int columns: Math.max(1, Math.round(width / cellWidth))
    readonly property int rows: Math.max(1, Math.round(height / cellHeight))
    // Never a falling head: signs are too short (the head looked as if it vanished), and these
    // digits look alike (0 9, 3 8, 5 6), so a head morphing between them looked frozen.
    property string notHeads: "035689:.=*+-<>"
    // Glyphs that may be heads first, so the shader knows the others by their place (headCount and on).
    readonly property var glyphList: Array.from(glyphs).filter(g => !notHeads.includes(g))
                                         .concat(Array.from(glyphs).filter(g => notHeads.includes(g)))
    readonly property int headCount: Array.from(glyphs).filter(g => !notHeads.includes(g)).length
    readonly property bool showsImage: colours.status === Image.Ready  // false: the green fallback
    // False until the picture at the current size is decoded (or failed) and handed over; the
    // checks wait for it before grabbing. Not "status is not Loading": right after the size is
    // known the source is set but its status has not yet moved from Null.
    readonly property bool ready: width > 0 && (image === ""
        || (colours.status === Image.Ready || colours.status === Image.Error)
           && colours.sourceSize.width === decoding.sourceSize.width && colours.sourceSize.height === decoding.sourceSize.height)

    // PreserveAspectCrop is done in the shader. `shown` is the part of the image this screen
    // shows: all of one axis, the middle of the other.
    readonly property real stretch: colours.status === Image.Ready
        ? (width / height) / (colours.implicitWidth / colours.implicitHeight) : 1
    readonly property size shown: stretch > 1 ? Qt.size(1, 1 / stretch) : Qt.size(stretch, 1)

    // The clock: advanced each time a frame has been shown. Changing `tick` makes the scene
    // dirty, so Qt draws again at the next vsync, and that frame advances it again; when the
    // window is not being shown no frame comes and the rain stands still at no cost.
    // Not a FrameAnimation: Plasma draws on its GUI thread (Qt's basic render loop), where
    // animations tick 62.5 times a second whatever the display does (measured; a 240 Hz
    // screen got a 60 fps rain).
    property real shownAt: 0                // when the last frame was shown, ms
    property real frameTime: 4              // smoothed ms between frames: Date.now() only counts whole ms
    Connections {
        target: root.running ? root.Window.window : null
        function onFrameSwapped() {
            const now = Date.now(), gap = now - root.shownAt;
            if (gap < 100 && gap > 1.5 * root.frameTime)
                root.lateFrames += 1;
            root.worstGap = Math.max(root.worstGap, gap < 100 ? gap : 0);
            // A long gap is a pause (window covered, machine asleep), not a slow frame; a
            // negative one is the system clock being set back, not time running backwards.
            if (gap > 0 && gap < 100)
                root.frameTime += (gap - root.frameTime) * 0.05;
            root.shownAt = now;
            root.frames += 1;
            // ponytail: the shader takes the tick in two parts that stay exact while the high
            // part fits a float's 24 bits, i.e. below 2^31 rows: one visible jump after that
            // (2.3 years at the default speed and cell size).
            root.tick = (root.tick + root.frameTime * root.speed / root.cellHeight / 1000) % 2147483648;
        }
    }
    // The only way to know the frame rate inside plasmashell: `./run.sh perf` switches this on
    // and reads the log. A late frame came more than one and a half frame times after the last.
    property int lateFrames: 0
    property int worstGap: 0
    property int loggedAt: 0
    onLogFrameRateChanged: { loggedAt = frames; lateFrames = 0; worstGap = 0; }
    Timer {
        interval: 2000
        repeat: true
        running: root.logFrameRate
        onTriggered: {
            console.warn(root.logName + ":", (root.frames - root.loggedAt) / 2, "frames/s,", root.lateFrames / 2,
                         "late/s, worst gap", root.worstGap, "ms, frame time", root.frameTime.toFixed(2), "ms,",
                         root.Window.window ? "in a window" : "no window", root.running ? "" : "(stopped)");
            root.loggedAt = root.frames;
            root.lateFrames = 0;
            root.worstGap = 0;
        }
    }

    // A path as Plasma's image wallpaper stores it; "#", "?" or "%" in a file name would otherwise
    // be read as parts of a URL.
    function toUrl(path) {
        return path.startsWith("/") ? "file://" + path.split("/").map(encodeURIComponent).join("/") : path;
    }

    // The chain stops when the tick stops changing (clock off, or speed 0), and then nothing is
    // dirty to start it again: ask for one frame.
    function kick() { if (running && Window.window) Window.window.update(); }
    onRunningChanged: kick()
    onSpeedChanged: kick()

    // The picture, decoded on Qt's image thread down to about one texel per cell: the shader's
    // single lookup per pixel then already is that cell's average colour. A new picture or size
    // (another glyph size, another screen) is decoded here first...
    Image {
        id: decoding
        visible: false
        asynchronous: true
        fillMode: Image.PreserveAspectCrop  // tells the loader how to read sourceSize
        sourceSize: Qt.size(root.columns, root.rows)
        source: root.width > 0 ? root.toUrl(root.image) : ""  // not before the size is known: that would decode it in full
        onStatusChanged: if (status !== Image.Loading) {
            colours.sourceSize = sourceSize;
            colours.source = source;
        }
    }
    // ...and handed to the one the shader draws from only once it is done, which then takes it
    // straight from Qt's image cache. Reloading in place emptied the texture for a few frames on
    // every change: the rain flashed green each time the glyph size was stepped.
    Image {
        id: colours
        visible: false
        fillMode: Image.PreserveAspectCrop
    }

    // The glyphs, drawn once into one row of cells and kept as a texture.
    Row {
        id: atlas
        visible: false
        layer.enabled: true
        // Nearest texel: glyphs stay sharp although the grid is stretched by a fraction of a
        // pixel per cell (a pixel column is doubled or dropped every few dozen cells).
        layer.smooth: false
        Repeater {
            model: root.glyphList
            Text {
                width: root.cellWidth
                height: root.cellHeight
                clip: true
                text: modelData
                color: "white"
                font.family: root.fontFamily
                font.pixelSize: Math.round(root.cellHeight * 0.8)
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }
    }

    // The clock in two parts that stay exact in a 32-bit float (see elapsed() in the shaders).
    readonly property real tickHigh: Math.floor(tick / 128)
    readonly property real tickLow: tick - tickHigh * 128

    // Every drop's place, once per frame (../shaders/drops.frag): one texel per column (plus two
    // either side) and drop, read by the rain shader below.
    ShaderEffect {
        id: dropTable
        width: root.columns + 4
        height: 4
        visible: false
        layer.enabled: true
        layer.smooth: false
        layer.format: ShaderEffectSource.RGBA32F
        layer.textureSize: Qt.size(width, height)
        readonly property real tickHigh: root.tickHigh
        readonly property real tickLow: root.tickLow
        readonly property real trailLength: root.trailLength
        readonly property size grid: Qt.size(root.columns, root.rows)
        fragmentShader: Qt.resolvedUrl("../shaders/drops.frag.qsb")
    }

    ShaderEffect {
        anchors.fill: parent
        blending: false                     // opaque: nothing behind it has to be drawn

        readonly property real tickHigh: root.tickHigh
        readonly property real tickLow: root.tickLow
        readonly property real glyphCount: root.glyphList.length
        readonly property real headCount: root.headCount
        readonly property real trailFloor: root.trailFloor
        readonly property real lift: root.lift
        readonly property real glide: root.glide
        readonly property real dropCount: Math.max(1, Math.min(4, root.drops))
        readonly property Item dropTex: dropTable
        readonly property real trailCurve: root.trailCurve
        readonly property real glow: root.glow
        readonly property real glowSize: Math.max(0.05, root.glowSize)
        readonly property real cellAspect: (root.width / root.columns) / (root.height / root.rows)
        readonly property real headWidth: root.headWidth
        readonly property real cellPixels: root.height / root.rows
        readonly property real atlasRows: root.cellHeight
        readonly property real headFade: root.headFade
        readonly property real hasImage: root.showsImage ? 1 : 0
        readonly property size grid: Qt.size(root.columns, root.rows)
        // cell position as a fraction of the grid -> image uv: xy scale, zw offset
        readonly property vector4d crop: Qt.vector4d(
            root.shown.width, root.shown.height, (1 - root.shown.width) / 2, (1 - root.shown.height) / 2)
        readonly property color fallback: root.fallback
        readonly property Item imageTex: colours
        readonly property Item atlasTex: atlas

        fragmentShader: Qt.resolvedUrl("../shaders/rain.frag.qsb")
    }
}
