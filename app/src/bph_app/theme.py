"""Thème unique clair de l'application : couleurs, feuille de style Qt et icônes vectorielles.

Les boutons choisissent leur apparence par la propriété `variant` :
    primary   action principale de l'écran (fond vert)
    ghost     action secondaire discrète (sans bordure)
    danger    action destructrice (texte rouge)
    icon      bouton icône seul (barre de lecture, en-têtes)
    play      grand bouton rond de lecture
Les libellés utilisent la propriété `role` : title, subtitle, section, badge, mono.

Les icônes sont dessinées ici (tracés SVG 24×24, trait de 2) : aucune dépendance externe.
"""

from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton, QWidget

BG = "#f4f6f8"
SURFACE = "#ffffff"
BORDER = "#e2e7ec"
BORDER_STRONG = "#cfd7df"
TEXT = "#15212b"
MUTED = "#5d6b78"
SUBTLE = "#eef2f5"
ACCENT = "#0b6e4f"
ACCENT_HOVER = "#095c42"
ACCENT_PRESSED = "#074a35"
ACCENT_SOFT = "#e3f1ec"
DANGER = "#c62f37"
DANGER_SOFT = "#fdecee"

# tracés des icônes : "s:" = trait, "f:" = forme pleine ; plusieurs tracés séparés par "|"
ICONS: dict[str, str] = {
    "play": "f:M8 5.2v13.6a.8.8 0 0 0 1.2.7l10.6-6.8a.8.8 0 0 0 0-1.4L9.2 4.5A.8.8 0 0 0 8 5.2z",
    "pause": "f:M7 4.5h3.2v15H7z|f:M13.8 4.5H17v15h-3.2z",
    "skip-start": "s:M18 18.5 9.5 12 18 5.5z|s:M6 5v14",
    "skip-end": "s:M6 5.5 14.5 12 6 18.5z|s:M18 5v14",
    "frame-back": "s:M15 6l-6 6 6 6",
    "frame-forward": "s:M9 6l6 6-6 6",
    "second-back": "s:M11.5 17l-5-5 5-5|s:M18 17l-5-5 5-5",
    "second-forward": "s:M12.5 17l5-5-5-5|s:M6 17l5-5-5-5",
    "library": "s:M4 5.5A1.5 1.5 0 0 1 5.5 4H9v16H5.5A1.5 1.5 0 0 1 4 18.5z|s:M9 4h5v16H9z"
               "|s:M14.6 5.2l3.4-.9 3.6 13.5-3.4.9z",
    "film": "s:M4 5h16v14H4z|s:M8 5v14|s:M16 5v14|s:M4 9.5h4|s:M4 14.5h4|s:M16 9.5h4|s:M16 14.5h4",
    "import": "s:M12 15V4|s:M7.5 8.5 12 4l4.5 4.5|s:M4 14v4.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V14",
    "search": "s:M11 4.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13z|s:M20 20l-4.4-4.4",
    "edit": "s:M4 20h4.2L19 9.2 14.8 5 4 15.8z|s:M12.8 7l4.2 4.2",
    "trash": "s:M4.5 7h15|s:M10 11v6|s:M14 11v6|s:M6.5 7l.9 12.1A1 1 0 0 0 8.4 20h7.2a1 1 0 0 0 1-.9L17.5 7"
             "|s:M9 7V4.8a.8.8 0 0 1 .8-.8h4.4a.8.8 0 0 1 .8.8V7",
    "open": "s:M5 12h14|s:M13 6l6 6-6 6",
    "back": "s:M19 12H5|s:M11 6l-6 6 6 6",
    "keyboard": "s:M3.5 6.5h17v11h-17z|s:M7 10h.01|s:M10.5 10h.01|s:M14 10h.01|s:M17.5 10h.01|s:M7.5 14h9",
    "target": "s:M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17z|s:M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"
              "|f:M12 10.6a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8z",
    "grid": "s:M4 4h6.5v6.5H4z|s:M13.5 4H20v6.5h-6.5z|s:M4 13.5h6.5V20H4z|s:M13.5 13.5H20V20h-6.5z",
    "info": "s:M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17z|s:M12 11v5.5|s:M12 7.8h.01",
    "plus": "s:M12 5v14|s:M5 12h14",
    "up": "s:M12 19V5|s:M6 11l6-6 6 6",
    "down": "s:M12 5v14|s:M6 13l6 6 6-6",
    "chevron-down": "s:M6.5 9.5 12 15l5.5-5.5",
    "tag": "s:M4 4h7.5L20 12.5 12.5 20 4 11.5z|f:M8 6.8a1.2 1.2 0 1 0 0 2.4 1.2 1.2 0 0 0 0-2.4z",
    "check": "s:M5 12.5l4.5 4.5L19 7.5",
    "speed": "s:M4.5 16a7.5 7.5 0 1 1 15 0|s:M12 16l4-5",
}


