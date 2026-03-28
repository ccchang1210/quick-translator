"""
擷取畫面區域 → OCR → 送入翻譯視窗
觸發：Ctrl+X

OCR 引擎優先順序：
  1. pytesseract + Tesseract-OCR  （英文 + 繁體中文）
  2. 提示安裝訊息
"""
import io
import re
import ctypes
import threading
import tkinter as tk
from PIL import ImageGrab, ImageTk, Image, ImageEnhance, ImageFilter

# 移除 CJK 字元周圍的多餘空格（Tesseract 的已知問題）
_CJK_SPACE = re.compile(
    r'(?<=[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\u3040-\u30ff])[ \t]+'
    r'|'
    r'[ \t]+(?=[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\u3040-\u30ff])'
)

def _clean_cjk_spaces(text: str) -> str:
    return _CJK_SPACE.sub('', text)

try:
    import pytesseract
    import os
    # 明確指定 Tesseract 路徑與語言資料路徑（避免 PATH 未生效的問題）
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    os.environ.setdefault('TESSDATA_PREFIX',
                          os.path.expandvars(r'%USERPROFILE%\tessdata'))
    HAS_TESS = True
except ImportError:
    HAS_TESS = False


# ── DPI 縮放比例（處理 150%/200% 高解析螢幕）────────────────────
def _dpi_scale() -> float:
    try:
        hdc  = ctypes.windll.user32.GetDC(0)
        dpi  = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)   # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi / 96.0
    except Exception:
        return 1.0


