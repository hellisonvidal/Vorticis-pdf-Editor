# -*- mode: python ; coding: utf-8 -*-
# Gera dist/VorticisPDF/VorticisPDF.exe  (pyinstaller VorticisPDF.spec)
# Modo "onedir": inicia muito mais rápido que um .exe único.
# Antes, baixe os modelos de OCR: python tools/fetch_tessdata.py
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

EXCLUDES = [
    "tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml",
    "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtPdf", "matplotlib", "IPython", "pytest",
    "pymupdf4llm", "pymupdf.layout", "pymupdf_layout", "onnxruntime", "pandas", "networkx",
    "pyhanko.cli", "click",
    "PySide6.QtWebChannel", "PySide6.QtPositioning", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtOpenGL", "PySide6.QtSvgWidgets", "PySide6.QtBluetooth", "PySide6.QtSensors",
]

a = Analysis(
    ["vorticis.py"],
    pathex=[],
    binaries=[],
    datas=[("vorticis_pdf/resources", "vorticis_pdf/resources")]
          + collect_data_files("pyhanko") + collect_data_files("pyhanko_certvalidator"),
    hiddenimports=["win32com.client", "pythoncom", "pywintypes", "pkcs11", "pkcs11.defaults",
                   "pkcs11.util.rsa", "pkcs11.util.ec", "pkcs11.util.x509"]
                  + collect_submodules("pyhanko") + collect_submodules("pyhanko_certvalidator"),
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="VorticisPDF",
    icon="vorticis_pdf/resources/icon.ico",
    console=False,
    version="installer/version_info.txt",
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="VorticisPDF")
