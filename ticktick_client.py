"""
TickTick API Client（OAuth2）
- 首次使用請執行 python setup_ticktick.py 完成授權
- token 存於 ticktick_token.json（自動 refresh）
"""
import os
import json
import time

_DIR        = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE  = os.path.join(_DIR, 'ticktick_token.json')
ENV_FILE    = os.path.join(_DIR, '.env')

API_BASE    = 'https://api.ticktick.com/open/v1'
TOKEN_URL   = 'https://ticktick.com/oauth/token'


class TickTickClient:

    def __init__(self):
        self.client_id     = ''
        self.client_secret = ''
        self._token        = None
        self._load_env()
        self._load_token()

    # ── 設定讀取 ────────────────────────────────────────────────
    def _load_env(self):
        """從 .env 讀取 TICKTICK_CLIENT_ID / TICKTICK_CLIENT_SECRET"""
        if os.path.exists(ENV_FILE):
            with open(ENV_FILE, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if '=' in line and not line.startswith('#'):
                        k, v = line.split('=', 1)
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k == 'TICKTICK_CLIENT_ID':
                            self.client_id = v
                        elif k == 'TICKTICK_CLIENT_SECRET':
                            self.client_secret = v
        # env vars override
        self.client_id     = os.getenv('TICKTICK_CLIENT_ID',     self.client_id)
        self.client_secret = os.getenv('TICKTICK_CLIENT_SECRET', self.client_secret)

    def _load_token(self):
        if os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE, encoding='utf-8') as f:
                    self._token = json.load(f)
            except Exception:
                self._token = None

    def _save_token(self, token: dict):
        token.setdefault('expires_at', time.time() + token.get('expires_in', 3600))
        self._token = token
        with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
            json.dump(token, f, indent=2)

    # ── 狀態 ────────────────────────────────────────────────────
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self._token)

    # ── Token 管理 ──────────────────────────────────────────────
    def _headers(self) -> dict:
        if not self._token:
            raise RuntimeError('尚未授權，請執行 python setup_ticktick.py')
        if time.time() > self._token.get('expires_at', 0) - 120:
            self._refresh()
        return {
            'Authorization': f'Bearer {self._token["access_token"]}',
            'Content-Type':  'application/json',
        }

    def _refresh(self):
        import requests
        resp = requests.post(
            TOKEN_URL,
            auth=(self.client_id, self.client_secret),
            data={
                'grant_type':    'refresh_token',
                'refresh_token': self._token['refresh_token'],
            },
            timeout=10,
        )
        resp.raise_for_status()
        self._save_token(resp.json())

    # ── API 操作 ────────────────────────────────────────────────
    def create_task(self, title: str, content: str = '',
                    url: str = None) -> dict:
        """
        建立任務到 Inbox。
        url 會附加到 content 開頭，方便在 TickTick 中點擊。
        """
        note = content
        if url and url not in content:
            note = f'{url}\n\n{content}'.strip()

        payload = {
            'title':   title[:200],
            'content': note[:20000],
        }
        import requests
        resp = requests.post(
            f'{API_BASE}/task',
            headers=self._headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
