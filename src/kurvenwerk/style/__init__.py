"""Design-Tokens (App-Design1) → Qt-Stylesheet. Einzige Quelle für Farben, Radien, Schriften."""
from pathlib import Path
from string import Template

FONTS = Path(__file__).parent / "fonts"

# color-mix/rgba aus App-Design1 vorberechnet; Qt-QSS kennt #AARRGGBB, kein color-mix.
ACCENT = {"accent": "#0FB5A6", "accent_deep": "#0B867B", "accent_lift": "#35C1B4",
          "accent_soft": "#1F0FB5A6"}
DARK = {**ACCENT, "on_accent": "#041917",
        "bg": "#0A100F", "surface": "#141C1A", "sunken": "#0F1615", "raised": "#1B2422",
        "ink": "#EBF2F0", "ink_2": "#A3B3AF", "ink_3": "#7A8985",
        "line": "#1AFFFFFF", "line_2": "#2EFFFFFF"}
LIGHT = {**ACCENT, "on_accent": "#05201D",
         "bg": "#F3F5F3", "surface": "#FFFFFF", "sunken": "#E8ECEA", "raised": "#FFFFFF",
         "ink": "#0F1614", "ink_2": "#4C5D58", "ink_3": "#7C8D88",
         "line": "#1A0F1614", "line_2": "#290F1614"}
RADIUS = {"r_xs": "8px", "r_sm": "12px"}

QSS = Template("""
* { font-family: "$sans"; font-size: 10pt; color: $ink; }
QMainWindow, QWidget#page { background: $bg; }
QMenuBar { background: $surface; border-bottom: 1px solid $line; }
QMenuBar::item { padding: 4px 10px; border-radius: $r_xs; }
QMenuBar::item:selected, QMenu::item:selected { background: $accent_soft; color: $accent_lift; }
QMenu { background: $raised; border: 1px solid $line_2; border-radius: $r_xs; padding: 4px; }
QMenu::item { padding: 5px 18px; border-radius: $r_xs; }
QMenu::separator { height: 1px; background: $line; margin: 4px 6px; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: $ink_2; padding: 6px 14px; margin: 4px 2px;
               border-radius: $r_xs; }
QTabBar::tab:selected { background: $accent_soft; color: $accent_lift; font-weight: 600; }
QTabBar::tab:hover:!selected { background: $sunken; color: $ink; }
QToolButton { background: transparent; border-radius: $r_xs; padding: 4px 8px; }
QToolButton:hover { background: $sunken; }
QPushButton { background: $accent; color: $on_accent; border: none; border-radius: $r_xs;
              padding: 6px 14px; font-weight: 600; }
QPushButton:hover { background: $accent_lift; }
QPushButton:pressed { background: $accent_deep; }
QSplitter::handle { background: $line; }
QSplitter::handle:horizontal { width: 1px; }
QTableView { background: $surface; alternate-background-color: $sunken; gridline-color: $line;
             border: 1px solid $line; border-radius: $r_sm; selection-background-color: $accent_soft;
             selection-color: $ink; font-family: "$mono"; }
QHeaderView::section { background: $raised; color: $ink_2; border: none;
                       border-bottom: 1px solid $line_2; padding: 4px 6px; font-family: "$mono"; }
QTableCornerButton::section { background: $raised; border: none; }
QLineEdit, QInputDialog QLineEdit { background: $sunken; border: 1px solid $line_2;
            border-radius: $r_xs; padding: 4px 8px; selection-background-color: $accent; }
QLineEdit:focus { border-color: $accent; }
QDialog, QMessageBox, QInputDialog { background: $surface; }
QScrollBar:vertical, QScrollBar:horizontal { background: transparent; width: 10px; height: 10px; }
QScrollBar::handle { background: $line_2; border-radius: 5px; min-height: 24px; min-width: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
""")


def apply(app, dark: bool = True) -> None:
    """Schriften aus dem Paket laden (kein Netz) und Stylesheet setzen."""
    from PySide6.QtGui import QFontDatabase

    families = {}
    for f in sorted(FONTS.glob("*.ttf")):
        fid = QFontDatabase.addApplicationFont(str(f))
        if fid >= 0:
            families[f.stem.split("-")[0]] = QFontDatabase.applicationFontFamilies(fid)[0]
    app.setStyleSheet(stylesheet(dark, families.get("Manrope", "sans-serif"),
                                 families.get("IBMPlexMono", "monospace")))


def stylesheet(dark: bool = True, sans: str = "Manrope", mono: str = "IBM Plex Mono") -> str:
    return QSS.substitute(DARK if dark else LIGHT, **RADIUS, sans=sans, mono=mono)
