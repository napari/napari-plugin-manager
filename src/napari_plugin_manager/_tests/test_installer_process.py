import logging
import re
import sys
import time
from pathlib import Path
from types import MethodType
from typing import TYPE_CHECKING

import pytest
from qtpy.QtCore import QProcessEnvironment

import napari_plugin_manager.base_qt_package_installer as bqpi
from napari_plugin_manager.base_qt_package_installer import (
    AbstractInstallerTool,
    InstallerActions,
    InstallerTools,
)
from napari_plugin_manager.qt_package_installer import (
    NapariCondaInstallerTool,
    NapariInstallerQueue,
    NapariPipInstallerTool,
)

if TYPE_CHECKING:
    from virtualenv.run import Session


def _assert_exit_code_not_zero(
    self, exit_code=None, exit_status=None, error=None
):
    errors = []
    if exit_code == 0:
        errors.append("- 'exit_code' should have been non-zero!")
    if error is not None:
        errors.append("- 'error' should have been None!")
    if errors:
        raise AssertionError("\n".join(errors))
    return self._on_process_done_original(exit_code, exit_status, error)


def _assert_error_used(self, exit_code=None, exit_status=None, error=None):
    errors = []
    if error is None:
        errors.append("- 'error' should have been populated!")
    if exit_code is not None:
        errors.append("- 'exit_code' should not have been populated!")
    if errors:
        raise AssertionError("\n".join(errors))
    return self._on_process_done_original(exit_code, exit_status, error)


class _NonExistingTool(AbstractInstallerTool):
    def executable(self):
        return f"this-tool-does-not-exist-{hash(time.time())}"

    def arguments(self):
        return ()

    def environment(self, env=None):
        return QProcessEnvironment.systemEnvironment()


def test_pip_installer_tasks(
    qtbot, tmp_virtualenv: 'Session', monkeypatch, caplog
):
    caplog.set_level(logging.DEBUG, logger=bqpi.__name__)
    installer = NapariInstallerQueue()
    monkeypatch.setattr(
        NapariPipInstallerTool,
        "executable",
        lambda *a: tmp_virtualenv.creator.exe,
    )
    monkeypatch.setattr(
        NapariPipInstallerTool,
        "origins",
        ("https://pypi.org/simple",),
    )
    with qtbot.waitSignal(installer.allFinished, timeout=20000):
        installer.install(
            tool=InstallerTools.PIP,
            pkgs=['pip-install-test'],
        )
        installer.install(
            tool=InstallerTools.PIP,
            pkgs=['typing-extensions'],
        )
        job_id = installer.install(
            tool=InstallerTools.PIP,
            pkgs=['requests'],
        )
        assert isinstance(job_id, int)
        installer.cancel(job_id)

    assert not installer.hasJobs()

    pkgs = 0
    for pth in tmp_virtualenv.creator.libs:
        if (pth / 'pip_install_test').exists():
            pkgs += 1
        if (pth / 'typing_extensions.py').exists():
            pkgs += 1
        if (pth / 'requests').exists():
            raise AssertionError('requests got installed')

    assert pkgs >= 2, 'package was not installed'

    with qtbot.waitSignal(installer.allFinished, timeout=10000):
        job_id = installer.uninstall(
            tool=InstallerTools.PIP,
            pkgs=['pip-install-test'],
        )

    for pth in tmp_virtualenv.creator.libs:
        assert not (
            pth / 'pip_install_test'
        ).exists(), 'pip_install_test still installed'
    assert not installer.hasJobs()

    # Test new signals
    with qtbot.waitSignal(installer.processFinished, timeout=20000) as blocker:
        installer.install(
            tool=InstallerTools.PIP,
            pkgs=['pydantic'],
        )
    process_finished_data = blocker.args[0]
    assert process_finished_data['action'] == InstallerActions.INSTALL
    assert process_finished_data['pkgs'] == ["pydantic"]

    # Test upgrade
    with qtbot.waitSignal(installer.allFinished, timeout=20000):
        installer.install(
            tool=InstallerTools.PIP,
            pkgs=['requests==2.30.0'],
        )
        installer.upgrade(
            tool=InstallerTools.PIP,
            pkgs=['requests'],
        )


