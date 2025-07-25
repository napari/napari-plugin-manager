import sys
from typing import TYPE_CHECKING

import pytest
from qtpy.QtWidgets import QDialog, QInputDialog, QMessageBox

from napari_plugin_manager.qt_package_installer import CondaInstallerTool


@pytest.fixture(autouse=True)
def _block_message_box(monkeypatch, request):
    def raise_on_call(*_, **__):
        raise RuntimeError('exec_ call')  # pragma: no cover

    monkeypatch.setattr(QMessageBox, 'exec_', raise_on_call)
    monkeypatch.setattr(QMessageBox, 'critical', raise_on_call)
    monkeypatch.setattr(QMessageBox, 'information', raise_on_call)
    monkeypatch.setattr(QMessageBox, 'question', raise_on_call)
    monkeypatch.setattr(QMessageBox, 'warning', raise_on_call)
    monkeypatch.setattr(QInputDialog, 'getText', raise_on_call)
    # QDialogs can be allowed via a marker; only raise if not decorated
    if 'enabledialog' not in request.keywords:
        monkeypatch.setattr(QDialog, 'exec_', raise_on_call)


if TYPE_CHECKING:
    from virtualenv.run import Session


@pytest.fixture
def tmp_virtualenv(tmp_path) -> 'Session':
    virtualenv = pytest.importorskip('virtualenv')

    cmd = [str(tmp_path), '--no-setuptools', '--no-wheel', '--activators', '']
    return virtualenv.cli_run(cmd)


@pytest.fixture
def tmp_conda_env(tmp_path):
    import subprocess

    try:
        subprocess.check_output(
            [
                CondaInstallerTool.executable(),
                'create',
                '-yq',
                '-p',
                str(tmp_path),
                '--override-channels',
                '-c',
                'conda-forge',
                f'python={sys.version_info.major}.{sys.version_info.minor}',
            ],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=300,
        )
    except subprocess.CalledProcessError as exc:
        print(exc.output)
        raise

    return tmp_path
