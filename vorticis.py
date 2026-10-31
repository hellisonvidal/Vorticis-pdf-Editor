"""Launcher usado pelo PyInstaller e para rodar a partir do código-fonte: python vorticis.py"""
import sys

from vorticis_pdf.app import main

if __name__ == "__main__":
    sys.exit(main())
