from qtpy.QtCore import Signal
from qtpy.QtGui import QMouseEvent
from qtpy.QtWidgets import QLabel, QWidget


class ClickableLabel(QLabel):
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        self.clicked.emit()
