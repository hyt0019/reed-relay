import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id:page
    property var transport:bridge.auditionController
    function clock(ms) { let s=Math.floor(ms/1000);return Math.floor(s/60).toString().padStart(2,"0")+":"+(s%60).toString().padStart(2,"0") }
    clip:true;contentWidth:availableWidth
    ColumnLayout {
        width:page.availableWidth;spacing:20
        RowLayout {
            Layout.fillWidth:true;Layout.margins:26;Layout.bottomMargin:0
            ColumnLayout {
                spacing:5
                Label { text:"先听见，再演奏";font.pixelSize:27;font.bold:true;color:"#17343b" }
                Label { text:"用口琴音色检查旋律、节奏与长音。";font.pixelSize:13;color:"#647e82" }
            }
            Item { Layout.fillWidth:true }
            ActionButton { text:"载入练习曲";enabled:!bridge.busy;onClicked:bridge.loadDemo() }
            ActionButton { text:"打开曲谱 / MIDI";enabled:!bridge.busy;onClicked:bridge.openProject() }
        }
        Rectangle {
            Layout.fillWidth:true;Layout.leftMargin:26;Layout.rightMargin:26;Layout.preferredHeight:190;radius:16;color:"#173c48"
            ColumnLayout {
                anchors.fill:parent;anchors.margins:24;spacing:12
                RowLayout {
                    Label { text:page.transport.status;color:"#c1d7d5";font.pixelSize:13 }
                    Item { Layout.fillWidth:true }
                    Label { text:page.transport.mode==="clean"?"旋律校对 · 保持原调":"游戏效果 · 含推算音色";color:"#e9bf97";font.pixelSize:12 }
                }
                Label { Layout.fillWidth:true;text:bridge.title;color:"#fcfdf9";font.pixelSize:29;font.bold:true;elide:Text.ElideRight }
                Slider { id:seek;Layout.fillWidth:true;from:0;to:Math.max(1,bridge.duration);value:page.transport.position;enabled:!page.transport.busy && bridge.notes.length>0;onMoved:page.transport.seek(value) }
                RowLayout {
                    Label { text:page.clock(page.transport.position);color:"#c1d7d5";font.pixelSize:13 }
                    Item { Layout.fillWidth:true }
                    Label { text:page.clock(bridge.duration)+"    "+bridge.notes.length+" 个音符";color:"#c1d7d5";font.pixelSize:13 }
                }
            }
        }
        RowLayout {
            Layout.fillWidth:true;Layout.leftMargin:26;Layout.rightMargin:26;spacing:12
            ActionButton { Layout.preferredWidth:176;implicitHeight:48;primary:true;enabled:!bridge.busy && bridge.notes.length>0;text:page.transport.busy?"取消生成":page.transport.playing?"暂停试听":"播放 / 继续";onClicked:bridge.auditionScore() }
            ActionButton { text:"停止";onClicked:bridge.stopAudio() }
            ComboBox { model:["旋律校对","游戏效果"];implicitWidth:146;currentIndex:page.transport.mode==="game"?1:0;onActivated:page.transport.setSound(page.transport.speed,currentIndex===0?"clean":"game") }
            Label { text:"速度 %";font.pixelSize:12;color:"#647e82" }
            SpinBox { from:25;to:200;stepSize:5;value:Math.round(page.transport.speed*100);implicitWidth:115;onValueModified:page.transport.setSound(value/100,page.transport.mode) }
            Item { Layout.fillWidth:true }
            Label { text:"音量";font.pixelSize:12;color:"#647e82" }
            Slider { Layout.preferredWidth:140;from:0;to:1;value:page.transport.volume;onMoved:page.transport.setVolume(value) }
        }
        ProgressBar { Layout.fillWidth:true;Layout.leftMargin:26;Layout.rightMargin:26;visible:page.transport.busy;value:page.transport.fraction }
        Panel {
            Layout.fillWidth:true;Layout.leftMargin:26;Layout.rightMargin:26
            ColumnLayout {
                anchors.fill:parent;spacing:13
                RowLayout {
                    Label { text:"旋律时间轴";font.pixelSize:18;font.bold:true;color:"#17343b" }
                    Item { Layout.fillWidth:true }
                    Label { text:"点击音符可选中片段";font.pixelSize:12;color:"#647e82" }
                    ActionButton { text:"重提主旋律";enabled:!bridge.busy && bridge.notes.length>0;onClicked:bridge.changeReduction(true) }
                    ActionButton { text:"循环选中音符";enabled:bridge.selectedNote>=0;onClicked:bridge.auditionSelected() }
                }
                MelodyTools { Layout.fillWidth:true }
                Item {
                    Layout.fillWidth:true;Layout.preferredHeight:145
                    PianoRoll { id:roll;anchors.fill:parent;notes:bridge.notes;selected:bridge.selectedNote;spanMs:12000;startMs:Math.floor(page.transport.position/12000)*12000;onPicked:function(index){bridge.selectNote(index)} }
                    Rectangle { x:44+((page.transport.position-roll.startMs)/roll.spanMs)*(parent.width-44);y:20;width:2;height:parent.height-20;color:"#d98b60" }
                }
                RowLayout {
                    CheckBox { text:"循环片段";checked:page.transport.looping;onToggled:page.transport.setLoop(checked,Number(loopStart.text)*1000,Number(loopEnd.text)*1000);font.pixelSize:13 }
                    Label { text:"起点 / 秒";font.pixelSize:12;color:"#647e82" }
                    Field { id:loopStart;Layout.preferredWidth:95;text:(page.transport.rangeStart/1000).toFixed(2);validator:DoubleValidator { bottom:0 } onEditingFinished:page.transport.setLoop(page.transport.looping,Number(text)*1000,Number(loopEnd.text)*1000) }
                    Label { text:"终点 / 秒";font.pixelSize:12;color:"#647e82" }
                    Field { id:loopEnd;Layout.preferredWidth:95;text:(page.transport.rangeEnd/1000).toFixed(2);validator:DoubleValidator { bottom:0 } onEditingFinished:page.transport.setLoop(page.transport.looping,Number(loopStart.text)*1000,Number(text)*1000) }
                    Item { Layout.fillWidth:true }
                    ActionButton { text:"恢复全曲";onClicked:{bridge.selectNote(-1);page.transport.setLoop(false,0,bridge.duration);page.transport.seek(0)} }
                }
            }
        }
        Label { Layout.fillWidth:true;Layout.leftMargin:29;Layout.rightMargin:29;wrapMode:Text.Wrap;text:page.transport.mode==="clean"?"旋律校对使用稳定音准和口琴音色，适合检查转谱结果；调整速度保持音高。":"游戏效果应用当前演奏映射和长音策略，模拟起音与持续发声变化。未录音符采用推算，最终效果以游戏实际发声为准。";font.pixelSize:13;color:"#647e82" }
        Item { height:15 }
    }
}
