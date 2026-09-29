from __future__ import annotations

import threading
import time
from reed_relay.core.profile import Plan


class PreviewOutput:
    def __init__(self):
        self.held = set()
        self.events = []

    def send(self, key, down):
        self.events.append((time.perf_counter(), key, down))
        if down:
            self.held.add(key)
        else:
            self.held.discard(key)

    def release_all(self):
        for key in list(self.held):
            self.send(key, False)


class PlayerEngine:
    def __init__(self, report=lambda *args: None):
        self.report = report
        self._cancel = threading.Event()
        self._thread = None
        self.output = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, plan: Plan, output, speed=1.0, delay=0, focused=lambda: True):
        if not plan.playable:
            raise ValueError("当前曲谱有无法演奏的音，请先处理检查列表")
        if self.running:
            raise ValueError("演奏正在停止，请稍后重试")
        if not .25 <= speed <= 2 or not 0 <= delay <= 15:
            raise ValueError("速度或倒计时无效")
        self._cancel.clear()
        self.output = output
        self._thread = threading.Thread(target=self._run, args=(plan, speed, delay, focused), daemon=True)
        self._thread.start()

    def stop(self):
        self._cancel.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

    def _run(self, plan, speed, delay, focused):
        message = "演奏结束"
        try:
            begin = time.perf_counter() + delay
            self.report("state", "倒计时" if delay else "演奏中")
            while time.perf_counter() < begin:
                if self._cancel.wait(.01):
                    message = "已停止"
                    return
                self.report("countdown", max(0, begin - time.perf_counter()))
            self.report("state", "演奏中")
            last_report = 0
            for event in plan.events:
                target = event.at_ms / 1000 / speed
                while True:
                    elapsed = time.perf_counter() - begin
                    if self._cancel.is_set():
                        message = "已停止"
                        return
                    if not focused():
                        message = "游戏窗口已失焦，已停止并释放按键"
                        return
                    if elapsed - last_report > .04:
                        self.report("progress", elapsed * 1000 * speed)
                        last_report = elapsed
                    if elapsed >= target:
                        break
                    self._cancel.wait(min(.01, target - elapsed))
                self.output.send(event.key, event.down)
                if event.note_id:
                    self.report("note", {"pitch": event.pitch, "down": event.down, "key": event.key})
            while (time.perf_counter() - begin) * 1000 * speed < plan.duration_ms:
                if self._cancel.wait(.01):
                    message = "已停止"
                    return
                if not focused():
                    message = "游戏窗口已失焦，已停止并释放按键"
                    return
                self.report("progress", (time.perf_counter() - begin) * 1000 * speed)
            self.report("progress", plan.duration_ms)
        except Exception as e:
            message = f"演奏失败：{e}"
        finally:
            try:
                self.output.release_all()
            except Exception as e:
                message += f"；释放输入失败：{e}，请手动松开按键"
            self.report("finished", message)
