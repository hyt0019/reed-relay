import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id:selection
    spacing:6
    function name(pitch) { return ["C","C♯","D","D♯","E","F","F♯","G","G♯","A","A♯","B"][pitch%12]+(Math.floor(pitch/12)-1) }
    RowLayout {
        Layout.fillWidth:true;spacing:10
        Label { text:"旋律音域 / MIDI";font.pixelSize:12;color:"#43636a" }
        SpinBox { id:lowest;objectName:"melodyMinimum";from:0;to:127;value:bridge.melodyDefaults.minimum;editable:true;implicitWidth:112;font.pixelSize:13;enabled:!bridge.busy;onValueModified:bridge.configureMelody(value,Math.max(value,highest.value)) }
        Label { text:"至";font.pixelSize:12;color:"#647e82" }
        SpinBox { id:highest;objectName:"melodyMaximum";from:0;to:127;value:bridge.melodyDefaults.maximum;editable:true;implicitWidth:112;font.pixelSize:13;enabled:!bridge.busy;onValueModified:bridge.configureMelody(Math.min(value,lowest.value),value) }
        Label { text:lowest.value===0 && highest.value===127?"自动判断音区":selection.name(lowest.value)+" – "+selection.name(highest.value);font.pixelSize:12;color:"#2362ba" }
        Item { Layout.fillWidth:true }
        ActionButton { text:"不限音域";enabled:!bridge.busy;onClicked:bridge.configureMelody(0,127) }
        ActionButton { objectName:"melodyExtract";text:"重新提取主旋律";enabled:!bridge.busy && bridge.notes.length>0;onClicked:bridge.changeReduction(true) }
    }
    Label { Layout.fillWidth:true;wrapMode:Text.Wrap;text:"从完整候选选择旋律；音域只筛选，不移调。选错低音时可提高最低音（如 C4 = 60）；可撤销。";font.pixelSize:12;color:"#71878a" }
}
