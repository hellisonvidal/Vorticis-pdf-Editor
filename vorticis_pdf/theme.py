"""Temas visuais do Vorticis PDF Editor: claro, escuro ou seguir o Windows."""
from __future__ import annotations

import sys
from string import Template

from PySide6.QtGui import QColor, QFont, QPalette

LIGHT = dict(
    accent="#d6232d", accent_hover="#e43a43", accent_soft="#fde8e9", accent_text="#d6232d",
    bg="#f5f6f8", surface="#ffffff", surface2="#f0f2f5", hover="#eef0f3", pressed="#e2e5ea",
    border="#e3e6eb", text="#1f2430", muted="#6b7280", disabled="#a0a6b0",
    canvas="#3a3f47", sidebar="#262a31", sidebar_text="#d7dbe0", sidebar_hover="#343a43",
    icon="#3b4250", icon_disabled="#b4bac4", tooltip="#1f2430", scroll="rgba(120,128,140,.45)",
    ok="#1b8a3a", warn="#b26a00", ok_soft="#e8f6ec", ok_border="#bfe5c9", accent_border="#f6c4c7",
    chevron="#4b5563",
)
DARK = dict(
    accent="#e5414a", accent_hover="#f05a62", accent_soft="#3a2226", accent_text="#ff8a90",
    bg="#16181d", surface="#1f2228", surface2="#262a31", hover="#2c3139", pressed="#353b45",
    border="#333842", text="#e6e8ec", muted="#9aa1ad", disabled="#5d6470",
    canvas="#0f1114", sidebar="#191b20", sidebar_text="#c9ced6", sidebar_hover="#2a2e36",
    icon="#d5d9e0", icon_disabled="#5d6470", tooltip="#000000", scroll="rgba(160,168,180,.35)",
    ok="#4cc27a", warn="#f0a640", ok_soft="#1c2e23", ok_border="#2f5a3e", accent_border="#5a2a30",
    chevron="#c9ced6",
)

_current = dict(LIGHT)
_mode = "light"

