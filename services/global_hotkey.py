"""全局热键服务 - 使用 Win32 API 注册系统级热键（窗口不在前台也能响应）"""

import ctypes
import ctypes.wintypes
import threading
from typing import Dict, Callable, Optional, Tuple, List

from PySide6.QtCore import QObject, Signal


# Win32 常量
MOD_ALT = 0x0001
MOD_CTRL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

# 虚拟键码映射（常用键）
_VK_MAP = {
    "A": 0x41, "B": 0x42, "C": 0x43, "D": 0x44, "E": 0x45,
    "F": 0x46, "G": 0x47, "H": 0x48, "I": 0x49, "J": 0x4A,
    "K": 0x4B, "L": 0x4C, "M": 0x4D, "N": 0x4E, "O": 0x4F,
    "P": 0x50, "Q": 0x51, "R": 0x52, "S": 0x53, "T": 0x54,
    "U": 0x55, "V": 0x56, "W": 0x57, "X": 0x58, "Y": 0x59, "Z": 0x5A,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "SPACE": 0x20, "RETURN": 0x0D, "ESCAPE": 0x1B,
    "TAB": 0x09, "BACKSPACE": 0x08, "DELETE": 0x2E,
    "INSERT": 0x2D, "HOME": 0x24, "END": 0x23,
    "PAGEUP": 0x21, "PAGEDOWN": 0x22,
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    "PGUP": 0x21, "PGDOWN": 0x22,
}


def parse_shortcut(shortcut_str: str) -> Optional[Tuple[int, int]]:
    """解析快捷键字符串为 (modifiers, vk_code)

    支持格式：
        "Alt+D", "Ctrl+Shift+S", "F5", "Ctrl+F1" 等

    Returns:
        (modifiers, vk_code) 或 None（解析失败）
    """
    parts = [p.strip() for p in shortcut_str.split("+")]
    modifiers = MOD_NOREPEAT  # 防止按住不放重复触发
    vk_code = 0

    for part in parts:
        upper = part.upper()
        if upper in ("ALT",):
            modifiers |= MOD_ALT
        elif upper in ("CTRL", "CONTROL"):
            modifiers |= MOD_CTRL
        elif upper in ("SHIFT",):
            modifiers |= MOD_SHIFT
        elif upper in ("WIN", "META", "SUPER"):
            modifiers |= MOD_WIN
        elif upper in _VK_MAP:
            vk_code = _VK_MAP[upper]
        else:
            return None  # 无法识别

    if vk_code == 0:
        return None

    return (modifiers, vk_code)


class GlobalHotkeyService(QObject):
    """全局热键服务

    在后台线程中运行 Win32 消息循环，监听系统级热键。
    RegisterHotKey / UnregisterHotKey 都在同一后台线程中执行，
    确保 WM_HOTKEY 消息能被正确接收。
    通过 Qt Signal 将热键事件分发到主线程。
    """

    hotkey_triggered = Signal(str)  # 热键名称

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hotkeys: Dict[int, str] = {}  # hotkey_id -> name
        self._next_id = 1
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._running = False
        # 待注册列表：[(name, shortcut_str)] - 在线程启动后由线程内部注册
        self._pending: List[Tuple[str, str]] = []
        self._started_event = threading.Event()

    def register(self, name: str, shortcut_str: str) -> bool:
        """注册一个全局热键（线程启动前调用，热键将在后台线程中实际注册）

        Args:
            name: 热键名称（用于回调识别）
            shortcut_str: 快捷键字符串，如 "Alt+D"

        Returns:
            是否解析成功（实际注册在线程启动后进行）
        """
        parsed = parse_shortcut(shortcut_str)
        if parsed is None:
            print(f"[GlobalHotkey] 无法解析快捷键: {shortcut_str}")
            return False

        self._pending.append((name, shortcut_str))
        return True

    def start(self):
        """启动热键监听线程"""
        if self._running:
            return
        self._running = True
        self._started_event.clear()
        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()
        # 等待线程完成热键注册（最多等2秒）
        self._started_event.wait(timeout=2)

    def stop(self):
        """停止热键监听"""
        self._running = False
        # 向消息循环线程发送退出消息
        if self._thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(
                self._thread_id, WM_QUIT, 0, 0
            )
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._hotkeys.clear()
        self._thread_id = None

    def _message_loop(self):
        """Win32 消息循环（在后台线程中运行）

        关键：RegisterHotKey 和 GetMessageW 必须在同一线程中，
        因为 WM_HOTKEY 消息会发送到调用 RegisterHotKey 的线程的消息队列。
        """
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        user32 = ctypes.windll.user32

        # 在此线程中注册所有待注册的热键
        for name, shortcut_str in self._pending:
            parsed = parse_shortcut(shortcut_str)
            if parsed is None:
                continue
            modifiers, vk_code = parsed
            hotkey_id = self._next_id
            self._next_id += 1

            result = user32.RegisterHotKey(None, hotkey_id, modifiers, vk_code)
            if result:
                self._hotkeys[hotkey_id] = name
                print(f"[GlobalHotkey] 注册成功: {name} = {shortcut_str} (id={hotkey_id})")
            else:
                err = ctypes.GetLastError()
                print(f"[GlobalHotkey] 注册失败: {name} = {shortcut_str}, error={err}")

        self._pending.clear()
        self._started_event.set()  # 通知主线程注册完成

        msg = ctypes.wintypes.MSG()
        while self._running:
            # GetMessage 会阻塞直到有消息
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break

            if msg.message == WM_HOTKEY:
                hotkey_id = msg.wParam
                name = self._hotkeys.get(hotkey_id)
                if name:
                    # 通过 Qt Signal 发到主线程
                    self.hotkey_triggered.emit(name)

        # 线程退出前注销所有热键（必须在同一线程）
        for hotkey_id in list(self._hotkeys.keys()):
            user32.UnregisterHotKey(None, hotkey_id)
        self._hotkeys.clear()
        self._thread_id = None
