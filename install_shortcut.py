"""
產生 icon.ico 並在桌面建立 Quick Translator 捷徑
執行：python install_shortcut.py
"""
import os
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw

APP_DIR = Path(__file__).parent.resolve()
ICO_PATH = APP_DIR / 'icon.ico'


def make_icon() -> None:
    """重用 main.py 的圖示設計，輸出多尺寸 .ico"""
    sizes = [256, 128, 64, 48, 32, 16]
    frames = []

    for size in sizes:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        d   = ImageDraw.Draw(img)
        s   = size

        d.ellipse([0, 0, s, s], fill='#313244')
        d.ellipse([int(s*.04), int(s*.04), int(s*.96), int(s*.96)], fill='#1e1e2e')
        d.ellipse([int(s*.04), int(s*.04), int(s*.96), int(s*.96)],
                  outline='#45475a', width=max(1, int(s*.015)))

        # 閃電（依比例縮放）
        r = s / 256
        pts = [(int(x*r), int(y*r)) for x, y in [
            (148, 18), (82, 128), (118, 128),
            (108, 238), (174, 118), (138, 118), (158, 18),
        ]]
        shadow = [(x+max(1,int(4*r)), y+max(1,int(4*r))) for x, y in pts]
        d.polygon(shadow, fill='#313244')
        d.polygon(pts, fill='#89b4fa')
        if s >= 32:
            d.polygon(pts, outline='#cdd6f4', width=max(1, int(3*r)))

        frames.append(img)

    frames[0].save(ICO_PATH, format='ICO', sizes=[(f.width, f.height) for f in frames],
                   append_images=frames[1:])
    print(f'[OK] icon.ico → {ICO_PATH}')


def create_shortcut() -> None:
    """用 PowerShell WScript.Shell 在桌面建立 .lnk 捷徑"""
    # 找 pythonw.exe（與目前 python.exe 同目錄）
    pythonw = Path(sys.executable).parent / 'pythonw.exe'
    if not pythonw.exists():
        pythonw = Path(sys.executable)   # fallback

    main_py   = APP_DIR / 'main.py'
    icon_loc  = str(ICO_PATH).replace("'", "''")
    target    = str(pythonw).replace("'", "''")
    args      = f'"{main_py}"'.replace("'", "''")
    work_dir  = str(APP_DIR).replace("'", "''")

    ps = f"""
$ws = New-Object -ComObject WScript.Shell
$desktop = [System.Environment]::GetFolderPath('Desktop')
$lnk = $ws.CreateShortcut("$desktop\\Quick Translator.lnk")
$lnk.TargetPath     = '{target}'
$lnk.Arguments      = '{args}'
$lnk.WorkingDirectory = '{work_dir}'
$lnk.IconLocation   = '{icon_loc}'
$lnk.Description    = 'Quick Translator'
$lnk.WindowStyle    = 7
$lnk.Save()
Write-Host '[OK] shortcut created'
"""
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-Command', ps],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(result.stdout.strip())
        print(f'[OK] 桌面捷徑已建立：Quick Translator.lnk')
    else:
        print('[ERROR]', result.stderr.strip())
        sys.exit(1)


if __name__ == '__main__':
    make_icon()
    create_shortcut()
