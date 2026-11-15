import QtQuick
import org.kde.plasma.plasmoid
import org.kde.taskmanager as TaskManager

// What Plasma loads. It hands the settings to MatrixRain, which has no KDE imports so that the
// same file also loads in the preview and the checks (scripts/rain.py), and pauses it while a
// fullscreen window has the focus.
WallpaperItem {
    id: root

    // Paused while the focused window on this screen is fullscreen, or covers the whole screen
    // (a borderless game that does not say it is fullscreen). KWin keeps sending frames to a
    // covered desktop (measured with a fullscreen application: 240 a second throughout), so
    // the rain would otherwise run unseen at full cost.
    property bool covered: false
    function checkCovered() {
        const role = name => tasks.data(tasks.activeTask, TaskManager.AbstractTasksModel[name]);
        const g = role("Geometry"), s = role("ScreenGeometry");
        covered = role("IsFullScreen") === true || (!!g && !!s && g.x <= s.x && g.y <= s.y
            && g.x + g.width >= s.x + s.width && g.y + g.height >= s.y + s.height);
    }
    TaskManager.TasksModel {
        id: tasks
        filterByScreen: true
        screenGeometry: root.Window.window
            ? Qt.rect(root.Window.window.x, root.Window.window.y, root.Window.window.width, root.Window.window.height)
            : Qt.rect(0, 0, 0, 0)
        groupMode: TaskManager.TasksModel.GroupDisabled
        onActiveTaskChanged: root.checkCovered()
        onDataChanged: root.checkCovered()  // a focused window going fullscreen or back
    }
    Component.onCompleted: checkCovered()

    MatrixRain {
        anchors.fill: parent
        running: !root.covered
        image: root.configuration.Image
        cellHeight: root.configuration.CellHeight
        speed: root.configuration.Speed
        trailFloor: root.configuration.TrailFloor
        lift: root.configuration.Lift
        glide: root.configuration.Glide
        logFrameRate: root.configuration.LogFrameRate
    }
}
