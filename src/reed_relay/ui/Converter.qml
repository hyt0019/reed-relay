import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: page
    signal requestAudition()
    clip: true
    contentWidth: availableWidth
    property var selectedData: bridge.selectedNote>=0 && bridge.selectedNote<bridge.notes.length ? bridge.notes[bridge.selectedNote] : null
    function select(index) { bridge.selectNote(index); if(index>=0) viewStart.value=Math.max(0,bridge.notes[index].start_ms-1000) }
    component Muted: Label { color: "#6b8387"; font.pixelSize: 12 }
    DropArea { anchors.fill: parent; onDropped: function(drop) { if(drop.hasUrls) bridge.setAudioFiles(JSON.stringify(drop.urls)) } }
    ColumnLayout {
        width: page.availableWidth; spacing: 17
        RowLayout {
            Layout.fillWidth: true; Layout.leftMargin: 26; Layout.rightMargin: 26; Layout.topMargin: 24
            ColumnLayout {
                spacing: 5
                Label { text: "把声音，写成可演奏的谱"; color: "#17343b"; font.pixelSize: 27; font.bold: true }
                Muted { text: "保留原调。还原歌声旋律时，请使用含人声的原曲或 MIDI。" }
            }
            Item { Layout.fillWidth: true }
            ActionButton { text:"导入曲谱";enabled:!bridge.busy;onClicked:bridge.openScores() }
            ActionButton { text: "恢复自动保存"; enabled: !bridge.busy; onClicked: bridge.recoverProject() }
            ActionButton { text: "关联原音"; enabled: !bridge.busy; onClicked: bridge.relinkAudio() }
            ActionButton { text: "打开工程 / MIDI"; enabled: !bridge.busy; onClicked: bridge.openProject() }
        }
        Panel {
            Layout.fillWidth: true; Layout.leftMargin: 26; Layout.rightMargin: 26
            ColumnLayout {
                anchors.fill: parent; spacing: 13
                RowLayout {
                    spacing: 15
                    Rectangle { width: 48; height: 48; radius: 12; color: "#2362ba"; Label { anchors.centerIn: parent; text:"音"; color:"white"; font.pixelSize:22 } }
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 5
                        Label { Layout.fillWidth: true; text: bridge.audioPath ? bridge.audioPath.split(/[/\\]/).pop() : "拖入音频，或选择文件"; color: "#17343b"; font.pixelSize: 18; font.bold: true; elide: Text.ElideMiddle }
                        Muted { text: "MP3 / WAV / FLAC / OGG / M4A"+(bridge.queuedCount ? "    已选择 "+bridge.queuedCount+" 首" : "") }
                    }
                    ActionButton { text: "选择音频"; enabled: !bridge.busy; onClicked: bridge.openAudio() }
                    ComboBox { id: mode; model: ["主旋律优先", "完整音符候选"]; enabled: !bridge.busy; implicitWidth: 155 }
                    ActionButton { text: bridge.busy ? "取消处理" : "开始转谱"; primary: true; onClicked: bridge.busy ? bridge.cancelConversion() : bridge.convert(mode.currentIndex===0) }
                }
                ProgressBar { Layout.fillWidth: true; value: bridge.conversionProgress; visible: bridge.busy || bridge.conversionProgress>0 }
                Canvas {
                    id: waveform; Layout.fillWidth: true; Layout.preferredHeight: 60
                    property var peaks: bridge.waveform
                    onPeaksChanged: requestPaint()
                    onWidthChanged: requestPaint()
                    onPaint: {
                        let c=getContext("2d");c.reset();c.fillStyle="#edf3ed";c.fillRect(0,0,width,height)
                        if(peaks.length) { c.strokeStyle="#4f82c6";c.lineWidth=2; for(let i=0;i<peaks.length;i++){let x=(i+.5)*width/peaks.length, a=peaks[i]*height*.43;c.beginPath();c.moveTo(x,height/2-a);c.lineTo(x,height/2+a);c.stroke()} }
                        else { c.strokeStyle="#ccddd3";c.beginPath();c.moveTo(15,height/2);c.lineTo(width-15,height/2);c.stroke() }
                    }
                }
            }
        }
        Panel {
            Layout.fillWidth: true; Layout.leftMargin: 26; Layout.rightMargin: 26
            ColumnLayout {
                anchors.fill: parent; spacing: 12
                RowLayout {
                    Label { Layout.fillWidth: true; text: bridge.title; color: "#17343b"; font.pixelSize: 19; font.bold: true; elide: Text.ElideRight }
                    Muted { text: bridge.notes.length+" 音符    "+(bridge.duration/1000).toFixed(1)+" 秒" }
                    ActionButton { text: "试听原音"; enabled: !bridge.busy && bridge.audioPath!==""; onClicked: bridge.auditionOriginal(loop.checked) }
                    ActionButton { objectName:"converterAudition";text: "口琴试听"; enabled: !bridge.busy && bridge.notes.length>0; onClicked: { page.requestAudition(); bridge.auditionScore() } }
                    ActionButton { text: "停止"; onClicked: bridge.stopAudio() }
                }
                RowLayout {
                    CheckBox { id: loop; text: "循环选中片段"; font.pixelSize: 12 }
                    ActionButton { text: "取消选中 / 全曲"; onClicked: bridge.selectNote(-1) }
                    Item { Layout.fillWidth: true }
                    Muted { text: "橙色为低模型分数，建议优先试听"; color: "#ad784d" }
                    ComboBox { id: zoom; model: ["12 秒视窗", "24 秒视窗", "48 秒视窗"]; implicitWidth: 125 }
                }
                MelodySelection { Layout.fillWidth:true }
                MelodyTools { Layout.fillWidth:true }
                PianoRoll { Layout.fillWidth: true; Layout.preferredHeight: 155; notes: bridge.notes; selected: bridge.selectedNote; startMs: viewStart.value; spanMs: 12000*Math.pow(2,zoom.currentIndex); onPicked: function(index) { bridge.selectNote(index) } }
                Slider { id: viewStart; Layout.fillWidth: true; from: 0; to: Math.max(0,bridge.duration-12000*Math.pow(2,zoom.currentIndex)); stepSize: 200; value: 0 }
                RowLayout {
                    Label { text: "音符校对"; color: "#17343b"; font.pixelSize: 16; font.bold: true }
                    Item { Layout.fillWidth: true }
                    ActionButton { text: "撤销"; enabled: bridge.canUndo && !bridge.busy; onClicked: bridge.undo() }
                    ActionButton { text: "重做"; enabled: bridge.canRedo && !bridge.busy; onClicked: bridge.redo() }
                    ActionButton { text: "恢复原始候选"; enabled: bridge.notes.length>0 && !bridge.busy; onClicked: bridge.changeReduction(false) }
                }
                Rectangle {
                    Layout.fillWidth: true; Layout.preferredHeight: 165; radius: 9; color: "#f4f7f2"
                    ColumnLayout {
                        anchors.fill: parent; spacing: 1
                        RowLayout {
                            Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; Layout.preferredHeight: 29
                            Repeater {
                                model: ["序号", "起始 / 秒", "音高", "时长 / 秒", "模型分数", "声部"]
                                delegate: Muted { required property string modelData; required property int index; Layout.preferredWidth: [50,110,105,100,90,120][index]; Layout.fillWidth: index===5; text: modelData; font.pixelSize: 11 }
                            }
                        }
                        ListView {
                            id: noteList; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; model: bridge.notes; currentIndex: bridge.selectedNote
                            onCurrentIndexChanged: if(currentIndex>=0) positionViewAtIndex(currentIndex,ListView.Contain)
                            delegate: Rectangle {
                                id: noteRow
                                required property var modelData
                                required property int index
                                width: ListView.view.width; height: 31; color: index===bridge.selectedNote ? "#dce8ef" : index%2 ? "#f5f8f3" : "#ffffff"
                                MouseArea { anchors.fill: parent; onClicked: page.select(noteRow.index) }
                                RowLayout {
                                    anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                                    Repeater {
                                        model: [String(noteRow.index+1),(noteRow.modelData.start_ms/1000).toFixed(3),noteRow.modelData.name+"  ("+noteRow.modelData.midi_pitch+")",(noteRow.modelData.duration_ms/1000).toFixed(3),noteRow.modelData.confidence.toFixed(2),noteRow.modelData.voice]
                                        delegate: Muted { required property string modelData; required property int index; Layout.preferredWidth: [50,110,105,100,90,120][index]; Layout.fillWidth: index===5; text: modelData; color: "#325560" }
                                    }
                                }
                            }
                        }
                    }
                }
                RowLayout {
                    Muted { text: "起始 ms" }
                    Field { id: start; Layout.preferredWidth: 100; text: page.selectedData ? String(page.selectedData.start_ms) : "0"; validator: DoubleValidator { bottom:0 } }
                    Muted { text: "时长 ms" }
                    Field { id: duration; Layout.preferredWidth: 90; text: page.selectedData ? String(page.selectedData.duration_ms) : "400"; validator: DoubleValidator { bottom:.1 } }
                    Muted { text: "MIDI 音高" }
                    Field { id: pitch; Layout.preferredWidth: 64; text: page.selectedData ? String(page.selectedData.midi_pitch) : "60"; validator: IntValidator { bottom:0;top:127 } }
                    ActionButton { text: "应用修改"; primary: true; enabled: !bridge.busy && page.selectedData!==null; onClicked: bridge.editNote(bridge.selectedNote,Number(start.text),Number(duration.text),Number(pitch.text)) }
                    ActionButton { text: "+ 新音符"; enabled: !bridge.busy; onClicked: bridge.addNote(Number(start.text),Number(duration.text),Number(pitch.text)) }
                    ActionButton { text: "删除"; enabled: !bridge.busy && page.selectedData!==null; onClicked: bridge.deleteNote(bridge.selectedNote) }
                }
                RowLayout {
                    ActionButton { text: "等分音符"; enabled: !bridge.busy && page.selectedData!==null; onClicked: bridge.splitNote(bridge.selectedNote) }
                    ActionButton { text: "合并下一同音"; enabled: !bridge.busy && page.selectedData!==null; onClicked: bridge.mergeNote(bridge.selectedNote) }
                    ComboBox { id: voice; model: bridge.voices; implicitWidth: 120 }
                    ActionButton { text: "仅保留该声部"; enabled: !bridge.busy && voice.currentIndex>=0; onClicked: bridge.selectVoice(voice.currentText) }
                    Item { Layout.fillWidth: true }
                    Muted { text: "修改后自动保存，可撤销 50 步" }
                }
            }
        }
        Panel {
            Layout.fillWidth: true; Layout.leftMargin: 26; Layout.rightMargin: 26
            visible: bridge.issues.length>0
            ColumnLayout {
                anchors.fill: parent; spacing: 10
                Label { text: "当前场景检查 · 点击定位音符"; color: "#17343b"; font.pixelSize: 16; font.bold: true }
                ListView {
                    Layout.fillWidth: true; Layout.preferredHeight: 140; clip: true; model: bridge.issues
                    delegate: ItemDelegate {
                        required property var modelData
                        width: ListView.view.width; height: 34
                        property int noteIndex: bridge.notes.findIndex(function(n) { return n.id===modelData.id })
                        text: (noteIndex>=0 ? (bridge.notes[noteIndex].start_ms/1000).toFixed(2)+" 秒  ·  " : "") + modelData.message
                        onClicked: if(noteIndex>=0) page.select(noteIndex)
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true; Layout.leftMargin: 26; Layout.rightMargin: 26; Layout.bottomMargin: 26
            Muted { Layout.fillWidth: true; text: "当前场景检查："+bridge.issues.length+" 项"; color: "#8b704e" }
            ActionButton { text: "导出 MIDI"; enabled: !bridge.busy && bridge.notes.length>0; onClicked: bridge.exportScore("midi") }
            ActionButton { text: "导出简谱"; enabled: !bridge.busy && bridge.notes.length>0; onClicked: bridge.exportScore("text") }
            ActionButton { text: "保存曲谱工程"; primary: true; enabled: !bridge.busy && bridge.notes.length>0; onClicked: bridge.exportScore("json") }
        }
    }
}
