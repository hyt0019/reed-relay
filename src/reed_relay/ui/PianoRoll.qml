import QtQuick
Canvas {
    id: canvas
    property var notes: []
    property int selected: -1
    property real startMs: 0
    property real spanMs: 12000
    property int lowest: 48
    property int highest: 84
    signal picked(int index)
    onNotesChanged: requestPaint()
    onSelectedChanged: requestPaint()
    onStartMsChanged: requestPaint()
    onSpanMsChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        let c=getContext("2d");c.reset();c.fillStyle="#f7faf6";c.fillRect(0,0,width,height)
        let lo=48,hi=84
        for(let n of notes) { if(n.start_ms+n.duration_ms>=startMs && n.start_ms<startMs+spanMs) { lo=Math.min(lo,n.midi_pitch-2);hi=Math.max(hi,n.midi_pitch+2) } }
        lowest=lo;highest=hi
        let row=(height-26)/(hi-lo+1), usable=width-44
        c.font="11px 'Microsoft YaHei'"
        for(let p=lo;p<=hi;p++) { let yy=20+(hi-p)*row;if(p%12===0) {c.fillStyle="#687f82";c.fillText("C"+(Math.floor(p/12)-1),3,yy+4);c.strokeStyle="#c7d9d1";c.beginPath();c.moveTo(40,yy);c.lineTo(width,yy);c.stroke()} }
        for(let s=0;s<=spanMs;s+=2000) {let xx=44+s/spanMs*usable;c.strokeStyle="#e0e9e2";c.beginPath();c.moveTo(xx,20);c.lineTo(xx,height);c.stroke();c.fillStyle="#708889";c.fillText(((startMs+s)/1000).toFixed(0)+"s",xx+3,12)}
        notes.forEach(function(n,i) {
            if(n.start_ms+n.duration_ms<startMs || n.start_ms>startMs+spanMs)return
            let xx=44+(n.start_ms-startMs)/spanMs*usable, yy=20+(hi-n.midi_pitch)*row, ww=Math.max(3,n.duration_ms/spanMs*usable)
            c.fillStyle=i===selected ? "#173c48" : n.confidence<.5 ? "#d99a6c" : "#427ac6"
            c.fillRect(Math.max(44,xx),yy,Math.max(0,Math.min(width,xx+ww)-Math.max(44,xx)),Math.max(3,row-1))
        })
    }
    MouseArea {
        anchors.fill: parent
        onClicked: function(mouse) {
            let time=canvas.startMs+(mouse.x-44)/(canvas.width-44)*canvas.spanMs
            let pitch=canvas.highest-Math.floor((mouse.y-20)/((canvas.height-26)/(canvas.highest-canvas.lowest+1)))
            let best=-1,dist=999
            canvas.notes.forEach(function(n,i){ if(time>=n.start_ms && time<=n.start_ms+n.duration_ms && Math.abs(n.midi_pitch-pitch)<dist) {best=i;dist=Math.abs(n.midi_pitch-pitch)} })
            canvas.picked(dist<=2 ? best : -1)
        }
    }
}