def test_pip_installer_invalid_action(tmp_virtualenv: 'Session', monkeypatch):
    installer = NapariInstallerQueue()
    monkeypatch.setattr(
        NapariPipInstallerTool,
        "executable",
        lambda *a: tmp_virtualenv.creator.exe,
    )
    invalid_action = 'Invalid Action'
    with pytest.raises(
        ValueError, match=f"Action '{invalid_action}' not supported!"
    ):
        item = installer._build_queue_item(
            tool=InstallerTools.PIP,
            action=invalid_action,
            pkgs=['pip-install-test'],
            prefix=None,
            origins=(),
            process=installer._create_process(),
        )
        installer._queue_item(item)


def test_installer_failures(qtbot, tmp_virtualenv: 'Session', monkeypatch):
    installer = NapariInstallerQueue()
    monkeypatch.setattr(
        NapariPipInstallerTool,
        "executable",
        lambda *a: tmp_virtualenv.creator.exe,
    )

    # CHECK 1) Errors should trigger finished and allFinished too
    with qtbot.waitSignal(installer.allFinished, timeout=10000):
        installer.install(
            tool=InstallerTools.PIP,
            pkgs=[f'this-package-does-not-exist-{hash(time.time())}'],
        )

    # Keep a reference before we monkey patch stuff
    installer._on_process_done_original = installer._on_process_done

    # CHECK 2) Non-existing packages should return non-zero
    monkeypatch.setattr(
        installer,
        "_on_process_done",
        MethodType(_assert_exit_code_not_zero, installer),
    )
    with qtbot.waitSignal(installer.allFinished, timeout=10000):
        installer.install(
            tool=InstallerTools.PIP,
            pkgs=[f'this-package-does-not-exist-{hash(time.time())}'],
        )

    # CHECK 3) Non-existing tools should fail to start
    monkeypatch.setattr(
        installer,
        "_on_process_done",
        MethodType(_assert_error_used, installer),
    )
    monkeypatch.setattr(installer, "_get_tool", lambda *a: _NonExistingTool)
    with qtbot.waitSignal(installer.allFinished, timeout=10000):
        installer.install(
            tool=_NonExistingTool,
            pkgs=[f'this-package-does-not-exist-{hash(time.time())}'],
        )


def test_cancel_incorrect_job_id(qtbot, tmp_virtualenv: 'Session'):
    installer = NapariInstallerQueue()
    with qtbot.waitSignal(installer.allFinished, timeout=20000):
        job_id = installer.install(
            tool=InstallerTools.PIP,
            pkgs=['requests'],
        )
        with pytest.raises(ValueError):
            installer.cancel(job_id + 1)


