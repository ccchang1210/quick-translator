"""
Quick Translator
  Ctrl+C × 2  → 翻譯剪貼簿文字
  Ctrl+X      → 框選螢幕區域 → OCR → 動作選單
  系統匣圖示  → 右鍵選單 / 雙擊開啟翻譯視窗
"""
import sys
import time
import queue
import threading
import tkinter as tk

try:
    import keyboard
except ImportError:
    print("請先安裝依賴: pip install -r requirements.txt")
    sys.exit(1)

try:
    import pyperclip
except ImportError:
    pyperclip = None

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

from translator_window import TranslatorWindow
from screen_capture    import SnipOverlay
from action_menu       import ActionMenu
from ticktick_client   import TickTickClient

# ── 事件佇列（hotkey / tray 執行緒 → tkinter 主執行緒）──────────
trigger_queue: queue.Queue = queue.Queue()

last_ctrl_c_time   = 0.0
DOUBLE_C_THRESHOLD = 0.5

last_ctrl_x_time   = 0.0
ctrl_x_count       = 0
TRIPLE_X_THRESHOLD = 0.5
_ctrl_down         = False


# ════════════════════════════════════════════════════════════════
# 系統匣圖示
# ════════════════════════════════════════════════════════════════
def _make_tray_image() -> Image.Image:
    """產生 256×256 高解析度圖示（圓形漸層底 + 粗閃電）"""
    size = 256
    img  = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d    = ImageDraw.Draw(img)

    # 外圈光暈
    d.ellipse([0, 0, size, size], fill='#313244')
    # 主圓背景
    d.ellipse([10, 10, size - 10, size - 10], fill='#1e1e2e')
    # 內圈細邊框
    d.ellipse([10, 10, size - 10, size - 10], outline='#45475a', width=4)

    # 粗大閃電（座標按 256 比例）
    pts = [
        (148, 18),   # 頂右
        (82,  128),  # 中左
        (118, 128),  # 中右偏左
        (108, 238),  # 底
        (174, 118),  # 中右
        (138, 118),  # 中左偏右
        (158, 18),   # 頂右閉合
    ]
    # 陰影層（深色偏移 2px，增加立體感）
    shadow = [(x + 4, y + 4) for x, y in pts]
    d.polygon(shadow, fill='#313244')
    # 主體
    d.polygon(pts, fill='#89b4fa')
    # 高光邊框
    d.polygon(pts, outline='#cdd6f4', width=3)

    return img


def _setup_tray(root: tk.Tk, window: TranslatorWindow) -> None:
    if not HAS_TRAY:
        return

    def _show_translator(icon=None, item=None):
        trigger_queue.put(('translate', ''))

    def _show_snip(icon=None, item=None):
        trigger_queue.put(('snip', ''))

    def _quit(icon=None, item=None):
        icon.stop()
        root.after(0, root.quit)

    menu = pystray.Menu(
        pystray.MenuItem('⚡  Quick Translator', None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('翻譯視窗',          _show_translator, default=True),
        pystray.MenuItem('框選識別 (Ctrl+X)', _show_snip),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('結束',              _quit),
    )

    icon = pystray.Icon(
        name    = 'quick_translator',
        icon    = _make_tray_image(),
        title   = 'Quick Translator',
        menu    = menu,
    )

    # 雙擊 = 開啟翻譯視窗
    icon.on_activate = _show_translator

    # 在背景執行緒跑 pystray（不阻塞 tkinter mainloop）
    t = threading.Thread(target=icon.run, daemon=True)
    t.start()


# ════════════════════════════════════════════════════════════════
# Hotkey 處理
# ════════════════════════════════════════════════════════════════
def _on_ctrl_x():
    global last_ctrl_x_time, ctrl_x_count
    now = time.time()
    if now - last_ctrl_x_time < TRIPLE_X_THRESHOLD:
        ctrl_x_count += 1
    else:
        ctrl_x_count = 1
    last_ctrl_x_time = now
    if ctrl_x_count >= 3:
        ctrl_x_count = 0
        trigger_queue.put(('snip', ''))


def _on_ctrl_c():
    global last_ctrl_c_time
    now = time.time()
    if now - last_ctrl_c_time < DOUBLE_C_THRESHOLD:
        last_ctrl_c_time = 0.0
        clip = ''
        if pyperclip:
            try:
                clip = pyperclip.paste() or ''
            except Exception:
                pass
        trigger_queue.put(('translate', clip))
    else:
        last_ctrl_c_time = now


# ── tkinter 主執行緒輪詢佇列 ─────────────────────────────────
def poll_trigger(root, window, snip):
    try:
        while True:
            action, data = trigger_queue.get_nowait()
            if action == 'translate':
                window.show(data)
            elif action == 'snip':
                snip.start()
    except queue.Empty:
        pass
    root.after(100, lambda: poll_trigger(root, window, snip))


# ════════════════════════════════════════════════════════════════
# 主程式
# ════════════════════════════════════════════════════════════════
def main():
    root = tk.Tk()
    root.withdraw()

    window   = TranslatorWindow(root)
    ticktick = TickTickClient()

    menu = ActionMenu(
        root              = root,
        translator_window = window,
        ticktick_client   = ticktick,
    )

    snip = SnipOverlay(
        root       = root,
        on_capture = lambda text, img, info: menu.show(text, img, info),
    )

    def _global_hook(event):
        global _ctrl_down
        if event.name in ('ctrl', 'left ctrl', 'right ctrl'):
            _ctrl_down = (event.event_type == 'down')
        elif event.event_type == 'down' and _ctrl_down and event.name == 'c':
            _on_ctrl_c()

    keyboard.hook(_global_hook)
    keyboard.add_hotkey('ctrl+x', _on_ctrl_x, suppress=False)

    _setup_tray(root, window)

    root.after(100, lambda: poll_trigger(root, window, snip))

    print("=" * 44)
    print("  Quick Translator 已在背景執行")
    print("  Ctrl+C × 2  →  翻譯選取文字")
    print("  Ctrl+X      →  框選畫面識別文字")
    print("  系統匣圖示  →  右鍵選單")
    print("  在此終端按 Ctrl+C 一次  →  結束")
    print("=" * 44)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\n已結束。")
        sys.exit(0)


if __name__ == '__main__':
    main()
