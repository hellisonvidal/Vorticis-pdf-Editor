"""Tema visual do Vorticis PDF Editor."""
from PySide6.QtGui import QColor, QFont, QPalette

ACCENT = "#d6232d"
ACCENT_HOVER = "#e43a43"
ACCENT_SOFT = "#fde8e9"
BG = "#f5f6f8"
SURFACE = "#ffffff"
BORDER = "#e3e6eb"
TEXT = "#1f2430"
MUTED = "#6b7280"
CANVAS = "#3a3f47"
SIDEBAR = "#262a31"

QSS = f"""
* {{ font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", sans-serif; font-size: 10pt; }}
QMainWindow, QDialog {{ background: {BG}; color: {TEXT}; }}
QToolTip {{ background: #1f2430; color: white; border: none; padding: 6px 9px; border-radius: 6px; }}

/* ---------- barra superior ---------- */
#HeaderBar {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
#HeaderBar QToolButton {{ border: none; border-radius: 8px; padding: 6px; margin: 0 1px; color: {TEXT}; }}
#HeaderBar QToolButton:hover {{ background: #eef0f3; }}
#HeaderBar QToolButton:pressed {{ background: #e2e5ea; }}
#HeaderBar QToolButton:checked {{ background: {ACCENT}; color: white; }}
#HeaderBar QToolButton#Primary {{ background: {ACCENT}; color: white; padding: 6px 12px; font-weight: 600; }}
#HeaderBar QToolButton#Primary:hover {{ background: {ACCENT_HOVER}; }}
#HeaderBar QToolButton::menu-indicator {{ image: none; }}
#AppTitle {{ font-size: 11pt; font-weight: 700; color: {TEXT}; }}
#DocTitle {{ color: {MUTED}; }}
#Sep {{ background: {BORDER}; min-width: 1px; max-width: 1px; margin: 8px 6px; }}

/* ---------- trilho de ferramentas ---------- */
#ToolRail {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
#ToolRail QToolButton {{ border: none; border-radius: 10px; padding: 8px; margin: 2px 6px; }}
#ToolRail QToolButton:hover {{ background: #eef0f3; }}
#ToolRail QToolButton:checked {{ background: {ACCENT}; }}

/* ---------- campos ---------- */
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 5px 8px;
    selection-background-color: {ACCENT}; selection-color: white; }}
QAbstractSpinBox {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 4px 6px; selection-background-color: {ACCENT}; selection-color: white; min-height: 20px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ subcontrol-origin: border; width: 20px;
    border: none; border-left: 1px solid {BORDER}; background: transparent; }}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; border-top-right-radius: 8px; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; border-bottom-right-radius: 8px; }}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: #eef0f3; }}
QAbstractSpinBox::up-arrow {{ image: url(@UP@); width: 10px; height: 10px; }}
QAbstractSpinBox::down-arrow {{ image: url(@DOWN@); width: 10px; height: 10px; }}
QComboBox::down-arrow {{ image: url(@DOWN@); width: 11px; height: 11px; }}
QLineEdit:focus, QAbstractSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px;
    selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT}; outline: 0; }}
#SearchBox {{ border-radius: 16px; padding: 6px 12px; background: #f0f2f5; border: 1px solid transparent; }}
#SearchBox:focus {{ background: white; border: 1px solid {ACCENT}; }}

/* ---------- botões ---------- */
QPushButton {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 7px 14px; color: {TEXT}; }}
QPushButton:hover {{ background: #f0f2f5; }}
QPushButton:pressed {{ background: #e5e8ec; }}
QPushButton:default, QPushButton#Primary {{ background: {ACCENT}; border: 1px solid {ACCENT}; color: white; font-weight: 600; }}
QPushButton:default:hover, QPushButton#Primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton:disabled {{ color: #a0a6b0; background: #f3f4f6; }}
#BigAction {{ text-align: left; padding: 14px 16px; border-radius: 12px; font-size: 10.5pt; }}
#BigAction:hover {{ border: 1px solid {ACCENT}; background: {ACCENT_SOFT}; }}

/* ---------- listas, abas, grupos ---------- */
QListWidget, QTableWidget {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; outline: 0; }}
QListWidget::item {{ padding: 6px; border-radius: 6px; }}
QListWidget::item:selected, QTableWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QHeaderView::section {{ background: {BG}; border: none; border-bottom: 1px solid {BORDER}; padding: 6px; font-weight: 600; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 10px; background: {SURFACE}; top: -1px; }}
QTabBar::tab {{ padding: 8px 16px; border: none; color: {MUTED}; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; font-weight: 600; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 10px; margin-top: 14px; padding: 12px 10px 8px; background: {SURFACE}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {MUTED}; font-weight: 600; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}

/* ---------- menus ---------- */
QMenuBar {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; padding: 2px 6px; }}
QMenuBar::item {{ padding: 5px 10px; border-radius: 6px; }}
QMenuBar::item:selected {{ background: #eef0f3; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 26px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QMenu::item:disabled {{ color: #a0a6b0; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}
QMenu::icon {{ padding-left: 8px; }}

/* ---------- barras de rolagem ---------- */
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(120,128,140,.45); border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(120,128,140,.75); }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: rgba(120,128,140,.45); border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- painel de miniaturas ---------- */
#ThumbHeader {{ background: {SIDEBAR}; color: #d7dbe0; }}
#ThumbHeader QLabel {{ color: #d7dbe0; font-weight: 600; }}
QSlider::groove:horizontal {{ height: 4px; background: #4a505a; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: white; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
QSplitter::handle {{ background: {BORDER}; width: 1px; }}

/* ---------- barra de status ---------- */
QStatusBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QStatusBar QLabel {{ padding: 0 8px; }}
#FontBadge {{ background: {ACCENT_SOFT}; color: {ACCENT}; border-radius: 9px; padding: 2px 10px; font-weight: 600; }}
#SavedBadge {{ color: #1b8a3a; }}
#DirtyBadge {{ color: #b26a00; }}

/* ---------- tela inicial ---------- */
#Welcome {{ background: {BG}; }}
#WelcomeCard {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 18px; }}
#WelcomeTitle {{ font-size: 20pt; font-weight: 700; color: {TEXT}; }}
#WelcomeSub {{ color: {MUTED}; font-size: 10.5pt; }}
#RecentList {{ border: none; }}
#RecentList::item {{ padding: 8px; }}
#RecentList::item:hover {{ background: #f3f4f6; }}
#Badge {{ background: {ACCENT_SOFT}; color: {ACCENT}; border-radius: 10px; padding: 3px 10px; font-weight: 600; }}
QProgressDialog QLabel {{ padding: 6px; }}
QProgressBar {{ border: none; background: #eceef1; border-radius: 6px; height: 10px; text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}
"""


def apply(app):
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(BG))
    pal.setColor(QPalette.Base, QColor(SURFACE))
    pal.setColor(QPalette.AlternateBase, QColor("#f7f8fa"))
    pal.setColor(QPalette.Text, QColor(TEXT))
    pal.setColor(QPalette.WindowText, QColor(TEXT))
    pal.setColor(QPalette.Button, QColor(SURFACE))
    pal.setColor(QPalette.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor("white"))
    pal.setColor(QPalette.ToolTipBase, QColor("#1f2430"))
    pal.setColor(QPalette.ToolTipText, QColor("white"))
    pal.setColor(QPalette.PlaceholderText, QColor("#9aa1ab"))
    app.setPalette(pal)
    f = QFont("Segoe UI", 10)
    app.setFont(f)
    from .config import resource_path
    up = resource_path("chevron_up.svg").replace("\\", "/")
    down = resource_path("chevron_down.svg").replace("\\", "/")
    app.setStyleSheet(QSS.replace("@UP@", up).replace("@DOWN@", down))
