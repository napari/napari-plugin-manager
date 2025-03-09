import pytest

from napari_plugin_manager.base_qt_package_installer import (
    AbstractInstallerTool,
)


def test_not_implemented_methods():
    tool = AbstractInstallerTool('install', ['requests'])
    with pytest.raises(NotImplementedError):
        tool.executable()

    with pytest.raises(NotImplementedError):
        tool.arguments()

    with pytest.raises(NotImplementedError):
        tool.environment()

    with pytest.raises(NotImplementedError):
        tool.constraints()

    with pytest.raises(NotImplementedError):
        tool.available()
