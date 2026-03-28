"""
翻譯彈窗 UI
- 自動偵測語言，帶入對應欄位
- 🔊 朗讀英文
- ⚙ 設定：字體大小 / 主題
- 📋 每個文字區塊頂部都有複製按鈕
"""
import os
import tkinter as tk
import threading

import settings as _cfg
from tts_engine import SpeakSession, engine_name, HAS_EDGE_TTS, HAS_PYGAME

# 載入 .env（ANTHROPIC_API_KEY 等）
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    pass

try:
    import anthropic as _anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    from deep_translator import GoogleTranslator
    HAS_TRANSLATOR = True
except ImportError:
    HAS_TRANSLATOR = False

try:
    import pyperclip
    HAS_CLIP = True
except ImportError:
    HAS_CLIP = False

# ── 主題定義 ─────────────────────────────────────────────────────
THEMES: dict[str, dict] = {
    'mocha': {                          # Catppuccin Mocha（深色）
        'bg':           '#1e1e2e',
        'input_bg':     '#2a2a3e',
        'text':         '#cdd6f4',
        'text_dim':     '#6c7086',
        'border':       '#45475a',
        'btn_on_bg':    '#89b4fa',
        'btn_on_fg':    '#1e1e2e',
        'btn_off_bg':   '#313244',
        'btn_off_fg':   '#cdd6f4',
        'status_ok':    '#a6e3a1',
        'status_err':   '#f38ba8',
        'swap':         '#cba6f7',
        'speak_idle':   '#f9e2af',
        'speak_active': '#fab387',
        'copy_fg':      '#89b4fa',
    },
    'latte': {                          # Catppuccin Latte（淺色）
        'bg':           '#eff1f5',
        'input_bg':     '#dce0e8',
        'text':         '#4c4f69',
        'text_dim':     '#8c8fa1',
        'border':       '#bcc0cc',
        'btn_on_bg':    '#1e66f5',
        'btn_on_fg':    '#eff1f5',
        'btn_off_bg':   '#ccd0da',
        'btn_off_fg':   '#4c4f69',
        'status_ok':    '#40a02b',
        'status_err':   '#d20f39',
        'swap':         '#8839ef',
        'speak_idle':   '#df8e1d',
        'speak_active': '#fe640b',
        'copy_fg':      '#1e66f5',
    },
    'nord': {                           # Nord（藍灰深色）
        'bg':           '#2e3440',
        'input_bg':     '#3b4252',
        'text':         '#eceff4',
        'text_dim':     '#7b88a1',
        'border':       '#434c5e',
        'btn_on_bg':    '#88c0d0',
        'btn_on_fg':    '#2e3440',
        'btn_off_bg':   '#434c5e',
        'btn_off_fg':   '#eceff4',
        'status_ok':    '#a3be8c',
        'status_err':   '#bf616a',
        'swap':         '#b48ead',
        'speak_idle':   '#ebcb8b',
        'speak_active': '#d08770',
        'copy_fg':      '#88c0d0',
    },
}

THEME_LABELS = {'mocha': '🌙 Mocha', 'latte': '☀️ Latte', 'nord': '❄️ Nord'}

# C 是執行期可變動的顏色字典（theme 切換時 in-place 更新）
C: dict = dict(THEMES['mocha'])

FONT_UI = ('Segoe UI', 10)


