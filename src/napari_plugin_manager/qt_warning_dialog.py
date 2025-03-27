from qtpy.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget


class RestartWarningDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle('Restart napari')
        okay_btn = QPushButton('Okay')
        self.restart_warning_text = """
Restart napari after installing/uninstalling npe2 plugins.
        """

        okay_btn.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(QLabel(self.restart_warning_text))
        layout.addWidget(okay_btn)
        self.setLayout(layout)
