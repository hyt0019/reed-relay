import os
import time

import pytest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
import reed_relay.backend as module
from reed_relay.player import permissions
from reed_relay.player.engine import PreviewOutput


@pytest.mark.parametrize('player_level,target_level,status,elevate', [
    (0x2000, 0x3000, 'blocked', True),
    (0x2000, 0x2000, 'ready', False),
    (0x3000, 0x3000, 'ready', False),
    (0x3000, 0x2000, 'ready', False),
    (0x2000, 0x2100, 'blocked', True),
    (0x2000, 0x4000, 'blocked', False),
    (0x3000, 0x4000, 'blocked', False),
])
def test_input_permission_order(player_level, target_level, status, elevate):
    player = {'level':player_level, 'elevated':player_level>=0x3000}
    target = {'level':target_level, 'elevated':target_level>=0x3000}
    result = permissions.compare_input_permissions(player, target)
    assert result['status'] == status and result['requires_admin'] == elevate
    assert result['player'] == player and result['target'] == target


def test_unreadable_target_is_unknown_and_not_assumed_elevated(monkeypatch):
    def denied(pid): raise PermissionError('access denied')
    monkeypatch.setattr(permissions, 'process_security', denied)
    result = permissions.input_permission_status({'pid':123})
    assert result['status'] == 'unknown' and not result['requires_admin']
    assert 'access denied' in result['message']


def test_real_current_process_token_abi():
    if os.name != 'nt': pytest.skip('Windows token ABI')
    first = permissions.process_security(os.getpid())
    second = permissions.process_security(os.getpid())
    assert first == second and 0 <= first['level'] <= 0x5000
    assert permissions.compare_input_permissions(first, second)['status'] == 'ready'


@pytest.fixture
def rig(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv('REED_RELAY_DATA_DIR', str(tmp_path))
    available = [{'handle':100, 'pid':10, 'title':'Game'}, {'handle':200, 'pid':20, 'title':'Other'}]
    monkeypatch.setattr(module, 'windows', lambda:list(available))
    monkeypatch.setattr(module, 'window_alive', lambda window:True)
    monkeypatch.setattr(module, 'focus_guard', lambda window:lambda:True)
    monkeypatch.setattr(module, 'input_permission_status', lambda window:{'status':'ready', 'message':'ready'})
    backend = module.Backend('player', no_hotkeys=True)
    class Keys:
        ready = True
        def close(self): pass
    backend.hotkeys.close()
    backend.hotkeys = Keys()
    backend.loadDemo()
    backend._profile.hotkeys['toggle'] = '0'
    yield app, backend, available
    backend.close()
    app.processEvents()


def test_blocked_input_is_rejected_before_output_and_preserves_custom_hotkey(rig, monkeypatch):
    app, b, available = rig
    blocked = permissions.compare_input_permissions({'level':0x2000,'elevated':False}, {'level':0x3000,'elevated':True})
    monkeypatch.setattr(module, 'input_permission_status', lambda window:blocked)
    def forbidden(): raise AssertionError('must not construct input output')
    monkeypatch.setattr(module, 'WindowsOutput', forbidden)
    b.configurePlayer(False, 1, 0, 0, False, False, 0)
    assert b.inputStatus['requires_admin']
    b.toggle()
    b._on_hotkey('toggle')
    assert not b.engine.running and b.progress == 0
    assert '权限低于游戏' in b.playerStartError
    assert b._profile.hotkeys['toggle'] == '0'


def test_hotkey_callback_starts_when_permissions_match_and_mode_change_stops(rig, monkeypatch):
    app, b, available = rig
    monkeypatch.setattr(module, 'WindowsOutput', PreviewOutput)
    b.configurePlayer(False, 1, 0, 0, False, False, 0)
    b._on_hotkey('toggle')
    time.sleep(.03)
    assert b.engine.running and b.engine.output.held
    output = b.engine.output
    b.configurePlayer(True, 1, 0, 0, False, False, 0)
    assert not b.engine.running and not output.held


def test_refresh_preserves_target_identity_after_reorder_and_title_change(rig):
    app, b, available = rig
    b.configurePlayer(False, 1, 0, 0, False, False, 0)
    available.reverse()
    available[1]['title'] = 'Renamed game'
    b.refreshWindows()
    assert b.targetIndex == 1 and b.windowList[b.targetIndex]['handle'] == 100
    assert b.inputStatus['status'] == 'ready'


def test_recycled_handle_or_missing_window_clears_selection_and_stops(rig, monkeypatch):
    app, b, available = rig
    monkeypatch.setattr(module, 'WindowsOutput', PreviewOutput)
    b.configurePlayer(False, 1, 0, 0, False, False, 0)
    b.toggle()
    time.sleep(.03)
    output = b.engine.output
    available[0] = {'handle':100, 'pid':999, 'title':'Different process'}
    b.refreshWindows()
    assert b.targetIndex == -1 and not b.engine.running and not output.held
    assert b.inputStatus['status'] == 'unselected' and '重新选择' in b.message


def test_closed_target_cannot_start_and_refresh_failure_keeps_selected_identity(rig, monkeypatch):
    app, b, available = rig
    b.configurePlayer(False, 1, 0, 0, False, False, 0)
    def broken(): raise OSError('enumeration failed')
    monkeypatch.setattr(module, 'windows', broken)
    b.refreshWindows()
    assert b.targetIndex == 0 and b.windowList[0]['handle'] == 100
    monkeypatch.setattr(module, 'window_alive', lambda window:False)
    b.toggle()
    assert not b.engine.running and b.inputStatus['status'] == 'closed'
    assert '请刷新' in b.playerStartError
