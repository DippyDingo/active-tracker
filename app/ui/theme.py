from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

ACCENT = "#66c0f4"

QSS = """
* {
    outline: 0;
}
QWidget {
    background-color: #1b2838;
    color: #c7d5e0;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 14px;
}
QMainWindow, QDialog {
    background-color: #1b2838;
}
QFrame#Header {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #171a21, stop:1 #1b2838);
    border-bottom: 1px solid #0e141b;
}
QLabel#AppTitle {
    color: #ffffff;
    font-size: 21px;
    font-weight: 600;
    background: transparent;
}
QLabel#subtleLabel {
    color: #8ba0b3;
    font-size: 12px;
    background: transparent;
}
QLabel#todayTotal {
    color: #66c0f4;
    font-size: 17px;
    font-weight: 700;
    background: transparent;
}
QLabel#emptyLabel {
    color: #8ba0b3;
    font-size: 15px;
    background: transparent;
}
QWidget#scrollContainer {
    background: transparent;
}
QFrame#appCard {
    background-color: #21303f;
    border: 1px solid #2a475e;
    border-radius: 6px;
}
QFrame#appCard:hover {
    background-color: #2a475e;
    border: 1px solid #3d6a8d;
}
QLabel#appName {
    color: #ffffff;
    font-size: 15px;
    font-weight: 600;
    background: transparent;
}
QLabel#appPath {
    color: #8ba0b3;
    font-size: 11px;
    background: transparent;
}
QLabel#timeBig {
    color: #66c0f4;
    font-size: 16px;
    font-weight: 700;
    background: transparent;
}
QLabel#runningDot {
    background-color: #75b022;
    border-radius: 4px;
    min-width: 8px;
    min-height: 8px;
    max-width: 8px;
    max-height: 8px;
}
QPushButton {
    background-color: #2a475e;
    color: #c7d5e0;
    border: 1px solid #3d6a8d;
    border-radius: 3px;
    padding: 7px 16px;
}
QPushButton:hover {
    background-color: #3d6a8d;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #1b2838;
}
QPushButton:disabled {
    background-color: #22303c;
    color: #55677a;
    border-color: #2a475e;
}
QPushButton#primary {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #75b022, stop:1 #588a1b);
    border: none;
    color: #d2ffa9;
    font-weight: 600;
}
QPushButton#primary:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #8ed629, stop:1 #6aa621);
    color: #ffffff;
}
QPushButton#primary:pressed {
    background-color: #4c6b13;
}
QPushButton#deleteBtn {
    background: transparent;
    border: none;
    color: #55677a;
    font-size: 14px;
    padding: 0;
}
QPushButton#deleteBtn:hover {
    color: #e05a4d;
    background: transparent;
}
QLineEdit, QSpinBox {
    background-color: #316282;
    border: 1px solid #0e141b;
    border-radius: 3px;
    padding: 6px 9px;
    color: #ffffff;
    selection-background-color: #66c0f4;
    selection-color: #10161c;
}
QLineEdit:focus, QSpinBox:focus {
    border: 1px solid #66c0f4;
}
QSpinBox::up-button, QSpinBox::down-button {
    background: #2a475e;
    border: none;
    width: 16px;
}
QLineEdit#searchEdit {
    font-size: 15px;
    padding: 8px 12px;
    background-color: #316282;
}
QListWidget {
    background-color: #16202d;
    border: 1px solid #2a475e;
    border-radius: 4px;
    padding: 2px;
}
QListWidget::item {
    padding: 7px 8px;
    border-bottom: 1px solid #20303f;
    color: #c7d5e0;
}
QListWidget::item:selected {
    background-color: #2a475e;
    color: #ffffff;
}
QListWidget::item:hover {
    background-color: #22364a;
}
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: #171a21;
    width: 12px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #3d6a8d;
    border-radius: 5px;
    min-height: 30px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover {
    background: #66c0f4;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    height: 0;
}
QStatusBar {
    background: #171a21;
    color: #8ba0b3;
    border-top: 1px solid #0e141b;
}
QStatusBar::item {
    border: none;
}
QStatusBar QLabel {
    background: transparent;
    color: #8ba0b3;
}
QToolTip {
    background-color: #171a21;
    color: #c7d5e0;
    border: 1px solid #2a475e;
    padding: 4px;
}
QMenu {
    background-color: #1b2838;
    border: 1px solid #2a475e;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px;
    border-radius: 2px;
}
QMenu::item:selected {
    background-color: #2a475e;
    color: #ffffff;
}
QCheckBox {
    background: transparent;
    color: #c7d5e0;
    spacing: 8px;
}
QCheckBox:hover {
    color: #ffffff;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #0e141b;
    border-radius: 3px;
    background: #316282;
}
QCheckBox::indicator:hover {
    border-color: #66c0f4;
}
QCheckBox::indicator:checked {
    background: #66c0f4;
    border-color: #66c0f4;
}
QMessageBox {
    background-color: #1b2838;
}
QMessageBox QLabel {
    background: transparent;
    font-size: 14px;
}
"""


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
