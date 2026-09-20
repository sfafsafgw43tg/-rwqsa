# -*- coding: utf-8 -*-
"""Start the native PrOximAl desktop application (no web server)."""
import os
from pathlib import Path
import sys
import traceback


def launch():
    try:
        from app.desktop import main
        main()
    except Exception:
        # pythonw has no terminal: never let a startup error disappear silently.
        folder = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'PrOximAl'
        folder.mkdir(parents=True, exist_ok=True)
        log = folder / 'startup-error.log'
        log.write_text(traceback.format_exc(), encoding='utf-8')
        message = f'Nie można uruchomić PrOximAl. Uruchom ponownie instalator.bat.\nSzczegóły: {log}'
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, 'PrOximAl edit', 0x10)
        else:
            print(message, file=sys.stderr)
            traceback.print_exc()
        raise SystemExit(1)


if __name__ == '__main__':
    launch()
