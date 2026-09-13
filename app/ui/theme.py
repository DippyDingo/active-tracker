from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

BG = "#0b1220"
SIDEBAR_TOP = "#0f1b2d"
CARD_TOP = "#1e293b"
ACCENT = "#60a5fa"
CYAN = "#22d3ee"
TXT = "#e5e7eb"
TXT2 = "#9ca3af"
TXT3 = "#6b7280"

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
    pen = QPen(QColor(ACCENT), 5)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QRectF(7, 7, 50, 50))
    painter.drawLine(32, 32, 32, 16)
    painter.drawLine(32, 32, 44, 38)
    painter.end()
    return QIcon(pm)


QSS = """
* {
    outline: 0;
}
QWidget {
    background: transparent;
    color: #e5e7eb;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 14px;
}
QMainWindow, QDialog {
    background-color: #0b1220;
}
QWidget#mainRoot {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #0b1220, stop:1 #0f172a);
}
QFrame#sidebar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #0f1b2d, stop:1 #0b1220);
    border-right: 1px solid #16202f;
}
QLabel {
    background: transparent;
}
QLabel#sectionTitle {
    color: #9ca3af;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#pageTitle {
    color: #e5e7eb;
    font-size: 23px;
    font-weight: 800;
}
QLabel#pageSub {
    color: #9ca3af;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
}
QLabel#subtleLabel {
    color: #9ca3af;
    font-size: 12px;
}
QLabel#mutedLabel {
    color: #6b7280;
    font-size: 11px;
}
QLabel#cardName {
    color: #e5e7eb;
    font-size: 14px;
    font-weight: 600;
}
QLabel#cardTime {
    color: #ffffff;
    font-size: 29px;
    font-weight: 800;
}
QLabel#dayLabel {
    color: #6b7280;
    font-size: 10px;
}
QLabel#cardFooter {
    color: #9ca3af;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.4px;
}
QLabel#sideName {
    color: #e5e7eb;
    font-size: 13px;
    font-weight: 600;
}
QLabel#pathLabel {
    color: #6b7280;
    font-size: 11px;
}
QLabel#statBig {
    color: #ffffff;
    font-size: 34px;
    font-weight: 800;
}
QLabel#statLabel {
    color: #6b7280;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.6px;
}
QLabel#statValue {
    color: #e5e7eb;
    font-size: 14px;
    font-weight: 600;
}
QLabel#modalTitle {
    color: #ffffff;
    font-size: 17px;
    font-weight: 800;
}
QLabel#emptyLabel {
    color: #6b7280;
    font-size: 15px;
}
QLabel#avatar {
    border-radius: 17px;
    color: #04121f;
    font-weight: 800;
    font-size: 15px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #60a5fa, stop:1 #22d3ee);
}
QLabel#runningDot {
    background-color: #22d3ee;
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
    background: rgba(255, 255, 255, 5%);
}
QFrame#sideItem[selected="true"] {
    background: rgba(59, 130, 246, 15%);
    border: 1px solid rgba(96, 165, 250, 50%);
}
QFrame#catHeader {
    border-radius: 8px;
    border: 1px solid rgba(96, 165, 250, 10%);
    background: rgba(255, 255, 255, 3%);
}
QFrame#catHeader:hover {
    background: rgba(96, 165, 250, 7%);
    border: 1px solid rgba(96, 165, 250, 25%);
}
QFrame#catHeader[droptarget="true"] {
    background: rgba(96, 165, 250, 12%);
    border: 1px solid rgba(96, 165, 250, 60%);
}
QFrame#catHeader[flash="true"] {
    background: rgba(96, 165, 250, 16%);
    border: 1px solid rgba(96, 165, 250, 65%);
}
QFrame#sideItem[flash="true"] {
    background: rgba(96, 165, 250, 18%);
    border: 1px solid rgba(96, 165, 250, 60%);
}
QLabel#catName {
    color: #b6c4d4;
    font-size: 11px;
    font-weight: 700;
}
QLabel#catArrow {
    color: #6b7280;
    font-size: 11px;
}
QLabel#catCount {
    color: #9db2c7;
    background: rgba(96, 165, 250, 12%);
    border-radius: 8px;
    padding: 1px 8px;
    font-size: 11px;
    font-weight: 700;
}
QMenu {
    background-color: #101a2c;
    border: 1px solid #24344d;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 8px 28px 8px 12px;
    border-radius: 7px;
    margin: 1px 3px;
    color: #c7d2de;
    background: transparent;
}
QMenu::item:selected {
    background: rgba(96, 165, 250, 12%);
    color: #ffffff;
}
QMenu::item:pressed {
    background: rgba(96, 165, 250, 24%);
    color: #ffffff;
}
QMenu::item:disabled {
    color: #55677a;
}
QMenu::separator {
    height: 1px;
    background: #1e293b;
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
    border: 1px solid rgba(96, 165, 250, 50%);
    background: rgba(59, 130, 246, 8%);
}
QFrame#inlineEdit QLineEdit {
    background: transparent;
    border: none;
    color: #e5e7eb;
    font-size: 13px;
    font-weight: 600;
    padding: 2px;
}

QScrollArea {
    border: none;
    background: transparent;
}
QWidget#cardsContainer {
    background: transparent;
}

QFrame#appCard {
    border-radius: 16px;
    border: 1px solid #223047;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #1e293b, stop:1 #131c2e);
}
QFrame#appCard:hover {
    border-color: #33507e;
}
QFrame#appCard[selected="true"] {
    border-color: #60a5fa;
}

QFrame#modalPanel {
    border-radius: 18px;
    border: 1px solid #24344d;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #101a2c, stop:1 #0c1424);
}
QFrame#statBox {
    border-radius: 12px;
    border: 1px solid #1e293b;
    background: rgba(255, 255, 255, 3%);
    padding: 8px;
}
QFrame#rangeResult {
    border-radius: 12px;
    border: 1px solid #1e293b;
    background: rgba(255, 255, 255, 3%);
}
QFrame#helpBox {
    border-radius: 12px;
    border: 1px solid rgba(96, 165, 250, 12%);
    background: rgba(96, 165, 250, 4%);
}
QLabel#helpTitle {
    color: #b6c4d4;
    font-size: 12px;
    font-weight: 700;
}
QLabel#helpBullet {
    color: #9ca3af;
    font-size: 12px;
}

QPushButton {
    background: rgba(255, 255, 255, 5%);
    border: 1px solid #1e293b;
    border-radius: 10px;
    padding: 8px 14px;
    color: #9ca3af;
    font-weight: 600;
}
QPushButton:hover {
    color: #e5e7eb;
    border-color: #33507e;
    background: rgba(96, 165, 250, 10%);
}
QPushButton:pressed {
    background: rgba(96, 165, 250, 16%);
}
QPushButton:disabled {
    color: #475569;
    border-color: #182234;
    background: transparent;
}
QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #3b82f6, stop:1 #2563eb);
    border: none;
    color: #ffffff;
    font-weight: 700;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #60a5fa, stop:1 #3b82f6);
    color: #ffffff;
}
QPushButton#primary:pressed {
    background: #2563eb;
}
QPushButton#danger {
    color: #f87171;
    border: 1px solid rgba(248, 113, 113, 25%);
    background: rgba(248, 113, 113, 6%);
}
QPushButton#danger:hover {
    background: rgba(248, 113, 113, 14%);
    color: #fecaca;
}
QPushButton#deleteBtn {
    background: transparent;
    border: none;
    color: #475569;
    font-size: 13px;
    padding: 0;
}
QPushButton#deleteBtn:hover {
    color: #f87171;
    background: transparent;
}
QPushButton#periodBtn {
    background: transparent;
    border: none;
    color: #9ca3af;
    padding: 6px 12px;
    border-radius: 8px;
    font-weight: 700;
    font-size: 13px;
}
QPushButton#periodBtn:hover {
    color: #e5e7eb;
    background: rgba(96, 165, 250, 8%);
}
QPushButton#periodBtn:checked {
    color: #60a5fa;
    background: rgba(96, 165, 250, 12%);
}
QPushButton#profileBtn {
    background: transparent;
    border: none;
    padding: 4px 10px;
    border-radius: 18px;
    color: #e5e7eb;
    font-weight: 600;
}
QPushButton#profileBtn:hover {
    background: rgba(255, 255, 255, 6%);
}
QFrame#popupItem {
    background: transparent;
    border: none;
    border-radius: 8px;
}
QFrame#popupItem:hover {
    background: rgba(96, 165, 250, 10%);
}
QLabel#popupItemText {
    color: #9ca3af;
    font-weight: 600;
    background: transparent;
}
QFrame#popupItem:hover QLabel#popupItemText {
    color: #e5e7eb;
}

QFrame#addRow {
    border-radius: 10px;
    border: 1px solid transparent;
    background: transparent;
}
QFrame#addRow:hover {
    background: rgba(96, 165, 250, 7%);
    border-color: #223047;
}
QPushButton#rowAdd {
    background: transparent;
    border: 1px solid #2a3a55;
    border-radius: 8px;
    color: #60a5fa;
    font-weight: 700;
    font-size: 12px;
    padding: 5px 10px;
}
QFrame#addRow:hover QPushButton#rowAdd {
    border-color: #60a5fa;
    background: rgba(96, 165, 250, 12%);
}
QPushButton#rowAddDone {
    background: rgba(34, 197, 94, 10%);
    border: 1px solid rgba(34, 197, 94, 40%);
    border-radius: 8px;
    color: #4ade80;
    font-weight: 700;
    font-size: 12px;
    padding: 5px 10px;
}

QLineEdit, QSpinBox {
    background: rgba(255, 255, 255, 5%);
    border: 1px solid #1e293b;
    border-radius: 10px;
    padding: 7px 12px;
    color: #e5e7eb;
    selection-background-color: #3b82f6;
}
QLineEdit:focus, QSpinBox:focus {
    border: 1px solid #60a5fa;
    background: rgba(255, 255, 255, 8%);
}
QLineEdit#searchEdit {
    border-radius: 16px;
    padding: 7px 16px;
}
QSpinBox::up-button, QSpinBox::down-button {
    background: rgba(255, 255, 255, 8%);
    border: none;
    width: 16px;
}

QListWidget#addList {
    background: #0d1626;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 3px;
}
QListWidget#addList::item {
    border-bottom: 1px solid #152031;
    padding: 2px;
}
QListWidget#addList::item:selected {
    background: rgba(96, 165, 250, 10%);
}

QScrollBar:vertical {
    background: rgba(255, 255, 255, 2%);
    width: 10px;
    margin: 0;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #1e293b;
    border-radius: 4px;
    min-height: 30px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover {
    background: #33507e;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    height: 0;
}

QStatusBar {
    background: #0b1220;
    border-top: 1px solid #16202f;
    color: #6b7280;
}
QStatusBar::item {
    border: none;
}
QStatusBar QLabel {
    color: #6b7280;
    background: transparent;
    font-size: 12px;
}

QToolTip {
    background-color: #0f1b2d;
    color: #e5e7eb;
    border: 1px solid #223047;
    padding: 5px 8px;
    border-radius: 6px;
}

QFrame#profilePopup {
    border-radius: 12px;
    border: 1px solid #223047;
    background: #101a2c;
}

QMessageBox {
    background-color: #101a2c;
}
QMessageBox QLabel {
    background: transparent;
    color: #e5e7eb;
    font-size: 14px;
}
"""
