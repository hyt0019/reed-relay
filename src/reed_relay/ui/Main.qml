import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    objectName: "mainWindow"
    width: 1280
    height: 900
    minimumWidth: 1060
    minimumHeight: 740
    visible: true
    title: (bridge.appMode === "player" ? "风箱" : "听谱") + " · ReedRelay"
    color: "#f5f8f3"
    palette.highlight: "#2362ba"
    palette.text: "#17343b"
    palette.buttonText: "#17343b"
    property string page: initialPage === "settings" ? "settings" : "main"
    property var draft: JSON.parse(JSON.stringify(bridge.profile))
    function reloadDraft() {
        draft = JSON.parse(JSON.stringify(bridge.profile))
        sceneName.text=draft.name; reference.text=String(draft.reference_hz)
        calibrated.checked=draft.calibrated; combine.checked=draft.combinations.length>4
        for(let i=0;i<8;i++) {
            keyRows.itemAt(i).keyValue=draft.keys[i]
            keyRows.itemAt(i).pitchValue=String(draft.pitches[i])
        }
        for(let i=0;i<3;i++) {
            modRows.itemAt(i).keyValue=draft.modifiers[i].key
            modRows.itemAt(i).shiftValue=String(draft.modifiers[i].semitones)
        }
        toggleHotkey.text=draft.hotkeys.toggle; previousHotkey.text=draft.hotkeys.previous
        nextHotkey.text=draft.hotkeys.next; emergencyHotkey.text=draft.hotkeys.emergency
    }
    function noteName(n) { return ["C","C♯","D","D♯","E","F","F♯","G","G♯","A","A♯","B"][((n%12)+12)%12] + (Math.floor(n/12)-1) }
    function clock(ms) { let s=Math.floor(ms/1000); return Math.floor(s/60).toString().padStart(2,"0")+":"+(s%60).toString().padStart(2,"0") }
    function saveDraft() {
        let value = JSON.parse(JSON.stringify(draft))
        value.name = sceneName.text
        value.reference_hz = Number(reference.text)
        value.calibrated = calibrated.checked
        for (let i=0;i<8;i++) { value.keys[i]=keyRows.itemAt(i).keyValue; value.pitches[i]=Number(keyRows.itemAt(i).pitchValue) }
        for (let i=0;i<3;i++) { value.modifiers[i].key=modRows.itemAt(i).keyValue; value.modifiers[i].semitones=Number(modRows.itemAt(i).shiftValue) }
        value.combinations = combine.checked ? [[],[0],[1],[2],[0,1],[1,2]] : [[],[0],[1],[2]]
        value.hotkeys={toggle:toggleHotkey.text,previous:previousHotkey.text,next:nextHotkey.text,emergency:emergencyHotkey.text}
        bridge.saveProfile(JSON.stringify(value))
    }
    header: Rectangle {
        height: 83
        color: "#fcfdf9"
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: "#dae4dc" }
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 28; anchors.rightMargin: 28; spacing: 16
            Rectangle {
                width: 43; height: 43; radius: 12; color: "#2362ba"
                Text { anchors.centerIn: parent; text: "R"; font.pixelSize: 27; font.bold: true; color: "white" }
            }
            ColumnLayout {
                spacing: 0
                Label { text: bridge.appMode === "player" ? "风箱  /  自动演奏" : "听谱  /  曲谱转换"; color: "#17343b"; font.pixelSize: 23; font.bold: true }
                Label { text: "ReedRelay    从声音，到你的演奏"; color: "#6a8287"; font.pixelSize: 12 }
            }
            Item { Layout.fillWidth: true }
            Label { text: bridge.profile.name; color: "#647e82"; font.pixelSize: 13 }
            Rectangle {
                implicitWidth: 110; implicitHeight: 32; radius: 16; color: bridge.profile.calibrated ? "#e2eee6" : "#fcf0de"
                Label { anchors.centerIn: parent; text: bridge.profile.calibrated ? "已确认调音" : "音高待校准"; color: bridge.profile.calibrated ? "#3e765b" : "#946324"; font.pixelSize: 12 }
            }
        }
    }
    footer: Rectangle {
        height: 65; color: "#ebf1eb"
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 12; spacing: 3
            Label { Layout.fillWidth: true; text: bridge.message; color: "#294e58"; font.pixelSize: 13; elide: Text.ElideRight }
            Label { Layout.fillWidth: true; text: bridge.appMode === "player" ? bridge.hotkeyStatus + "    ·    紧急停止 " + bridge.profile.hotkeys.emergency : "原谱保留绝对音高与时间；请试听校对混音歌曲的识别结果"; color: "#6b8387"; font.pixelSize: 11; elide: Text.ElideRight }
        }
    }
    RowLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            Layout.preferredWidth: 91; Layout.fillHeight: true; color: "#eaf0e9"
            ColumnLayout {
                anchors.top: parent.top; anchors.topMargin: 24; anchors.horizontalCenter: parent.horizontalCenter; spacing: 13
                ActionButton { text: bridge.appMode === "player" ? "演奏" : "听谱"; primary: root.page === "main"; implicitWidth: 63; implicitHeight: 57; onClicked: root.page="main" }
                ActionButton { text: "调音"; primary: root.page === "settings"; implicitWidth: 63; implicitHeight: 57; onClicked: { root.reloadDraft(); if(root.page!=="settings" && bridge.captureSource==="system")bridge.refreshAudioDevices(); root.page="settings" } }
            }
            Label { anchors.bottom: parent.bottom; anchors.bottomMargin: 26; anchors.horizontalCenter: parent.horizontalCenter; text: "0.1.0"; color: "#78918e"; font.pixelSize: 12 }
        }
        StackLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; currentIndex: root.page === "settings" ? 1 : 0
            Loader { sourceComponent: bridge.appMode === "player" ? playerPage : converterPage }
            ScrollView {
                id: settingsScroll; clip: true; contentWidth: availableWidth
                ColumnLayout {
                    width: settingsScroll.availableWidth; spacing: 18
                    RowLayout {
                        Layout.topMargin: 24; Layout.leftMargin: 26; Layout.rightMargin: 26; Layout.fillWidth: true
                        ColumnLayout {
                            Label { text: "让每个场景，都有自己的音准"; color: "#17343b"; font.pixelSize: 25; font.bold: true }
                            Label { text: "先测音，再对应实际按键。默认音高只是待校准模板。"; color: "#6a8287"; font.pixelSize: 13 }
                        }
                        Item { Layout.fillWidth: true }
                        ActionButton { text: "导入场景"; onClicked: { bridge.importProfile(); root.reloadDraft() } }
                        ActionButton { text: "导出已保存场景"; onClicked: bridge.exportProfile() }
                    }
                    Panel {
                        Layout.leftMargin: 26; Layout.rightMargin: 26; Layout.fillWidth: true
                        RowLayout {
                            anchors.fill: parent; spacing: 24
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 12
                                Label { text: "场景与参考频率"; font.pixelSize: 17; font.bold: true; color: "#17343b" }
                                RowLayout {
                                    Field { id: sceneName; Layout.fillWidth: true; text: root.draft.name; placeholderText: "为场景起个名字" }
                                    Label { text: "A4"; color: "#617c83" }
                                    Field { id: reference; Layout.preferredWidth: 80; text: String(root.draft.reference_hz); validator: DoubleValidator { bottom: 400; top: 480 } }
                                    Label { text: "Hz"; color: "#617c83" }
                                }
                                RowLayout {
                                    Label { text: "测音来源"; color: "#617c83" }
                                    ComboBox {
                                        Layout.fillWidth: true
                                        model: ["电脑声音（耳机 / 扬声器）", "麦克风"]
                                        currentIndex: bridge.captureSource==="system" ? 0 : 1
                                        onActivated: bridge.setCaptureSource(currentIndex===0 ? "system" : "microphone")
                                    }
                                    ActionButton { text: bridge.listening ? "停止测音" : "开始测音"; primary: !bridge.listening; enabled: bridge.listening || bridge.captureSource!=="system" || bridge.captureDevice>=0; onClicked: bridge.toggleTuning() }
                                }
                                RowLayout {
                                    visible: bridge.captureSource==="system"
                                    ComboBox {
                                        Layout.fillWidth: true; Layout.minimumWidth: 150
                                        model: bridge.captureDevices; textRole: "label"
                                        currentIndex: bridge.captureDevice
                                        displayText: currentIndex<0 ? "未找到输出设备" : currentText
                                        onActivated: bridge.setCaptureDevice(currentIndex)
                                    }
                                    ActionButton { text: "刷新设备"; onClicked: bridge.refreshAudioDevices() }
                                }
                                RowLayout {
                                    Label { text: "输入音量"; color: "#617c83"; font.pixelSize: 12 }
                                    ProgressBar { Layout.fillWidth: true; value: bridge.captureLevel; palette.highlight: "#508878" }
                                    Label { text: bridge.listening ? "采集中" : "未采集"; color: bridge.listening ? "#3e765b" : "#7a8f91"; font.pixelSize: 12 }
                                }
                                Label { Layout.fillWidth: true; text: bridge.captureStatus; wrapMode: Text.Wrap; color: "#43636a"; font.pixelSize: 12 }
                                RowLayout {
                                    ActionButton { text: "分析 WAV 单音"; onClicked: bridge.tuneFile() }
                                    ActionButton { text: "试听 A4"; onClicked: bridge.playTone(69, Number(reference.text)) }
                                }
                                Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: bridge.captureSource==="system" ? "采集所选设备上的所有声音，请暂停其他音乐或视频。声音仅用于本地测音。" : "使用 Windows 默认录音设备。点击开始测音后才会使用麦克风。"; color: "#7a8f91"; font.pixelSize: 11 }
                                Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "测音使用已保存的 A4；播放参考音会停止采集。"; color: "#7a8f91"; font.pixelSize: 11 }
                            }
                            Rectangle {
                                Layout.preferredWidth: 245; Layout.preferredHeight: 142; radius: 12; color: "#173c48"
                                ColumnLayout {
                                    anchors.centerIn: parent; spacing: 6
                                    Label { Layout.alignment: Qt.AlignHCenter; text: bridge.tuning.name || "等待测音"; color: "#f5faf5"; font.pixelSize: 29; font.bold: true }
                                    Label { Layout.alignment: Qt.AlignHCenter; text: bridge.tuning.frequency>0 ? "MIDI " + bridge.tuning.pitch : "逐个弹奏，读取音高"; color: "#bed5d5"; font.pixelSize: 12 }
                                    Label { Layout.alignment: Qt.AlignHCenter; text: (bridge.tuning.frequency || 0).toFixed(1) + " Hz    " + (bridge.tuning.cents || 0).toFixed(1) + " 音分"; color: "#bed5d5"; font.pixelSize: 13 }
                                    Rectangle {
                                        Layout.alignment: Qt.AlignHCenter; width: 190; height: 20; color: "transparent"
                                        Rectangle { anchors.verticalCenter: parent.verticalCenter; width: parent.width; height: 3; color: "#597a80" }
                                        Rectangle { x: 94; width: 2; height: 20; color: "#afc6c5" }
                                        Rectangle { x: Math.max(0, Math.min(182, 91 + (bridge.tuning.cents || 0)*1.8)); y: 6; width: 8; height: 8; radius: 4; color: "#e4ac73" }
                                    }
                                }
                            }
                        }
                    }
                    Panel {
                        Layout.leftMargin: 26; Layout.rightMargin: 26; Layout.fillWidth: true
                        ColumnLayout {
                            anchors.fill: parent; spacing: 16
                            RowLayout {
                                Label { text: "八个音符键"; color: "#17343b"; font.pixelSize: 17; font.bold: true }
                                Item { Layout.fillWidth: true }
                                ActionButton { text: "音区 −12"; onClicked: { for(let i=0;i<8;i++)keyRows.itemAt(i).pitchValue=String(Math.max(0,Number(keyRows.itemAt(i).pitchValue)-12)) } }
                                ActionButton { text: "音区 +12"; onClicked: { for(let i=0;i<8;i++)keyRows.itemAt(i).pitchValue=String(Math.min(127,Number(keyRows.itemAt(i).pitchValue)+12)) } }
                                Label { text: "MIDI 60 = C4    ·    点击试听检验对应音高"; color: "#6f878a"; font.pixelSize: 12 }
                            }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 12
                                Repeater {
                                    id: keyRows; model: 8
                                    delegate: ColumnLayout {
                                        required property int index
                                        property alias keyValue: keyInput.text
                                        property alias pitchValue: pitchInput.text
                                        Layout.fillWidth: true; spacing: 7
                                        Label { Layout.alignment: Qt.AlignHCenter; text: index===7 ? "高音 1" : String(index+1); color: "#43636a"; font.bold: true }
                                        Field { id: keyInput; Layout.fillWidth: true; Layout.preferredWidth: 70; text: root.draft.keys[index]; horizontalAlignment: Text.AlignHCenter }
                                        Field { id: pitchInput; Layout.fillWidth: true; Layout.preferredWidth: 70; text: String(root.draft.pitches[index]); horizontalAlignment: Text.AlignHCenter; validator: IntValidator { bottom:0; top:127 } }
                                        ActionButton { Layout.fillWidth: true; implicitWidth: 60; text: root.noteName(Number(pitchInput.text)); onClicked: bridge.playTone(Number(pitchInput.text), Number(reference.text)) }
                                    }
                                }
                            }
                            RowLayout {
                                Label { text: "按键支持字母、数字、F 键或 MOUSE_LEFT 等鼠标名称；输入音高后保存。"; color: "#6f878a"; font.pixelSize: 12 }
                            }
                        }
                    }
                    Panel {
                        Layout.leftMargin: 26; Layout.rightMargin: 26; Layout.fillWidth: true
                        ColumnLayout {
                            anchors.fill: parent; spacing: 13
                            Label { text: "鼠标修饰 · 按住生效，松开恢复"; color: "#17343b"; font.pixelSize: 17; font.bold: true }
                            RowLayout {
                                spacing: 20
                                Repeater {
                                    id: modRows; model: 3
                                    delegate: RowLayout {
                                        required property int index
                                        property alias keyValue: modifierKey.text
                                        property alias shiftValue: modifierShift.text
                                        Layout.fillWidth: true
                                        Label { text: root.draft.modifiers[index].label; color: "#40606a" }
                                        Field { id: modifierKey; Layout.fillWidth: true; Layout.minimumWidth: 118; text: root.draft.modifiers[index].key; font.pixelSize: 12 }
                                        Field { id: modifierShift; Layout.preferredWidth: 58; text: String(root.draft.modifiers[index].semitones); validator: IntValidator { bottom:-48; top:48 } }
                                    }
                                }
                            }
                            CheckBox { id: combine; text: "允许降调+半音、升调+半音组合（确认游戏支持后开启）"; checked: root.draft.combinations.length>4; font.pixelSize: 13 }
                        }
                    }
                    Panel {
                        Layout.leftMargin: 26; Layout.rightMargin: 26; Layout.fillWidth: true
                        ColumnLayout {
                            anchors.fill: parent; spacing: 12
                            Label { text: "全局热键"; color: "#17343b"; font.pixelSize: 17; font.bold: true }
                            RowLayout {
                                spacing: 14
                                Label { text: "启停" }
                                Field { id: toggleHotkey; Layout.fillWidth: true; text: root.draft.hotkeys.toggle }
                                Label { text: "上一首" }
                                Field { id: previousHotkey; Layout.fillWidth: true; text: root.draft.hotkeys.previous }
                                Label { text: "下一首" }
                                Field { id: nextHotkey; Layout.fillWidth: true; text: root.draft.hotkeys.next }
                                Label { text: "紧急停止" }
                                Field { id: emergencyHotkey; Layout.fillWidth: true; text: root.draft.hotkeys.emergency }
                            }
                            Label { text: "组合键示例：CTRL+F8。热键不能与音符键重复。"; color: "#6f878a"; font.pixelSize: 12 }
                        }
                    }
                    RowLayout {
                        Layout.leftMargin: 26; Layout.rightMargin: 26; Layout.bottomMargin: 26; Layout.fillWidth: true
                        CheckBox { id: calibrated; text: "我已核对基础音高、修饰音程和组合"; checked: root.draft.calibrated; font.pixelSize: 13 }
                        Item { Layout.fillWidth: true }
                        ActionButton { text: "保存并应用场景"; primary: true; onClicked: root.saveDraft() }
                    }
                }
            }
        }
    }
    Component {
        id: playerPage
        ScrollView {
            id: playScroll; contentWidth: availableWidth; clip: true
            function applyOptions() { bridge.configurePlayer(preview.checked, speed.value/100, delay.value, transpose.value, melody.checked, skip.checked, target.currentIndex, autoContinue.checked) }
            Component.onCompleted: applyOptions()
            ColumnLayout {
                width: playScroll.availableWidth; spacing: 19
                RowLayout {
                    Layout.topMargin: 24; Layout.leftMargin: 27; Layout.rightMargin: 27; Layout.fillWidth: true
                    Label { text: "准备好，下一首。"; color: "#17343b"; font.pixelSize: 27; font.bold: true }
                    Item { Layout.fillWidth: true }
                    ActionButton { text: "载入练习曲"; onClicked: bridge.loadDemo() }
                    ActionButton { text: "+ 添加曲谱"; onClicked: bridge.openScores() }
                }
                RowLayout {
                    Layout.leftMargin: 27; Layout.rightMargin: 27; Layout.fillWidth: true; spacing: 21
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 19
                        Rectangle {
                            Layout.fillWidth: true; Layout.preferredHeight: 183; radius: 16; color: "#173c48"
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 23; spacing: 8
                                RowLayout {
                                    Label { text: bridge.state + (preview.checked ? "  /  预演模式" : "  /  游戏输入"); color: "#c1d7d5"; font.pixelSize: 13 }
                                    Item { Layout.fillWidth: true }
                                    Label { text: transpose.value===0 ? "保持原调" : "演奏移调 " + transpose.value + " 半音"; color: "#e9bf97"; font.pixelSize: 12 }
                                }
                                Label { Layout.fillWidth: true; text: bridge.title; color: "#fbfdf7"; font.pixelSize: 28; font.bold: true; elide: Text.ElideRight }
                                Item { Layout.fillHeight: true }
                                ProgressBar { Layout.fillWidth: true; from: 0; to: Math.max(1,bridge.duration); value: bridge.progress; palette.highlight: "#d98b60" }
                                RowLayout {
                                    Label { text: root.clock(bridge.progress); color: "#c3d6d5"; font.pixelSize: 12 }
                                    Item { Layout.fillWidth: true }
                                    Label { text: root.clock(bridge.duration); color: "#c3d6d5"; font.pixelSize: 12 }
                                }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            ActionButton { text: "上一首"; onClicked: bridge.stepSong(-1) }
                            ActionButton { Layout.fillWidth: true; text: bridge.running ? "停止演奏" : "开始演奏  " + bridge.profile.hotkeys.toggle; primary: true; implicitHeight: 46; onClicked: { playScroll.applyOptions(); bridge.toggle() } }
                            ActionButton { text: "下一首"; onClicked: bridge.stepSong(1) }
                        }
                        Label { text: "游戏按键"; color: "#17343b"; font.pixelSize: 17; font.bold: true }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 8
                            Repeater {
                                model: 8
                                delegate: Rectangle {
                                    required property int index
                                    Layout.fillWidth: true; Layout.preferredHeight: 100; radius: 10
                                    color: bridge.activeKey===bridge.profile.keys[index] ? "#2362ba" : "#ffffff"
                                    border.color: "#d5e1d9"
                                    ColumnLayout {
                                        anchors.centerIn: parent; spacing: 9
                                        Label { Layout.alignment: Qt.AlignHCenter; text: index===7 ? "i" : String(index+1); color: bridge.activeKey===bridge.profile.keys[index] ? "white" : "#17343b"; font.pixelSize: 25; font.bold: true }
                                        Label { Layout.alignment: Qt.AlignHCenter; text: bridge.profile.keys[index]; color: bridge.activeKey===bridge.profile.keys[index] ? "white" : "#55767d"; font.pixelSize: 13 }
                                    }
                                }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 10
                            Repeater {
                                model: bridge.profile.modifiers
                                delegate: Rectangle {
                                    required property var modelData
                                    Layout.fillWidth: true; Layout.preferredHeight: 54; radius: 10; color: "#eaf0e9"
                                    Label { anchors.centerIn: parent; text: modelData.label+"  "+modelData.key.replace("MOUSE_LEFT","左键").replace("MOUSE_MIDDLE","中键").replace("MOUSE_RIGHT","右键"); color: "#42646b"; font.pixelSize: 13 }
                                }
                            }
                        }
                        Panel {
                            Layout.fillWidth: true
                            ColumnLayout {
                                anchors.fill: parent; spacing: 8
                                RowLayout {
                                    CheckBox { id: preview; text: "预演（不发送按键）"; checked: true; onToggled: playScroll.applyOptions(); font.pixelSize: 13 }
                                    Item { Layout.fillWidth: true }
                                    Label { text: "倒计时 / 秒"; color: "#6c8388"; font.pixelSize: 12 }
                                    SpinBox { id: delay; from: 0; to: 15; value: bridge.playbackDefaults.delay; onValueModified: playScroll.applyOptions(); implicitWidth: 106 }
                                }
                                RowLayout {
                                    Label { text: "速度 %"; color: "#6c8388"; font.pixelSize: 12 }
                                    SpinBox { id: speed; from: 25; to: 200; value: bridge.playbackDefaults.speed; stepSize: 5; onValueModified: playScroll.applyOptions(); implicitWidth: 120 }
                                    Item { Layout.fillWidth: true }
                                    Label { text: "演奏移调 / 半音"; color: "#6c8388"; font.pixelSize: 12 }
                                    SpinBox { id: transpose; from: -48; to: 48; value: bridge.playbackDefaults.transpose; onValueModified: playScroll.applyOptions(); implicitWidth: 110 }
                                }
                                RowLayout {
                                    CheckBox { id: melody; text: "提取主旋律"; checked: bridge.playbackDefaults.melody; onToggled: playScroll.applyOptions(); font.pixelSize: 13 }
                                    CheckBox { id: skip; text: "跳过音域外音"; checked: bridge.playbackDefaults.skip; onToggled: playScroll.applyOptions(); font.pixelSize: 13 }
                                }
                                CheckBox { id: autoContinue; text: "演奏中切歌后自动继续"; checked: bridge.playbackDefaults.auto_continue; onToggled: playScroll.applyOptions(); font.pixelSize: 13 }
                                RowLayout {
                                    ComboBox { id: target; Layout.fillWidth: true; model: bridge.windowList; textRole: "title"; currentIndex: -1; displayText: currentIndex<0 ? "选择游戏窗口" : currentText; onActivated: playScroll.applyOptions() }
                                    ActionButton { text: "刷新"; onClicked: { bridge.refreshWindows(); target.currentIndex=-1; playScroll.applyOptions() } }
                                }
                            }
                        }
                    }
                    ColumnLayout {
                        Layout.preferredWidth: 278; Layout.minimumWidth: 270; Layout.maximumWidth: 290; Layout.alignment: Qt.AlignTop; spacing: 15
                        Panel {
                            Layout.fillWidth: true; Layout.preferredHeight: 340
                            ColumnLayout {
                                anchors.fill: parent; spacing: 10
                                RowLayout {
                                    Label { text: "播放列表"; color: "#17343b"; font.pixelSize: 18; font.bold: true }
                                    Item { Layout.fillWidth: true }
                                    ToolButton { text: "↑"; onClicked: bridge.moveSong(-1) }
                                    ToolButton { text: "↓"; onClicked: bridge.moveSong(1) }
                                }
                                Label { visible: bridge.playlist.length===0; text: "添加曲谱，或载入练习曲\n两个模块都可独立使用。"; color: "#70898e"; font.pixelSize: 13; lineHeight: 1.5 }
                                ListView {
                                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 6; model: bridge.playlist
                                    delegate: Rectangle {
                                        required property var modelData
                                        required property int index
                                        width: ListView.view.width; height: 66; radius: 9; color: index===bridge.selected ? "#e9f0e9" : "#ffffff"
                                        MouseArea { anchors.fill: parent; onClicked: bridge.selectSong(index) }
                                        ColumnLayout {
                                            anchors.left: parent.left; anchors.leftMargin: 11; anchors.right: remove.left; anchors.verticalCenter: parent.verticalCenter; spacing: 4
                                            Label { Layout.fillWidth: true; text: modelData.title; color: "#254b57"; font.pixelSize: 13; elide: Text.ElideRight }
                                            Label { text: root.clock(modelData.duration); color: "#789191"; font.pixelSize: 11 }
                                        }
                                        ToolButton { id: remove; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: 32; text: "×"; onClicked: bridge.removeSong(index) }
                                    }
                                }
                            }
                        }
                        Panel {
                            Layout.fillWidth: true; Layout.preferredHeight: 293
                            ColumnLayout {
                                anchors.fill: parent; spacing: 10
                                Label { text: "演奏检查"; color: "#17343b"; font.pixelSize: 17; font.bold: true }
                                Label { text: bridge.issues.length ? bridge.issues.length+" 项需要查看" : "当前未发现映射冲突"; color: bridge.issues.length ? "#ac7046" : "#5c7d72"; font.pixelSize: 12 }
                                ListView {
                                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; model: bridge.issues; spacing: 7
                                    delegate: Label {
                                        required property var modelData
                                        width: ListView.view.width; text: (modelData.blocking ? "!  " : "·  ")+modelData.message; wrapMode: Text.Wrap; color: modelData.blocking ? "#a66340" : "#71848b"; font.pixelSize: 12
                                    }
                                }
                            }
                        }
                    }
                }
                Item { height: 22 }
            }
        }
    }
    Component {
        id: converterPage
        Loader { source: "Converter.qml" }
    }
}
