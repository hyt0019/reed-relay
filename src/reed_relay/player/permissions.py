"""Read Windows process tokens to explain input restrictions before playing."""
from __future__ import annotations

import ctypes as c
from ctypes import wintypes as w
import os


class SidAndAttributes(c.Structure):
    _fields_ = [('sid', c.c_void_p), ('attributes', w.DWORD)]


def process_security(pid: int) -> dict:
    if os.name != 'nt':
        raise OSError('进程权限检查仅支持 Windows')
    kernel = c.WinDLL('kernel32', use_last_error=True)
    advapi = c.WinDLL('advapi32', use_last_error=True)
    kernel.OpenProcess.argtypes = (w.DWORD, w.BOOL, w.DWORD)
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = (w.HANDLE,)
    kernel.CloseHandle.restype = w.BOOL
    advapi.OpenProcessToken.argtypes = (w.HANDLE, w.DWORD, c.POINTER(w.HANDLE))
    advapi.OpenProcessToken.restype = w.BOOL
    advapi.GetTokenInformation.argtypes = (w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD))
    advapi.GetTokenInformation.restype = w.BOOL
    advapi.GetSidSubAuthorityCount.argtypes = (c.c_void_p,)
    advapi.GetSidSubAuthorityCount.restype = c.POINTER(w.BYTE)
    advapi.GetSidSubAuthority.argtypes = (c.c_void_p, w.DWORD)
    advapi.GetSidSubAuthority.restype = c.POINTER(w.DWORD)
    process = kernel.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not process:
        raise c.WinError(c.get_last_error())
    token = w.HANDLE()
    try:
        if not advapi.OpenProcessToken(process, 0x8, c.byref(token)):  # TOKEN_QUERY
            raise c.WinError(c.get_last_error())
        try:
            elevation, needed = w.DWORD(), w.DWORD()
            if not advapi.GetTokenInformation(token, 20, c.byref(elevation), c.sizeof(elevation), c.byref(needed)):
                raise c.WinError(c.get_last_error())
            # TOKEN_MANDATORY_LABEL contains a SID pointing inside this buffer.
            advapi.GetTokenInformation(token, 25, None, 0, c.byref(needed))
            if not needed.value:
                raise c.WinError(c.get_last_error())
            buffer = c.create_string_buffer(needed.value)
            if not advapi.GetTokenInformation(token, 25, buffer, len(buffer), c.byref(needed)):
                raise c.WinError(c.get_last_error())
            sid = c.cast(buffer, c.POINTER(SidAndAttributes)).contents.sid
            count = advapi.GetSidSubAuthorityCount(sid).contents.value
            if not count:
                raise OSError('进程权限标识无效')
            level = advapi.GetSidSubAuthority(sid, count-1).contents.value
            return {'pid': pid, 'elevated': bool(elevation.value), 'level': level}
        finally:
            kernel.CloseHandle(token)
    finally:
        kernel.CloseHandle(process)


def compare_input_permissions(player: dict, target: dict) -> dict:
    blocked = player['level'] < target['level']
    can_elevate = blocked and player['level'] < 0x3000 and target['level'] <= 0x3000
    if can_elevate:
        message = '风箱权限低于游戏：请先关闭风箱，再使用「启动风箱（管理员）」重新启动'
    elif blocked:
        message = '目标窗口权限高于风箱，当前无法发送输入；请确认选中了游戏窗口'
    else:
        message = '窗口权限匹配；回到游戏口琴界面后按启停热键开始'
    return {'status': 'blocked' if blocked else 'ready', 'requires_admin': can_elevate,
            'message': message, 'player': player, 'target': target}


def input_permission_status(window: dict) -> dict:
    try:
        return compare_input_permissions(process_security(os.getpid()), process_security(window['pid']))
    except (OSError, KeyError, ValueError) as error:
        # A protected process may deny token reads. Unknown is not proof that
        # input is blocked; retain SendInput's own error handling in that case.
        return {'status': 'unknown', 'requires_admin': False,
                'message': f'未能读取窗口权限：{error}；若游戏以管理员身份运行，请使用管理员启动版'}
