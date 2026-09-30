import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts

Window {
    id: overlay
    objectName: "calibrationOverlay"
    title: "ReedRelay 调音引导"
    width: 560
    height: 304
    color: "transparent"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus
    visible: bridge.calibration.visible
    property var guide: bridge.calibration
    Rectangle {
        anchors.fill: parent; anchors.margins: 1
        color: "#f51a3a46"; radius: 16; border.width: 1; border.color: "#728d94"
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 22; spacing: 8
            RowLayout {
                Label { text: "ReedRelay  /  游戏内调音"; color: "#b8d0cd"; font.pixelSize: 13 }
                Item { Layout.fillWidth: true }
                Label { text: guide.step+" / "+guide.total; color: "#c4d6d7"; font.pixelSize: 13 }
            }
            RowLayout {
                spacing: 15
                Label { text: guide.title; color: "#fbfdf7"; font.bold: true; font.pixelSize: 24 }
                Label { Layout.fillWidth: true; Layout.preferredHeight: 54; text: guide.instruction; color: "#f2c59b"; font.bold: true; font.pixelSize: 23; wrapMode: Text.Wrap; verticalAlignment: Text.AlignVCenter }
            }
            Label { Layout.fillWidth: true; text: guide.hint; color: "#e5eee9"; font.pixelSize: 14; wrapMode: Text.Wrap; Layout.preferredHeight: 40; verticalAlignment: Text.AlignVCenter }
            Label { Layout.fillWidth: true; text: guide.last_note || "每个音稳定确认 3 次，再自动记录"; color: "#abc4c5"; font.pixelSize: 12; elide: Text.ElideRight }
            ProgressBar { Layout.fillWidth: true; value: guide.progress; palette.highlight: "#81b4a3" }
            GridLayout {
                columns: 2; columnSpacing: 18; rowSpacing: 4
                Label { Layout.fillWidth: true; text: guide.hotkeys.toggle+" 暂停/继续"; color: "#cfdfdb"; font.pixelSize: 12; wrapMode: Text.Wrap }
                Label { Layout.fillWidth: true; text: guide.hotkeys.previous+" 重测"; color: "#cfdfdb"; font.pixelSize: 12; wrapMode: Text.Wrap }
                Label { Layout.fillWidth: true; text: guide.hotkeys.next+" 跳过组合"; color: guide.optional ? "#f2c59b" : "#8da8ad"; font.pixelSize: 12; wrapMode: Text.Wrap }
                Label { Layout.fillWidth: true; text: guide.hotkeys.emergency+(guide.active ? " 取消" : " 关闭"); color: "#f2c59b"; font.pixelSize: 12; wrapMode: Text.Wrap }
            }
        }
    }
}