@pytest.mark.skipif(
    not NapariCondaInstallerTool.available(), reason="Conda is not available."
)
def test_conda_installer(qtbot, caplog, monkeypatch, tmp_conda_env: Path):
    if sys.platform == "darwin":
        # check  handled for `PYTHONEXECUTABLE` env definition on macOS
        monkeypatch.setenv("PYTHONEXECUTABLE", sys.executable)
    caplog.set_level(logging.DEBUG, logger=bqpi.__name__)
    conda_meta = tmp_conda_env / "conda-meta"
    glob_pat = "typing-extensions-*.json"
    glob_pat_2 = "pyzenhub-*.json"
    installer = NapariInstallerQueue()

    with qtbot.waitSignal(installer.allFinished, timeout=600_000):
        installer.install(
            tool=InstallerTools.CONDA,
            pkgs=['typing-extensions'],
            prefix=tmp_conda_env,
        )

    assert not installer.hasJobs()
    assert list(conda_meta.glob(glob_pat))

    with qtbot.waitSignal(installer.allFinished, timeout=600_000):
        installer.uninstall(
            tool=InstallerTools.CONDA,
            pkgs=['typing-extensions'],
            prefix=tmp_conda_env,
        )

    assert not installer.hasJobs()
    assert not list(conda_meta.glob(glob_pat))

    # Check canceling all works
    with qtbot.waitSignal(installer.allFinished, timeout=600_000):
        installer.install(
            tool=InstallerTools.CONDA,
            pkgs=['typing-extensions'],
            prefix=tmp_conda_env,
        )
        installer.install(
            tool=InstallerTools.CONDA,
            pkgs=['pyzenhub'],
            prefix=tmp_conda_env,
        )
        assert installer.currentJobs() == 2
        installer.cancel_all()

    assert not installer.hasJobs()
    assert not list(conda_meta.glob(glob_pat))
    assert not list(conda_meta.glob(glob_pat_2))

    # Check canceling current job works (1st in queue)
    with qtbot.waitSignal(installer.allFinished, timeout=600_000):
        job_id_1 = installer.install(
            tool=InstallerTools.CONDA,
            pkgs=['typing-extensions'],
            prefix=tmp_conda_env,
        )
        job_id_2 = installer.install(
            tool=InstallerTools.CONDA,
            pkgs=['pyzenhub'],
            prefix=tmp_conda_env,
        )
        assert installer.currentJobs() == 2
        installer.cancel(job_id_1)
        assert installer.currentJobs() == 1

    assert not installer.hasJobs()

    # Check canceling queued job works (somewhere besides 1st position in queue)
    with qtbot.waitSignal(installer.allFinished, timeout=600_000):
        job_id_1 = installer.install(
            tool=InstallerTools.CONDA,
            pkgs=['typing-extensions'],
            prefix=tmp_conda_env,
        )
        job_id_2 = installer.install(
            tool=InstallerTools.CONDA,
            pkgs=['pyzenhub'],
            prefix=tmp_conda_env,
        )
        assert installer.currentJobs() == 2
        installer.cancel(job_id_2)
        assert installer.currentJobs() == 1

    assert not installer.hasJobs()


def test_installer_error(qtbot, tmp_virtualenv: 'Session', monkeypatch):
    installer = NapariInstallerQueue()
    monkeypatch.setattr(
        NapariPipInstallerTool,
        "executable",
        lambda *a: 'not-a-real-executable',
    )
    with qtbot.waitSignal(installer.allFinished, timeout=600_000):
        installer.install(
            tool=InstallerTools.PIP,
            pkgs=['some-package-that-does-not-exist'],
        )


@pytest.mark.skipif(
    not NapariCondaInstallerTool.available(), reason="Conda is not available."
)
def test_conda_installer_wait_for_finished(qtbot, tmp_conda_env: Path):
    installer = NapariInstallerQueue()

    with qtbot.waitSignal(installer.allFinished, timeout=600_000):
        installer.install(
            tool=InstallerTools.CONDA,
            pkgs=['requests'],
            prefix=tmp_conda_env,
        )
        installer.install(
            tool=InstallerTools.CONDA,
            pkgs=['pyzenhub'],
            prefix=tmp_conda_env,
        )
        installer.waitForFinished(20000)


def test_constraints_are_in_sync():
    conda_constraints = sorted(NapariCondaInstallerTool.constraints())
    pip_constraints = sorted(NapariPipInstallerTool.constraints())

    assert len(conda_constraints) == len(pip_constraints)

    name_re = re.compile(r"([a-z0-9_\-]+).*")
    for conda_constraint, pip_constraint in zip(
        conda_constraints, pip_constraints, strict=False
    ):
        conda_name = name_re.match(conda_constraint).group(1)
        pip_name = name_re.match(pip_constraint).group(1)
        assert conda_name == pip_name


def test_executables():
    assert NapariCondaInstallerTool.executable()
    assert NapariPipInstallerTool.executable()


def test_available():
    assert str(NapariCondaInstallerTool.available())
    assert NapariPipInstallerTool.available()


def test_unrecognized_tool():
    with pytest.raises(ValueError):
        NapariInstallerQueue().install(tool='shrug', pkgs=[])
