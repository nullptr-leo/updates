"""Two compact QSS themes. No third-party widget library required."""

LIGHT_QSS = """
QWidget { font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif; font-size: 13px; color: #1f2328; }
QMainWindow, QDialog { background: #f6f7f9; }
QFrame#Card { background: #ffffff; border: 1px solid #e3e6ea; border-radius: 10px; }
QScrollArea#DetailScroll, QWidget#DetailViewport, QWidget#DetailContent { background: transparent; border: none; }
QLabel#Title { font-size: 19px; font-weight: 600; color: #111418; }
QLabel#Subtle { color: #6b7280; }
QLabel#Stat { color: #374151; padding: 2px 8px; }
QPushButton { background: #ffffff; border: 1px solid #d5d9df; border-radius: 7px; padding: 6px 14px; }
QPushButton:hover { border-color: #9aa4b2; background: #f2f4f7; }
QPushButton:pressed { background: #e8ebef; }
QPushButton:disabled { color: #a7adb7; background: #f2f3f5; }
QPushButton#Primary { background: #2563eb; color: #ffffff; border: 1px solid #2563eb; font-weight: 600; }
QPushButton#Primary:hover { background: #1d4ed8; }
QPushButton#Primary:disabled { background: #a9c2f5; border-color: #a9c2f5; }
QPushButton#Danger { color: #b42318; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {
    background: #ffffff; border: 1px solid #d5d9df; border-radius: 7px; padding: 5px 9px;
}
QLineEdit:focus, QComboBox:focus { border-color: #2563eb; }
QTableView { background: #ffffff; border: 1px solid #e3e6ea; border-radius: 10px;
             gridline-color: #f0f1f3; selection-background-color: #e8f0fe; selection-color: #111418; }
QHeaderView::section { background: #fafbfc; border: none; border-bottom: 1px solid #e3e6ea;
                       padding: 8px 6px; color: #6b7280; font-weight: 600; }
QTableView::item { padding: 4px 6px; }
QScrollBar:vertical { width: 10px; background: transparent; }
QScrollBar::handle:vertical { background: #cfd4db; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #aeb6c1; }
QSplitter::handle { background: #e3e6ea; }
QCheckBox { spacing: 6px; }
QMenu { background: #ffffff; border: 1px solid #d5d9df; border-radius: 8px; padding: 4px; }
QMenu::item { padding: 6px 22px; border-radius: 5px; }
QMenu::item:selected { background: #e8f0fe; }
QToolTip { background: #111418; color: #ffffff; border: none; padding: 5px; }
"""

DARK_QSS = """
QWidget { font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif; font-size: 13px; color: #e6e8eb; }
QMainWindow, QDialog { background: #161a20; }
QFrame#Card { background: #1d222a; border: 1px solid #2c333d; border-radius: 10px; }
QScrollArea#DetailScroll, QWidget#DetailViewport, QWidget#DetailContent { background: transparent; border: none; }
QLabel#Title { font-size: 19px; font-weight: 600; color: #f3f5f7; }
QLabel#Subtle { color: #8b95a3; }
QLabel#Stat { color: #c6ccd4; padding: 2px 8px; }
QPushButton { background: #232a33; border: 1px solid #343d48; border-radius: 7px; padding: 6px 14px; color: #e6e8eb; }
QPushButton:hover { border-color: #4b5665; background: #2b333d; }
QPushButton:pressed { background: #343d48; }
QPushButton:disabled { color: #6a7480; background: #1d222a; }
QPushButton#Primary { background: #3b82f6; color: #ffffff; border: 1px solid #3b82f6; font-weight: 600; }
QPushButton#Primary:hover { background: #2f6fe0; }
QPushButton#Primary:disabled { background: #31476e; border-color: #31476e; }
QPushButton#Danger { color: #ff8f82; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {
    background: #1d222a; border: 1px solid #343d48; border-radius: 7px; padding: 5px 9px; color: #e6e8eb;
}
QLineEdit:focus, QComboBox:focus { border-color: #3b82f6; }
QTableView { background: #1d222a; border: 1px solid #2c333d; border-radius: 10px;
             gridline-color: #262d36; selection-background-color: #2c3f5e; selection-color: #ffffff; }
QHeaderView::section { background: #20262e; border: none; border-bottom: 1px solid #2c333d;
                       padding: 8px 6px; color: #8b95a3; font-weight: 600; }
QTableView::item { padding: 4px 6px; }
QScrollBar:vertical { width: 10px; background: transparent; }
QScrollBar::handle:vertical { background: #3c4551; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #505b69; }
QSplitter::handle { background: #2c333d; }
QCheckBox { spacing: 6px; }
QMenu { background: #232a33; border: 1px solid #343d48; border-radius: 8px; padding: 4px; }
QMenu::item { padding: 6px 22px; border-radius: 5px; }
QMenu::item:selected { background: #2c3f5e; }
QToolTip { background: #0d1015; color: #e6e8eb; border: 1px solid #343d48; padding: 5px; }
"""

PALETTE = {
    "light": {
        "idle": "#8b95a1", "running": "#2563eb", "success": "#15803d",
        "warning": "#b45309", "error": "#dc2626", "update": "#7c3aed",
        "track": "#e8ebef", "text": "#1f2328",
    },
    "dark": {
        "idle": "#7b8592", "running": "#60a5fa", "success": "#4ade80",
        "warning": "#fbbf24", "error": "#f87171", "update": "#c084fc",
        "track": "#2c333d", "text": "#e6e8eb",
    },
}


def stylesheet(theme: str) -> str:
    return DARK_QSS if theme == "dark" else LIGHT_QSS


def palette(theme: str) -> dict[str, str]:
    return PALETTE["dark" if theme == "dark" else "light"]
