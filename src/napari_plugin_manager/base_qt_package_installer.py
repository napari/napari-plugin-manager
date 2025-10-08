"""Package tool-agnostic installation logic for the plugin manager.

The main object is `InstallerQueue`, a `QProcess` subclass
with the notion of a job queue.

The queued jobs are represented by a `deque` of `*InstallerTool` dataclasses
that contain the executable path, arguments and environment modifications.

Available actions for each tool are `install`, `uninstall`
and `cancel`.
"""

import contextlib
import os
import sys
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import auto
from functools import lru_cache
from logging import getLogger
from pathlib import Path
from subprocess import run
from tempfile import gettempdir
from typing import TypedDict

from napari.plugins import plugin_manager
from napari.plugins.npe2api import _user_agent
from napari.utils.misc import StringEnum
from napari.utils.translations import trans
from npe2 import PluginManager
from qtpy.QtCore import QObject, QProcess, QProcessEnvironment, Signal
from qtpy.QtWidgets import QTextEdit

# Alias for int type to represent a job idenfifier in the installer queue
JobId = int

log = getLogger(__name__)


class InstallerActions(StringEnum):
    "Available actions for the plugin manager"

    INSTALL = auto()
    UNINSTALL = auto()
    CANCEL = auto()
    CANCEL_ALL = auto()
    UPGRADE = auto()


class ProcessFinishedData(TypedDict):
    """Data about a finished process."""

    exit_code: int
    exit_status: int
    action: InstallerActions
    pkgs: tuple[str, ...]


class InstallerTools(StringEnum):
    "Installer tools selectable by InstallerQueue jobs"

    CONDA = auto()
    PYPI = auto()


@dataclass(frozen=True)
class AbstractInstallerTool:
    """Abstract base class for installer tools."""

    action: InstallerActions
    pkgs: tuple[str, ...]
    origins: tuple[str, ...] = ()
    prefix: str | None = None
    process: QProcess = None

    @property
    def ident(self) -> JobId:
        return hash(
            (self.action, *self.pkgs, *self.origins, self.prefix, self.process)
        )

    # abstract method
    @classmethod
    def executable(cls) -> str:
        "Path to the executable that will run the task"
        raise NotImplementedError

    # abstract method
    def arguments(self) -> list[str]:
        "Arguments supplied to the executable"
        raise NotImplementedError

    # abstract method
    def environment(
        self, env: QProcessEnvironment = None
    ) -> QProcessEnvironment:
        "Changes needed in the environment variables."
        raise NotImplementedError

    @staticmethod
    def constraints() -> list[str]:
        """
        Version constraints to limit unwanted changes in installation.
        """
        raise NotImplementedError

    @classmethod
    def available(cls) -> bool:
        """
        Check if the tool is available by performing a little test
        """
        raise NotImplementedError


class PipInstallerTool(AbstractInstallerTool):
    """Pip installer tool for the plugin manager.

    This class is used to install and uninstall packages using pip.
    """

    @classmethod
    def available(cls) -> bool:
        """Check if pip is available."""
        process = run(
            [cls.executable(), '-m', 'pip', '--version'], capture_output=True
        )
        return process.returncode == 0

    def arguments(self) -> list[str]:
        """Compose arguments for the pip command."""
        args = ['-m', 'pip']

        if self.action == InstallerActions.INSTALL:
            args += ['install', '-c', self._constraints_file()]
            for origin in self.origins:
                args += ['--extra-index-url', origin]

        elif self.action == InstallerActions.UPGRADE:
            args += [
                'install',
                '--upgrade',
                '-c',
                self._constraints_file(),
            ]
            for origin in self.origins:
                args += ['--extra-index-url', origin]

        elif self.action == InstallerActions.UNINSTALL:
            args += ['uninstall', '-y']

        else:
            raise ValueError(f"Action '{self.action}' not supported!")

        if log.getEffectiveLevel() < 30:  # DEBUG and INFO level
            args.append('-vvv')

        if self.prefix is not None:
            args.extend(['--prefix', str(self.prefix)])

        return [*args, *self.pkgs]

    def environment(
        self, env: QProcessEnvironment = None
    ) -> QProcessEnvironment:
        if env is None:
            env = QProcessEnvironment.systemEnvironment()
        env.insert('PIP_USER_AGENT_USER_DATA', _user_agent())
        return env

    @classmethod
    @lru_cache(maxsize=0)
    def _constraints_file(cls) -> str:
        raise NotImplementedError