QSS = Template("""
* { font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", sans-serif; font-size: 10pt; }
QMainWindow, QDialog, QMessageBox, QWizard { background: $bg; color: $text; }
QWidget { color: $text; }
QLabel { background: transparent; }
QToolTip { background: $tooltip; color: white; border: 1px solid $border; padding: 6px 9px; border-radius: 6px; }

#HeaderBar { background: $surface; border: none; border-bottom: 1px solid $border; }
#HeaderBar QToolButton { border: none; border-radius: 8px; padding: 6px; margin: 0 1px; color: $text; }
#HeaderBar QToolButton:hover { background: $hover; }
#HeaderBar QToolButton:pressed { background: $pressed; }
#HeaderBar QToolButton:checked { background: $accent; color: white; }
#HeaderBar QToolButton#Primary { background: $accent; color: white; padding: 6px 12px; font-weight: 600; }
#HeaderBar QToolButton#Primary:hover { background: $accent_hover; }
#HeaderBar QToolButton::menu-indicator { image: none; }
#Sep { background: $border; min-width: 1px; max-width: 1px; margin: 8px 6px; }
#Muted { color: $muted; }

#ToolRail { background: $surface; border: none; border-right: 1px solid $border; }
#ToolRail QToolButton { border: none; border-radius: 10px; padding: 8px; margin: 2px 6px; }
#ToolRail QToolButton:hover { background: $hover; }
#ToolRail QToolButton:checked { background: $accent; }
#RailSep { border-bottom: 1px solid $border; margin: 0 12px 4px 12px; }

QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QTextBrowser {
    background: $surface; color: $text; border: 1px solid $border; border-radius: 8px; padding: 5px 8px;
    selection-background-color: $accent; selection-color: white; }
QAbstractSpinBox { background: $surface; color: $text; border: 1px solid $border; border-radius: 8px;
    padding: 4px 6px; selection-background-color: $accent; selection-color: white; min-height: 20px; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { subcontrol-origin: border; width: 20px;
    border: none; border-left: 1px solid $border; background: transparent; }
QAbstractSpinBox::up-button { subcontrol-position: top right; border-top-right-radius: 8px; }
QAbstractSpinBox::down-button { subcontrol-position: bottom right; border-bottom-right-radius: 8px; }
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover { background: $hover; }
QAbstractSpinBox::up-arrow { image: url(@UP@); width: 10px; height: 10px; }
QAbstractSpinBox::down-arrow { image: url(@DOWN@); width: 10px; height: 10px; }
QComboBox::down-arrow { image: url(@DOWN@); width: 11px; height: 11px; }
QLineEdit:focus, QAbstractSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus { border: 1px solid $accent; }
QLineEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled { color: $disabled; background: $surface2; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: $surface; color: $text; border: 1px solid $border; border-radius: 8px;
    selection-background-color: $accent_soft; selection-color: $text; outline: 0; }
#SearchBox { border-radius: 16px; padding: 6px 12px; background: $surface2; border: 1px solid transparent; }
#SearchBox:focus { background: $surface; border: 1px solid $accent; }

QPushButton { background: $surface; border: 1px solid $border; border-radius: 8px; padding: 7px 14px; color: $text; }
QPushButton:hover { background: $hover; }
QPushButton:pressed { background: $pressed; }
QPushButton:default, QPushButton#Primary { background: $accent; border: 1px solid $accent; color: white; font-weight: 600; }
QPushButton:default:hover, QPushButton#Primary:hover { background: $accent_hover; }
QPushButton:disabled { color: $disabled; background: $surface2; }
#BigAction { text-align: left; padding: 14px 16px; border-radius: 12px; font-size: 10.5pt; }
#BigAction:hover { border: 1px solid $accent; background: $accent_soft; }

QListWidget, QTableWidget, QTreeWidget { background: $surface; color: $text; border: 1px solid $border;
    border-radius: 10px; outline: 0; gridline-color: $border; alternate-background-color: $surface2; }
QListWidget::item { padding: 6px; border-radius: 6px; }
QListWidget::item:selected, QTableWidget::item:selected, QTreeWidget::item:selected { background: $accent_soft; color: $text; }
QHeaderView::section { background: $bg; color: $text; border: none; border-bottom: 1px solid $border; padding: 6px; font-weight: 600; }
QTableCornerButton::section { background: $bg; border: none; }
QTabWidget::pane { border: 1px solid $border; border-radius: 10px; background: $surface; top: -1px; }
QTabBar::tab { padding: 8px 16px; border: none; color: $muted; background: transparent; }
QTabBar::tab:selected { color: $accent_text; border-bottom: 2px solid $accent; font-weight: 600; }
QGroupBox { border: 1px solid $border; border-radius: 10px; margin-top: 14px; padding: 12px 10px 8px; background: $surface; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: $muted; font-weight: 600; }
QCheckBox, QRadioButton { spacing: 7px; background: transparent; }
QCheckBox::indicator, QRadioButton::indicator { width: 15px; height: 15px; border: 1.5px solid $muted; background: $surface; }
QCheckBox::indicator { border-radius: 4px; }
QRadioButton::indicator { border-radius: 9px; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: $accent; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: url(@CHECK@); }
QRadioButton::indicator:checked { background: $accent; border-color: $accent; image: url(@DOT@); }
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled { border-color: $disabled; background: $surface2; }
QListWidget::indicator { width: 15px; height: 15px; border: 1.5px solid $muted; border-radius: 4px; background: $surface; }
QListWidget::indicator:checked { background: $accent; border-color: $accent; image: url(@CHECK@); }

QMenuBar { background: $surface; color: $text; border-bottom: 1px solid $border; padding: 2px 6px; }
QMenuBar::item { padding: 5px 10px; border-radius: 6px; background: transparent; }
QMenuBar::item:selected { background: $hover; }
QMenu { background: $surface; color: $text; border: 1px solid $border; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 26px 7px 12px; border-radius: 6px; }
QMenu::item:selected { background: $accent_soft; color: $text; }
QMenu::item:disabled { color: $disabled; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }
QMenu::icon { padding-left: 8px; }

QScrollBar:vertical { background: transparent; width: 11px; margin: 2px; }
QScrollBar::handle:vertical { background: $scroll; border-radius: 4px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 11px; margin: 2px; }
QScrollBar::handle:horizontal { background: $scroll; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

#ThumbHeader { background: $sidebar; }
#ThumbHeader QLabel { color: $sidebar_text; font-weight: 600; }
QSlider::groove:horizontal { height: 4px; background: #4a505a; border-radius: 2px; }
QSlider::sub-page:horizontal { background: $accent; border-radius: 2px; }
QSlider::handle:horizontal { background: white; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
QSplitter::handle { background: $border; width: 1px; }

QStatusBar { background: $surface; border-top: 1px solid $border; color: $muted; }
QStatusBar QLabel { padding: 0 8px; color: $muted; }
QStatusBar::item { border: none; }
#FontBadge { background: $accent_soft; color: $accent_text; border-radius: 9px; padding: 2px 10px; font-weight: 600; }
#SavedBadge { color: $ok; }
#DirtyBadge { color: $warn; }

#Welcome { background: $bg; }
#WelcomeCard { background: $surface; border: 1px solid $border; border-radius: 18px; }
#WelcomeTitle { font-size: 20pt; font-weight: 700; color: $text; }
#WelcomeSub { color: $muted; font-size: 10.5pt; }
#RecentList { border: none; background: transparent; }
#RecentList::item { padding: 8px; }
#RecentList::item:hover { background: $hover; }
#Badge { background: $accent_soft; color: $accent_text; border-radius: 10px; padding: 3px 10px; font-weight: 600; }
#AiBox { background: $accent_soft; border: 1px solid $accent_border; border-radius: 12px; padding: 12px; }
#FreeBox { background: $ok_soft; border: 1px solid $ok_border; border-radius: 12px; padding: 12px; }
#Paper { background: white; color: black; border: 1px solid $border; border-radius: 8px; padding: 8px; }
QProgressDialog QLabel { padding: 6px; }
QProgressBar { border: none; background: $surface2; border-radius: 6px; height: 10px; text-align: center; color: $text; }
QProgressBar::chunk { background: $accent; border-radius: 6px; }
""")


