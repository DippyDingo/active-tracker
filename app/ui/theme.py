from dataclasses import dataclass
from pathlib import Path
from string import Template

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPen, QPixmap


@dataclass(frozen=True)
class Palette:
    key: str
    title: str
    bg: str
    bg2: str
    sidebar: str
    card: str
    card_hover: str
    border: str
    text: str
    text2: str
    text3: str
    accent: str
    cyan: str
    danger: str
    popup: str
    overlay: tuple
    shadow: tuple
    chart_fill_top: int
    chart_fill_bottom: int
    is_light: bool = False


PALETTES: dict[str, Palette] = {
    p.key: p
    for p in (
        Palette(
            "midnight", "Полночь",
            "#0b1220", "#0f172a", "#0f1b2d", "#1e293b", "#243247", "#24344d",
            "#e5e7eb", "#9ca3af", "#6b7280", "#60a5fa", "#22d3ee", "#f87171",
            "#101a2c", (4, 9, 20, 150), (2, 6, 23, 150), 70, 6,
        ),
        Palette(
            "obsidian", "Обсидиан",
            "#07080b", "#0c0e13", "#0d1015", "#15181f", "#1c1f28", "#232833",
            "#e7e9ef", "#98a0ae", "#676f7e", "#7aa2f7", "#56cfe1", "#f87171",
            "#101319", (0, 0, 0, 175), (0, 0, 0, 180), 78, 8,
        ),
        Palette(
            "fog", "Туман",
            "#1d2534", "#253044", "#232d40", "#2c3850", "#35435e", "#3d4c68",
            "#eef2f8", "#a9b6ca", "#7c8aa1", "#7fb0ff", "#5fd3e8", "#f87171",
            "#26314a", (8, 12, 22, 160), (6, 10, 20, 140), 85, 10,
        ),
        Palette(
            "morning", "Утро",
            "#eceff6", "#e3e9f3", "#e6ebf4", "#fbfcfe", "#ffffff", "#d5dcea",
            "#1e293b", "#55637a", "#8b98ac", "#2f6fed", "#0e8fa8", "#dc2626",
            "#ffffff", (30, 41, 59, 110), (100, 116, 139, 90), 130, 30,
            is_light=True,
        ),
    )
}
DEFAULT_THEME = "midnight"


