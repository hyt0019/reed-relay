"""Focused keyboard capture; mouse presses are supplied by the binding dialog."""
from PySide6.QtCore import QObject, QEvent, Qt, QTimer, Property, Signal, Slot
from PySide6.QtWidgets import QApplication
from .core.profile import normalize_key
from .player.windows import VK


class BindingCapture(QObject):
    changed = Signal()
    captured = Signal(str, str)
    started = Signal()
    ended = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._target,self._label,self._hint="","",""
        self.timer=QTimer(self);self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.cancel)
        QApplication.instance().installEventFilter(self)

    @Property(bool, notify=changed)
    def active(self): return bool(self._target)
    @Property(str, notify=changed)
    def label(self): return self._label
    @Property(str, notify=changed)
    def hint(self): return self._hint
    @Property(bool, notify=changed)
    def mouseAllowed(self): return not self._target.startswith("hotkey:")

    @Slot(str, str)
    def begin(self, target, label):
        if self.active: self.cancel()
        self._target,self._label,self._hint=target,label,"请按下按键，或在下方区域点击鼠标"
        self.started.emit();self.timer.start(15000);self.changed.emit()

    @Slot()
    def cancel(self):
        if not self.active: return
        self._target="";self.timer.stop();self.changed.emit();self.ended.emit()

    def reject(self, message):
        self._hint=message;self.timer.start(15000);self.changed.emit()

    def accept(self): self.cancel()

    @Slot(int)
    def mouse(self, button):
        if not self.active: return
        if not self.mouseAllowed:
            self.reject("全局热键请使用键盘或 Ctrl / Alt / Shift 组合键");return
        keys={1:"MOUSE_LEFT",2:"MOUSE_RIGHT",4:"MOUSE_MIDDLE"}
        if button in keys: self.captured.emit(self._target,keys[button])

    def eventFilter(self, watched, event):
        if not self.active: return False
        if event.type() == QEvent.Type.ApplicationDeactivate:
            self.cancel();return False
        if event.type() in (QEvent.Type.KeyPress,QEvent.Type.KeyRelease,QEvent.Type.ShortcutOverride):
            if event.type() != QEvent.Type.KeyPress:
                event.accept();return True
            if event.isAutoRepeat(): return True
            if event.key() == Qt.Key.Key_Escape:
                self.cancel();return True
            names={Qt.Key.Key_Control:"CTRL",Qt.Key.Key_Shift:"SHIFT",Qt.Key.Key_Alt:"ALT"}
            if event.key() in names:
                if self.mouseAllowed: self.captured.emit(self._target,names[event.key()])
                else: self._hint=names[event.key()]+" + …";self.changed.emit()
                return True
            key=next((name for name,vk in VK.items() if vk == event.nativeVirtualKey()),None)
            if key is None:
                special={Qt.Key.Key_Space:"SPACE",Qt.Key.Key_Tab:"TAB",Qt.Key.Key_Return:"ENTER",Qt.Key.Key_Enter:"ENTER",
                         Qt.Key.Key_Delete:"DELETE",Qt.Key.Key_Insert:"INSERT",Qt.Key.Key_Home:"HOME",Qt.Key.Key_End:"END",
                         Qt.Key.Key_PageUp:"PAGEUP",Qt.Key.Key_PageDown:"PAGEDOWN",Qt.Key.Key_Left:"LEFT",Qt.Key.Key_Right:"RIGHT",
                         Qt.Key.Key_Up:"UP",Qt.Key.Key_Down:"DOWN",Qt.Key.Key_Pause:"PAUSE"}
                key=special.get(event.key())
                if key is None and Qt.Key.Key_F1 <= event.key() <= Qt.Key.Key_F24:
                    key="F"+str(event.key()-Qt.Key.Key_F1+1)
                if key is None and 0 <= event.key() < 128: key=chr(event.key())
            try: key=normalize_key(key)
            except ValueError:
                self.reject("此按键暂不支持，请换一个按键");return True
            if not self.mouseAllowed:
                mods=[]
                for flag,name in [(Qt.KeyboardModifier.AltModifier,"ALT"),(Qt.KeyboardModifier.ControlModifier,"CTRL"),
                                  (Qt.KeyboardModifier.ShiftModifier,"SHIFT"),(Qt.KeyboardModifier.MetaModifier,"WIN")]:
                    if event.modifiers() & flag: mods.append(name)
                key="+".join(mods+[key])
            self.captured.emit(self._target,key)
            return True
        return False

    def close(self):
        self.cancel()
        QApplication.instance().removeEventFilter(self)