def system_prefers_dark() -> bool:
    if sys.platform.startswith("win"):
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            v, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
            return v == 0
        except OSError:
            return False
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def current() -> dict:
    return _current


def is_dark() -> bool:
    return _mode == "dark"


def c(name: str) -> str:
    """Cor do tema atual (para estilos em código)."""
    return _current[name]


def _svg_files(color):
    """Setas, marca de seleção e ponto dos controles na cor do tema (SVGs em cache)."""
    from .config import app_data_dir
    shapes = {
        "up": (color, '<path d="M6 15l6-6 6 6"/>'),
        "down": (color, '<path d="M6 9l6 6 6-6"/>'),
        "check": ("#ffffff", '<path d="M5 12.5l4.5 4.5L19 7.5"/>'),
        "dot": ("#ffffff", '<circle cx="12" cy="12" r="4.5" fill="#ffffff"/>'),
    }
    out = {}
    for name, (col, body) in shapes.items():
        f = app_data_dir() / "ui" / f"{name}_{col.lstrip('#')}.svg"
        f.parent.mkdir(parents=True, exist_ok=True)
        if not f.exists():
            f.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
                         f'stroke="{col}" stroke-width="2.6" stroke-linecap="round" '
                         f'stroke-linejoin="round">{body}</svg>', "utf-8")
        out[name] = str(f).replace("\\", "/")
    return out


def apply(app, mode: str | None = None):
    """mode: 'light' | 'dark' | 'system' (padrão: preferência salva)."""
    global _mode
    from .config import settings
    if mode is None:
        mode = settings().value("theme", "system")
    else:
        settings().setValue("theme", mode)
    _mode = "dark" if mode == "dark" or (mode == "system" and system_prefers_dark()) else "light"
    _current.clear()
    _current.update(DARK if _mode == "dark" else LIGHT)
    t = _current

    app.setStyle("Fusion")
    pal = QPalette()
    for role, key in ((QPalette.Window, "bg"), (QPalette.Base, "surface"), (QPalette.AlternateBase, "surface2"),
                      (QPalette.Text, "text"), (QPalette.WindowText, "text"), (QPalette.Button, "surface"),
                      (QPalette.ButtonText, "text"), (QPalette.Highlight, "accent"),
                      (QPalette.ToolTipBase, "tooltip"), (QPalette.PlaceholderText, "muted"),
                      (QPalette.Mid, "border"), (QPalette.Dark, "border")):
        pal.setColor(role, QColor(t[key]))
    pal.setColor(QPalette.HighlightedText, QColor("white"))
    pal.setColor(QPalette.ToolTipText, QColor("white"))
    pal.setColor(QPalette.Link, QColor(t["accent_text"]))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(t["disabled"]))
    app.setPalette(pal)
    app.setFont(QFont("Segoe UI", 10))
    svg = _svg_files(t["chevron"])
    qss = QSS.substitute(t)
    for key in ("UP", "DOWN", "CHECK", "DOT"):
        qss = qss.replace(f"@{key}@", svg[key.lower()])
    app.setStyleSheet(qss)

    from . import icons
    icons.retheme()