def _hx(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def _to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _mix_hex(a: str, b: str, t: float) -> str:
    ra, ga, ba = _hx(a)
    rb, gb, bb = _hx(b)
    return _to_hex((
        round(ra + (rb - ra) * t),
        round(ga + (gb - ga) * t),
        round(ba + (bb - ba) * t),
    ))


def _rgb_str(value: str) -> str:
    r, g, b = _hx(value)
    return f"{r},{g},{b}"


def _button_colors(p: Palette) -> tuple[str, str, str, str]:
    """Градиент главной (акцентной) кнопки: обычный и hover.

    Один источник для QSS и для нарисованных вручную кнопок — чтобы кнопка
    «добавить приложение» в панели и кнопки диалогов были одного цвета во всех
    темах.
    """
    if p.key == "midnight":
        return "#3b82f6", "#2563eb", "#60a5fa", "#3b82f6"
    top = _mix_hex(p.accent, "#000000", 0.08)
    bottom = _mix_hex(p.accent, "#000000", 0.28)
    return top, bottom, p.accent, top


def _derive(p: Palette) -> dict[str, str]:
    soft_rgb = "30,41,59" if p.is_light else "255,255,255"

    def soft(pct: int) -> str:
        return f"rgba({soft_rgb},{pct}%)"

    btn_top, btn_bottom, btn_hover_top, btn_hover_bottom = _button_colors(p)

    return {
        "bg": p.bg, "bg2": p.bg2, "sidebar": p.sidebar,
        "card": p.card, "border": p.border,
        "text": p.text, "text2": p.text2, "text3": p.text3,
        "accent": p.accent, "cyan": p.cyan, "danger": p.danger, "popup": p.popup,
        "accent_rgb": _rgb_str(p.accent), "danger_rgb": _rgb_str(p.danger),
        "sidebar_edge": _mix_hex(p.border, p.bg, 0.55),
        "card2": _mix_hex(p.card, p.bg, 0.35),
        "card_border": _mix_hex(p.border, p.card, 0.45),
        "hover_border": _mix_hex(p.accent, p.border, 0.65),
        "popup2": _mix_hex(p.popup, p.bg, 0.5),
        "menu_text": _mix_hex(p.text, p.text2, 0.55),
        "menu_disabled": _mix_hex(p.text3, p.bg, 0.5),
        "disabled_text": _mix_hex(p.text3, p.bg, 0.4),
        "disabled_border": _mix_hex(p.border, p.bg, 0.6),
        "list_bg": _mix_hex(p.bg, p.card, 0.35),
        "list_item_border": _mix_hex(p.bg, p.card, 0.18),
        "row_btn_border": _mix_hex(p.border, p.text3, 0.45),
        "btn_top": btn_top, "btn_bottom": btn_bottom,
        "btn_hover_top": btn_hover_top, "btn_hover_bottom": btn_hover_bottom,
        "add_btn_top": btn_top, "add_btn_bottom": btn_bottom,
        "add_btn_hover_top": btn_hover_top, "add_btn_hover_bottom": btn_hover_bottom,
        "add_btn_border": _mix_hex(p.accent, p.border, 0.35),
        "danger_hover_text": _mix_hex(p.danger, "#ffffff", 0.5),        "avatar_text": "#ffffff" if p.is_light else "#04121f",
        "soft2": soft(2), "soft3": soft(3), "soft4": soft(4), "soft5": soft(5),
        "soft6": soft(6), "soft8": soft(8),
    }


_QSS_TEMPLATE = Template("""
* {
    outline: 0;
}
QWidget {
    background: transparent;
    color: $text;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 14px;
}
QMainWindow, QDialog {
    background-color: $bg;
}
QWidget#mainRoot {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $bg, stop:1 $bg2);
}
QFrame#sidebar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $sidebar, stop:1 $bg);
    /* Боковая панель вплотную примыкает к контенту: отдельная граница
       превращалась в заметную вертикальную полоску после смены темы. */
    border: none;
}
QLabel {
    background: transparent;
}
QLabel#sectionTitle {
    color: $text2;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#pageTitle {
    color: $text;
    font-size: 23px;
    font-weight: 800;
}
QLabel#pageSub {
    color: $text2;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
}
QLabel#subtleLabel {
    color: $text2;
    font-size: 12px;
}
QLabel#mutedLabel {
    color: $text3;
    font-size: 11px;
}
QLabel#cardName {
    color: $text;
    font-size: 14px;
    font-weight: 600;
}
QLabel#cardTime {
    color: $text;
    font-size: 29px;
    font-weight: 800;
}
QLabel#cardFooter {
    color: $text2;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.4px;
}
QLabel#sideName {
    color: $text;
    font-size: 13px;
    font-weight: 600;
}
QLabel#pathLabel {
    color: $text3;
    font-size: 11px;
}
QLabel#statBig {
    color: $text;
    font-size: 34px;
    font-weight: 800;
}
QLabel#statLabel {
    color: $text3;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.6px;
}
QLabel#statValue {
    color: $text;
    font-size: 14px;
    font-weight: 600;
}
QLabel#modalTitle {
    color: $text;
    font-size: 17px;
    font-weight: 800;
}
QLabel#emptyLabel {
    color: $text3;
    font-size: 15px;
}
QLabel#avatar {
    border-radius: 17px;
    color: $avatar_text;
    font-weight: 800;
    font-size: 15px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 $accent, stop:1 $cyan);
}
QLabel#runningDot {
    background-color: $cyan;
    border-radius: 4px;
    min-width: 8px;
    min-height: 8px;
    max-width: 8px;
    max-height: 8px;
}

QFrame#sideItem {
    border-radius: 10px;
    border: 1px solid transparent;
}
QFrame#sideItem:hover {
    background: $soft5;
}
QFrame#sideItem[selected="true"] {
    background: rgba($accent_rgb, 15%);
    border: 1px solid rgba($accent_rgb, 50%);
}
QFrame#catHeader {
    border-radius: 8px;
    border: 1px solid rgba($accent_rgb, 10%);
    background: $soft3;
}
QFrame#catHeader:hover {
    background: rgba($accent_rgb, 7%);
    border: 1px solid rgba($accent_rgb, 25%);
}
QFrame#catHeader[droptarget="true"] {
    background: rgba($accent_rgb, 12%);
    border: 1px solid rgba($accent_rgb, 60%);
}
QFrame#catHeader[flash="true"] {
    background: rgba($accent_rgb, 16%);
    border: 1px solid rgba($accent_rgb, 65%);
}
QFrame#sideItem[flash="true"] {
    background: rgba($accent_rgb, 18%);
    border: 1px solid rgba($accent_rgb, 60%);
}
QLabel#catName {
    color: $menu_text;
    font-size: 11px;
    font-weight: 700;
}
QLabel#catArrow {
    color: $text3;
    font-size: 11px;
}
QLabel#catCount {
    color: $text2;
    background: rgba($accent_rgb, 12%);
    border-radius: 8px;
    padding: 1px 8px;
    font-size: 11px;
    font-weight: 700;
}
QMenu {
    background-color: $popup;
    border: 1px solid $border;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 8px 28px 8px 12px;
    border-radius: 7px;
    margin: 1px 3px;
    color: $menu_text;
    background: transparent;
}
QMenu::item:selected {
    background: rgba($accent_rgb, 12%);
    color: $text;
}
QMenu::item:pressed {
    background: rgba($accent_rgb, 24%);
    color: $text;
}
QMenu::item:disabled {
    color: $menu_disabled;
}
QMenu::separator {
    height: 1px;
    background: $card;
    margin: 5px 8px;
}
QMenu::icon {
    margin-left: 6px;
}
QWidget#sidebarContainer {
    background: transparent;
}
QFrame#inlineEdit {
    border-radius: 10px;
    border: 1px solid rgba($accent_rgb, 50%);
    background: rgba($accent_rgb, 8%);
}
QFrame#inlineEdit QLineEdit {
    background: transparent;
    border: none;
    color: $text;
    font-size: 13px;
    font-weight: 600;
    padding: 2px;
}

QScrollArea {
    border: none;
    background: transparent;
}
QScrollArea#cardsScroll,
QScrollArea#cardsScroll > QWidget,
QScrollArea#cardsScroll > QWidget > QWidget,
QScrollArea#cardsScroll QWidget#qt_scrollarea_viewport {
    background: transparent;
    border: none;
}
QScrollArea#sidebarScroll,
QScrollArea#sidebarScroll > QWidget,
QScrollArea#sidebarScroll > QWidget > QWidget,
QScrollArea#sidebarScroll QWidget#sidebarContainer,
QScrollArea#sidebarScroll QWidget#qt_scrollarea_viewport {
    background: transparent;
    border: none;
}
QScrollArea#sidebarScroll QScrollBar:vertical,
QScrollArea#sidebarScroll QScrollBar:horizontal {
    width: 0px;
    height: 0px;
    background: transparent;
    border: none;
    margin: 0px;
}
QScrollArea#sidebarScroll QScrollBar::handle:vertical,
QScrollArea#sidebarScroll QScrollBar::handle:horizontal,
QScrollArea#sidebarScroll QScrollBar::add-line:vertical,
QScrollArea#sidebarScroll QScrollBar::sub-line:vertical,
QScrollArea#sidebarScroll QScrollBar::add-line:horizontal,
QScrollArea#sidebarScroll QScrollBar::sub-line:horizontal {
    width: 0px;
    height: 0px;
    background: transparent;
    border: none;
}
QWidget#cardsContainer {
    background: transparent;
}

QFrame#appCard {
    border-radius: 16px;
    border: 1px solid $card_border;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $card, stop:1 $card2);
}
QFrame#appCard:hover {
    border-color: $hover_border;
    border: 2px solid $hover_border;
}
QFrame#appCard[selected="true"] {
    border-color: $accent;
    border: 2px solid $accent;
}

QFrame#modalPanel {
    border-radius: 18px;
    border: 1px solid $border;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $popup, stop:1 $popup2);
}
QFrame#statBox {
    border-radius: 12px;
    border: 1px solid $card_border;
    background: $soft3;
    padding: 8px;
}
QFrame#rangeResult {
    border-radius: 12px;
    border: 1px solid $card_border;
    background: $soft3;
}
QFrame#helpBox {
    border-radius: 12px;
    border: 1px solid rgba($accent_rgb, 12%);
    background: rgba($accent_rgb, 4%);
}
QLabel#helpTitle {
    color: $menu_text;
    font-size: 12px;
    font-weight: 700;
}
QLabel#helpBullet {
    color: $text2;
    font-size: 12px;
}

QPushButton {
    background: $soft5;
    border: 1px solid $card;
    border-radius: 10px;
    padding: 8px 14px;
    color: $text2;
    font-weight: 600;
}
QPushButton:hover {
    color: $text;
    border-color: $hover_border;
    background: rgba($accent_rgb, 10%);
}
QPushButton:pressed {
    background: rgba($accent_rgb, 16%);
}
QPushButton:disabled {
    color: $disabled_text;
    border-color: $disabled_border;
    background: transparent;
}
QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $btn_top, stop:1 $btn_bottom);
    border: none;
    color: #ffffff;
    font-weight: 700;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $btn_hover_top, stop:1 $btn_hover_bottom);
    color: #ffffff;
}
QPushButton#primary:pressed {
    background: $btn_bottom;
}
QPushButton#addAppBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $add_btn_top, stop:1 $add_btn_bottom);
    border: 1px solid $add_btn_border;
    border-radius: 18px;
    color: #ffffff;
    padding: 0 8px;
    font-size: 12px;
    font-weight: 700;
}
QPushButton#addAppBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $add_btn_hover_top, stop:1 $add_btn_hover_bottom);
    border-color: $add_btn_border;
    color: #ffffff;
}
QPushButton#addAppBtn:pressed {
    background: $add_btn_bottom;
}
QPushButton#danger {
    color: $danger;
    border: 1px solid rgba($danger_rgb, 25%);
    background: rgba($danger_rgb, 6%);
}
QPushButton#danger:hover {
    background: rgba($danger_rgb, 14%);
    color: $danger_hover_text;
}
QPushButton#deleteBtn {
    background: transparent;
    border: none;
    color: $text3;
    font-size: 13px;
    padding: 0;
}
QPushButton#deleteBtn:hover {
    color: $danger;
    background: transparent;
}
QPushButton#periodBtn {
    background: transparent;
    border: none;
    color: $text2;
    padding: 6px 12px;
    border-radius: 8px;
    font-weight: 700;
    font-size: 13px;
}
QPushButton#periodBtn:hover {
    color: $text;
    background: rgba($accent_rgb, 8%);
}
QPushButton#periodBtn:checked {
    color: $accent;
    background: rgba($accent_rgb, 12%);
}
QPushButton#navBtn {
    background: $soft4;
    border: 1px solid $card;
    border-radius: 16px;
    padding: 0;
}
QPushButton#navBtn:hover {
    border-color: $hover_border;
    background: rgba($accent_rgb, 12%);
}
QPushButton#navBtn:pressed {
    background: rgba($accent_rgb, 18%);
}
QPushButton#navBtn:disabled {
    background: transparent;
    border-color: $disabled_border;
}
QLabel#periodLabel {
    color: $menu_text;
    font-size: 12px;
    font-weight: 600;
}
QPushButton#profileBtn {
    background: transparent;
    border: none;
    padding: 4px 10px;
    border-radius: 18px;
    color: $text;
    font-weight: 600;
}
QPushButton#profileBtn:hover {
    background: $soft6;
}
QFrame#popupItem {
    background: transparent;
    border: none;
    border-radius: 8px;
}
QFrame#popupItem:hover {
    background: rgba($accent_rgb, 10%);
}
QLabel#popupItemText {
    color: $text2;
    font-weight: 600;
    background: transparent;
}
QFrame#popupItem:hover QLabel#popupItemText {
    color: $text;
}

QFrame#addRow {
    border-radius: 10px;
    border: 1px solid transparent;
    background: transparent;
}
QFrame#addRow:hover {
    background: rgba($accent_rgb, 7%);
    border-color: $card_border;
}
QPushButton#rowAdd {
    background: transparent;
    border: 1px solid $row_btn_border;
    border-radius: 8px;
    color: $accent;
    font-weight: 700;
    font-size: 12px;
    padding: 5px 10px;
}
QFrame#addRow:hover QPushButton#rowAdd {
    border-color: $accent;
    background: rgba($accent_rgb, 12%);
}
QPushButton#rowAddDone {
    background: rgba($accent_rgb, 12%);
    border: 1px solid rgba($accent_rgb, 42%);
    border-radius: 8px;
    color: $accent;
    font-weight: 700;
    font-size: 12px;
    padding: 5px 10px;
}

QLineEdit, QSpinBox {
    background: $soft5;
    border: 1px solid $card;
    border-radius: 10px;
    padding: 7px 12px;
    color: $text;
    selection-background-color: $btn_top;
}
QLineEdit:focus, QSpinBox:focus {
    border: 1px solid $accent;
    background: $soft8;
}
QLineEdit#searchEdit {
    border-radius: 16px;
    padding: 7px 16px;
}
QSpinBox::up-button, QSpinBox::down-button {
    background: $soft8;
    border: none;
    width: 16px;
}

QListWidget#addList {
    background: $list_bg;
    border: 1px solid $card;
    border-radius: 12px;
    padding: 3px;
}
QListWidget#addList::item {
    border-bottom: 1px solid $list_item_border;
    padding: 2px;
}
QListWidget#addList::item:selected {
    background: rgba($accent_rgb, 10%);
}

/* Список приложений в окне добавления: QScrollArea с фоном темы.
   Вьюпорт красится явно (theme.paint_background), эти правила — страховка. */
QScrollArea#addScroll {
    background: $list_bg;
    border: 1px solid $card;
    border-radius: 12px;
}
QScrollArea#addScroll > QWidget > QWidget {
    background: $list_bg;
}
QWidget#addHost {
    background: $list_bg;
}

QScrollBar:vertical {
    background: $soft2;
    width: 10px;
    margin: 0;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: $card;
    border-radius: 4px;
    min-height: 30px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover {
    background: $hover_border;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    height: 0;
}

QStatusBar {
    background: $bg;
    border-top: 1px solid $sidebar_edge;
    color: $text3;
}
QStatusBar::item {
    border: none;
}
QStatusBar QLabel {
    color: $text3;
    background: transparent;
    font-size: 12px;
}

QToolTip {
    background-color: $sidebar;
    color: $text;
    border: 1px solid $card_border;
    padding: 5px 8px;
    border-radius: 6px;
}

QFrame#profilePopup {
    border-radius: 12px;
    border: 1px solid $card_border;
    background: $popup;
}

QMessageBox {
    background-color: $popup;
}
QMessageBox QLabel {
    background: transparent;
    color: $text;
    font-size: 14px;
}

QFrame#themeSample {
    border: 1px solid $card_border;
    border-radius: 10px;
    background: $soft3;
}
QFrame#themeSample:hover {
    border-color: $hover_border;
}
QFrame#themeSample[active="true"] {
    border: 1px solid $accent;
    background: rgba($accent_rgb, 10%);
}
QLabel#themeName {
    color: $text2;
    font-size: 12px;
    font-weight: 600;
}
QFrame#themeSample[active="true"] QLabel#themeName {
    color: $text;
}

QProgressBar {
    background: $soft5;
    border: 1px solid $card_border;
    border-radius: 6px;
    text-align: center;
    color: transparent;
    font-size: 1px;
}
QProgressBar::chunk {
    background: $accent;
    border-radius: 5px;
}

QFrame#updateBanner {
    border-radius: 12px;
    border: 1px solid rgba($accent_rgb, 40%);
    background: rgba($accent_rgb, 10%);
}
QLabel#updateBannerTitle {
    color: $text;
    font-size: 13px;
    font-weight: 700;
}
QFrame#updatePlate {
    border-radius: 12px;
    border: 1px solid rgba($accent_rgb, 35%);
    background: rgba($accent_rgb, 12%);
}
QLabel#updatePlateText {
    color: $text;
    font-size: 13px;
    font-weight: 700;
}
QLabel#popupVersion {
    color: $text3;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 12px;
}
""")


def build_qss(p: Palette) -> str:
    return _QSS_TEMPLATE.safe_substitute(_derive(p))


def build_palette(p: Palette) -> QPalette:
    """Нативная палитра в цветах темы.

    QSS красит только те элементы, которые умеет; всё остальное (фон окна до
    первой отрисовки, вьюпорты QScrollArea, QMessageBox, рамки диалогов и
    всплывающие подсказки ОС) берёт цвета отсюда. Без этого при старте и при
    перестроении виджетов мелькает системный белый фон.
    """
    bg = QColor(p.bg)
    bg2 = QColor(p.bg2)
    text = QColor(p.text)
    text2 = QColor(p.text2)
    text3 = QColor(p.text3)
    accent = QColor(p.accent)
    card = QColor(p.card)
    popup = QColor(p.popup)
    dimmed = QColor(p.border)

    pal = QPalette()
    roles_window = (QPalette.Window, QPalette.Base, QPalette.AlternateBase,
                    QPalette.ToolTipBase, QPalette.Button, QPalette.Light,
                    QPalette.Midlight, QPalette.Dark, QPalette.Mid, QPalette.Shadow)
    for role in roles_window:
        pal.setColor(role, bg)
    roles_window_text = (QPalette.WindowText, QPalette.Text, QPalette.ToolTipText,
                         QPalette.ButtonText, QPalette.BrightText)
    for role in roles_window_text:
        pal.setColor(role, text)
    pal.setColor(QPalette.Highlight, accent)
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.Link, accent)
    pal.setColor(QPalette.LinkVisited, accent)
    pal.setColor(QPalette.PlaceholderText, text3)
    pal.setColor(QPalette.Disabled, QPalette.Text, text3)
    pal.setColor(QPalette.Disabled, QPalette.WindowText, text3)
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, text3)
    pal.setColor(QPalette.Disabled, QPalette.Base, bg2)
    pal.setColor(QPalette.Disabled, QPalette.Highlight, dimmed)
    pal.setColor(QPalette.Disabled, QPalette.HighlightedText, text2)
    pal.setColor(QPalette.Disabled, QPalette.Light, card)
    pal.setColor(QPalette.Disabled, QPalette.Mid, dimmed)
    # Тёмные темы почти не используют эти роли, но системные диалоги — да.
    pal.setColor(QPalette.ToolTipBase, popup)
    pal.setColor(QPalette.ToolTipText, text)
    if p.is_light:
        pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    else:
        pal.setColor(QPalette.HighlightedText, QColor("#04121f"))
    return pal


