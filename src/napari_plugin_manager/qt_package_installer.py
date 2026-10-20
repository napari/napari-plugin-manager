"""
The installation logic for the napari plugin manager.

The main object is `NapariInstallerQueue`, a `InstallerQueue` subclass
with the notion of a job queue. The queued jobs are represented
by a `deque` of `*InstallerTool` dataclasses (`NapariPipInstallerTool` and
`NapariCondaInstallerTool`).
"""

import atexit
import os
import sys
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile

from napari._version import (
    version as _napari_version,
    version_tuple as _napari_version_tuple,
)

from napari_plugin_manager.base_qt_package_installer import (
    CondaInstallerTool,
    InstallerQueue,
    PipInstallerTool,
    UvInstallerTool,
)


def _get_python_exe() -> str:
    # Note: is_bundled_app() returns False even if using a Briefcase bundle...
    # Workaround: see if sys.executable is set to something something napari on Mac
    if (
        sys.executable.endswith('napari')
        and sys.platform == 'darwin'
        and (python := Path(sys.prefix) / 'bin' / 'python3').is_file()
    ):
        # sys.prefix should be <napari.app>/Contents/Resources/Support/Python/Resources
        return str(python)
    return sys.executable


class NapariPipInstallerTool(PipInstallerTool):
    @classmethod
    def executable(cls) -> str:
        return str(_get_python_exe())

    @staticmethod
    def constraints() -> list[str]:
        """
        Version constraints to limit unwanted changes in installation.
        """
        return [f'napari=={_napari_version}']

    @classmethod
    @lru_cache(maxsize=0)
    def _constraints_file(cls) -> str:
        with NamedTemporaryFile(
            'w', suffix='-napari-constraints.txt', delete=False
        ) as f:
            f.write('\n'.join(cls.constraints()))
        atexit.register(os.unlink, f.name)
        return f.name


class NapariUvInstallerTool(UvInstallerTool):
    @staticmethod
    def constraints() -> list[str]:
        """
        Version constraints to limit unwanted changes in installation.
        """
        return [f'napari=={_napari_version}']

    @classmethod
    @lru_cache(maxsize=0)
    def _constraints_file(cls) -> str:
        with NamedTemporaryFile(
            'w', suffix='-napari-constraints.txt', delete=False
        ) as f:
            f.write('\n'.join(cls.constraints()))
        atexit.register(os.unlink, f.name)
        return f.name

    def _python_executable(self) -> str:
        return str(_get_python_exe())


class NapariCondaInstallerTool(CondaInstallerTool):
    @staticmethod
    def constraints() -> list[str]:
        # FIXME
        # dev or rc versions might not be available in public channels
        # but only installed locally - if we try to pin those, mamba
        # will fail to pin it because there's no record of that version
        # in the remote index, only locally; to work around this bug
        # we will have to pin to e.g. 0.4.* instead of 0.4.17.* for now
        version_lower = _napari_version.lower()
        is_dev = 'rc' in version_lower or 'dev' in version_lower
        pin_level = 2 if is_dev else 3
        version = '.'.join([str(x) for x in _napari_version_tuple[:pin_level]])

        return [f'napari={version}']


class NapariInstallerQueue(InstallerQueue):
    PYPI_INSTALLER_TOOL_CLASS = (
        NapariUvInstallerTool
        if NapariUvInstallerTool.available()
        else NapariPipInstallerTool
    )
    CONDA_INSTALLER_TOOL_CLASS = NapariCondaInstallerTool
    BASE_PACKAGE_NAME = 'napari'
