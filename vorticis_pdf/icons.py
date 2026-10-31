"""Ícones vetoriais do aplicativo (SVG 24×24, traço), coloridos conforme o estado do botão."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

NORMAL = "#3b4250"
ACTIVE = "#ffffff"
DISABLED = "#b4bac4"
ACCENT = "#d6232d"

_P = {
    # arquivo
    "open": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v1"/><path d="M3 7v10a2 2 0 0 0 2 2h12.5a2 2 0 0 0 1.9-1.4L21.8 11a1 1 0 0 0-1-1.3H8.2a2 2 0 0 0-1.9 1.4L3.6 19"/>',
    "save": '<path d="M5 3h11l5 5v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M7 3v5h8V3"/><rect x="7" y="13" width="10" height="8" rx="1"/>',
    "save_as": '<path d="M13 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v4"/><path d="M7 3v5h8V3"/><path d="M7 21v-6h5"/><path d="M19.5 14.5l2 2-5 5H14.5v-2z"/>',
    "print": '<path d="M6 9V3h12v6"/><rect x="2.5" y="9" width="19" height="8" rx="2"/><path d="M6 14h12v7H6z"/><circle cx="18" cy="12" r=".6" fill="currentColor"/>',
    "undo": '<path d="M9 14L4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    "redo": '<path d="M15 14l5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>',
    "zoom_in": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3M11 8v6M8 11h6"/>',
    "zoom_out": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3M8 11h6"/>',
    "fit_width": '<path d="M3 4v16M21 4v16"/><path d="M7 12h10M7 12l3-3M7 12l3 3M17 12l-3-3M17 12l-3 3"/>',
    "fit_page": '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8l-2-2M15 8l2-2M9 16l-2 2M15 16l2 2"/>',
    "organize": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "rotate_left": '<path d="M3 4v5h5"/><path d="M3.5 9A8.5 8.5 0 1 1 5 17"/>',
    "rotate_right": '<path d="M21 4v5h-5"/><path d="M20.5 9A8.5 8.5 0 1 0 19 17"/>',
    "merge": '<path d="M8 3v5a4 4 0 0 0 4 4 4 4 0 0 1 4 4v5"/><path d="M16 3v5a4 4 0 0 1-4 4"/><path d="M13 18l3 3 3-3"/>',
    "split": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4L8.1 15.9M14.5 14.5L20 20M8.1 8.1L12 12"/>',
    "convert": '<path d="M4 8h13l-3-3M20 16H7l3 3"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    "history": '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M5 7l1 13a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1l1-13M9 7V4h6v3"/>',
    "pages": '<rect x="7" y="3" width="12" height="15" rx="2"/><path d="M5 7v12a2 2 0 0 0 2 2h9"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    # ferramentas
    "select": '<path d="M5 3l14 7-6 2-2 6z"/>',
    "pan": '<path d="M8 13V5.5a1.5 1.5 0 0 1 3 0V12"/><path d="M11 11V4.5a1.5 1.5 0 0 1 3 0V12"/><path d="M14 11V6.5a1.5 1.5 0 0 1 3 0V13"/><path d="M17 9.5a1.5 1.5 0 0 1 3 0V15a6 6 0 0 1-6 6h-1.5a6 6 0 0 1-4.6-2.2L4.6 15a1.6 1.6 0 0 1 2.3-2.2L8 14"/>',
    "edit_text": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    "add_text": '<path d="M5 6V4h14v2M12 4v16M9 20h6"/>',
    "highlight": '<path d="M9 11l-5 5v4h4l5-5"/><path d="M14 4l6 6-7 7-6-6z"/><path d="M15 21h6"/>',
    "rect": '<rect x="3.5" y="5.5" width="17" height="13" rx="2"/>',
    "whiteout": '<path d="M7 21h13"/><path d="M5.5 16.5l9-9a2 2 0 0 1 2.8 0l1.2 1.2a2 2 0 0 1 0 2.8L12 18H7.5z"/><path d="M10 12l4 4"/>',
    "note": '<path d="M4 5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-5 4z"/><path d="M8 8h8M8 12h5"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="9.5" r="1.8"/><path d="M21 16l-5-5-9 9"/>',
    "crop": '<path d="M6 2v14a2 2 0 0 0 2 2h14"/><path d="M2 6h14a2 2 0 0 1 2 2v14"/>',
    "font": '<path d="M4 20L10 4h1l6 16M6.5 14h8"/><path d="M17 20h4"/>',
}


def _svg(name: str, color: str) -> bytes:
    body = _P[name].replace("currentColor", color)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
            f'{body}</svg>').encode()


def _pixmap(name, color, size):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(_svg(name, color))).render(p, QRectF(0, 0, size, size))
    p.end()
    return pm


@lru_cache(maxsize=None)
def icon(name: str, color: str = NORMAL, active: str = ACTIVE) -> QIcon:
    """Ícone com cores para os estados normal, marcado (botão ativo) e desabilitado."""
    ic = QIcon()
    for size in (16, 20, 24, 32, 48):
        ic.addPixmap(_pixmap(name, color, size), QIcon.Normal, QIcon.Off)
        ic.addPixmap(_pixmap(name, active, size), QIcon.Normal, QIcon.On)
        ic.addPixmap(_pixmap(name, active, size), QIcon.Active, QIcon.On)
        ic.addPixmap(_pixmap(name, DISABLED, size), QIcon.Disabled, QIcon.Off)
    return ic


def accent(name: str) -> QIcon:
    return icon(name, ACCENT, ACTIVE)
