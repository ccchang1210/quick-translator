"""
截圖 OCR 完成後的動作選單（美化版）

版面：
  ┌──────────────────────────────────────┐
  │ 🌐 Google Chrome          [✕]        │  ← app source
  ├──────────────────────────────────────┤
  │  [縮圖預覽]  340×140 px              │
  ├──────────────────────────────────────┤
  │  🔗 https://...                      │  ← URL (if any)
  ├──────────────────────────────────────┤
  │  📝 識別文字（可編輯）               │
  │  [text box]                          │
  ├──────────────────────────────────────┤
  │  [📋 複製]  [🔍 翻譯]  [✅ TickTick] │
  └──────────────────────────────────────┘
"""
import re
import threading
from datetime import datetime
from PIL import Image, ImageTk

try:
    import pyperclip
    HAS_CLIP = True
except ImportError:
    HAS_CLIP = False

import tkinter as tk

# ── 配色 (Catppuccin Mocha) ─────────────────────────────────────
C = {
    'bg':        '#1e1e2e',
    'surface0':  '#313244',
    'surface1':  '#45475a',
    'overlay0':  '#6c7086',
    'text':      '#cdd6f4',
    'subtext':   '#a6adc8',
    'blue':      '#89b4fa',
    'teal':      '#94e2d5',
    'green':     '#a6e3a1',
    'red':       '#f38ba8',
    'mauve':     '#cba6f7',
    'input_bg':  '#24273a',
}

FONT_TITLE = ('Segoe UI', 10, 'bold')
FONT_LABEL = ('Segoe UI', 9)
FONT_MONO  = ('Consolas', 9)
FONT_BTN   = ('Segoe UI', 10)

THUMB_W, THUMB_H = 360, 160
W = 400   # window width


# ════════════════════════════════════════════════════════════════
# URL 工具
# ════════════════════════════════════════════════════════════════
_URL_RE = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]{4,}', re.IGNORECASE)
_WWW_RE = re.compile(r'www\.[a-zA-Z0-9][-a-zA-Z0-9.]+\.[a-zA-Z]{2,}[/\w.?=%&@#~-]*',
                     re.IGNORECASE)


def _extract_url(raw_text: str) -> str:
    def trim(u): return u.rstrip('.,;:)!?\'">/\\')

    candidates: list[str] = []

    m = _URL_RE.search(raw_text)
    if m:
        candidates.append(trim(m.group(0)))

    m = _WWW_RE.search(raw_text)
    if m:
        candidates.append('https://' + trim(m.group(0)))

    buf = ''
    best = ''
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            buf = ''
            continue
        is_frag = bool(re.match(r'^[/.\w?=&%#~@:-]+$', line))
        buf = (buf + line) if (buf and is_frag) else line
        m = _URL_RE.search(buf)
        if m:
            u = trim(m.group(0))
            if len(u) > len(best):
                best = u

    if best:
        candidates.append(best)

    valid = [u for u in candidates if len(u) > 12]
    return max(valid, key=len) if valid else ''



# ════════════════════════════════════════════════════════════════
def _sep(parent, color=None):
    """1px 分隔線"""
    tk.Frame(parent, bg=color or C['surface1'], height=1).pack(fill='x')


def _label(parent, text, fg=None, font=None, anchor='w', pady=0, padx=0):
    tk.Label(parent, text=text,
             bg=C['bg'], fg=fg or C['subtext'],
             font=font or FONT_LABEL,
             anchor=anchor).pack(anchor='w', padx=padx, pady=pady)


