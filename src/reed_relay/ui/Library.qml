import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id:page
    signal requestMain()
    signal requestAudition()
    clip:true;contentWidth:availableWidth
    property var entries: {
        let query=search.text.trim().toLowerCase()
        return bridge.libraryEntries.filter(function(song) { return !query || (song.title+" "+song.filename).toLowerCase().indexOf(query)>=0 })
    }
    function clock(ms) { let seconds=Math.floor(ms/1000);return Math.floor(seconds/60).toString().padStart(2,"0")+":"+(seconds%60).toString().padStart(2,"0") }
    function noteName(pitch) { return ["C","C♯","D","D♯","E","F","F♯","G","G♯","A","A♯","B"][pitch%12]+(Math.floor(pitch/12)-1) }
    DropArea { anchors.fill:parent;onDropped:function(drop){if(drop.hasUrls)bridge.importScoreFiles(JSON.stringify(drop.urls))} }
    ColumnLayout {
        width:page.availableWidth;spacing:18
        RowLayout {
            Layout.fillWidth:true;Layout.leftMargin:26;Layout.rightMargin:26;Layout.topMargin:24
            ColumnLayout {
                spacing:5
                Label { text:"好曲谱，直接演奏";font.pixelSize:27;font.bold:true;color:"#17343b" }
                Label { text:"导入已有曲谱，保留音高与节奏。也可以把文件直接放进曲库。";font.pixelSize:13;color:"#647e82" }
            }
            Item { Layout.fillWidth:true }
            ActionButton { text:"刷新曲库";enabled:!bridge.busy;onClicked:bridge.refreshLibrary() }
            ActionButton { objectName:"libraryImport";text:"导入曲谱";primary:true;enabled:!bridge.busy;onClicked:bridge.openScores() }
        }
        Panel {
            Layout.fillWidth:true;Layout.leftMargin:26;Layout.rightMargin:26
            ColumnLayout {
                anchors.fill:parent;spacing:12
                RowLayout {
                    Label { text:"演奏库文件夹";font.pixelSize:14;font.bold:true;color:"#17343b" }
                    Item { Layout.fillWidth:true }
                    ActionButton { text:"打开文件夹";onClicked:bridge.showLibraryFolder() }
                    ActionButton { objectName:"libraryChoose";text:"更换文件夹";enabled:!bridge.busy;onClicked:bridge.chooseLibrary() }
                }
                Field { objectName:"libraryPath";Layout.fillWidth:true;text:bridge.libraryPath;readOnly:true;font.pixelSize:13 }
                Label { text:"支持 MIDI（.mid / .midi）与 ReedRelay JSON。外部文件导入后复制进曲库，同名文件保留双方。";Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:12;color:"#647e82" }
            }
        }
        Panel {
            Layout.fillWidth:true;Layout.leftMargin:26;Layout.rightMargin:26
            ColumnLayout {
                anchors.fill:parent;spacing:14
                RowLayout {
                    Label { text:"曲目";font.pixelSize:18;font.bold:true;color:"#17343b" }
                    Label { text:page.entries.length+" / "+bridge.libraryEntries.length+" 份";font.pixelSize:12;color:"#647e82" }
                    Item { Layout.fillWidth:true }
                    Field { id:search;objectName:"librarySearch";Layout.preferredWidth:260;placeholderText:"搜索曲名或文件名" }
                    ActionButton { objectName:"libraryAddAll";text:"全部加入播放列表";visible:bridge.appMode==="player";enabled:!bridge.busy && bridge.libraryEntries.length>0;onClicked:bridge.addLibraryToPlaylist() }
                }
                Rectangle { Layout.fillWidth:true;height:1;color:"#e1e9e2" }
                ListView {
                    id:songs;objectName:"librarySongs";Layout.fillWidth:true;Layout.preferredHeight:Math.max(220,Math.min(320,count*98));clip:true;model:page.entries;spacing:0
                    ScrollBar.vertical:ScrollBar {}
                    delegate:Item {
                        id:row
                        required property var modelData
                        required property int index
                        width:ListView.view.width;height:98
                        RowLayout {
                            anchors.fill:parent;anchors.topMargin:12;anchors.bottomMargin:12;spacing:14
                            Rectangle {
                                width:48;height:48;radius:10;color:row.modelData.error?"#f4e8dd":"#e8f0e7"
                                Label { anchors.centerIn:parent;text:row.modelData.error?"!":"谱";font.pixelSize:23;color:row.modelData.error?"#a66340":"#3c7066" }
                            }
                            ColumnLayout {
                                Layout.fillWidth:true;spacing:5
                                Label { Layout.fillWidth:true;text:row.modelData.title;font.pixelSize:16;font.bold:true;color:"#254b57";elide:Text.ElideRight }
                                Label { Layout.fillWidth:true;text:row.modelData.error?row.modelData.error:row.modelData.format+"    "+page.clock(row.modelData.duration)+"    "+row.modelData.note_count+" 音符    "+page.noteName(row.modelData.minimum_pitch)+"–"+page.noteName(row.modelData.maximum_pitch);font.pixelSize:12;color:row.modelData.error?"#a66340":"#647e82";elide:Text.ElideRight }
                                Label { Layout.fillWidth:true;text:row.modelData.filename+(row.modelData.in_playlist?"    ·    已加入播放列表":"");font.pixelSize:11;color:"#819492";elide:Text.ElideMiddle }
                            }
                            ActionButton { objectName:"libraryPreview"+row.index;text:"试听";enabled:!bridge.busy && !row.modelData.error;onClicked:{if(bridge.previewLibraryScore(row.modelData.path))page.requestAudition()} }
                            ActionButton { objectName:"libraryOpen"+row.index;text:bridge.appMode==="player"?"载入演奏":"打开校对";enabled:!bridge.busy && !row.modelData.error;onClicked:{if(bridge.openLibraryScore(row.modelData.path))page.requestMain()} }
                        }
                        Rectangle { anchors.bottom:parent.bottom;width:parent.width;height:1;color:"#edf1ed" }
                    }
                    Label { anchors.centerIn:parent;visible:songs.count===0;text:bridge.libraryEntries.length?"没有匹配曲目，换个关键词试试":"曲库还没有曲谱\n点击「导入曲谱」，或拖入 MIDI / JSON 文件。";horizontalAlignment:Text.AlignHCenter;font.pixelSize:15;lineHeight:1.6;color:"#78918e" }
                }
                Label { Layout.fillWidth:true;wrapMode:Text.Wrap;text:bridge.appMode==="player"?"载入后，在演奏页选择游戏窗口并按启动键。播放列表支持上一首 / 下一首；移出列表保留曲库文件。":"打开校对后可编辑、试听并另存。风箱可独立读取同一个曲库，无需重新转谱。";font.pixelSize:12;color:"#71878a" }
            }
        }
        Item { height:14 }
    }
}
