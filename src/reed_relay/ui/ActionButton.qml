import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool primary: false
    implicitHeight: 42
    implicitWidth: Math.max(82, contentItem.implicitWidth + 30)
    font.pixelSize: 14
    font.bold: primary
    contentItem: Text {
        text: control.text
        font: control.font
        color: !control.enabled ? "#99aaa7" : control.primary ? "#ffffff" : "#24454c"
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        radius: 9
        color: !control.enabled ? "#e6ece7" : control.primary ? (control.pressed ? "#174886" : control.hovered ? "#1d58ae" : "#2362ba") : (control.hovered ? "#e7efea" : "#f4f7f2")
        border.color: control.activeFocus ? "#2362ba" : control.primary ? "transparent" : "#d4e0d9"
        border.width: control.activeFocus ? 2 : 1
    }
}
