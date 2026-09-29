import QtQuick
import QtQuick.Controls

TextField {
    id: control
    implicitHeight: 40
    color: "#17343b"
    font.pixelSize: 14
    selectByMouse: true
    leftPadding: 12
    rightPadding: 10
    background: Rectangle {
        radius: 7
        color: control.enabled ? "#ffffff" : "#edf1ed"
        border.color: control.activeFocus ? "#2362ba" : "#d4e0d9"
        border.width: control.activeFocus ? 2 : 1
    }
}