def _svg(name: str, color: str) -> bytes:
    parts = []
    for spec in ICONS[name].split("|"):
        kind, d = spec.split(":", 1)
        if kind == "f":
            parts.append(f'<path d="{d}" fill="{color}"/>')
        else:
            parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" '
                         'stroke-linecap="round" stroke-linejoin="round"/>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{"".join(parts)}</svg>'.encode()


@lru_cache(maxsize=256)
def pixmap(name: str, color: str = TEXT, size: int = 20) -> QPixmap:
    app = QGuiApplication.instance()
    ratio = app.devicePixelRatio() if isinstance(app, QGuiApplication) else 1.0
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(_svg(name, color))).render(painter, QRectF(0, 0, pm.width(), pm.height()))
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, color: str = TEXT, active_color: str | None = None, size: int = 20) -> QIcon:
    """Icône ; `active_color` colore l'état coché (navigation) ou survolé."""
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal, QIcon.State.Off)
    ic.addPixmap(pixmap(name, "#a0a8b0", size), QIcon.Mode.Disabled, QIcon.State.Off)
    if active_color:
        ic.addPixmap(pixmap(name, active_color, size), QIcon.Mode.Normal, QIcon.State.On)
        ic.addPixmap(pixmap(name, active_color, size), QIcon.Mode.Active, QIcon.State.Off)
    return ic


@lru_cache(maxsize=64)
def dot(color: str, size: int = 10) -> QIcon:
    """Pastille de couleur (code d'un tag dans les listes)."""
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(0, 0, size * 2, size * 2)
    painter.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


W = TypeVar("W", bound=QWidget)
B = TypeVar("B", bound=QAbstractButton)


def named(widget: W, name: str) -> W:
    """Nom d'objet utilisé par la feuille de style (#card, #rail…)."""
    widget.setObjectName(name)
    return widget


def style(widget: W, **props: str) -> W:
    """Applique des propriétés de style (variant=…, role=…)."""
    for key, value in props.items():
        widget.setProperty(key, value)
    return widget


def decorate(button: B, icon_name: str, variant: str = "", color: str | None = None, size: int = 18) -> B:
    if variant:
        button.setProperty("variant", variant)
    default = {"primary": "#ffffff", "danger": DANGER, "play": "#ffffff"}.get(variant, TEXT)
    button.setIcon(icon(icon_name, color or default, size=size))
    button.setIconSize(QSize(size, size))
    return button


