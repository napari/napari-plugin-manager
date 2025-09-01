import textwrap

from qtpy.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget


class RestartWarningDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle('Restart napari')
        okay_btn = QPushButton('Okay')
        self.restart_warning_text = """
            Plugins have been added/removed or updated. If you notice any issues
            with plugin functionality, you may need to restart napari.
        """

        okay_btn.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(QLabel(textwrap.dedent(self.restart_warning_text)))
        layout.addWidget(okay_btn)
        self.setLayout(layout)
