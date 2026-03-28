"""
Windows 前景視窗偵測
- 取得目前前景 App 的 exe 名稱、友善名稱、emoji
- 若是瀏覽器，透過 UI Automation 直接讀取網址列 URL
"""
import os
import ctypes
import ctypes.wintypes as wintypes

try:
    import uiautomation as auto
    HAS_UIA = True
except Exception:
    HAS_UIA = False

# ── exe → (友善名稱, emoji) ──────────────────────────────────────
_APP_MAP: dict[str, tuple[str, str]] = {
    'chrome.exe':    ('Google Chrome',   '🌐'),
    'msedge.exe':   ('Microsoft Edge',  '🌐'),
    'firefox.exe':  ('Firefox',         '🌐'),
    'brave.exe':    ('Brave',           '🌐'),
    'opera.exe':    ('Opera',           '🌐'),
    'vivaldi.exe':  ('Vivaldi',         '🌐'),
    'explorer.exe': ('File Explorer',   '📁'),
    'code.exe':     ('VS Code',         '💻'),
    'notepad.exe':  ('Notepad',         '📝'),
    'notepad++.exe':('Notepad++',       '📝'),
    'winword.exe':  ('Word',            '📄'),
    'excel.exe':    ('Excel',           '📊'),
    'powerpnt.exe': ('PowerPoint',      '📊'),
    'acrobat.exe':  ('Acrobat',         '📕'),
    'acrord32.exe': ('Acrobat Reader',  '📕'),
}

_BROWSER_EXES = frozenset(
    ('chrome.exe', 'msedge.exe', 'firefox.exe', 'brave.exe', 'opera.exe', 'vivaldi.exe'))

_EMPTY_INFO: dict = {
    'exe': '', 'app_name': '', 'icon': '🖥️',
    'title': '', 'is_browser': False, 'url': '',
}


# ════════════════════════════════════════════════════════════════
def get_active_window_info() -> dict:
    """
    必須在 overlay 顯示「之前」呼叫，否則 tkinter overlay 會成為前景視窗。

    回傳：
      exe        str   e.g. 'chrome.exe'
      app_name   str   e.g. 'Google Chrome'
      icon       str   emoji
      title      str   視窗標題
      is_browser bool
      url        str   瀏覽器網址（無則為 ''）
    """
    try:
        hwnd  = ctypes.windll.user32.GetForegroundWindow()
        title = _window_title(hwnd)
        exe   = _exe_name(hwnd)

        app_name, icon = _APP_MAP.get(exe, (exe.replace('.exe', '').capitalize(), '🖥️'))
        is_browser     = exe in _BROWSER_EXES
        url            = _browser_url(hwnd, exe) if is_browser else ''

        return {
            'exe':        exe,
            'app_name':   app_name,
            'icon':       icon,
            'title':      title,
            'is_browser': is_browser,
            'url':        url,
        }
    except Exception:
        return _EMPTY_INFO.copy()


# ── 內部工具 ─────────────────────────────────────────────────────

def _window_title(hwnd: int) -> str:
    n   = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _exe_name(hwnd: int) -> str:
    pid = wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        hProc = ctypes.windll.kernel32.OpenProcess(
            0x1000, False, pid.value)       # PROCESS_QUERY_LIMITED_INFORMATION
        if not hProc:
            return ''
        buf  = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        ctypes.windll.kernel32.QueryFullProcessImageNameW(
            hProc, 0, buf, ctypes.byref(size))
        ctypes.windll.kernel32.CloseHandle(hProc)
        return os.path.basename(buf.value).lower()
    except Exception:
        return ''


def _browser_url(hwnd: int, exe: str) -> str:
    """UI Automation 從瀏覽器網址列讀取 URL（需 uiautomation 套件）。"""
    if not HAS_UIA:
        return ''
    try:
        win = auto.ControlFromHandle(hwnd)

        if exe in ('chrome.exe', 'msedge.exe', 'brave.exe',
                   'opera.exe', 'vivaldi.exe'):
            # Chromium 系：網址列是視窗內第一個 Edit control
            edit = win.EditControl(searchDepth=12)
            if edit.Exists(maxSearchSeconds=1.5):
                val = edit.GetValuePattern().Value.strip()
                if val and len(val) > 4:
                    return val if val.startswith('http') else f'https://{val}'

        elif exe == 'firefox.exe':
            # Firefox：AutomationId = 'urlbar-input'
            edit = win.EditControl(AutomationId='urlbar-input', searchDepth=15)
            if not edit.Exists(maxSearchSeconds=0.5):
                edit = win.EditControl(searchDepth=15)
            if edit.Exists(maxSearchSeconds=0.5):
                val = edit.GetValuePattern().Value.strip()
                if val:
                    return val if val.startswith('http') else f'https://{val}'

    except Exception:
        pass
    return ''
