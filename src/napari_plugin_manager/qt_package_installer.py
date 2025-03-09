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
from importlib.metadata import version as package_version
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Sequence

import qtpy
from packaging.version import parse as parse_version

from napari_plugin_manager.base_qt_package_installer import (
    CondaInstallerTool,
    InstallerQueue,
    PipInstallerTool,
)

CRITICAL_PACKAGES = [
    "app-model",
    "lazy_loader",
    "magicgui",
    "napari",
    "numpy",
    "psygnal",
    "pydantic",
    "superqt",
    "vispy",
]

QT_BACKENDS = ["PyQt5", "PySide2", "PySide6", "PyQt6"]
CURRENT_BACKEND = qtpy.API_NAME

QT_BACKENDS_PIN = [
    (
        f"{pkg}=={package_version(pkg)}"
        if pkg == CURRENT_BACKEND
        else f"{pkg}==0"
    )
    for pkg in QT_BACKENDS
]

CRITICAL_PACKAGES_PIN = [
    f"{pkg}=={package_version(pkg)}" for pkg in CRITICAL_PACKAGES
] + QT_BACKENDS_PIN

# dev or rc versions might not be available in public channels
# but only installed locally - if we try to pin those, mamba
# will fail to pin it because there's no record of that version
# in the remote index, only locally; to work around this bug
# we will have to pin to e.g. 0.4.* instead of 0.4.17.* for now
CRITICAL_PACKAGES_PIN_CONDA = [
    f"{pkg}={parse_version(package_version(pkg)).base_version}"
    for pkg in CRITICAL_PACKAGES
]  # + QT_BACKENDS_PIN


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


class NapariPipInstallerTool(PipInstallerTool):
    @classmethod
    def executable(cls):
        return str(_get_python_exe())

    @staticmethod
    def constraints() -> Sequence[str]:
        """
        Version constraints to limit unwanted changes in installation.
        """
        return CRITICAL_PACKAGES_PIN

    @classmethod
    @lru_cache(maxsize=0)
    def _constraints_file(cls) -> str:
        with NamedTemporaryFile(
            "w", suffix="-napari-constraints.txt", delete=False
        ) as f:
            f.write("\n".join(cls.constraints()))
        atexit.register(os.unlink, f.name)
        return f.name


class NapariCondaInstallerTool(CondaInstallerTool):
    @staticmethod
    def constraints() -> Sequence[str]:

        return CRITICAL_PACKAGES_PIN_CONDA


class NapariInstallerQueue(InstallerQueue):
    PIP_INSTALLER_TOOL_CLASS = NapariPipInstallerTool
    CONDA_INSTALLER_TOOL_CLASS = NapariCondaInstallerTool
    BASE_PACKAGE_NAME = 'napari'