def paint_background(widget, color: QColor | None = None) -> None:
    """Красит нативный фон виджета и его вьюпорта (если он есть) под тему."""
    col = QColor(color) if color is not None else QColor(_current.bg)
    pal = widget.palette()
    pal.setColor(QPalette.Window, col)
    pal.setColor(QPalette.Base, col)
    widget.setPalette(pal)
    widget.setAutoFillBackground(True)
    viewport = getattr(widget, "viewport", None)
    if callable(viewport):
        try:
            vp = viewport()
        except Exception:
            vp = None
        if vp is not None and vp is not widget:
            vpal = vp.palette()
            vpal.setColor(QPalette.Window, col)
            vpal.setColor(QPalette.Base, col)
            vp.setPalette(vpal)
            vp.setAutoFillBackground(True)


_current: Palette = PALETTES[DEFAULT_THEME]
_COLOR_CACHE: dict[str, QColor] = {}

BG = _current.bg
SIDEBAR_TOP = _current.sidebar
CARD_TOP = _current.card
ACCENT = _current.accent
CYAN = _current.cyan
TXT = _current.text
TXT2 = _current.text2
TXT3 = _current.text3
QSS = build_qss(_current)


def pal() -> Palette:
    return _current


def apply_theme(app, key: str) -> Palette:
    """Применяет палитру: неизвестное имя молча возвращает тёмную по умолчанию."""
    global _current, QSS, BG, SIDEBAR_TOP, CARD_TOP, ACCENT, CYAN, TXT, TXT2, TXT3
    p = PALETTES.get(key, PALETTES[DEFAULT_THEME])
    _current = p
    _COLOR_CACHE.clear()
    BG, SIDEBAR_TOP, CARD_TOP = p.bg, p.sidebar, p.card
    ACCENT, CYAN, TXT, TXT2, TXT3 = p.accent, p.cyan, p.text, p.text2, p.text3
    QSS = build_qss(p)
    if app is not None:
        # Глобальная нативная палитра: без неё системные части (фоны окон,
        # вьюпорты, диалоги, тултипы) остаются светлыми и мелькают белым.
        app.setPalette(build_palette(p))
        app.setStyleSheet(QSS)
        _paint_all_scrollareas(app)
    return p


