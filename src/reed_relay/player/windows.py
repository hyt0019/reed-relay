from __future__ import annotations

import ctypes as c
from ctypes import wintypes as w
import os
import threading
from .engine import PreviewOutput


VK = {**{chr(n): n for n in range(65, 91)}, **{str(n): 48+n for n in range(10)},
      **{f"F{n}": 111+n for n in range(1, 25)}, "SPACE": 32, "TAB": 9, "ENTER": 13,
      "ESC": 27, "PAUSE": 19, "SHIFT": 16, "CTRL": 17, "ALT": 18, "HOME": 36, "END": 35,
      "INSERT": 45, "DELETE": 46, "PAGEUP": 33, "PAGEDOWN": 34, "UP": 38, "DOWN": 40,
      "LEFT": 37, "RIGHT": 39, ",": 188, ".": 190, ";": 186, "'": 222, "[": 219,
      "]": 221, "\\": 220, "/": 191, "-": 189, "=": 187, "`": 192}


class MOUSEINPUT(c.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD), ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", c.c_size_t)]


class KEYBDINPUT(c.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", c.c_size_t)]


class INPUTUNION(c.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(c.Structure):
    _anonymous_ = ("value",)
    _fields_ = [("type", w.DWORD), ("value", INPUTUNION)]


def user32():
    if os.name != "nt":
        raise RuntimeError("真实按键输入仅支持 Windows；可以使用预演")
    api = c.WinDLL("user32", use_last_error=True)
    api.SendInput.argtypes = (w.UINT, c.POINTER(INPUT), c.c_int)
    api.SendInput.restype = w.UINT
    api.GetForegroundWindow.restype = w.HWND
    api.IsWindow.argtypes = (w.HWND,)
    api.GetWindowThreadProcessId.argtypes = (w.HWND, c.POINTER(w.DWORD))
    api.GetWindowTextLengthW.argtypes = (w.HWND,)
    api.GetWindowTextW.argtypes = (w.HWND, w.LPWSTR, c.c_int)
    api.IsWindowVisible.argtypes = (w.HWND,)
    return api


class WindowsOutput:
    def __init__(self):
        self.api = user32()
        self.held = set()

    def send(self, key, down):
        if key.startswith("MOUSE_"):
            flags = {"MOUSE_LEFT": (2, 4), "MOUSE_RIGHT": (8, 16), "MOUSE_MIDDLE": (32, 64)}[key]
            event = INPUT(type=0, value=INPUTUNION(mi=MOUSEINPUT(0, 0, 0, flags[0 if down else 1], 0, 0)))
        else:
            scan = self.api.MapVirtualKeyW(VK[key], 0)
            flags = 8 | (0 if down else 2)
            if key in {"INSERT", "DELETE", "HOME", "END", "PAGEUP", "PAGEDOWN", "UP", "DOWN", "LEFT", "RIGHT"}:
                flags |= 1
            event = INPUT(type=1, value=INPUTUNION(ki=KEYBDINPUT(0, scan, flags, 0, 0)))
        # Record ownership before insertion: if the OS reports a partial failure,
        # cleanup must still attempt a release.
        if down:
            self.held.add(key)
        if self.api.SendInput(1, c.byref(event), c.sizeof(INPUT)) != 1:
            raise RuntimeError(f"Windows 未接受 {key} 输入（{c.get_last_error()}）；检查窗口权限")
        if not down:
            self.held.discard(key)

    def release_all(self):
        failures = []
        for key in list(self.held):
            try:
                self.send(key, False)
            except Exception as e:
                failures.append(str(e))
        if failures:
            raise RuntimeError("；".join(failures))


def windows():
    if os.name != "nt":
        return []
    api, result = user32(), []
    callback_type = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    @callback_type
    def visit(hwnd, _):
        length = api.GetWindowTextLengthW(hwnd)
        if length and api.IsWindowVisible(hwnd):
            title = c.create_unicode_buffer(length + 1)
            api.GetWindowTextW(hwnd, title, len(title))
            pid = w.DWORD()
            api.GetWindowThreadProcessId(hwnd, c.byref(pid))
            if pid.value != os.getpid():
                result.append({"handle": int(hwnd), "pid": pid.value, "title": title.value})
        return True
    api.EnumWindows(visit, 0)
    return result


def focus_guard(window):
    api = user32()
    hwnd, expected_pid = window["handle"], window["pid"]
    def check():
        if not api.IsWindow(hwnd) or api.GetForegroundWindow() != hwnd:
            return False
        pid = w.DWORD()
        api.GetWindowThreadProcessId(hwnd, c.byref(pid))
        return pid.value == expected_pid
    return check


def window_alive(window):
    api, pid = user32(), w.DWORD()
    if not api.IsWindow(window["handle"]): return False
    api.GetWindowThreadProcessId(window["handle"], c.byref(pid))
    return pid.value == window["pid"]


def held_controls(keys):
    """Read only the configured instrument controls; do not consume key events."""
    api = user32()
    api.GetAsyncKeyState.argtypes = (c.c_int,)
    api.GetAsyncKeyState.restype = w.SHORT
    mouse = {"MOUSE_LEFT":1, "MOUSE_RIGHT":2, "MOUSE_MIDDLE":4}
    return {key for key in keys if api.GetAsyncKeyState(mouse[key] if key in mouse else VK[key]) & 0x8000}


def monitor_name(window):
    class MONITORINFOEX(c.Structure):
        _fields_ = [("cbSize",w.DWORD),("rcMonitor",w.RECT),("rcWork",w.RECT),
                    ("dwFlags",w.DWORD),("szDevice",w.WCHAR*32)]
    api = user32()
    api.MonitorFromWindow.argtypes = (w.HWND,w.DWORD)
    api.MonitorFromWindow.restype = w.HANDLE
    api.GetMonitorInfoW.argtypes = (w.HANDLE,c.POINTER(MONITORINFOEX))
    info = MONITORINFOEX()
    info.cbSize = c.sizeof(info)
    monitor = api.MonitorFromWindow(window["handle"],2)
    return info.szDevice if api.GetMonitorInfoW(monitor,c.byref(info)) else ""


class Hotkeys:
    def __init__(self, callback, report):
        self.callback, self.report = callback, report
        self.stop_event = threading.Event()
        self.thread = None
        self.ready = False
        self.started_event = threading.Event()
        self.error = ""

    def start(self, bindings):
        self.close()
        self.started_event.clear()
        self.error = ""
        if os.name != "nt":
            self.report("此系统只能使用界面按钮；全局热键需要 Windows")
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._listen, args=(dict(bindings),), daemon=True)
        self.thread.start()

    def try_start(self, bindings):
        """Register on the owning thread before committing a changed binding."""
        self.start(bindings)
        self.started_event.wait(timeout=1)
        if not self.ready:
            self.close()
            return False
        return True

    def _listen(self, bindings):
        api, registered, actions = user32(), [], {}
        try:
            for i, (action, binding) in enumerate(bindings.items(), 1):
                parts = binding.split("+")
                mods = 0x4000
                for p in parts[:-1]:
                    mods |= {"ALT": 1, "CTRL": 2, "SHIFT": 4, "WIN": 8}[p]
                if not api.RegisterHotKey(None, i, mods, VK[parts[-1]]):
                    raise RuntimeError(f"{binding} 被其他程序占用，请修改后重新保存")
                registered.append(i)
                actions[i] = action
            self.ready = True
            self.started_event.set()
            self.report("全局热键已注册")
            msg = w.MSG()
            while not self.stop_event.wait(.01):
                while api.PeekMessageW(c.byref(msg), None, 0x312, 0x312, 1):
                    self.callback(actions.get(msg.wParam, ""))
        except Exception as e:
            self.error = str(e)
            self.report(str(e))
        finally:
            self.started_event.set()
            self.ready = False
            for i in registered:
                api.UnregisterHotKey(None, i)

    def close(self):
        self.ready = False
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
        self.thread = None
