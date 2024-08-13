from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QMouseEvent, QPainter
from qtpy.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QStyleOption,
    QWidget,
)


class ClickableLabel(QLabel):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)

    def mouseReleaseEvent(self, event: QMouseEvent):
        super().mouseReleaseEvent(event)
        self.clicked.emit()


class DisclaimerWidget(QWidget):
    def __init__(self, text, parent=None):
        super().__init__(parent=parent)

        # Setup widgets
        disclaimer_label = QLabel(text)
        disclaimer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        disclaimer_button = QPushButton("x")
        disclaimer_button.setFixedSize(20, 20)
        disclaimer_button.clicked.connect(self.hide)

        # Setup layout
        disclaimer_layout = QHBoxLayout()
        disclaimer_layout.addWidget(disclaimer_label)
        disclaimer_layout.addWidget(disclaimer_button)
        self.setLayout(disclaimer_layout)

    def paintEvent(self, paint_event):
        """
        Override so `QWidget` subclass can be affect by the stylesheet.

        For details you can check: https://doc.qt.io/qt-5/stylesheet-reference.html#list-of-stylable-widgets
        """
        style_option = QStyleOption()
        style_option.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(
            QStyle.PE_Widget, style_option, painter, self
        )