class UvInstallerTool(AbstractInstallerTool):
    """Uv installer tool for the plugin manager.

    This class is used to install and uninstall packages using uv.
    """

    @classmethod
    def executable(cls) -> str:
        "Path to the executable that will run the task"
        if sys.platform == 'win32':
            path = os.path.join(sys.prefix, 'Scripts', 'uv.exe')
        else:
            path = os.path.join(sys.prefix, 'bin', 'uv')
        if os.path.isfile(path):
            return path
        return 'uv'

    @classmethod
    def available(cls) -> bool:
        """Check if uv is available."""
        try:
            process = run([cls.executable(), '--version'], capture_output=True)
        except FileNotFoundError:  # pragma: no cover
            return False
        else:
            return process.returncode == 0

    def arguments(self) -> list[str]:
        """Compose arguments for the uv pip command."""
        args = ['pip']

        if self.action == InstallerActions.INSTALL:
            args += ['install', '-c', self._constraints_file()]
            for origin in self.origins:
                args += ['--extra-index-url', origin]

        elif self.action == InstallerActions.UPGRADE:
            args += ['install', '-c', self._constraints_file()]
            for origin in self.origins:
                args += ['--extra-index-url', origin]
            for pkg in self.pkgs:
                args.append(f'--upgrade-package={pkg}')
        elif self.action == InstallerActions.UNINSTALL:
            args += ['uninstall']

        else:
            raise ValueError(f"Action '{self.action}' not supported!")

        if log.getEffectiveLevel() < 30:  # DEBUG and INFO level
            args.append('-vvv')

        if self.prefix is not None:
            args.extend(['--prefix', str(self.prefix)])
        args.extend(['--python', self._python_executable()])

        return [*args, *self.pkgs]

    def environment(
        self, env: QProcessEnvironment = None
    ) -> QProcessEnvironment:
        if env is None:
            env = QProcessEnvironment.systemEnvironment()
        return env

    @classmethod
    @lru_cache(maxsize=0)
    def _constraints_file(cls) -> str:
        raise NotImplementedError

    def _python_executable(self) -> str:
        raise NotImplementedError


class CondaInstallerTool(AbstractInstallerTool):
    """Conda installer tool for the plugin manager.

    This class is used to install and uninstall packages using conda or conda-like executable.
    """

    @classmethod
    def executable(cls) -> str:
        """Find a path to the executable.

        This method assumes that if no environment variable is set that conda is available in the PATH.
        """
        bat = '.bat' if os.name == 'nt' else ''
        for path in (
            Path(os.environ.get('MAMBA_EXE', '')),
            Path(os.environ.get('CONDA_EXE', '')),
            # $CONDA is usually only available on GitHub Actions
            Path(os.environ.get('CONDA', '')) / 'condabin' / f'conda{bat}',
        ):
            if path.is_file():
                # return the path to the executable
                return str(path)
        # Otherwise, we assume that conda is available in the PATH
        return f'conda{bat}'

    @classmethod
    def available(cls) -> bool:
        """Check if the executable is available by checking if it can output its version."""
        try:
            process = run([cls.executable(), '--version'], capture_output=True)
        except FileNotFoundError:  # pragma: no cover
            return False
        else:
            return process.returncode == 0

    def arguments(self) -> list[str]:
        """Compose arguments for the conda command."""
        prefix = self.prefix or self._default_prefix()

        if self.action == InstallerActions.UPGRADE:
            args = ['update', '-y', '--prefix', prefix]
        else:
            args = [self.action.value, '-y', '--prefix', prefix]

        args.append('--override-channels')
        for channel in (*self.origins, *self._default_channels()):
            args.extend(['-c', channel])

        return [*args, *self.pkgs]

    def environment(
        self, env: QProcessEnvironment = None
    ) -> QProcessEnvironment:
        if env is None:
            env = QProcessEnvironment.systemEnvironment()
        self._add_constraints_to_env(env)
        if 10 <= log.getEffectiveLevel() < 30:  # DEBUG level
            env.insert('CONDA_VERBOSITY', '3')
        if os.name == 'nt':
            if not env.contains('TEMP'):
                temp = gettempdir()
                env.insert('TMP', temp)
                env.insert('TEMP', temp)
            if not env.contains('USERPROFILE'):
                env.insert('HOME', os.path.expanduser('~'))
                env.insert('USERPROFILE', os.path.expanduser('~'))
        if sys.platform == 'darwin' and env.contains('PYTHONEXECUTABLE'):
            # Fix for macOS when napari launched from terminal
            # related to https://github.com/napari/napari/pull/5531
            env.remove('PYTHONEXECUTABLE')
        return env

    def _add_constraints_to_env(
        self, env: QProcessEnvironment
    ) -> QProcessEnvironment:
        """Add constraints to the environment."""
        PINNED = 'CONDA_PINNED_PACKAGES'
        constraints = self.constraints()
        if env.contains(PINNED):
            constraints.append(env.value(PINNED))
        env.insert(PINNED, '&'.join(constraints))
        return env

    def _default_channels(self) -> list[str]:
        """Default channels for conda installations."""
        return ['conda-forge']

    def _default_prefix(self) -> str:
        """Default prefix for conda installations."""
        if (Path(sys.prefix) / 'conda-meta').is_dir():
            return sys.prefix
        raise ValueError('Prefix has not been specified!')


