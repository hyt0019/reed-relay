import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id:page
    clip:true;contentWidth:availableWidth
    ColumnLayout {
        width:page.availableWidth;spacing:21
        ColumnLayout {
            Layout.fillWidth:true;Layout.margins:26;Layout.bottomMargin:0;spacing:6
            Label { text:"把作品，存到你选的位置";font.pixelSize:27;font.bold:true;color:"#17343b" }
            Label { text:"两个模块使用同一份保存位置记录，默认放在程序旁。";font.pixelSize:13;color:"#647e82" }
        }
        Panel {
            Layout.fillWidth:true;Layout.leftMargin:26;Layout.rightMargin:26
            ColumnLayout {
                anchors.fill:parent;spacing:19
                Label { text:"当前保存目录";font.pixelSize:19;font.bold:true;color:"#17343b" }
                RowLayout {
                    Layout.fillWidth:true;spacing:12
                    Field { objectName:"storagePath";Layout.fillWidth:true;text:bridge.storagePath;readOnly:true;selectByMouse:true;font.pixelSize:15 }
                    ActionButton { objectName:"chooseStorage";text:"选择目录";primary:true;enabled:!bridge.busy && !bridge.storageFixed;onClicked:bridge.chooseStorage() }
                    ActionButton { text:"打开文件夹";onClicked:bridge.showStorage(false) }
                }
                Label { Layout.fillWidth:true;wrapMode:Text.Wrap;text:"转谱工程、自动保存、场景配置和试听临时音频都使用这里。手动导出时也从这个目录开始，可为每次导出另选位置。";font.pixelSize:14;color:"#52717a";lineHeight:1.5 }
                Rectangle { Layout.fillWidth:true;height:1;color:"#e2eae3" }
                Label { Layout.fillWidth:true;wrapMode:Text.Wrap;text:"更换目录会复制已有作品和配置，保留原目录。同名文件内容不同时会提示选择空目录。另一个已打开的模块需重新启动，才能使用新位置。";font.pixelSize:13;color:"#647e82";lineHeight:1.5 }
                Label { visible:bridge.storageFixed;Layout.fillWidth:true;wrapMode:Text.Wrap;text:"当前启动配置 REED_RELAY_DATA_DIR 已指定目录。移除该配置后可在这里更换保存位置。";font.pixelSize:13;color:"#ac7046" }
            }
        }
        Panel {
            Layout.fillWidth:true;Layout.leftMargin:26;Layout.rightMargin:26
            ColumnLayout {
                anchors.fill:parent;spacing:14
                RowLayout {
                    Label { text:"升级前的数据";font.pixelSize:18;font.bold:true;color:"#17343b" }
                    Item { Layout.fillWidth:true }
                    ActionButton { text:"打开旧目录";onClicked:bridge.showStorage(true) }
                }
                Label { Layout.fillWidth:true;wrapMode:Text.Wrap;text:"首次升级会将旧 AppData 数据复制到程序旁，原文件保留。若自动迁入遇到冲突，可从旧目录打开原工程，再导出到当前保存目录。";font.pixelSize:13;color:"#647e82";lineHeight:1.5 }
                Field { Layout.fillWidth:true;readOnly:true;selectByMouse:true;text:bridge.legacyStoragePath }
            }
        }
        Item { height:20 }
    }
}
