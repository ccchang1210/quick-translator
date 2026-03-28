"""
使用者設定：讀寫 settings.json
"""
import json
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings.json')

DEFAULTS: dict = {
    'font_size': 14,
    'theme':     'mocha',
}


def load() -> dict:
    s = DEFAULTS.copy()
    try:
        with open(_PATH, encoding='utf-8') as f:
            s.update(json.load(f))
    except Exception:
        pass
    return s


def save(s: dict) -> None:
    with open(_PATH, 'w', encoding='utf-8') as f:
        json.dump(s, f, indent=2, ensure_ascii=False)
