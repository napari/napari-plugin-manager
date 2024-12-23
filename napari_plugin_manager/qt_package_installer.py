"""
A tool-agnostic installation logic for the plugin manager.

The main object is `InstallerQueue`, a `QProcess` subclass
with the notion of a job queue. The queued jobs are represented
by a `deque` of `*InstallerTool` dataclasses that contain the
executable path, arguments and environment modifications.
Available actions for each tool are `install`, `uninstall`
and `cancel`.
"""

import atexit
import contextlib
import os
import sys
from collections import deque
from dataclasses import dataclass
from enum import auto
from functools import lru_cache
from logging import getLogger
from pathlib import Path
from subprocess import call
from tempfile import NamedTemporaryFile, gettempdir
from typing import Deque, Optional, Sequence, Tuple, TypedDict

from napari._version import version as _napari_version
from napari._version import version_tuple as _napari_version_tuple
from napari.plugins import plugin_manager
from napari.plugins.npe2api import _user_agent
from napari.utils.misc import StringEnum
from napari.utils.translations import trans
from npe2 import PluginManager
from qtpy.QtCore import QObject, QProcess, QProcessEnvironment, Signal
from qtpy.QtWidgets import QTextEdit

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
    exit_code: int
    exit_status: int
    action: InstallerActions
    pkgs: Tuple[str, ...]


class InstallerTools(StringEnum):
    "Available tools for InstallerQueue jobs"
    CONDA = auto()
    PIP = auto()


@dataclass(frozen=True)
class AbstractInstallerTool:
    action: InstallerActions
    pkgs: Tuple[str, ...]
    origins: Tuple[str, ...] = ()
    prefix: Optional[str] = None
    process: QProcess = None

    @property
    def ident(self):
        return hash(
            (self.action, *self.pkgs, *self.origins, self.prefix, self.process)
        )

    # abstract method
    @classmethod
    def executable(cls):
        "Path to the executable that will run the task"
        raise NotImplementedError

    # abstract method
    def arguments(self):
        "Arguments supplied to the executable"
        raise NotImplementedError

    # abstract method
    def environment(
        self, env: QProcessEnvironment = None
    ) -> QProcessEnvironment:
        "Changes needed in the environment variables."
        raise NotImplementedError

    @staticmethod
    def constraints() -> Sequence[str]:
        """
        Version constraints to limit unwanted changes in installation.
        """
        return [f"napari=={_napari_version}"]

    @classmethod
    def available(cls) -> bool:
        """
        Check if the tool is available by performing a little test
        """
        raise NotImplementedError


class PipInstallerTool(AbstractInstallerTool):
    @classmethod
    def executable(cls):
        return str(_get_python_exe())

    @classmethod
    def available(cls):
        return call([cls.executable(), "-m", "pip", "--version"]) == 0

    def arguments(self) -> Tuple[str, ...]:
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
        if 10 <= log.getEffectiveLevel() < 30:  # DEBUG level
            args.append('-vvv')
        if self.prefix is not None:
            args.extend(['--prefix', str(self.prefix)])
        return (*args, *self.pkgs)

    def environment(
        self, env: QProcessEnvironment = None
    ) -> QProcessEnvironment:
        if env is None:
            env = QProcessEnvironment.systemEnvironment()
        env.insert("PIP_USER_AGENT_USER_DATA", _user_agent())
        return env

    @classmethod
    @lru_cache(maxsize=0)
    def _constraints_file(cls) -> str:
        with NamedTemporaryFile(
            "w", suffix="-napari-constraints.txt", delete=False
        ) as f:
            f.write("\n".join(cls.constraints()))
        atexit.register(os.unlink, f.name)
        return f.name


