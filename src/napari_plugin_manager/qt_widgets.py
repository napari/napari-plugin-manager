from qtpy.QtCore import Signal
from qtpy.QtGui import QMouseEvent
from qtpy.QtWidgets import QLabel


class ClickableLabel(QLabel):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)

    def mouseReleaseEvent(self, event: QMouseEvent):
        super().mouseReleaseEvent(event)
        self.clicked.emit()
