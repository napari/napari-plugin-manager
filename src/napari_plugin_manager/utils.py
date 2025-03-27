import re
import sys
from pathlib import Path
from typing import Optional

from qtpy.QtWidgets import QDialog, QWidget


def is_conda_package(pkg: str, prefix: Optional[str] = None) -> bool:
    """Determines if plugin was installed through conda.

    Returns
    -------
    bool
        ``True` if a conda package, ``False`` if not.
    """
    # Installed conda packages within a conda installation and environment can
    # be identified as files with the template ``<package-name>-<version>-<build-string>.json``
    # saved within a ``conda-meta`` folder within the given environment of interest.
    conda_meta_dir = Path(prefix or sys.prefix) / 'conda-meta'
    return any(
        re.match(rf"{pkg}-[^-]+-[^-]+.json", p.name)
        for p in conda_meta_dir.glob(f"{pkg}-*-*.json")
    )


def get_dialog_from_widget(widget: QWidget) -> QDialog | None:
    """Returns the parent dialog of the given widget.

    Parameters
    ----------
    widget : QWidget
        Widget to find parent for.

    Returns
    -------
    QtPluginDialog | None
        The dialog containing the given widget, if available
    """
    from napari_plugin_manager.qt_plugin_dialog import QtPluginDialog

    while widget is not None:
        if isinstance(widget, QtPluginDialog):
            return widget
        widget = widget.parent()
    return None
