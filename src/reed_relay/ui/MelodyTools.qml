import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id:tools
    spacing:8
    function update() { bridge.configureRepair(shortest.value,gap.value,merge.checked) }
    RowLayout {
        Layout.fillWidth:true;spacing:10
        Label { text:"碎音阈值 / ms";font.pixelSize:12;color:"#43636a" }
        SpinBox { id:shortest;objectName:"repairMinimum";from:0;to:500;stepSize:10;value:bridge.repairDefaults.minimum;implicitWidth:120;Layout.minimumWidth:120;font.pixelSize:13;enabled:!bridge.busy;onValueModified:tools.update() }
        Label { text:"衔接间隙 / ms";font.pixelSize:12;color:"#43636a" }
        SpinBox { id:gap;objectName:"repairGap";from:0;to:250;stepSize:10;value:bridge.repairDefaults.gap;implicitWidth:120;Layout.minimumWidth:120;font.pixelSize:13;enabled:!bridge.busy;onValueModified:tools.update() }
        CheckBox { id:merge;text:"合并相邻同音";checked:bridge.repairDefaults.merge;font.pixelSize:12;enabled:!bridge.busy;onToggled:tools.update() }
        Item { Layout.fillWidth:true }
        ActionButton { objectName:"repairApply";text:"连贯修整";primary:true;enabled:!bridge.busy && bridge.notes.length>0;onClicked:bridge.repairCurrent() }
        ActionButton { objectName:"repairUndo";text:"撤销";enabled:!bridge.busy && bridge.canUndo;onClicked:bridge.undo() }
        ActionButton { text:"导出曲谱";enabled:!bridge.busy && bridge.notes.length>0;onClicked:bridge.exportScore("json") }
    }
    Label { Layout.fillWidth:true;wrapMode:Text.Wrap;text:"删除低于阈值的碎音，连接短间隙；0 ms 保留快速音符。多声部先提取主旋律，较长休止保留；修整可撤销。";font.pixelSize:12;color:"#71878a" }
}