def _paint_all_scrollareas(app) -> None:
    """Красит нативные фоны ВСЕХ прокручиваемых областей в дереве виджетов.

    QSS красит только сами области, а их viewport() — системный, белый.
    Перекраска при применении темы гарантирует, что и вьюпорты модальных
    панелей (настройки, статистика, обновление) не мигнут белым.
    """
    try:
        from PySide6.QtWidgets import QAbstractScrollArea

        def walk(widget):
            for child in widget.findChildren(QAbstractScrollArea):
                # Сайдбар намеренно прозрачный: его viewport должен показывать
                # фон mainRoot, иначе при смене темы появляется полоса на стыке.
                if child.objectName() == "sidebarScroll":
                    child.setAutoFillBackground(False)
                    child.viewport().setAutoFillBackground(False)
                else:
                    paint_background(child)
            for child in widget.findChildren(QAbstractScrollArea):
                walk(child)

        walk(app)
    except Exception:
        pass


def accent_alpha(alpha: int) -> QColor:
    r, g, b = _hx(_current.accent)
    return QColor(r, g, b, max(0, min(255, int(alpha))))


def _make_color(token: str) -> QColor:
    p = _current
    simple = {
        "bg": p.bg, "bg2": p.bg2, "sidebar": p.sidebar, "card": p.card,
        "card_hover": p.card_hover, "border": p.border, "text": p.text,
        "text2": p.text2, "text3": p.text3, "accent": p.accent,
        "chart_line": p.accent, "cyan": p.cyan, "danger": p.danger,
        "popup": p.popup, "chart_dim": p.text3, "tooltip_border": p.border,
        "tooltip_text": p.text, "point_ring": p.card, "popup_bg": p.popup,
        "popup_border": p.border, "popup_sep": p.card, "icon": p.text2,
        "add_btn_border": _mix_hex(p.accent, p.border, 0.35),
    }
    if token in simple:
        return QColor(simple[token])
    ar, ag, ab = _hx(p.accent)
    if token == "chart_fill_top":
        return QColor(ar, ag, ab, p.chart_fill_top)
    if token == "chart_fill_bottom":
        return QColor(ar, ag, ab, p.chart_fill_bottom)
    if token == "tooltip_bg":
        pr, pg, pb = _hx(p.popup)
        return QColor(pr, pg, pb, 240)
    if token == "dim":
        if p.is_light:
            return QColor(30, 41, 59, 70)
        br, bg_, bb = _hx(p.bg)
        return QColor(br, bg_, bb, 100)
    if token == "shadow":
        return QColor(*p.shadow)
    if token == "shadow_hover":
        return QColor(ar, ag, ab, 70 if p.is_light else 110)
    if token == "overlay":
        return QColor(*p.overlay)
    if token == "toggle_off":
        return QColor(_mix_hex(p.card_hover, p.border, 0.6))
    if token == "knob":
        return QColor("#ffffff" if p.is_light else "#e8eef6")
    return QColor(p.accent)


def color(token: str) -> QColor:
    cached = _COLOR_CACHE.get(token)
    if cached is None:
        cached = _make_color(token)
        _COLOR_CACHE[token] = cached
    return cached


def button_colors() -> tuple[str, str, str, str]:
    """Градиент акцентной кнопки текущей темы (обычный / hover)."""
    return _button_colors(_current)


_ICON_PATH = Path(__file__).resolve().parents[2] / "assets" / "app_icon.ico"


def load_app_icon() -> QIcon:
    if _ICON_PATH.exists():
        icon = QIcon(str(_ICON_PATH))
        if not icon.isNull():
            return icon
    return make_clock_icon()


def make_clock_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(pal().accent), 5)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QRectF(7, 7, 50, 50))
    painter.drawLine(32, 32, 32, 16)
    painter.drawLine(32, 32, 44, 38)
    painter.end()
    return QIcon(pm)
