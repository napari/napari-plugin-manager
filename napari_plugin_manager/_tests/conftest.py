import pytest
from qtpy.QtWidgets import QDialog, QInputDialog, QMessageBox


@pytest.fixture(autouse=True)
def _block_message_box(monkeypatch, request):
    def raise_on_call(*_, **__):
        raise RuntimeError("exec_ call")  # pragma: no cover

    monkeypatch.setattr(QMessageBox, "exec_", raise_on_call)
    monkeypatch.setattr(QMessageBox, "critical", raise_on_call)
    monkeypatch.setattr(QMessageBox, "information", raise_on_call)
    monkeypatch.setattr(QMessageBox, "question", raise_on_call)
    monkeypatch.setattr(QMessageBox, "warning", raise_on_call)
    monkeypatch.setattr(QInputDialog, "getText", raise_on_call)
    # QDialogs can be allowed via a marker; only raise if not decorated
    if "enabledialog" not in request.keywords:
        monkeypatch.setattr(QDialog, "exec_", raise_on_call)
