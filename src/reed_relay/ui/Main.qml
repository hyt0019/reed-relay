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
    onClosing: Qt.quit()
    title: (bridge.appMode === "player" ? "风箱" : "听谱") + " · ReedRelay"
    color: "#f5f8f3"
    palette.highlight: "#2362ba"
    palette.text: "#17343b"
    palette.buttonText: "#17343b"
    property string page: ["settings","audition"].indexOf(initialPage)>=0 ? initialPage : "main"
    property var binding: bridge.bindingController
    property bool pagesReady: mainLoader.status===Loader.Ready && auditionLoader.status===Loader.Ready && settingsLoader.status===Loader.Ready
    function reloadDraft() { if(settingsLoader.item)settingsLoader.item.reload() }
    function profileDraft() { return settingsLoader.item ? settingsLoader.item.profileDraft() : bridge.profile }
    function noteName(n) { return ["C","C♯","D","D♯","E","F","F♯","G","G♯","A","A♯","B"][((n%12)+12)%12] + (Math.floor(n/12)-1) }
    function clock(ms) { let s=Math.floor(ms/1000); return Math.floor(s/60).toString().padStart(2,"0")+":"+(s%60).toString().padStart(2,"0") }
    Popup {
        id: bindingDialog
        objectName: "bindingDialog"
        anchors.centerIn: parent
        width: 490; height: 320
        modal: true; focus: true; closePolicy: Popup.NoAutoClose
        visible: root.binding.active
        padding: 25
        background: Rectangle { color:"#fcfdf9";radius:16;border.color:"#bdcfc5" }
        ColumnLayout {
            anchors.fill:parent;spacing:16
            Label { text:"绑定 "+root.binding.label;font.pixelSize:23;font.bold:true;color:"#17343b" }
            Label { Layout.fillWidth:true;wrapMode:Text.Wrap;text:root.binding.hint;font.pixelSize:14;color:"#52717a" }
            Rectangle {
                Layout.fillWidth:true;Layout.fillHeight:true;radius:10;color:"#e9f0e9"
                Label { anchors.centerIn:parent;text:root.binding.mouseAllowed?"按键盘，或在这里点击鼠标":"按下键盘组合键";font.pixelSize:15;color:"#43636a" }
                MouseArea { anchors.fill:parent;acceptedButtons:Qt.LeftButton|Qt.RightButton|Qt.MiddleButton;onClicked:function(mouse){root.binding.mouse(mouse.button)} }
            }
            RowLayout {
                Label { text:"Esc 取消 · 15 秒未完成自动退出";font.pixelSize:12;color:"#7a8f91" }
                Item { Layout.fillWidth:true }
                ActionButton { text:"取消";onClicked:root.binding.cancel() }
            }
        }
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
                implicitWidth: 110; implicitHeight: 32; radius: 16; color: "#e2eee6"
                Label { anchors.centerIn: parent; text: bridge.profile.pitch_source === "sample-inferred" ? "内置口琴" : "自定义场景"; color: "#3e765b"; font.pixelSize: 12 }
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
                ActionButton { text: "试听"; primary: root.page === "audition"; implicitWidth: 63; implicitHeight: 57; onClicked: root.page="audition" }
                ActionButton { text: "按键"; primary: root.page === "settings"; implicitWidth: 63; implicitHeight: 57; onClicked: { root.reloadDraft(); root.page="settings" } }
            }
            Label { anchors.bottom: parent.bottom; anchors.bottomMargin: 26; anchors.horizontalCenter: parent.horizontalCenter; text: "0.1.0"; color: "#78918e"; font.pixelSize: 12 }
        }
        StackLayout {
            Layout.fillWidth:true;Layout.fillHeight:true
            currentIndex:root.page==="settings"?2:root.page==="audition"?1:0
            Loader { id:mainLoader;sourceComponent:bridge.appMode==="player"?playerPage:converterPage }
            Loader { id:auditionLoader;source:"Audition.qml" }
            Loader { id:settingsLoader;source:"Settings.qml" }
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
                                RowLayout {
                                    Label { text:"单个长音";font.pixelSize:12;color:"#6c8388" }
                                    ComboBox { id:longPolicy;Layout.fillWidth:true;model:["保留长按（默认）","分段重奏"];currentIndex:bridge.playbackDefaults.long_policy==="rearticulate"?1:0;onActivated:bridge.configureArticulation(currentIndex===0?"hold":"rearticulate",repeatGap.value) }
                                }
                                RowLayout {
                                    Label { text:"同音松键间隔 / ms";font.pixelSize:12;color:"#6c8388" }
                                    SpinBox { id:repeatGap;from:0;to:150;stepSize:5;value:bridge.playbackDefaults.repeat_gap;implicitWidth:110;onValueModified:bridge.configureArticulation(longPolicy.currentIndex===0?"hold":"rearticulate",value) }
                                    Label { Layout.fillWidth:true;wrapMode:Text.Wrap;text:"不同音连续切换不换气";font.pixelSize:11;color:"#71878a" }
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
        Loader { source: "Converter.qml";onLoaded:item.requestAudition.connect(function(){root.page="audition"}) }
    }
}
