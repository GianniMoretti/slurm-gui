"""Dark theme with blue, violet and green accents. The single source of every colour in the app."""

from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

# ---------------------------------------------------------------- tokens

BG = "#0f1117"           # window background
SURFACE = "#171a23"      # sidebar, header, cards
SURFACE_2 = "#1f2330"    # inputs, hovered rows
SURFACE_3 = "#272c3b"    # pressed / raised
BORDER = "#2a2f3d"
TEXT = "#e6e8ef"
TEXT_MUTED = "#8b90a0"
TEXT_DIM = "#5c6172"

BLUE = "#4f8cff"         # primary actions, links, focus, resources
BLUE_DIM = "#1e2a45"
VIOLET = "#a77bff"       # selection, pending, active tab
VIOLET_DIM = "#2a2145"
GREEN = "#3ddc97"        # running, success, connected
GREEN_DIM = "#173a2e"
RED = "#ff5c7a"          # errors only
RED_DIM = "#3d1a24"
AMBER = "#f5b041"        # held, drained: needs attention but not an error
AMBER_DIM = "#3b2e14"

MONO = "JetBrains Mono, Cascadia Mono, SF Mono, Menlo, Consolas, DejaVu Sans Mono, monospace"

# ---------------------------------------------------------------- semantic colours

def job_state_color(state: str) -> str:
    if state in {"RUNNING", "COMPLETING", "CONFIGURING"}:
        return GREEN
    if state in {"PENDING", "REQUEUED"}:
        return VIOLET
    if state == "COMPLETED":
        return BLUE
    if state in {"FAILED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL", "BOOT_FAIL", "DEADLINE", "PREEMPTED"}:
        return RED
    if state in {"SUSPENDED", "STOPPED", "REQUEUE_HOLD"}:
        return AMBER
    return TEXT_MUTED   # CANCELLED and anything unknown


def node_state_color(state: str, flags: list[str]) -> str:
    if {"DRAIN", "DRAINING", "DRAINED"} & set(flags) or state == "DRAINED":
        return AMBER
    if state in {"DOWN", "FAIL", "UNKNOWN"} or "NOT_RESPONDING" in flags:
        return RED
    if "POWERED_DOWN" in flags or "POWERING_DOWN" in flags:
        return TEXT_DIM
    return {"IDLE": GREEN, "MIXED": BLUE, "ALLOCATED": VIOLET, "COMPLETING": VIOLET}.get(state, TEXT_MUTED)


# ---------------------------------------------------------------- application style

