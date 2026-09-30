"""Place the passive Qt overlay on the target game's monitor in logical pixels."""
from PySide6.QtGui import QGuiApplication


def position_overlay(window, monitor, position):
    screen = next((s for s in QGuiApplication.screens() if s.name()==monitor), None)
    screen = screen or window.screen() or QGuiApplication.primaryScreen()
    if screen is None: return
    window.setScreen(screen)
    area = screen.availableGeometry()
    window.setWidth(min(560, area.width()-32))
    margin = 24
    if position == "top-left":
        x,y = area.left()+margin, area.top()+margin
    elif position == "bottom-center":
        x,y = area.left()+(area.width()-window.width())//2, area.bottom()-window.height()-margin
    else:
        x,y = area.right()-window.width()-margin, area.top()+margin
    window.setPosition(x,y)
