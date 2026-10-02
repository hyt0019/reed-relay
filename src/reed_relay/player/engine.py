from __future__ import annotations

import threading
import time
from dataclasses import replace
from reed_relay.core.profile import Plan, Event
from reed_relay.core.score import number


def events_from_position(plan: Plan, start_ms: float) -> list[Event]:
    """Rebuild held inputs at the cursor, retaining the source timeline."""
    number(start_ms, "演奏起点", 0, plan.duration_ms)
    held, future = {}, []
    for event in plan.events:
        if event.at_ms <= start_ms:
            if event.down:
                held[event.key] = event
            else:
                held.pop(event.key, None)
        else:
            future.append(event)
    # Resolve boundary releases/presses first, so notes ending at the cursor
    # are not retriggered. Restore modifiers before the note key.
    initial = sorted((replace(event, at_ms=start_ms) for event in held.values()),
                     key=lambda event: event.priority)
    return initial + future


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
        self._position_ms = 0.
        self.result = ""

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    @property
    def position_ms(self):
        return self._position_ms

    def start(self, plan: Plan, output, speed=1.0, delay=0, focused=lambda: True, *,
              start_ms=0., report=None):
        if not plan.playable:
            raise ValueError("当前曲谱有无法演奏的音，请先处理检查列表")
        if self.running:
            raise ValueError("演奏正在停止，请稍后重试")
        number(speed, "演奏速度", .25, 2)
        number(delay, "准备倒计时", 0, 15)
        events = events_from_position(plan, start_ms)
        self._cancel.clear()
        self.output = output
        self._position_ms, self.result = float(start_ms), ""
        # Capture each run's callback/output so callers can tag queued reports.
        self._thread = threading.Thread(target=self._run,
            args=(events, plan.duration_ms, speed, delay, focused, start_ms, output,
                  self.report if report is None else report), daemon=True)
        self._thread.start()

    def stop(self):
        self._cancel.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

    def _run(self, events, duration_ms, speed, delay, focused, start_ms, output, report):
        message = "演奏结束"
        begin = time.perf_counter() + delay

        def position():
            self._position_ms = min(duration_ms, start_ms + max(0., time.perf_counter()-begin)*1000*speed)
            return self._position_ms

        try:
            report("progress", start_ms)
            report("state", "倒计时" if delay else "演奏中")
            while time.perf_counter() < begin:
                if self._cancel.wait(.01):
                    message = "已停止"
                    return
                report("countdown", max(0, begin - time.perf_counter()))
            report("state", "演奏中")
            last_report = 0
            for event in events:
                target = (event.at_ms - start_ms) / 1000 / speed
                while True:
                    elapsed = time.perf_counter() - begin
                    position()
                    if self._cancel.is_set():
                        message = "已停止"
                        return
                    if not focused():
                        message = "游戏窗口已失焦，已停止并释放按键"
                        return
                    if elapsed - last_report > .04:
                        report("progress", self._position_ms)
                        last_report = elapsed
                    if elapsed >= target:
                        break
                    self._cancel.wait(min(.01, target - elapsed))
                output.send(event.key, event.down)
                if event.note_id:
                    report("note", {"pitch": event.pitch, "down": event.down, "key": event.key})
            while position() < duration_ms:
                if self._cancel.wait(.01):
                    message = "已停止"
                    return
                if not focused():
                    message = "游戏窗口已失焦，已停止并释放按键"
                    return
                report("progress", position())
        except Exception as e:
            message = f"演奏失败：{e}"
        finally:
            position()
            try:
                output.release_all()
            except Exception as e:
                message += f"；释放输入失败：{e}，请手动松开按键"
            self.result = message
            report("progress", self._position_ms)
            report("finished", message)