# ════════════════════════════════════════════════════════════════
class SnipOverlay:
    """
    全螢幕截圖選取 overlay。
    用法：snip.start()  →  使用者框選  →  on_capture(text, image) 被呼叫。
    """

    def __init__(self, root: tk.Tk, on_capture):
        self.root       = root
        self.on_capture = on_capture   # callback(text, image, app_info)
        self._win       = None

    # ── 入口 ────────────────────────────────────────────────────
    def start(self):
        if self._win and self._win.winfo_exists():
            self._win.destroy()

        # ① 在 overlay 出現前，先記錄當前前景 App（含瀏覽器 URL）
        try:
            from win_utils import get_active_window_info
            self._app_info = get_active_window_info()
        except Exception:
            self._app_info = {}

        # ② 截圖
        self._screenshot = ImageGrab.grab(all_screens=False)
        self._scale      = _dpi_scale()
        self._build()

    # ── 建立全螢幕 overlay ─────────────────────────────────────
    def _build(self):
        win = tk.Toplevel(self.root)
        self._win = win
        win.overrideredirect(True)
        win.attributes('-topmost', True)

        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(f'{sw}x{sh}+0+0')
        win.bind('<Escape>', lambda e: self._cancel())

        # ── 暗化背景截圖 ──────────────────────────────────────
        # 以邏輯解析度顯示（螢幕顯示），但保留原圖供裁切
        display_img  = self._screenshot.resize((sw, sh), Image.LANCZOS)
        dark_layer   = Image.new('RGBA', (sw, sh), (0, 0, 0, 130))
        display_rgba = display_img.convert('RGBA')
        darkened     = Image.alpha_composite(display_rgba, dark_layer).convert('RGB')
        self._bg_tk  = ImageTk.PhotoImage(darkened)

        # ── Canvas ──────────────────────────────────────────────
        canvas = tk.Canvas(win, cursor='crosshair', highlightthickness=0)
        canvas.pack(fill='both', expand=True)
        canvas.create_image(0, 0, anchor='nw', image=self._bg_tk)

        # 提示文字
        canvas.create_rectangle(sw//2 - 190, 16, sw//2 + 190, 46,
                                 fill='#1e1e2e', outline='#45475a')
        canvas.create_text(sw // 2, 31,
                           text='拖曳框選要識別的區域    Esc 取消',
                           fill='#cdd6f4', font=('Segoe UI', 11))

        self._canvas   = canvas
        self._x0 = self._y0 = 0
        self._rect_id  = None
        self._dim_id   = None

        canvas.bind('<ButtonPress-1>',   self._on_press)
        canvas.bind('<B1-Motion>',       self._on_drag)
        canvas.bind('<ButtonRelease-1>', self._on_release)

    # ── 滑鼠事件 ────────────────────────────────────────────────
    def _on_press(self, e):
        self._x0, self._y0 = e.x, e.y
        self._clear_rect()

    def _on_drag(self, e):
        self._clear_rect()
        c = self._canvas
        x0, y0 = self._x0, self._y0
        x1, y1 = e.x, e.y

        # 外框
        self._rect_id = c.create_rectangle(
            x0, y0, x1, y1,
            outline='#89b4fa', width=2)

        # 四角標記（讓框看起來更清晰）
        sz = 6
        for cx, cy in [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]:
            c.create_rectangle(cx - sz, cy - sz, cx + sz, cy + sz,
                               fill='#89b4fa', outline='', tags='corner')

        # 尺寸提示
        w = abs(x1 - x0)
        h = abs(y1 - y0)
        self._dim_id = c.create_text(
            (x0 + x1) // 2, max(y0, y1) + 14,
            text=f'{w} × {h}',
            fill='#a6e3a1', font=('Segoe UI', 9))

    def _on_release(self, e):
        x1 = min(self._x0, e.x)
        y1 = min(self._y0, e.y)
        x2 = max(self._x0, e.x)
        y2 = max(self._y0, e.y)

        if x2 - x1 < 8 or y2 - y1 < 8:
            return    # 太小，忽略

        # 換成物理像素座標裁切原始截圖
        s   = self._scale
        px1, py1 = int(x1 * s), int(y1 * s)
        px2, py2 = int(x2 * s), int(y2 * s)
        region = self._screenshot.crop((px1, py1, px2, py2))
        self._orig_region = region        # 保留未前處理原圖供 action_menu 使用

        self._cancel()
        threading.Thread(target=lambda: self._ocr(region), daemon=True).start()

    # ── 清除矩形繪圖 ────────────────────────────────────────────
    def _clear_rect(self):
        c = self._canvas
        if self._rect_id:
            c.delete(self._rect_id)
            self._rect_id = None
        if self._dim_id:
            c.delete(self._dim_id)
            self._dim_id = None
        c.delete('corner')

    def _cancel(self):
        if self._win and self._win.winfo_exists():
            self._win.destroy()
        self._win = None

    # ── OCR ─────────────────────────────────────────────────────
    def _ocr(self, img: Image.Image):
        raw_img = self._orig_region   # 原始截圖（未前處理）供 action_menu 使用

        if not HAS_TESS:
            self._deliver('[需要安裝 Tesseract-OCR]\n\n'
                          '1. 下載安裝：https://github.com/UB-Mannheim/tesseract/wiki\n'
                          '   ✦ 安裝時勾選 "Additional language data" → chi_tra（繁體中文）\n'
                          '2. pip install pytesseract\n'
                          '3. 重新啟動程式', raw_img)
            return

        try:
            # 前處理：放大 + 灰階 + 對比 + 銳化  → 提升識別率
            w, h  = img.size
            scale = max(1, min(4, 2400 // max(w, h, 1)))
            if scale > 1:
                img = img.resize((w * scale, h * scale), Image.LANCZOS)

            img = img.convert('L')
            img = ImageEnhance.Contrast(img).enhance(2.0)
            img = img.filter(ImageFilter.SHARPEN)

            # 嘗試英文 + 繁體中文，若語言包缺失退回純英文
            try:
                text = pytesseract.image_to_string(
                    img, lang='eng+chi_tra',
                    config='--psm 6 --oem 3')
            except pytesseract.TesseractError:
                text = pytesseract.image_to_string(
                    img, lang='eng',
                    config='--psm 6 --oem 3')

            text = _clean_cjk_spaces(text.strip())
            self._deliver(text, raw_img)

        except Exception as ex:
            self._deliver(f'[OCR 錯誤] {ex}', raw_img)

    def _deliver(self, text: str, image: Image.Image):
        info = getattr(self, '_app_info', {})
        self.root.after(0, lambda: self.on_capture(text, image, info))
