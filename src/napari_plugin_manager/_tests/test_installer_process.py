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
    NapariUvInstallerTool,
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
        raise AssertionError('\n'.join(errors))
    return self._on_process_done_original(exit_code, exit_status, error)


def _assert_error_used(self, exit_code=None, exit_status=None, error=None):
    errors = []
    if error is None:
        errors.append("- 'error' should have been populated!")
    if exit_code is not None:
        errors.append("- 'exit_code' should not have been populated!")
    if errors:
        raise AssertionError('\n'.join(errors))
    return self._on_process_done_original(exit_code, exit_status, error)


class _NonExistingTool(AbstractInstallerTool):
    def executable(self):
        return f'this-tool-does-not-exist-{hash(time.time())}'

    def arguments(self):
        return ()

    def environment(self, env=None):
        return QProcessEnvironment.systemEnvironment()


@pytest.fixture
def patch_tool_executable(request):
    mp = request.getfixturevalue('monkeypatch')
    venv = request.getfixturevalue('tmp_virtualenv')
    tool = request.getfixturevalue('tool')
    mp.setattr(
        tool,
        'executable'
        if tool == NapariPipInstallerTool
        else '_python_executable',
        lambda *a: venv.creator.exe,
    )


@pytest.mark.parametrize(
    'tool', [NapariPipInstallerTool, NapariUvInstallerTool]
)
def test_pip_installer_tasks(
    qtbot,
    tool,
    tmp_virtualenv: 'Session',
    monkeypatch,
    caplog,
    patch_tool_executable,
):
    caplog.set_level(logging.DEBUG, logger=bqpi.__name__)
    monkeypatch.setattr(
        NapariInstallerQueue, 'PYPI_INSTALLER_TOOL_CLASS', tool
    )
    installer = NapariInstallerQueue()
    monkeypatch.setattr(
        tool,
        'origins',
        ('https://pypi.org/simple',),
    )
    with qtbot.waitSignal(installer.allFinished, timeout=30_000):
        installer.install(
            tool=InstallerTools.PYPI,
            pkgs=['pip-install-test'],
        )
        installer.install(
            tool=InstallerTools.PYPI,
            pkgs=['typing-extensions'],
        )
        job_id = installer.install(
            tool=InstallerTools.PYPI,
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

    with qtbot.waitSignal(installer.allFinished, timeout=30_000):
        job_id = installer.uninstall(
            tool=InstallerTools.PYPI,
            pkgs=['pip-install-test'],
        )

    for pth in tmp_virtualenv.creator.libs:
        assert not (pth / 'pip_install_test').exists(), (
            'pip_install_test still installed'
        )
    assert not installer.hasJobs()

    # Test new signals
    with qtbot.waitSignal(
        installer.processFinished, timeout=30_000
    ) as blocker:
        installer.install(
            tool=InstallerTools.PYPI,
            pkgs=['pydantic'],
        )
    process_finished_data = blocker.args[0]
    assert process_finished_data['action'] == InstallerActions.INSTALL
    assert process_finished_data['pkgs'] == ('pydantic',)

    # Test upgrade
    with qtbot.waitSignal(installer.allFinished, timeout=30_000):
        installer.install(
            tool=InstallerTools.PYPI,
            pkgs=['requests==2.30.0'],
        )
        installer.upgrade(
            tool=InstallerTools.PYPI,
            pkgs=['requests'],
        )


@pytest.mark.parametrize(
    'tool', [NapariPipInstallerTool, NapariUvInstallerTool]
)
def test_pip_installer_invalid_action(
    tool, tmp_virtualenv: 'Session', monkeypatch, patch_tool_executable
):
    monkeypatch.setattr(
        NapariInstallerQueue, 'PYPI_INSTALLER_TOOL_CLASS', tool
    )
    installer = NapariInstallerQueue()
    invalid_action = 'Invalid Action'
    item = installer._build_queue_item(
        tool=InstallerTools.PYPI,
        action=invalid_action,
        pkgs=['pip-install-test'],
        prefix=None,
        origins=(),
        process=installer._create_process(),
    )
    with pytest.raises(
        ValueError, match=f"Action '{invalid_action}' not supported!"
    ):
        installer._queue_item(item)


@pytest.mark.parametrize(
    'tool', [NapariPipInstallerTool, NapariUvInstallerTool]
)
def test_installer_failures(
    tool, qtbot, tmp_virtualenv: 'Session', monkeypatch, patch_tool_executable
):
    monkeypatch.setattr(
        NapariInstallerQueue, 'PYPI_INSTALLER_TOOL_CLASS', tool
    )
    installer = NapariInstallerQueue()

    # CHECK 1) Errors should trigger finished and allFinished too
    with qtbot.waitSignal(installer.allFinished, timeout=10_000):
        installer.install(
            tool=InstallerTools.PYPI,
            pkgs=[f'this-package-does-not-exist-{hash(time.time())}'],
        )

    # Keep a reference before we monkey patch stuff
    installer._on_process_done_original = installer._on_process_done

    # CHECK 2) Non-existing packages should return non-zero
    monkeypatch.setattr(
        installer,
        '_on_process_done',
        MethodType(_assert_exit_code_not_zero, installer),
    )
    with qtbot.waitSignal(installer.allFinished, timeout=10_000):
        installer.install(
            tool=InstallerTools.PYPI,
            pkgs=[f'this-package-does-not-exist-{hash(time.time())}'],
        )

    # CHECK 3) Non-existing tools should fail to start
    monkeypatch.setattr(
        installer,
        '_on_process_done',
        MethodType(_assert_error_used, installer),
    )
    monkeypatch.setattr(installer, '_get_tool', lambda *a: _NonExistingTool)
    with qtbot.waitSignal(installer.allFinished, timeout=10_000):
        installer.install(
            tool=_NonExistingTool,
            pkgs=[f'this-package-does-not-exist-{hash(time.time())}'],
        )


@pytest.mark.parametrize(
    'tool', [NapariPipInstallerTool, NapariUvInstallerTool]
)
def test_cancel_incorrect_job_id(tool, qtbot, monkeypatch):
    monkeypatch.setattr(
        NapariInstallerQueue, 'PYPI_INSTALLER_TOOL_CLASS', tool
    )
    installer = NapariInstallerQueue()
    with qtbot.waitSignal(installer.allFinished, timeout=30_000):
        job_id = installer.install(
            tool=InstallerTools.PYPI,
            pkgs=['requests'],
        )
        with pytest.raises(ValueError, match=f'No job with id {job_id + 1}.'):
            installer.cancel(job_id + 1)


@pytest.mark.skipif(
    not NapariCondaInstallerTool.available(), reason='Conda is not available.'
)
def test_conda_installer(qtbot, caplog, monkeypatch, tmp_conda_env: Path):
    if sys.platform == 'darwin':
        # check  handled for `PYTHONEXECUTABLE` env definition on macOS
        monkeypatch.setenv('PYTHONEXECUTABLE', sys.executable)
    caplog.set_level(logging.DEBUG, logger=bqpi.__name__)
    conda_meta = tmp_conda_env / 'conda-meta'
    glob_pat = 'typing-extensions-*.json'
    glob_pat_2 = 'packaging-*.json'
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
            pkgs=['packaging'],
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
            pkgs=['packaging'],
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
            pkgs=['packaging'],
            prefix=tmp_conda_env,
        )
        assert installer.currentJobs() == 2
        installer.cancel(job_id_2)
        assert installer.currentJobs() == 1

    assert not installer.hasJobs()