def palette() -> QPalette:
    p = QPalette()
    for role, value in {
        QPalette.ColorRole.Window: BG,
        QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: SURFACE,
        QPalette.ColorRole.AlternateBase: "#f8fafb",
        QPalette.ColorRole.Text: TEXT,
        QPalette.ColorRole.Button: SURFACE,
        QPalette.ColorRole.ButtonText: TEXT,
        QPalette.ColorRole.Highlight: ACCENT,
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.Mid: "#9aa5b0",
        QPalette.ColorRole.ToolTipBase: TEXT,
        QPalette.ColorRole.ToolTipText: "#ffffff",
        QPalette.ColorRole.PlaceholderText: "#8592a0",
    }.items():
        p.setColor(role, QColor(value))
    disabled = QPalette.ColorGroup.Disabled
    for role in (QPalette.ColorRole.ButtonText, QPalette.ColorRole.Text, QPalette.ColorRole.WindowText):
        p.setColor(disabled, role, QColor("#a0a8b0"))
    p.setColor(disabled, QPalette.ColorRole.Button, QColor(SUBTLE))
    return p


def stylesheet() -> str:
    """Feuille de style complète ; les flèches des champs sont écrites en SVG dans un dossier temporaire."""
    folder = Path(tempfile.gettempdir()) / "bph-theme"
    folder.mkdir(exist_ok=True)
    arrows = {}
    for name, d in (("down", "M6.5 9.5 12 15l5.5-5.5"), ("up", "M6.5 14.5 12 9l5.5 5.5")):
        path = folder / f"chevron-{name}.svg"
        path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="{d}" fill="none" '
                        f'stroke="{MUTED}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
                        encoding="utf-8")
        arrows[name] = path.as_posix()
    return STYLESHEET + f"""
QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url("{arrows['down']}"); width: 14px; height: 14px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ border: none; background: transparent; width: 18px; }}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: {SUBTLE}; border-radius: 4px; }}
QAbstractSpinBox::up-arrow {{ image: url("{arrows['up']}"); width: 11px; height: 11px; }}
QAbstractSpinBox::down-arrow {{ image: url("{arrows['down']}"); width: 11px; height: 11px; }}
QAbstractSpinBox[compact="true"] {{ padding: 1px 4px; border-radius: 6px; border-color: {BORDER}; }}
"""


