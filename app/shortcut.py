"""Create a Windows desktop shortcut and convert the supplied PNG to an ICO."""
from pathlib import Path
import os
import subprocess
import sys
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent


def prepare_icon():
    candidates = [folder / name for folder in (ROOT, ROOT / 'app/assets')
                  for name in ('csssanvas.png', '1.png')]
    source = next((path for path in candidates if path.is_file()), None)
    if source:
        with Image.open(source) as image:
            image = image.convert('RGBA')
            image.thumbnail((256, 256), Image.Resampling.LANCZOS)
            canvas = Image.new('RGBA', (256, 256))
            canvas.alpha_composite(image, ((256 - image.width) // 2, (256 - image.height) // 2))
    else:
        # Clearly a fallback, not a recreation of the missing user's icon.
        canvas = Image.new('RGBA', (256, 256), '#202226')
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((62, 52, 91, 201), fill='#c8d5e5')
        draw.rounded_rectangle((70, 52, 198, 149), radius=35, fill='#c8d5e5')
        draw.rounded_rectangle((92, 78, 169, 122), radius=15, fill='#202226')
    target = ROOT / 'app/assets/proximal.ico'
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return target


def create_shortcut():
    if sys.platform != 'win32':
        raise RuntimeError('Automatyczny skrót jest przeznaczony dla Windows.')
    icon = prepare_icon()
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    if not pythonw.is_file():
        raise RuntimeError('Nie znaleziono pythonw.exe w środowisku aplikacji.')
    # Pass paths via environment variables, never interpolate them as PowerShell code.
    env = {**os.environ, 'PROX_ROOT': str(ROOT), 'PROX_PYTHON': str(pythonw), 'PROX_ICON': str(icon)}
    script = r'''
$ErrorActionPreference = 'Stop'
$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$s = $ws.CreateShortcut((Join-Path $desktop 'PrOximAl.lnk'))
$s.TargetPath = $env:PROX_PYTHON
$s.Arguments = '"' + (Join-Path $env:PROX_ROOT 'uruchom.py') + '"'
$s.WorkingDirectory = $env:PROX_ROOT
$s.IconLocation = $env:PROX_ICON + ',0'
$s.Description = 'PrOximAl edit - lokalny edytor PDF'
$s.Save()
'''
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                   env=env, check=True, timeout=30)


if __name__ == '__main__':
    create_shortcut()
    print('Utworzono skrót PrOximAl na pulpicie.')