class CondaInstallerTool(AbstractInstallerTool):
    @classmethod
    def executable(cls):
        bat = ".bat" if os.name == "nt" else ""
        for path in (
            Path(os.environ.get('MAMBA_EXE', '')),
            Path(os.environ.get('CONDA_EXE', '')),
            # $CONDA is usually only available on GitHub Actions
            Path(os.environ.get('CONDA', '')) / 'condabin' / f'conda{bat}',
        ):
            if path.is_file():
                return str(path)
        return f'conda{bat}'  # cross our fingers 'conda' is in PATH

    @classmethod
    def available(cls):
        executable = cls.executable()
        try:
            return call([executable, "--version"]) == 0
        except FileNotFoundError:  # pragma: no cover
            return False

    def arguments(self) -> Tuple[str, ...]:
        prefix = self.prefix or self._default_prefix()
        if self.action == InstallerActions.UPGRADE:
            args = ['update', '-y', '--prefix', prefix]
        else:
            args = [self.action.value, '-y', '--prefix', prefix]
        args.append('--override-channels')
        for channel in (*self.origins, *self._default_channels()):
            args.extend(["-c", channel])
        return (*args, *self.pkgs)

    def environment(
        self, env: QProcessEnvironment = None
    ) -> QProcessEnvironment:
        if env is None:
            env = QProcessEnvironment.systemEnvironment()
        self._add_constraints_to_env(env)
        if 10 <= log.getEffectiveLevel() < 30:  # DEBUG level
            env.insert('CONDA_VERBOSITY', '3')
        if os.name == "nt":
            if not env.contains("TEMP"):
                temp = gettempdir()
                env.insert("TMP", temp)
                env.insert("TEMP", temp)
            if not env.contains("USERPROFILE"):
                env.insert("HOME", os.path.expanduser("~"))
                env.insert("USERPROFILE", os.path.expanduser("~"))
        if sys.platform == 'darwin' and env.contains('PYTHONEXECUTABLE'):
            # Fix for macOS when napari launched from terminal
            # related to https://github.com/napari/napari/pull/5531
            env.remove("PYTHONEXECUTABLE")
        return env

    @staticmethod
    def constraints() -> Sequence[str]:
        # FIXME
        # dev or rc versions might not be available in public channels
        # but only installed locally - if we try to pin those, mamba
        # will fail to pin it because there's no record of that version
        # in the remote index, only locally; to work around this bug
        # we will have to pin to e.g. 0.4.* instead of 0.4.17.* for now
        version_lower = _napari_version.lower()
        is_dev = "rc" in version_lower or "dev" in version_lower
        pin_level = 2 if is_dev else 3
        version = ".".join([str(x) for x in _napari_version_tuple[:pin_level]])

        return [f"napari={version}"]

    def _add_constraints_to_env(
        self, env: QProcessEnvironment
    ) -> QProcessEnvironment:
        PINNED = 'CONDA_PINNED_PACKAGES'
        constraints = self.constraints()
        if env.contains(PINNED):
            constraints.append(env.value(PINNED))
        env.insert(PINNED, "&".join(constraints))
        return env

    def _default_channels(self):
        return ('conda-forge',)

    def _default_prefix(self):
        if (Path(sys.prefix) / "conda-meta").is_dir():
            return sys.prefix
        raise ValueError("Prefix has not been specified!")


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

    def __init__(
        self, parent: Optional[QObject] = None, prefix: Optional[str] = None
    ) -> None:
        super().__init__(parent)
        self._queue: Deque[AbstractInstallerTool] = deque()
        self._current_process: QProcess = None
        self._prefix = prefix
        self._output_widget = None
        self._exit_codes = []

    # -------------------------- Public API ------------------------------
    def install(
        self,
        tool: InstallerTools,
        pkgs: Sequence[str],
        *,
        prefix: Optional[str] = None,
        origins: Sequence[str] = (),
        **kwargs,
    ) -> JobId:
        """Install packages in `pkgs` into `prefix` using `tool` with additional
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
            ID that can be used to cancel the process.
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
        prefix: Optional[str] = None,
        origins: Sequence[str] = (),
        **kwargs,
    ) -> JobId:
        """Upgrade packages in `pkgs` into `prefix` using `tool` with additional
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
            ID that can be used to cancel the process.
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
        prefix: Optional[str] = None,
        **kwargs,
    ) -> JobId:
        """Uninstall packages in `pkgs` from `prefix` using `tool`.

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
            ID that can be used to cancel the process.
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

    def cancel(self, job_id: JobId):
        """Cancel `job_id` if it is running. If `job_id` does not exist int the queue,
        a ValueError is raised.

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
                    # still pending, just remove from queue
                    self._queue.remove(item)

                self.processFinished.emit(
                    {
                        'exit_code': 1,
                        'exit_status': 0,
                        'action': InstallerActions.CANCEL,
                        'pkgs': item.pkgs,
                    }
                )
                self._process_queue()
                return

        msg = f"No job with id {job_id}. Current queue:\n - "
        msg += "\n - ".join(
            [
                f"{item.ident} -> {item.executable()} {item.arguments()}"
                for item in self._queue
            ]
        )
        raise ValueError(msg)

    def cancel_all(self):
        """Terminate all process in the queue and emit the `processFinished` signal."""
        all_pkgs = []
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

    def set_output_widget(self, output_widget: QTextEdit):
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

    def _log(self, msg: str):
        log.debug(msg)
        if self._output_widget:
            self._output_widget.append(msg)

    def _get_tool(self, tool: InstallerTools):
        if tool == InstallerTools.PIP:
            return PipInstallerTool
        if tool == InstallerTools.CONDA:
            return CondaInstallerTool
        raise ValueError(f"InstallerTool {tool} not recognized!")

    def _build_queue_item(
        self,
        tool: InstallerTools,
        action: InstallerActions,
        pkgs: Sequence[str],
        prefix: Optional[str] = None,
        origins: Sequence[str] = (),
        **kwargs,
    ) -> AbstractInstallerTool:
        return self._get_tool(tool)(
            pkgs=pkgs,
            action=action,
            origins=origins,
            prefix=prefix or self._prefix,
            **kwargs,
        )

    def _queue_item(self, item: AbstractInstallerTool) -> JobId:
        self._queue.append(item)
        self._process_queue()
        return item.ident

    def _process_queue(self):
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

    def _end_process(self, process: QProcess):
        if os.name == 'nt':
            # TODO: this might be too agressive and won't allow rollbacks!
            # investigate whether we can also do .terminate()
            process.kill()
        else:
            process.terminate()

        if self._output_widget:
            self._output_widget.append(
                trans._("\nTask was cancelled by the user.")
            )

    def _on_process_finished(
        self, exit_code: int, exit_status: QProcess.ExitStatus
    ):
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
                        'Cannot unregister %s, not a known napari plugin.', pkg
                    )
        self._on_process_done(exit_code=exit_code, exit_status=exit_status)

    def _on_error_occurred(self, error: QProcess.ProcessError):
        self._on_process_done(error=error)

    def _on_process_done(
        self,
        exit_code: Optional[int] = None,
        exit_status: Optional[QProcess.ExitStatus] = None,
        error: Optional[QProcess.ProcessError] = None,
    ):
        item = None
        with contextlib.suppress(IndexError):
            item = self._queue.popleft()

        if error:
            msg = trans._(
                "Task finished with errors! Error: {error}.", error=error
            )
        else:
            msg = trans._(
                "Task finished with exit code {exit_code} with status {exit_status}.",
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

    def _on_stdout_ready(self):
        if self._current_process is not None:
            text = (
                self._current_process.readAllStandardOutput().data().decode()
            )
            if text:
                self._log(text)

    def _on_stderr_ready(self):
        if self._current_process is not None:
            text = self._current_process.readAllStandardError().data().decode()
            if text:
                self._log(text)


def _get_python_exe():
    # Note: is_bundled_app() returns False even if using a Briefcase bundle...
    # Workaround: see if sys.executable is set to something something napari on Mac
    if (
        sys.executable.endswith("napari")
        and sys.platform == 'darwin'
        and (python := Path(sys.prefix) / "bin" / "python3").is_file()
    ):
        # sys.prefix should be <napari.app>/Contents/Resources/Support/Python/Resources
        return str(python)
    return sys.executable