# ════════════════════════════════════════════════════════════════
class ActionMenu:

    def __init__(self, root: tk.Tk, translator_window, ticktick_client):
        self.root       = root
        self.translator = translator_window
        self.ticktick   = ticktick_client
        self._win       = None
        self._thumb_ref = None

    # ── 入口 ────────────────────────────────────────────────────
    def show(self, text: str, image: Image.Image, app_info: dict = None):
        if self._win and self._win.winfo_exists():
            self._win.destroy()

        self._image    = image
        self._app_info = app_info or {}

        browser_url = self._app_info.get('url', '')
        ocr_url     = _extract_url(text)
        best_url    = browser_url or ocr_url

        self._build(text.strip(), best_url)

    # ── 建立 UI ─────────────────────────────────────────────────
    def _build(self, ocr_text: str, found_url: str):
        win = tk.Toplevel(self.root)
        self._win = win
        win.title('Quick Capture')
        win.configure(bg=C['bg'])
        win.attributes('-topmost', True)
        win.resizable(False, False)
        win.bind('<Escape>', lambda e: win.destroy())
        win.protocol('WM_DELETE_WINDOW', win.destroy)
        win.geometry(f'{W}x10')

        # ── 標題列 ──────────────────────────────────────────────
        self._build_header(win)
        _sep(win, C['surface0'])

        # ── 縮圖 ────────────────────────────────────────────────
        self._build_thumb(win)
        _sep(win, C['surface0'])

        # ── URL（永遠顯示）──────────────────────────────────────
        self._url_var = tk.StringVar(value=found_url)
        self._build_url_section(win, found_url)
        _sep(win, C['surface0'])

        # ── OCR 文字 ─────────────────────────────────────────────
        self._build_text_section(win, ocr_text)
        _sep(win, C['surface0'])

        # ── 按鈕 ─────────────────────────────────────────────────
        self._build_buttons(win)

        # ── 狀態列 ───────────────────────────────────────────────
        self._status = tk.Label(win, text='', bg=C['bg'],
                                fg=C['green'], font=FONT_LABEL)
        self._status.pack(pady=(2, 8))

        # 置中偏右定位
        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        h  = win.winfo_reqheight()
        win.geometry(f'{W}x{h}+{sw - W - 28}+{(sh - h) // 2}')

    # ── 標題列 ──────────────────────────────────────────────────
    def _build_header(self, win):
        frm = tk.Frame(win, bg=C['bg'])
        frm.pack(fill='x', padx=14, pady=(10, 8))

        # App 來源（有則顯示，無則顯示預設）
        icon     = self._app_info.get('icon', '✂')
        app_name = self._app_info.get('app_name', '') or '截圖識別'
        source   = f'{icon}  {app_name}'

        tk.Label(frm, text=source, bg=C['bg'], fg=C['text'],
                 font=FONT_TITLE).pack(side='left')

        tk.Button(frm, text='✕', bg=C['bg'], fg=C['overlay0'],
                  relief='flat', font=('Segoe UI', 12), cursor='hand2',
                  activebackground=C['surface0'],
                  activeforeground=C['text'],
                  bd=0, highlightthickness=0,
                  command=win.destroy).pack(side='right')

    # ── 縮圖 ────────────────────────────────────────────────────
    def _build_thumb(self, win):
        frm = tk.Frame(win, bg=C['surface0'])
        frm.pack(fill='x')

        thumb = self._image.copy()
        thumb.thumbnail((THUMB_W, THUMB_H), Image.LANCZOS)
        self._thumb_ref = ImageTk.PhotoImage(thumb)

        tk.Label(frm, image=self._thumb_ref, bg=C['surface0'],
                 cursor='hand2').pack(pady=(8, 4))

        w, h = self._image.size
        tk.Label(frm, text=f'{w} × {h} px', bg=C['surface0'],
                 fg=C['overlay0'], font=('Segoe UI', 8)).pack(pady=(0, 6))

    # ── URL 欄（永遠顯示，可編輯）──────────────────────────────
    def _build_url_section(self, win, found_url: str):
        frm = tk.Frame(win, bg=C['bg'])
        frm.pack(fill='x', padx=14, pady=(8, 6))

        # 標題列：標籤 + 來源 badge
        row = tk.Frame(frm, bg=C['bg'])
        row.pack(fill='x', pady=(0, 4))

        tk.Label(row, text='🔗  網址', bg=C['bg'], fg=C['subtext'],
                 font=FONT_LABEL).pack(side='left')

        if found_url:
            # 顯示來源（browser 或 OCR）
            browser_url = self._app_info.get('url', '')
            source_text = '  ✦ 瀏覽器' if (found_url == browser_url) else '  ✦ OCR 偵測'
            source_color = C['teal'] if (found_url == browser_url) else C['mauve']
            tk.Label(row, text=source_text, bg=C['bg'], fg=source_color,
                     font=('Segoe UI', 8)).pack(side='left', padx=(4, 0))
        else:
            tk.Label(row, text='  （未偵測到，可手動填入）', bg=C['bg'],
                     fg=C['overlay0'], font=('Segoe UI', 8)).pack(side='left')

        # 可編輯的輸入框
        entry = tk.Entry(frm, textvariable=self._url_var,
                         bg=C['input_bg'], fg=C['teal'],
                         insertbackground=C['text'],
                         disabledbackground=C['input_bg'],
                         font=FONT_MONO, relief='flat',
                         highlightthickness=1,
                         highlightbackground=C['surface1'],
                         highlightcolor=C['blue'])
        entry.pack(fill='x', ipady=5)

        # 有內容時右側加一個小複製按鈕
        if found_url:
            def _copy_url():
                url = self._url_var.get().strip()
                if not url:
                    return
                if HAS_CLIP:
                    pyperclip.copy(url)
                else:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(url)
                copy_btn.config(text='✓ 已複製', fg=C['green'])
                win.after(1000, lambda: copy_btn.config(text='複製', fg=C['subtext']))

            copy_btn = tk.Button(frm, text='複製', bg=C['bg'], fg=C['subtext'],
                                 font=('Segoe UI', 8), relief='flat', cursor='hand2',
                                 bd=0, highlightthickness=0, command=_copy_url)
            copy_btn.pack(anchor='e', pady=(2, 0))

    # ── OCR 文字欄 ──────────────────────────────────────────────
    def _build_text_section(self, win, ocr_text: str):
        frm = tk.Frame(win, bg=C['bg'])
        frm.pack(fill='x', padx=14, pady=(8, 6))

        tk.Label(frm, text='📝  識別文字', bg=C['bg'],
                 fg=C['subtext'], font=FONT_LABEL).pack(anchor='w')

        self._text_box = tk.Text(
            frm, height=4,
            bg=C['input_bg'], fg=C['text'],
            insertbackground=C['text'],
            font=FONT_MONO, relief='flat', wrap='word',
            padx=8, pady=6,
            highlightthickness=1,
            highlightbackground=C['surface1'],
            highlightcolor=C['blue'],
            selectbackground=C['surface0'],
        )
        self._text_box.insert('1.0', ocr_text)
        self._text_box.pack(fill='x', pady=(4, 0))

    # ── 按鈕列 ──────────────────────────────────────────────────
    def _build_buttons(self, win):
        frm = tk.Frame(win, bg=C['bg'])
        frm.pack(fill='x', padx=14, pady=(10, 8))

        btn_specs = [
            ('📋  複製',       C['surface0'],  C['text'],    self._do_copy),
            ('🔍  翻譯',       C['surface0'],  C['text'],    self._do_translate),
            ('✅  TickTick',   C['mauve'],     C['bg'],      self._do_ticktick),
        ]
        self._btns = []
        for label, bg, fg, cmd in btn_specs:
            btn = tk.Button(
                frm, text=label, font=FONT_BTN,
                bg=bg, fg=fg, relief='flat',
                padx=12, pady=7, cursor='hand2',
                activebackground=C['blue'],
                activeforeground=C['bg'],
                bd=0, highlightthickness=0,
                command=cmd,
            )
            btn.pack(side='left', padx=(0, 8))
            # hover effect
            _bg, _fg = bg, fg
            btn.bind('<Enter>', lambda e, b=btn: b.config(bg=C['blue'], fg=C['bg']))
            btn.bind('<Leave>', lambda e, b=btn, bg_=_bg, fg_=_fg: b.config(bg=bg_, fg=fg_))
            self._btns.append(btn)

    # ── 取得欄位值 ───────────────────────────────────────────────
    def _cur_url(self) -> str:
        return self._url_var.get().strip()

    def _cur_text(self) -> str:
        return self._text_box.get('1.0', 'end-1c').strip()

    # ════════════════════════════════════════════════════════════
    # 動作
    # ════════════════════════════════════════════════════════════

    def _do_copy(self):
        content = self._cur_url() or self._cur_text()
        if HAS_CLIP:
            pyperclip.copy(content)
        else:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
        self._flash('已複製到剪貼簿 ✓', close=True)

    def _do_translate(self):
        self.translator.show(self._cur_text())
        self._win.destroy()

    def _do_ticktick(self):
        if not self.ticktick.is_configured():
            self._flash('請先執行 python setup_ticktick.py', error=True)
            return

        for b in self._btns:
            b.config(state='disabled')
        self._flash('加入中…')

        url  = self._cur_url()
        text = self._cur_text()
        img  = self._image

        def _run():
            try:
                msg = self._send_to_ticktick(url, text, img)
                self.root.after(0, lambda: self._flash(msg, close=True))
            except Exception as ex:
                self.root.after(0, lambda: self._flash(f'錯誤：{ex}', error=True))

        threading.Thread(target=_run, daemon=True).start()

    def _send_to_ticktick(self, url: str, text: str, img: Image.Image) -> str:
        # 組合 note：識別文字在前，URL 在後
        parts = []
        if text:
            parts.append(text)
        if url:
            parts.append(f'\n🔗 {url}')
        note = '\n'.join(parts)

        # title：識別文字第一行 > 網址 > 預設
        if text:
            lines = [l for l in text.splitlines() if l.strip()]
            title = lines[0][:80] if lines else 'Quick Capture'
        elif url:
            title = url[:80]
        else:
            title = f'Quick Capture {datetime.now().strftime("%m/%d %H:%M")}'

        self.ticktick.create_task(title=title, content=note)

        # 識別文字複製到剪貼簿
        clip_content = text or url
        if clip_content:
            if HAS_CLIP:
                pyperclip.copy(clip_content)
            else:
                self.root.clipboard_clear()
                self.root.clipboard_append(clip_content)
            return '已加入 TickTick，識別文字已複製到剪貼簿 ✓'
        return '已加入 TickTick ✓'

    # ── 狀態訊息 ─────────────────────────────────────────────────
    def _flash(self, msg: str, error: bool = False, close: bool = False):
        if not self._win or not self._win.winfo_exists():
            return
        self._status.config(text=msg, fg=C['red'] if error else C['green'])
        if close:
            self._win.after(2000, self._win.destroy)