# ════════════════════════════════════════════════════════════════
class TranslatorWindow:

    def __init__(self, root: tk.Tk):
        self.root           = root
        self.win            = None
        self.mode           = 'en_to_zh'
        self._job           = None
        self._speak_session: SpeakSession | None = None
        self._speaking      = False
        self._settings_win  = None

        # 載入設定
        cfg = _cfg.load()
        self._font_size  = int(cfg.get('font_size', 14))
        self._theme_name = cfg.get('theme', 'mocha')
        C.update(THEMES.get(self._theme_name, THEMES['mocha']))

    # ── 字體屬性 ─────────────────────────────────────────────────
    @property
    def _font_body(self) -> tuple:
        return ('Segoe UI', self._font_size)

    # ═══════════════════════════════════════════════════════════
    # 公開 API
    # ═══════════════════════════════════════════════════════════
    def show(self, clipboard_text: str = ''):
        if self.win and self.win.winfo_exists():
            self._force_foreground()
            if clipboard_text:
                self._auto_fill(clipboard_text)
            return
        self._build_ui()
        if clipboard_text:
            self._auto_fill(clipboard_text)

    # ═══════════════════════════════════════════════════════════
    # 強制前景
    # ═══════════════════════════════════════════════════════════
    def _force_foreground(self):
        win = self.win
        win.deiconify()
        win.attributes('-topmost', True)
        win.lift()
        win.focus_force()
        win.after(150, lambda: win.attributes('-topmost', False))

    # ═══════════════════════════════════════════════════════════
    # 語言偵測
    # ═══════════════════════════════════════════════════════════
    @staticmethod
    def _detect_lang(text: str) -> str:
        if not text:
            return 'en'
        cjk = sum(1 for c in text
                  if '\u4e00' <= c <= '\u9fff' or '\u3040' <= c <= '\u30ff')
        return 'zh' if (cjk / len(text)) > 0.15 else 'en'

    def _auto_fill(self, text: str):
        lang = self._detect_lang(text)
        if lang == 'en' and self.mode != 'en_to_zh':
            self.mode = 'en_to_zh'
            self._refresh_mode()
        elif lang == 'zh' and self.mode != 'zh_to_en':
            self.mode = 'zh_to_en'
            self._refresh_mode()
        self._set_source(text)

    # ═══════════════════════════════════════════════════════════
    # 建立 UI
    # ═══════════════════════════════════════════════════════════
    def _build_ui(self):
        win = tk.Toplevel(self.root)
        self.win = win
        win.title('Quick Translator')
        win.configure(bg=C['bg'])
        win.resizable(True, True)
        win.bind('<Escape>', lambda e: win.withdraw())
        win.bind('<F5>', lambda e: self._f5_speak())
        win.protocol('WM_DELETE_WINDOW', win.withdraw)

        W, H = 520, 360
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f'{W}x{H}+{sw - W - 24}+{(sh - H) // 2}')

        self._build_header(win)
        self._build_panels(win)
        self._build_footer(win)
        self._refresh_mode()

    # ── Header ──────────────────────────────────────────────────
    def _build_header(self, win):
        hdr = tk.Frame(win, bg=C['bg'], pady=10)
        hdr.pack(fill='x', padx=14)

        tk.Label(hdr, text='⚡ Quick Translator',
                 bg=C['bg'], fg=C['text'],
                 font=('Segoe UI', 11, 'bold')).pack(side='left')

        # ✕ close
        tk.Button(hdr, text='✕', font=('Segoe UI', 12),
                  bg=C['bg'], fg=C['text_dim'], relief='flat', cursor='hand2',
                  activebackground=C['input_bg'], activeforeground=C['text'],
                  bd=0, highlightthickness=0,
                  command=lambda: win.withdraw()).pack(side='right')

        # ⚙ settings
        tk.Button(hdr, text='⚙', font=('Segoe UI', 12),
                  bg=C['bg'], fg=C['text_dim'], relief='flat', cursor='hand2',
                  activebackground=C['input_bg'], activeforeground=C['text'],
                  bd=0, highlightthickness=0,
                  command=self._open_settings).pack(side='right', padx=(0, 6))

        # 語言切換
        toggle = tk.Frame(hdr, bg=C['bg'])
        toggle.pack(side='left', padx=16)

        self.btn_en_zh = tk.Button(
            toggle, text='英 → 中', font=FONT_UI,
            padx=14, pady=5, relief='flat', cursor='hand2',
            bd=0, highlightthickness=0,
            command=lambda: self._set_mode('en_to_zh'))
        self.btn_en_zh.pack(side='left', padx=2)

        self.btn_zh_en = tk.Button(
            toggle, text='中 → 英', font=FONT_UI,
            padx=14, pady=5, relief='flat', cursor='hand2',
            bd=0, highlightthickness=0,
            command=lambda: self._set_mode('zh_to_en'))
        self.btn_zh_en.pack(side='left', padx=2)

        tk.Button(
            toggle, text='⇄', font=('Segoe UI', 13),
            padx=8, pady=3, bg=C['bg'], fg=C['swap'],
            relief='flat', cursor='hand2', bd=0, highlightthickness=0,
            activebackground=C['input_bg'],
            command=self._swap).pack(side='left', padx=6)

    # ── 主面板 ───────────────────────────────────────────────────
    def _build_panels(self, win):
        frame = tk.Frame(win, bg=C['bg'])
        frame.pack(fill='both', expand=True, padx=14, pady=4)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(2, weight=1)
        frame.rowconfigure(1, weight=1)

        # ── 左側 header row ──────────────────────────────────
        left_hdr = tk.Frame(frame, bg=C['bg'])
        left_hdr.grid(row=0, column=0, sticky='ew', pady=(0, 4))

        self.lbl_left = tk.Label(left_hdr, bg=C['bg'], fg=C['text_dim'],
                                 font=('Segoe UI', 9))
        self.lbl_left.pack(side='left')

        self.btn_speak_left = self._make_speak_btn(left_hdr)
        self.btn_speak_left.pack(side='left', padx=(6, 0))

        # ✨ 優化英文
        self.btn_optimize = tk.Button(
            left_hdr, text='✨ 優化', font=('Segoe UI', 9),
            bg=C['btn_off_bg'], fg=C['text'],
            relief='flat', cursor='hand2',
            padx=8, pady=1,
            bd=0, highlightthickness=0,
            activebackground=C['btn_on_bg'],
            activeforeground=C['btn_on_fg'],
            command=self._optimize_english)
        # 顯示/隱藏由 _refresh_mode 控制

        # 📋 複製來源
        self.btn_copy_src = tk.Button(
            left_hdr, text='📋', font=('Segoe UI', 9),
            bg=C['bg'], fg=C['copy_fg'], relief='flat',
            cursor='hand2', bd=0, highlightthickness=0,
            activebackground=C['input_bg'],
            command=self._copy_src)
        self.btn_copy_src.pack(side='right')

        # ── 右側 header row ──────────────────────────────────
        right_hdr = tk.Frame(frame, bg=C['bg'])
        right_hdr.grid(row=0, column=2, sticky='ew', pady=(0, 4))

        self.lbl_right = tk.Label(right_hdr, bg=C['bg'], fg=C['text_dim'],
                                  font=('Segoe UI', 9))
        self.lbl_right.pack(side='left')

        self.btn_speak_right = self._make_speak_btn(right_hdr)
        self.btn_speak_right.pack(side='left', padx=(6, 0))

        # 📋 複製譯文
        self.btn_copy_dst = tk.Button(
            right_hdr, text='📋', font=('Segoe UI', 9),
            bg=C['bg'], fg=C['copy_fg'], relief='flat',
            cursor='hand2', bd=0, highlightthickness=0,
            activebackground=C['input_bg'],
            command=self._copy_dst)
        self.btn_copy_dst.pack(side='right')

        # ── 左側輸入框 ────────────────────────────────────────
        left_wrap = tk.Frame(frame, bg=C['border'], padx=1, pady=1)
        left_wrap.grid(row=1, column=0, sticky='nsew')
        self.src = tk.Text(
            left_wrap, bg=C['input_bg'], fg=C['text'],
            insertbackground=C['text'], font=self._font_body,
            wrap='word', relief='flat', padx=10, pady=8, undo=True)
        self.src.pack(fill='both', expand=True)
        self.src.bind('<KeyRelease>', self._on_input)

        # ── 分隔線 ────────────────────────────────────────────
        tk.Frame(frame, bg=C['border'], width=1).grid(
            row=1, column=1, sticky='ns', padx=8)

        # ── 右側譯文框 ────────────────────────────────────────
        right_wrap = tk.Frame(frame, bg=C['border'], padx=1, pady=1)
        right_wrap.grid(row=1, column=2, sticky='nsew')
        self.dst = tk.Text(
            right_wrap, bg=C['input_bg'], fg=C['text'],
            insertbackground=C['text'], font=self._font_body,
            wrap='word', relief='flat', padx=10, pady=8,
            state='disabled')
        self.dst.pack(fill='both', expand=True)

    def _make_speak_btn(self, parent) -> tk.Button:
        return tk.Button(
            parent, text='🔊', font=('Segoe UI', 9),
            bg=C['bg'], fg=C['speak_idle'],
            relief='flat', cursor='hand2', padx=2,
            bd=0, highlightthickness=0,
            activebackground=C['input_bg'],
            command=self._toggle_speak)

    # ── Footer ──────────────────────────────────────────────────
    def _build_footer(self, win):
        foot = tk.Frame(win, bg=C['bg'], pady=8)
        foot.pack(fill='x', padx=14)

        tk.Button(
            foot, text='清除', font=FONT_UI, padx=10, pady=3,
            bg=C['btn_off_bg'], fg=C['text_dim'],
            relief='flat', cursor='hand2',
            bd=0, highlightthickness=0,
            activebackground=C['border'],
            command=self._clear).pack(side='left')

        self.lbl_status = tk.Label(
            foot, text='', bg=C['bg'], fg=C['status_ok'],
            font=('Segoe UI', 9))
        self.lbl_status.pack(side='left', padx=12)

        eng = engine_name()
        tk.Label(foot, text=f'🔈 {eng}',
                 bg=C['bg'], fg=C['text_dim'],
                 font=('Segoe UI', 8)).pack(side='right', padx=(0, 4))

    # ═══════════════════════════════════════════════════════════
    # ⚙ 設定視窗
    # ═══════════════════════════════════════════════════════════
    def _open_settings(self):
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.lift()
            self._settings_win.focus_force()
            return

        sw = tk.Toplevel(self.root)
        self._settings_win = sw
        sw.title('設定')
        sw.configure(bg=C['bg'])
        sw.resizable(False, False)
        sw.attributes('-topmost', True)
        sw.bind('<Escape>', lambda e: sw.destroy())

        W  = 300
        px = self.win.winfo_x() + 20 if (self.win and self.win.winfo_exists()) else 200
        py = self.win.winfo_y() + 60 if (self.win and self.win.winfo_exists()) else 200

        # ── 字體大小 ──────────────────────────────────────────
        tk.Frame(sw, bg=C['border'], height=1).pack(fill='x')
        sec1 = tk.Frame(sw, bg=C['bg'])
        sec1.pack(fill='x', padx=18, pady=(14, 10))

        tk.Label(sec1, text='字體大小', bg=C['bg'], fg=C['text'],
                 font=('Segoe UI', 10, 'bold')).pack(anchor='w')

        size_row = tk.Frame(sec1, bg=C['bg'])
        size_row.pack(anchor='w', pady=(6, 0))

        size_var = tk.IntVar(value=self._font_size)

        def _dec():
            v = max(8, size_var.get() - 1)
            size_var.set(v)
            _preview_font(v)

        def _inc():
            v = min(24, size_var.get() + 1)
            size_var.set(v)
            _preview_font(v)

        def _preview_font(v):
            if self.win and self.win.winfo_exists():
                self.src.config(font=('Segoe UI', v))
                self.dst.config(font=('Segoe UI', v))

        btn_style = dict(bg=C['btn_off_bg'], fg=C['text'], relief='flat',
                         font=('Segoe UI', 12), cursor='hand2',
                         padx=10, pady=2, bd=0, highlightthickness=0,
                         activebackground=C['btn_on_bg'],
                         activeforeground=C['btn_on_fg'])

        tk.Button(size_row, text='－', command=_dec, **btn_style).pack(side='left')

        size_lbl = tk.Label(size_row, textvariable=size_var,
                            bg=C['bg'], fg=C['text'],
                            font=('Segoe UI', 12, 'bold'), width=3)
        size_lbl.pack(side='left', padx=8)

        tk.Button(size_row, text='＋', command=_inc, **btn_style).pack(side='left')

        tk.Label(sec1, text='範圍 8 – 24　預設 12',
                 bg=C['bg'], fg=C['text_dim'],
                 font=('Segoe UI', 8)).pack(anchor='w', pady=(4, 0))

        # ── 主題 ──────────────────────────────────────────────
        tk.Frame(sw, bg=C['border'], height=1).pack(fill='x')
        sec2 = tk.Frame(sw, bg=C['bg'])
        sec2.pack(fill='x', padx=18, pady=(14, 10))

        tk.Label(sec2, text='主題', bg=C['bg'], fg=C['text'],
                 font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(0, 6))

        theme_var = tk.StringVar(value=self._theme_name)

        for key, label in THEME_LABELS.items():
            rb = tk.Radiobutton(
                sec2, text=label, variable=theme_var, value=key,
                bg=C['bg'], fg=C['text'],
                selectcolor=C['input_bg'],
                activebackground=C['bg'], activeforeground=C['btn_on_bg'],
                font=('Segoe UI', 10), cursor='hand2',
                relief='flat', bd=0)
            rb.pack(anchor='w', pady=2)

        # ── 套用 / 取消 ───────────────────────────────────────
        tk.Frame(sw, bg=C['border'], height=1).pack(fill='x')
        btn_row = tk.Frame(sw, bg=C['bg'])
        btn_row.pack(fill='x', padx=18, pady=10)

        def _apply():
            new_size  = size_var.get()
            new_theme = theme_var.get()
            changed_theme = (new_theme != self._theme_name)

            self._font_size  = new_size
            self._theme_name = new_theme
            _cfg.save({'font_size': new_size, 'theme': new_theme})

            if changed_theme:
                sw.destroy()
                self._rebuild_with_theme(new_theme)
            else:
                _preview_font(new_size)
                sw.destroy()

        tk.Button(btn_row, text='套用', font=FONT_UI,
                  bg=C['btn_on_bg'], fg=C['btn_on_fg'],
                  relief='flat', padx=16, pady=5, cursor='hand2',
                  bd=0, highlightthickness=0,
                  command=_apply).pack(side='left')

        tk.Button(btn_row, text='取消', font=FONT_UI,
                  bg=C['btn_off_bg'], fg=C['text_dim'],
                  relief='flat', padx=16, pady=5, cursor='hand2',
                  bd=0, highlightthickness=0,
                  command=sw.destroy).pack(side='left', padx=(8, 0))

        sw.update_idletasks()
        h = sw.winfo_reqheight()
        sw.geometry(f'{W}x{h}+{px}+{py}')

    # ── 主題切換（重建視窗）─────────────────────────────────────
    def _rebuild_with_theme(self, theme_name: str):
        src_text = ''
        mode     = self.mode
        if self.win and self.win.winfo_exists():
            src_text = self.src.get('1.0', 'end-1c')
            self.win.destroy()
            self.win = None

        C.update(THEMES.get(theme_name, THEMES['mocha']))
        self.mode = mode
        self._build_ui()
        if src_text:
            self._set_source(src_text)
            self._translate_now()

    # ═══════════════════════════════════════════════════════════
    # 模式切換
    # ═══════════════════════════════════════════════════════════
    def _set_mode(self, mode):
        self.mode = mode
        self._refresh_mode()
        self._translate_now()

    def _refresh_mode(self):
        if not self.win:
            return
        if self.mode == 'en_to_zh':
            self.btn_en_zh.config(bg=C['btn_on_bg'], fg=C['btn_on_fg'])
            self.btn_zh_en.config(bg=C['btn_off_bg'], fg=C['btn_off_fg'])
            self.lbl_left.config(text='English')
            self.lbl_right.config(text='中文')
            self.btn_speak_left.pack(side='left', padx=(6, 0))
            self.btn_speak_right.pack_forget()
            self.btn_optimize.pack(side='left', padx=(8, 0))
        else:
            self.btn_en_zh.config(bg=C['btn_off_bg'], fg=C['btn_off_fg'])
            self.btn_zh_en.config(bg=C['btn_on_bg'], fg=C['btn_on_fg'])
            self.lbl_left.config(text='中文')
            self.lbl_right.config(text='English')
            self.btn_speak_right.pack(side='left', padx=(6, 0))
            self.btn_speak_left.pack_forget()
            self.btn_optimize.pack_forget()
        self._update_speak_btns()

    def _swap(self):
        src_text = self.src.get('1.0', 'end-1c')
        dst_text = self.dst.get('1.0', 'end-1c')
        self._stop_speak()
        self.mode = 'zh_to_en' if self.mode == 'en_to_zh' else 'en_to_zh'
        self._refresh_mode()
        self._set_source(dst_text)
        if src_text:
            self._set_dst(src_text)

    # ═══════════════════════════════════════════════════════════
    # ✨ AI 優化英文
    # ═══════════════════════════════════════════════════════════
    def _optimize_english(self):
        import urllib.request
        import json as _json
        import socket
        import subprocess
        import shutil
        import time

        text = self.src.get('1.0', 'end-1c').strip()
        if not text:
            return

        self.btn_optimize.config(state='disabled', text='處理中…')
        self._set_status('AI 優化中…')

        prompt = (
            'Fix any spelling and grammar errors in the following English text. '
            'Return ONLY the corrected text with no explanation, '
            'no quotes, and no extra commentary:\n\n' + text
        )

        def _ollama_running():
            try:
                s = socket.create_connection(('localhost', 11434), timeout=1)
                s.close()
                return True
            except Exception:
                return False

        def _run():
            ollama_exe = (shutil.which('ollama') or
                          r'C:\Users\USER\AppData\Local\Programs\Ollama\ollama.exe')
            proc          = None
            we_started_it = False

            try:
                if not _ollama_running():
                    self.win.after(0, lambda: self._set_status('啟動 Ollama…'))
                    proc = subprocess.Popen(
                        [ollama_exe, 'serve'],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    we_started_it = True
                    # 等待 Ollama 就緒（最多 20 秒）
                    for _ in range(40):
                        if _ollama_running():
                            break
                        time.sleep(0.5)
                    else:
                        raise RuntimeError('Ollama 啟動逾時')
                    self.win.after(0, lambda: self._set_status('AI 優化中…'))

                payload = _json.dumps({
                    'model': 'gemma3:4b',
                    'messages': [{'role': 'user', 'content': prompt}],
                    'stream': False,
                }).encode()

                req = urllib.request.Request(
                    'http://localhost:11434/api/chat',
                    data=payload,
                    headers={'Content-Type': 'application/json'},
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data      = _json.loads(resp.read())
                    corrected = data['message']['content'].strip()

                def _apply():
                    self._set_source(corrected)
                    self._set_status('英文已優化 ✓')
                    self.btn_optimize.config(state='normal', text='✨ 優化')
                    self.win.after(2500, lambda: self._set_status(''))

                self.win.after(0, _apply)

            except Exception as e:
                def _err(m=str(e)):
                    self._set_status(f'優化失敗：{m}', error=True)
                    self.btn_optimize.config(state='normal', text='✨ 優化')
                self.win.after(0, _err)

            finally:
                # 用完就關閉 Ollama，不佔記憶體
                if we_started_it:
                    time.sleep(1)
                    subprocess.run(
                        ['taskkill', '/F', '/IM', 'ollama.exe'],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )

        threading.Thread(target=_run, daemon=True).start()

    # ═══════════════════════════════════════════════════════════
    # 🔊 語音朗讀
    # ═══════════════════════════════════════════════════════════
    def _get_english_text(self) -> str:
        if self.mode == 'en_to_zh':
            return self.src.get('1.0', 'end-1c').strip()
        else:
            return self.dst.get('1.0', 'end-1c').strip()

    def _f5_speak(self):
        """F5：英翻中模式才觸發，朗讀左側英文區塊"""
        if self.mode == 'en_to_zh':
            self._toggle_speak()

    def _toggle_speak(self):
        if self._speaking:
            self._stop_speak()
        else:
            self._start_speak()

    def _start_speak(self):
        text = self._get_english_text()
        if not text:
            self._set_status('沒有英文文字可以朗讀', error=True)
            self.win.after(1800, lambda: self._set_status(''))
            return
        self._speaking = True
        self._update_speak_btns()
        self._set_status('🔊 產生語音中…' if HAS_EDGE_TTS else '🔊 朗讀中…')

        def _on_done():
            if self.win and self.win.winfo_exists():
                self.win.after(0, self._on_speak_done)

        def _on_error(msg):
            if self.win and self.win.winfo_exists():
                self.win.after(0, lambda: self._set_status(f'TTS 錯誤：{msg}', error=True))

        self._speak_session = SpeakSession(text, on_done=_on_done, on_error=_on_error)
        self._speak_session.start()

    def _stop_speak(self):
        if self._speak_session:
            self._speak_session.stop()
            self._speak_session = None
        self._on_speak_done()

    def _on_speak_done(self):
        self._speaking = False
        self._speak_session = None
        self._update_speak_btns()
        if self.lbl_status.cget('text').startswith('🔊'):
            self._set_status('')

    def _update_speak_btns(self):
        if not self.win:
            return
        cfg = dict(text='⏹', fg=C['speak_active']) if self._speaking \
            else dict(text='🔊', fg=C['speak_idle'])
        self.btn_speak_left.config(**cfg)
        self.btn_speak_right.config(**cfg)

    # ═══════════════════════════════════════════════════════════
    # 翻譯
    # ═══════════════════════════════════════════════════════════
    def _on_input(self, _event=None):
        if self._job:
            self.win.after_cancel(self._job)
        self._job = self.win.after(600, self._translate_now)

    def _translate_now(self):
        if not HAS_TRANSLATOR:
            self._set_status('未安裝 deep-translator', error=True)
            return
        text = self.src.get('1.0', 'end-1c').strip()
        if not text:
            self._set_dst('')
            self._set_status('')
            return

        src_lang = 'en'    if self.mode == 'en_to_zh' else 'zh-TW'
        tgt_lang = 'zh-TW' if self.mode == 'en_to_zh' else 'en'
        self._set_status('翻譯中…')

        def _run():
            try:
                result = GoogleTranslator(source=src_lang, target=tgt_lang).translate(text)
                if self.win and self.win.winfo_exists():
                    self.win.after(0, lambda: self._set_dst(result))
                    self.win.after(0, lambda: self._set_status(''))
            except Exception as e:
                if self.win and self.win.winfo_exists():
                    self.win.after(0, lambda: self._set_status(f'翻譯錯誤：{e}', error=True))

        threading.Thread(target=_run, daemon=True).start()

    # ═══════════════════════════════════════════════════════════
    # 輔助
    # ═══════════════════════════════════════════════════════════
    def _set_source(self, text: str):
        if not self.win:
            return
        self.src.delete('1.0', 'end')
        self.src.insert('1.0', text)
        self._on_input()

    def _set_dst(self, text: str):
        self.dst.config(state='normal')
        self.dst.delete('1.0', 'end')
        if text:
            self.dst.insert('1.0', text)
        self.dst.config(state='disabled')

    def _set_status(self, msg: str, error: bool = False):
        color = C['status_err'] if error else C['status_ok']
        self.lbl_status.config(text=msg, fg=color)

    def _clear(self):
        self._stop_speak()
        self._set_source('')
        self._set_dst('')
        self._set_status('')

    def _copy_src(self):
        text = self.src.get('1.0', 'end-1c').strip()
        if not text:
            return
        self._do_copy(text)
        orig = self.btn_copy_src.cget('fg')
        self.btn_copy_src.config(text='✓', fg=C['status_ok'])
        self.win.after(900, lambda: self.btn_copy_src.config(text='📋', fg=C['copy_fg']))

    def _copy_dst(self):
        text = self.dst.get('1.0', 'end-1c').strip()
        if not text:
            return
        self._do_copy(text)
        self.btn_copy_dst.config(text='✓', fg=C['status_ok'])
        self.win.after(900, lambda: self.btn_copy_dst.config(text='📋', fg=C['copy_fg']))

    def _do_copy(self, text: str):
        if HAS_CLIP:
            import pyperclip
            pyperclip.copy(text)
        else:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