STYLESHEET = f"""
* {{ outline: 0; }}
QWidget {{ background: {BG}; color: {TEXT}; font-size: 13px; }}
QToolTip {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; }}

#Header, #Sidebar {{ background: {SURFACE}; }}
#Header {{ border-bottom: 1px solid {BORDER}; }}
#Sidebar {{ border-right: 1px solid {BORDER}; }}
#Header QLabel, #Sidebar QLabel {{ background: transparent; }}
#Muted {{ color: {TEXT_MUTED}; background: transparent; }}
#PageTitle {{ font-size: 18px; font-weight: 600; background: transparent; }}
#SectionTitle {{ font-size: 14px; font-weight: 600; color: {TEXT}; background: transparent; }}

#Sidebar QListWidget {{ background: transparent; border: none; padding-top: 8px; }}
#Sidebar QListWidget::item {{ padding: 9px 14px; color: {TEXT_MUTED}; border-left: 2px solid transparent; }}
#Sidebar QListWidget::item:hover {{ color: {TEXT}; background: {SURFACE_2}; }}
#Sidebar QListWidget::item:selected {{ color: {TEXT}; background: {BLUE_DIM}; border-left: 2px solid {BLUE}; }}

#ConnectionCard {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; }}
#ConnectionCard:hover {{ border-color: {BLUE}; background: {SURFACE_2}; }}
#ConnectionCard QLabel {{ background: transparent; }}
QPushButton#Link {{ background: transparent; border: none; color: {TEXT_MUTED}; padding: 4px 8px; }}
QPushButton#Link:hover {{ color: {BLUE}; }}
#ErrorBanner {{ background: {RED_DIM}; color: {RED}; border: 1px solid {RED}; border-radius: 8px; padding: 10px 12px; }}

#Card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; }}
#Card QLabel {{ background: transparent; }}
#CardValue {{ font-size: 24px; font-weight: 600; }}

QPushButton {{
    background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 6px 14px;
}}
QPushButton:hover {{ border-color: {BLUE}; }}
QPushButton:pressed {{ background: {SURFACE_3}; }}
QPushButton:disabled {{ color: {TEXT_DIM}; border-color: {BORDER}; }}
QPushButton#Primary {{ background: {BLUE}; color: #0b1020; border-color: {BLUE}; font-weight: 600; }}
QPushButton#Primary:hover {{ background: #6b9fff; }}
QPushButton#Danger:hover {{ border-color: {RED}; color: {RED}; }}
QPushButton:checked {{ background: {VIOLET_DIM}; border-color: {VIOLET}; }}

QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 5px 8px; selection-background-color: {VIOLET}; selection-color: {BG};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {BLUE}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; selection-background-color: {VIOLET_DIM};
}}
QCheckBox {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {BORDER}; border-radius: 4px; background: {SURFACE_2}; }}
QCheckBox::indicator:checked {{ background: {GREEN}; border-color: {GREEN}; }}

QTableView, QTreeView, QListView {{
    background: {BG}; alternate-background-color: {SURFACE};
    border: 1px solid {BORDER}; border-radius: 6px; gridline-color: {BORDER};
    selection-background-color: {VIOLET_DIM}; selection-color: {TEXT};
}}
QTableView::item {{ padding: 2px 6px; border: none; }}
QHeaderView {{ background: {SURFACE}; border: none; }}
QHeaderView::section {{
    background: {SURFACE}; color: {TEXT_MUTED}; border: none;
    border-bottom: 1px solid {BORDER}; padding: 6px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {SURFACE}; border: none; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 6px; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {TEXT_MUTED}; padding: 7px 14px; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {VIOLET}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

QScrollBar:vertical, QScrollBar:horizontal {{ background: transparent; border: none; margin: 0; }}
QScrollBar:vertical {{ width: 10px; }}
QScrollBar:horizontal {{ height: 10px; }}
QScrollBar::handle {{ background: {SURFACE_3}; border-radius: 4px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {TEXT_DIM}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; width: 0; background: none; }}

QStatusBar {{ background: {SURFACE}; color: {TEXT_MUTED}; border-top: 1px solid {BORDER}; }}
QStatusBar QLabel {{ background: transparent; }}
QMenu {{ background: {SURFACE_2}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {VIOLET_DIM}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}
QDialog {{ background: {BG}; }}
QSplitter::handle {{ background: {BORDER}; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")   # identical look on Linux, macOS and Windows
    pal = QPalette()
    for role, color in {
        QPalette.ColorRole.Window: BG, QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: SURFACE_2, QPalette.ColorRole.AlternateBase: SURFACE,
        QPalette.ColorRole.Text: TEXT, QPalette.ColorRole.Button: SURFACE_2,
        QPalette.ColorRole.ButtonText: TEXT, QPalette.ColorRole.Highlight: VIOLET,
        QPalette.ColorRole.HighlightedText: BG, QPalette.ColorRole.ToolTipBase: SURFACE_2,
        QPalette.ColorRole.ToolTipText: TEXT, QPalette.ColorRole.PlaceholderText: TEXT_DIM,
        QPalette.ColorRole.Link: BLUE, QPalette.ColorRole.BrightText: RED,
    }.items():
        pal.setColor(role, QColor(color))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(TEXT_DIM))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(TEXT_DIM))
    app.setPalette(pal)
    app.setStyleSheet(STYLESHEET)
