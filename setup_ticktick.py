"""
TickTick OAuth2 一次性授權設定

執行方式：python setup_ticktick.py
完成後會產生 ticktick_token.json，之後程式自動使用。

前置步驟：
  1. 前往 https://developer.ticktick.com/manage
  2. 建立新的 App（Redirect URI 填 http://localhost:8765/callback）
  3. 複製 Client ID 與 Client Secret
  4. 填入 .env 檔，或直接在本腳本執行時輸入
"""
import os
import sys
import json
import time
import webbrowser
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs

_DIR         = os.path.dirname(os.path.abspath(__file__))
ENV_FILE     = os.path.join(_DIR, '.env')
TOKEN_FILE   = os.path.join(_DIR, 'ticktick_token.json')

AUTH_URL     = 'https://ticktick.com/oauth/authorize'
TOKEN_URL    = 'https://ticktick.com/oauth/token'
REDIRECT_URI = 'http://localhost:8765/callback'
SCOPE        = 'tasks:write tasks:read'
PORT         = 8765


# ── 讀取 .env ────────────────────────────────────────────────
def _read_env() -> tuple[str, str]:
    cid = csec = ''
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k == 'TICKTICK_CLIENT_ID':     cid  = v
                    if k == 'TICKTICK_CLIENT_SECRET': csec = v
    return cid, csec


def _write_env(cid: str, csec: str):
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding='utf-8') as f:
            lines = f.readlines()

    keys_written = set()
    new_lines = []
    for line in lines:
        if line.startswith('TICKTICK_CLIENT_ID='):
            new_lines.append(f'TICKTICK_CLIENT_ID={cid}\n')
            keys_written.add('id')
        elif line.startswith('TICKTICK_CLIENT_SECRET='):
            new_lines.append(f'TICKTICK_CLIENT_SECRET={csec}\n')
            keys_written.add('sec')
        else:
            new_lines.append(line)

    if 'id' not in keys_written:
        new_lines.append(f'TICKTICK_CLIENT_ID={cid}\n')
    if 'sec' not in keys_written:
        new_lines.append(f'TICKTICK_CLIENT_SECRET={csec}\n')

    with open(ENV_FILE, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)


# ── OAuth2 callback server ────────────────────────────────────
_auth_code: str | None = None

class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if 'code' in params:
            _auth_code = params['code'][0]
            body = b'<html><body><h2>TickTick authorized OK - can close this tab.</h2></body></html>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, *_):
        pass   # suppress server logs


def _wait_for_code(timeout: int = 120) -> str | None:
    server = HTTPServer(('localhost', PORT), _CallbackHandler)
    server.timeout = 2
    deadline = time.time() + timeout
    while time.time() < deadline and _auth_code is None:
        server.handle_request()
    server.server_close()
    return _auth_code


# ── 主流程 ────────────────────────────────────────────────────
def main():
    print('=' * 52)
    print('  TickTick OAuth2 設定精靈')
    print('=' * 52)
    print()

    cid, csec = _read_env()

    if not cid:
        print('請輸入 TickTick App 的 Client ID：', end='')
        cid = input().strip()
    else:
        print(f'已讀取 Client ID：{cid[:8]}...')

    if not csec:
        print('請輸入 TickTick App 的 Client Secret：', end='')
        csec = input().strip()
    else:
        print('已讀取 Client Secret。')

    if not cid or not csec:
        print('[錯誤] Client ID 或 Client Secret 不能為空。')
        sys.exit(1)

    _write_env(cid, csec)
    print('\n.env 已儲存。')

    # ── 開啟瀏覽器授權 ──────────────────────────────────────
    params = {
        'client_id':     cid,
        'scope':         SCOPE,
        'response_type': 'code',
        'redirect_uri':  REDIRECT_URI,
    }
    auth_link = f'{AUTH_URL}?{urlencode(params)}'
    print(f'\n即將開啟瀏覽器，請在 TickTick 頁面點擊「允許」...')
    webbrowser.open(auth_link)

    print('等待授權回調（最多 120 秒）...')
    code = _wait_for_code(timeout=120)

    if not code:
        print('[錯誤] 授權逾時，請重試。')
        sys.exit(1)

    print('取得授權碼，正在換取 Access Token...')

    # ── 換取 token ──────────────────────────────────────────
    resp = requests.post(
        TOKEN_URL,
        auth=(cid, csec),
        data={
            'code':         code,
            'grant_type':   'authorization_code',
            'redirect_uri': REDIRECT_URI,
        },
        timeout=15,
    )
    resp.raise_for_status()
    token = resp.json()
    token['expires_at'] = time.time() + token.get('expires_in', 3600)

    with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
        json.dump(token, f, indent=2)

    print(f'\n授權成功！Token 已儲存至 {TOKEN_FILE}')
    print('現在可以使用 TickTick 功能了。')


if __name__ == '__main__':
    main()