class InstallerQueue(QObject):
    """Queue for installation and uninstallation tasks in the plugin manager."""

    # emitted when all jobs are finished. Not to be confused with finished,
    # which is emitted when each individual job is finished.
    # Tuple of exit codes for each individual job
    allFinished = Signal(tuple)

    # emitted when each job finishes
    # dict: ProcessFinishedData
    processFinished = Signal(dict)

    # emitted when each job starts
    started = Signal()

    # classes to manage pip and conda installations
    PYPI_INSTALLER_TOOL_CLASS = PipInstallerTool
    CONDA_INSTALLER_TOOL_CLASS = CondaInstallerTool
    # This should be set to the name of package that handles plugins
    # e.g `napari` for napari
    BASE_PACKAGE_NAME = ''

    def __init__(
        self, parent: QObject | None = None, prefix: str | None = None
    ) -> None:
        super().__init__(parent)
        self._queue: deque[AbstractInstallerTool] = deque()
        self._current_process: QProcess = None
        self._prefix = prefix
        self._output_widget = None
        self._exit_codes: list[int] = []

    # -------------------------- Public API ------------------------------
    def install(
        self,
        tool: InstallerTools,
        pkgs: Sequence[str],
        *,
        prefix: str | None = None,
        origins: Sequence[str] = (),
        **kwargs,
    ) -> JobId:
        """Install packages in the installer queue.

        This installs packages in `pkgs` into `prefix` using `tool` with additional
        `origins` as source for `pkgs`.

        Parameters
        ----------
        tool : InstallerTools
            Which type of installation tool to use.
        pkgs : Sequence[str]
            List of packages to install.
        prefix : Optional[str], optional
            Optional prefix to install packages into.
        origins : Optional[Sequence[str]], optional
            Additional sources for packages to be downloaded from.

        Returns
        -------
        JobId : int
            An ID to reference the job. Use to cancel the process.
        """
        item = self._build_queue_item(
            tool=tool,
            action=InstallerActions.INSTALL,
            pkgs=pkgs,
            prefix=prefix,
            origins=origins,
            process=self._create_process(),
            **kwargs,
        )
        return self._queue_item(item)

    def upgrade(
        self,
        tool: InstallerTools,
        pkgs: Sequence[str],
        *,
        prefix: str | None = None,
        origins: Sequence[str] = (),
        **kwargs,
    ) -> JobId:
        """Upgrade packages in the installer queue.

        Upgrade in `pkgs` into `prefix` using `tool` with additional
        `origins` as source for `pkgs`.

        Parameters
        ----------
        tool : InstallerTools
            Which type of installation tool to use.
        pkgs : Sequence[str]
            List of packages to install.
        prefix : Optional[str], optional
            Optional prefix to install packages into.
        origins : Optional[Sequence[str]], optional
            Additional sources for packages to be downloaded from.

        Returns
        -------
        JobId : int
            An ID to reference the job. Use to cancel the process.
        """
        item = self._build_queue_item(
            tool=tool,
            action=InstallerActions.UPGRADE,
            pkgs=pkgs,
            prefix=prefix,
            origins=origins,
            process=self._create_process(),
            **kwargs,
        )
        return self._queue_item(item)

    def uninstall(
        self,
        tool: InstallerTools,
        pkgs: Sequence[str],
        *,
        prefix: str | None = None,
        **kwargs,
    ) -> JobId:
        """Uninstall packages in the installer queue.

        Uninstall packages in `pkgs` from `prefix` using `tool`.

        Parameters
        ----------
        tool : InstallerTools
            Which type of installation tool to use.
        pkgs : Sequence[str]
            List of packages to uninstall.
        prefix : Optional[str], optional
            Optional prefix from which to uninstall packages.

        Returns
        -------
        JobId : int
            An ID to reference the job. Use to cancel the process.
        """
        item = self._build_queue_item(
            tool=tool,
            action=InstallerActions.UNINSTALL,
            pkgs=pkgs,
            prefix=prefix,
            process=self._create_process(),
            **kwargs,
        )
        return self._queue_item(item)

    def cancel(self, job_id: JobId) -> None:
        """Cancel a job.

        Cancel the process, if it is running, referenced by `job_id`.
        If `job_id` does not exist in the queue, a ValueError is raised.

        Parameters
        ----------
        job_id : JobId
            Job ID to cancel.
        """
        for i, item in enumerate(deque(self._queue)):
            if item.ident == job_id:
                if i == 0:
                    # first in queue, currently running
                    self._queue.remove(item)

                    with contextlib.suppress(RuntimeError):
                        item.process.finished.disconnect(
                            self._on_process_finished
                        )
                        item.process.errorOccurred.disconnect(
                            self._on_error_occurred
                        )

                    self._end_process(item.process)
                else:
                    # job is still pending, just remove it from the queue
                    self._queue.remove(item)

                self.processFinished.emit(
                    {
                        'exit_code': 1,
                        'exit_status': 0,
                        'action': InstallerActions.CANCEL,
                        'pkgs': item.pkgs,
                    }
                )
                # continue processing the queue
                self._process_queue()
                return

        msg = f'No job with id {job_id}. Current queue:\n - '
        msg += '\n - '.join(
            [
                f'{item.ident} -> {item.executable()} {item.arguments()}'
                for item in self._queue
            ]
        )
        raise ValueError(msg)

    def cancel_all(self) -> None:
        """Terminate all processes in the queue and emit the `processFinished` signal."""
        all_pkgs: list[str] = []
        for item in deque(self._queue):
            all_pkgs.extend(item.pkgs)
            process = item.process

            with contextlib.suppress(RuntimeError):
                process.finished.disconnect(self._on_process_finished)
                process.errorOccurred.disconnect(self._on_error_occurred)

            self._end_process(process)

        self._queue.clear()
        self._current_process = None
        self.processFinished.emit(
            {
                'exit_code': 1,
                'exit_status': 0,
                'action': InstallerActions.CANCEL_ALL,
                'pkgs': all_pkgs,
            }
        )
        self._process_queue()
        return

    def waitForFinished(self, msecs: int = 10000) -> bool:
        """Block and wait for all jobs to finish.

        Parameters
        ----------
        msecs : int, optional
            Time to wait, by default 10000
        """
        while self.hasJobs():
            if self._current_process is not None:
                self._current_process.waitForFinished(msecs)
        return True

    def hasJobs(self) -> bool:
        """True if there are jobs remaining in the queue."""
        return bool(self._queue)

    def currentJobs(self) -> int:
        """Return the number of running jobs in the queue."""
        return len(self._queue)

    def set_output_widget(self, output_widget: QTextEdit) -> None:
        """Set the output widget for text output."""
        if output_widget:
            self._output_widget = output_widget

    # -------------------------- Private methods ------------------------------
    def _create_process(self) -> QProcess:
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(self._on_stdout_ready)
        process.readyReadStandardError.connect(self._on_stderr_ready)
        process.finished.connect(self._on_process_finished)
        process.errorOccurred.connect(self._on_error_occurred)
        return process

    def _log(self, msg: str) -> None:
        log.debug(msg)
        if self._output_widget:
            self._output_widget.append(msg)

    def _get_tool(self, tool: InstallerTools) -> type[AbstractInstallerTool]:
        if tool == InstallerTools.PYPI:
            return self.PYPI_INSTALLER_TOOL_CLASS
        if tool == InstallerTools.CONDA:
            return self.CONDA_INSTALLER_TOOL_CLASS
        raise ValueError(f'InstallerTool {tool} not recognized!')

    def _build_queue_item(
        self,
        tool: InstallerTools,
        action: InstallerActions,
        pkgs: Iterable[str],
        prefix: str | None = None,
        origins: Iterable[str] = (),
        **kwargs,
    ) -> AbstractInstallerTool:
        return self._get_tool(tool)(
            pkgs=tuple(pkgs),
            action=action,
            origins=tuple(origins),
            prefix=prefix or self._prefix,
            **kwargs,
        )

    def _queue_item(self, item: AbstractInstallerTool) -> JobId:
        self._queue.append(item)
        self._process_queue()
        return item.ident

    def _process_queue(self) -> None:
        if not self._queue:
            self.allFinished.emit(tuple(self._exit_codes))
            self._exit_codes = []
            return

        tool = self._queue[0]
        process = tool.process

        if process.state() != QProcess.Running:
            process.setProgram(str(tool.executable()))
            process.setProcessEnvironment(tool.environment())
            process.setArguments([str(arg) for arg in tool.arguments()])
            process.started.connect(self.started)

            self._log(
                trans._(
                    "Starting '{program}' with args {args}",
                    program=process.program(),
                    args=process.arguments(),
                )
            )

            process.start()
            self._current_process = process

    def _end_process(self, process: QProcess) -> None:
        if os.name == 'nt':
            # TODO: this might be too agressive and won't allow rollbacks!
            # investigate whether we can also do .terminate()
            process.kill()
        else:
            process.terminate()

        if self._output_widget:
            self._output_widget.append(
                trans._('\nTask was cancelled by the user.')
            )

    def _on_process_finished(
        self, exit_code: int, exit_status: QProcess.ExitStatus
    ) -> None:
        try:
            current = self._queue[0]
        except IndexError:
            current = None
        if (
            current
            and current.action == InstallerActions.UNINSTALL
            and exit_status == QProcess.ExitStatus.NormalExit
            and exit_code == 0
        ):
            pm2 = PluginManager.instance()
            npe1_plugins = set(plugin_manager.iter_available())
            for pkg in current.pkgs:
                if pkg in pm2:
                    pm2.unregister(pkg)
                elif pkg in npe1_plugins:
                    plugin_manager.unregister(pkg)
                else:
                    log.warning(
                        'Cannot unregister %s, not a known %s plugin.',
                        pkg,
                        self.BASE_PACKAGE_NAME,
                    )
        self._on_process_done(exit_code=exit_code, exit_status=exit_status)

    def _on_error_occurred(self, error: QProcess.ProcessError) -> None:
        self._on_process_done(error=error)

    def _on_process_done(
        self,
        exit_code: int | None = None,
        exit_status: QProcess.ExitStatus | None = None,
        error: QProcess.ProcessError | None = None,
    ) -> None:
        item = None
        with contextlib.suppress(IndexError):
            item = self._queue.popleft()

        if error:
            msg = trans._(
                'Task finished with errors! Error: {error}.', error=error
            )
        else:
            msg = trans._(
                'Task finished with exit code {exit_code} with status {exit_status}.',
                exit_code=exit_code,
                exit_status=exit_status,
            )

        if item is not None:
            self.processFinished.emit(
                {
                    'exit_code': exit_code,
                    'exit_status': exit_status,
                    'action': item.action,
                    'pkgs': item.pkgs,
                }
            )
            self._exit_codes.append(exit_code)

        self._log(msg)
        self._process_queue()

    def _on_stdout_ready(self) -> None:
        if self._current_process is not None:
            try:
                text = (
                    self._current_process.readAllStandardOutput()
                    .data()
                    .decode()
                )
            except UnicodeDecodeError:
                log.exception('Could not decode stdout')
                return
            if text:
                self._log(text)

    def _on_stderr_ready(self) -> None:
        if self._current_process is not None:
            text = self._current_process.readAllStandardError().data().decode()
            if text:
                self._log(text)