STYLESHEET = f"""
QWidget {{ font-size: 13px; color: {TEXT}; }}
QMainWindow, QDialog, QMessageBox {{ background: {BG}; }}
QLabel {{ background: transparent; }}

/* --- cartes et zones --- */
QFrame#card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#rail {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
QFrame#videoFrame {{ background: #0c1116; border-radius: 12px; }}
QLabel#logo {{ background: {ACCENT}; color: white; border-radius: 10px; font-size: 18px; font-weight: 800; }}

/* --- typographie --- */
QLabel[role="title"] {{ font-size: 22px; font-weight: 700; }}
QLabel[role="subtitle"] {{ color: {MUTED}; font-size: 13px; }}
QLabel[role="section"] {{ color: {MUTED}; font-size: 12px; font-weight: 700; }}
QLabel[role="badge"] {{ background: {SUBTLE}; color: {MUTED}; border-radius: 10px; padding: 2px 9px;
                        font-size: 12px; font-weight: 700; }}
QLabel[role="mono"] {{ font-family: "JetBrains Mono", "Cascadia Mono", "SF Mono", Menlo, Consolas, monospace;
                       font-size: 15px; font-weight: 600; }}
QLabel[role="monoMuted"] {{ font-family: "JetBrains Mono", "Cascadia Mono", "SF Mono", Menlo, Consolas, monospace;
                            font-size: 12px; color: {MUTED}; }}
QLabel[role="emptyIcon"] {{ background: {ACCENT_SOFT}; border-radius: 36px; }}

/* --- boutons --- */
QPushButton {{ background: {SURFACE}; border: 1px solid {BORDER_STRONG}; border-radius: 9px;
               padding: 8px 15px; font-weight: 600; }}
QPushButton:hover {{ background: #f3f6f8; border-color: #b9c3cd; }}
QPushButton:pressed {{ background: #e8edf1; }}
QPushButton:focus {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: #a0a8b0; background: #f6f8f9; border-color: {BORDER}; }}
QPushButton[variant="primary"] {{ background: {ACCENT}; color: white; border: 1px solid {ACCENT}; }}
QPushButton[variant="primary"]:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton[variant="primary"]:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton[variant="primary"]:disabled {{ background: #a7cbbf; border-color: #a7cbbf; color: #f4faf8; }}
QPushButton[variant="ghost"] {{ background: transparent; border: 1px solid transparent; }}
QPushButton[variant="ghost"]:hover {{ background: {SUBTLE}; }}
QPushButton[variant="danger"] {{ color: {DANGER}; background: transparent; border: 1px solid transparent; }}
QPushButton[variant="danger"]:hover {{ background: {DANGER_SOFT}; border-color: #f3c3c7; }}
QPushButton[variant="danger"]:disabled {{ color: #d9a7ab; background: transparent; }}

QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 9px; padding: 6px; }}
QToolButton:hover {{ background: {SUBTLE}; }}
QToolButton:pressed {{ background: #e3e8ec; }}
QToolButton[variant="play"] {{ background: {ACCENT}; border-radius: 24px; min-width: 48px; min-height: 48px;
                               max-width: 48px; max-height: 48px; padding: 0; }}
QToolButton[variant="play"]:hover {{ background: {ACCENT_HOVER}; }}
QToolButton[variant="play"]:pressed {{ background: {ACCENT_PRESSED}; }}
QToolButton[variant="chip"] {{ border: 1px solid {BORDER_STRONG}; border-radius: 9px; padding: 5px 10px;
                               font-weight: 700; color: {MUTED}; }}
QToolButton[variant="chip"]:hover {{ color: {TEXT}; }}

/* navigation latérale */
QFrame#rail QToolButton {{ border: none; border-radius: 12px; color: {MUTED}; font-size: 11px;
                          font-weight: 600; padding: 8px 2px 6px 2px; }}
QFrame#rail QToolButton:hover {{ background: {SUBTLE}; color: {TEXT}; }}
QFrame#rail QToolButton:checked {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}
QFrame#rail QToolButton:disabled {{ color: #b7bfc7; }}

/* --- champs --- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {{
    background: {SURFACE}; border: 1px solid {BORDER_STRONG}; border-radius: 9px; padding: 7px 10px;
    selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT}; }}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QDateEdit:hover {{ border-color: #b9c3cd; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{
    border: 1px solid {ACCENT}; }}
QComboBox::drop-down, QDateEdit::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px;
                               padding: 4px; selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT};
                               outline: none; }}
QPlainTextEdit {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: 6px;
                  font-family: "JetBrains Mono", "Cascadia Mono", Menlo, Consolas, monospace; }}

/* --- tableaux --- */
QTableWidget {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; gridline-color: {SUBTLE};
                alternate-background-color: #f9fbfc; selection-background-color: {ACCENT_SOFT};
                selection-color: {TEXT}; outline: none; }}
QTableWidget::item {{ padding: 6px 8px; border: none; }}
QTableWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {SURFACE}; border: none; border-bottom: 1px solid {BORDER};
                        padding: 9px 8px; color: {MUTED}; font-weight: 700; font-size: 12px; }}
QTableCornerButton::section {{ background: {SURFACE}; border: none; }}

/* --- barres de défilement fines --- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px 4px; }}
QScrollBar::handle {{ background: #cdd5dd; border-radius: 3px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: #aeb9c4; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* --- menus, bulles, barre d'état --- */
QMenuBar {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; padding: 2px 6px; }}
QMenuBar::item {{ padding: 6px 10px; border-radius: 6px; background: transparent; }}
QMenuBar::item:selected {{ background: {SUBTLE}; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 22px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}
QToolTip {{ background: {TEXT}; color: white; border: none; border-radius: 6px; padding: 6px 9px; }}
QStatusBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QStatusBar::item {{ border: none; }}
QProgressBar {{ background: #e5eaee; border: none; border-radius: 6px; min-height: 12px; max-height: 12px;
                text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: 14px; }}
"""
