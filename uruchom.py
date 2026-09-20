# -*- coding: utf-8 -*-
"""KAMELEON PDF — punkt wejścia. Uruchamia lokalny serwer aplikacji."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.webapp import main
if __name__ == "__main__":
    main()
