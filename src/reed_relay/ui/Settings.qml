import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: settings
    clip: true
    contentWidth: availableWidth
    function keyLabel(key) { return key.replace("MOUSE_LEFT","鼠标左键").replace("MOUSE_MIDDLE","鼠标中键").replace("MOUSE_RIGHT","鼠标右键") }
    function hasCombo(a,b) { return bridge.profile.combinations.some(c => c.length===2 && c.indexOf(a)>=0 && c.indexOf(b)>=0) }
    function profileDraft() {
        let value=JSON.parse(JSON.stringify(bridge.profile))
        value.name=sceneName.text
        value.reference_hz=Number(reference.text)
        let mappingChanged=value.reference_hz!==bridge.profile.reference_hz
        for(let i=0;i<8;i++) { let pitch=Number(pitchRows.itemAt(i).text); mappingChanged=mappingChanged || pitch!==value.pitches[i]; value.pitches[i]=pitch }
        for(let i=0;i<3;i++) { let shift=Number(shiftRows.itemAt(i).shift); mappingChanged=mappingChanged || shift!==value.modifiers[i].semitones; value.modifiers[i].semitones=shift }
        value.combinations=value.combinations.filter(c => c.length!==2 || !(c.indexOf(1)>=0 && (c.indexOf(0)>=0 || c.indexOf(2)>=0)))
        if(lower.checked)value.combinations.push([0,1])
        if(upper.checked)value.combinations.push([1,2])
        if(mappingChanged) { value.pitch_source="custom";value.calibrated=false }
        return value
    }
    function reload() {
        sceneName.text=bridge.profile.name;reference.text=String(bridge.profile.reference_hz)
        lower.checked=hasCombo(0,1);upper.checked=hasCombo(1,2)
        for(let i=0;i<8;i++)pitchRows.itemAt(i).text=String(bridge.profile.pitches[i])
        for(let i=0;i<3;i++)shiftRows.itemAt(i).shift=String(bridge.profile.modifiers[i].semitones)
    }
    Connections { target: bridge; function onProfileChanged() { settings.reload() } }
    ColumnLayout {
        width: settings.availableWidth;spacing: 19
        RowLayout {
            Layout.fillWidth: true;Layout.margins: 26;Layout.bottomMargin: 0
            ColumnLayout {
                spacing: 6
                Label { text:"把顺手的按键，留给音乐";font.pixelSize:26;font.bold:true;color:"#17343b" }
                Label { text:"点击键位，再按下要绑定的键。成功后自动保存。";font.pixelSize:13;color:"#647e82" }
            }
            Item { Layout.fillWidth:true }
            ActionButton { text:"导入场景";enabled:!bridge.busy;onClicked:bridge.importProfile() }
            ActionButton { text:"导出场景";onClicked:bridge.exportProfile() }
        }
        Panel {
            Layout.fillWidth:true;Layout.leftMargin:26;Layout.rightMargin:26
            ColumnLayout {
                anchors.fill:parent;spacing:18
                Label { text:"八个音符键";font.pixelSize:18;font.bold:true;color:"#17343b" }
                RowLayout {
                    Layout.fillWidth:true;spacing:10
                    Repeater {
                        model:8
                        delegate: ColumnLayout {
                            required property int index
                            Layout.fillWidth:true;spacing:8
                            Label { Layout.alignment:Qt.AlignHCenter;text:index===7?"高音 1":String(index+1);font.pixelSize:23;font.bold:true;color:"#173c48" }
                            ActionButton { objectName:"bindNote"+index;Layout.fillWidth:true;Layout.preferredWidth:85;implicitHeight:55;text:settings.keyLabel(bridge.profile.keys[index]);onClicked:bridge.beginBinding("note:"+index,index===7?"高音 1":"音符 "+(index+1)) }
                            Label { Layout.alignment:Qt.AlignHCenter;text:["C","C♯","D","D♯","E","F","F♯","G","G♯","A","A♯","B"][bridge.profile.pitches[index]%12]+(Math.floor(bridge.profile.pitches[index]/12)-1);font.pixelSize:12;color:"#78908a" }
                        }
                    }
                }
                Rectangle { Layout.fillWidth:true;height:1;color:"#e2eae3" }
                RowLayout {
                    Layout.fillWidth:true;spacing:20
                    Repeater {
                        model:3
                        delegate: RowLayout {
                            required property int index
                            Layout.fillWidth:true;spacing:12
                            Label { text:bridge.profile.modifiers[index].label;font.pixelSize:14;color:"#43636a" }
                            ActionButton { objectName:"bindModifier"+index;Layout.fillWidth:true;text:settings.keyLabel(bridge.profile.modifiers[index].key);onClicked:bridge.beginBinding("modifier:"+index,bridge.profile.modifiers[index].label) }
                        }
                    }
                }
                Label { text:"鼠标修饰按住生效，松开恢复。绑定支持键盘和鼠标左、中、右键。";font.pixelSize:12;color:"#71878a" }
            }
        }
        Panel {
            Layout.fillWidth:true;Layout.leftMargin:26;Layout.rightMargin:26
            ColumnLayout {
                anchors.fill:parent;spacing:16
                Label { text:"游戏内控制";font.pixelSize:18;font.bold:true;color:"#17343b" }
                RowLayout {
                    Layout.fillWidth:true;spacing:18
                    Repeater {
                        model:[{id:"toggle",label:"开始 / 停止"},{id:"previous",label:"上一首"},{id:"next",label:"下一首"},{id:"emergency",label:"紧急停止"}]
                        delegate: ColumnLayout {
                            required property var modelData
                            Layout.fillWidth:true;spacing:9
                            Label { text:modelData.label;color:"#557079";font.pixelSize:13 }
                            ActionButton { objectName:"bindHotkey"+modelData.id;Layout.fillWidth:true;text:bridge.profile.hotkeys[modelData.id];onClicked:bridge.beginBinding("hotkey:"+modelData.id,modelData.label) }
                        }
                    }
                }
                Label { text:"支持 Ctrl、Alt、Shift 等组合键。按 Esc 取消绑定，冲突时保留原按键。";font.pixelSize:12;color:"#71878a" }
            }
        }
        Panel {
            Layout.fillWidth:true;Layout.leftMargin:26;Layout.rightMargin:26
            ColumnLayout {
                anchors.fill:parent;spacing:12
                RowLayout {
                    Label { text:"口琴预设";font.pixelSize:18;font.bold:true;color:"#17343b" }
                    Item { Layout.fillWidth:true }
                    ActionButton { text:"使用内置音高";enabled:!bridge.busy;onClicked:bridge.useBuiltinProfile() }
                }
                Label { Layout.fillWidth:true;wrapMode:Text.Wrap;text:"内置音高来自录音与音阶推算，可以直接演奏。切换其他乐器时，可导入场景或展开高级映射。";font.pixelSize:13;color:"#647e82" }
                CheckBox { id:advanced;text:"高级音高映射";font.pixelSize:13 }
                ColumnLayout {
                    visible:advanced.checked;Layout.fillWidth:true;spacing:12
                    RowLayout {
                        Label { text:"场景名称";font.pixelSize:13 }
                        Field { id:sceneName;Layout.fillWidth:true;text:bridge.profile.name }
                        Label { text:"A4 / Hz";font.pixelSize:13 }
                        Field { id:reference;Layout.preferredWidth:86;text:String(bridge.profile.reference_hz);validator:DoubleValidator { bottom:400;top:480 } }
                    }
                    RowLayout {
                        Label { text:"基础 MIDI 音高";font.pixelSize:13 }
                        Repeater { id:pitchRows;model:8;delegate:Field { required property int index;Layout.fillWidth:true;Layout.preferredWidth:65;text:String(bridge.profile.pitches[index]);validator:IntValidator { bottom:0;top:127 } } }
                    }
                    RowLayout {
                        Repeater { id:shiftRows;model:3;delegate:RowLayout { required property int index;property alias shift:shiftInput.text;Layout.fillWidth:true;Label { text:bridge.profile.modifiers[index].label+" / 半音";font.pixelSize:13 } Field { id:shiftInput;Layout.fillWidth:true;text:String(bridge.profile.modifiers[index].semitones);validator:IntValidator { bottom:-48;top:48 } } } }
                    }
                    RowLayout {
                        CheckBox { id:lower;text:"降调 + 半音";checked:settings.hasCombo(0,1);font.pixelSize:13 }
                        CheckBox { id:upper;text:"升调 + 半音";checked:settings.hasCombo(1,2);font.pixelSize:13 }
                        Label { text:"组合按音阶推算，可按游戏表现关闭。";font.pixelSize:12;color:"#71878a" }
                        Item { Layout.fillWidth:true }
                        ActionButton { text:"保存映射";primary:true;enabled:!bridge.busy;onClicked:bridge.saveProfile(JSON.stringify(settings.profileDraft())) }
                    }
                }
            }
        }
        Item { height:12 }
    }
}