@pytest.mark.parametrize(
    'tool', [NapariPipInstallerTool, NapariUvInstallerTool]
)
def test_installer_error(qtbot, tool, monkeypatch):
    monkeypatch.setattr(
        NapariInstallerQueue, 'PYPI_INSTALLER_TOOL_CLASS', tool
    )
    installer = NapariInstallerQueue()
    monkeypatch.setattr(tool, 'executable', lambda *a: 'not-a-real-executable')
    with qtbot.waitSignal(installer.allFinished, timeout=600_000):
        installer.install(
            tool=InstallerTools.PYPI,
            pkgs=['some-package-that-does-not-exist'],
        )


@pytest.mark.skipif(
    not NapariCondaInstallerTool.available(), reason='Conda is not available.'
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
            pkgs=['packaging'],
            prefix=tmp_conda_env,
        )
        installer.waitForFinished(30_000)


def test_constraints_are_in_sync():
    conda_constraints = sorted(NapariCondaInstallerTool.constraints())
    pypi_constraints = sorted(NapariPipInstallerTool.constraints())

    assert len(conda_constraints) == len(pypi_constraints)

    name_re = re.compile(r'([a-z0-9_\-]+).*')
    for conda_constraint, pypi_constraint in zip(
        conda_constraints, pypi_constraints, strict=False
    ):
        conda_name = name_re.match(conda_constraint).group(1)
        pypi_name = name_re.match(pypi_constraint).group(1)
        assert conda_name == pypi_name


def test_executables():
    assert NapariCondaInstallerTool.executable()
    assert NapariPipInstallerTool.executable()
    assert NapariUvInstallerTool.executable()


def test_available():
    assert str(NapariCondaInstallerTool.available())
    assert NapariPipInstallerTool.available()
    assert NapariUvInstallerTool.available()


def test_unrecognized_tool():
    with pytest.raises(
        ValueError, match='InstallerTool shrug not recognized!'
    ):
        NapariInstallerQueue().install(tool='shrug', pkgs=[])
