import importlib.metadata
import os
import platform
import sys
from typing import Generator, Optional, Tuple
from unittest.mock import patch

import napari.plugins
import npe2
import pytest
import qtpy
from napari.plugins._tests.test_npe2 import mock_pm  # noqa
from napari.utils.translations import trans
from qtpy.QtCore import QMimeData, QPointF, Qt, QUrl
from qtpy.QtGui import QDropEvent

if (qtpy.API_NAME == 'PySide2' and platform.system() != "Linux") or (
    sys.version_info[:2] > (3, 10) and platform.system() == "Linux"
):
    pytest.skip(
        "Known PySide2 x Python incompatibility: "
        "... object cannot be interpreted as an integer",
        allow_module_level=True,
    )

from napari_plugin_manager import qt_plugin_dialog
from napari_plugin_manager.qt_package_installer import InstallerActions

N_MOCKED_PLUGINS = 2


def _iter_napari_pypi_plugin_info(
    conda_forge: bool = True,
) -> Generator[
    Tuple[Optional[npe2.PackageMetadata], bool], None, None
]:  # pragma: no cover  (this function is used in thread and codecov has a problem with the collection of coverage in such cases)
    """Mock the pypi method to collect available plugins.

    This will mock napari.plugins.pypi.iter_napari_plugin_info` for pypi.

    It will return two fake plugins that will populate the available plugins
    list (the bottom one).
    """
    # This mock `base_data`` will be the same for both fake plugins.
    packages = ['pyzenhub', 'requests']
    base_data = {
        "metadata_version": "1.0",
        "version": "0.1.0",
        "summary": "some test package",
        "home_page": "http://napari.org",
        "author": "test author",
        "license": "UNKNOWN",
    }
    for i in range(N_MOCKED_PLUGINS):
        yield npe2.PackageMetadata(name=f"{packages[i]}", **base_data), bool(
            i
        ), {
            "home_page": 'www.mywebsite.com',
            "pypi_versions": ['2.31.0'],
            "conda_versions": ['2.31.0'],
        }


class PluginsMock:
    def __init__(self):
        self.plugins = {
            'requests': True,
            'pyzenhub': True,
            'my-plugin': True,
        }


class OldPluginsMock:
    def __init__(self):
        self.plugins = [
            ('my-test-old-plugin-1', False, 'my-test-old-plugin-1')
        ]
        self.enabled = [True]


@pytest.fixture
def old_plugins(qtbot):
    return OldPluginsMock()


@pytest.fixture
def plugins(qtbot):
    return PluginsMock()


class WarnPopupMock:
    def __init__(self, text):
        self._is_visible = False

    def exec_(self):
        self._is_visible = True

    def move(self, pos):
        return False

    def isVisible(self):
        return self._is_visible

    def close(self):
        self._is_visible = False


@pytest.fixture(params=[True, False], ids=["constructor", "no-constructor"])
def plugin_dialog(
    request,
    qtbot,
    monkeypatch,
    mock_pm,  # noqa
    plugins,
    old_plugins,
):
    """Fixture that provides a plugin dialog for a normal napari install."""

    class PluginManagerMock:
        def instance(self):
            return PluginManagerInstanceMock(plugins)

    class PluginManagerInstanceMock:
        def __init__(self, plugins):
            self.plugins = plugins.plugins

        def __iter__(self):
            yield from self.plugins

        def iter_manifests(self):
            yield from [mock_pm.get_manifest('my-plugin')]

        def is_disabled(self, name):
            return False

        def discover(self):
            return ['plugin']

        def enable(self, plugin):
            self.plugins[plugin] = True
            return

        def disable(self, plugin):
            self.plugins[plugin] = False
            return

    def mock_metadata(name):
        meta = {
            'version': '0.1.0',
            'summary': '',
            'Home-page': '',
            'author': '',
            'license': '',
        }
        return meta

    class OldPluginManagerMock:
        def __init__(self):
            self.plugins = old_plugins.plugins
            self.enabled = old_plugins.enabled

        def iter_available(self):
            return self.plugins

        def discover(self):
            return None

        def is_blocked(self, plugin):
            return self.plugins[0][1]

        def set_blocked(self, plugin, blocked):
            self.enabled[0] = not blocked
            return

    monkeypatch.setattr(
        qt_plugin_dialog,
        "iter_napari_plugin_info",
        _iter_napari_pypi_plugin_info,
    )
    monkeypatch.setattr(qt_plugin_dialog, 'WarnPopup', WarnPopupMock)

    # This is patching `napari.utils.misc.running_as_constructor_app` function
    # to mock a normal napari install.
    monkeypatch.setattr(
        qt_plugin_dialog, "running_as_constructor_app", lambda: request.param
    )
    monkeypatch.setattr(qt_plugin_dialog, "ON_BUNDLE", request.param)

    monkeypatch.setattr(
        napari.plugins, 'plugin_manager', OldPluginManagerMock()
    )

    monkeypatch.setattr(importlib.metadata, 'metadata', mock_metadata)

    monkeypatch.setattr(npe2, 'PluginManager', PluginManagerMock())

    widget = qt_plugin_dialog.QtPluginDialog()
    monkeypatch.setattr(widget, '_tag_outdated_plugins', lambda: None)
    widget.show()
    qtbot.waitUntil(widget.isVisible, timeout=300)

    def available_list_populated():
        return widget.available_list.count() == N_MOCKED_PLUGINS

    qtbot.waitUntil(available_list_populated, timeout=3000)
    qtbot.add_widget(widget)
    yield widget
    widget.hide()
    widget._add_items_timer.stop()
    assert not widget._add_items_timer.isActive()


def test_filter_not_available_plugins(request, plugin_dialog):
    """
    Check that the plugins listed under available plugins are
    enabled and disabled accordingly.
    """
    if "no-constructor" in request.node.name:
        pytest.skip(
            reason="This test is only relevant for constructor-based installs"
        )
    item = plugin_dialog.available_list.item(0)
    widget = plugin_dialog.available_list.itemWidget(item)
    if widget:
        assert not widget.action_button.isEnabled()
        assert widget.warning_tooltip.isVisible()

    item = plugin_dialog.available_list.item(1)
    widget = plugin_dialog.available_list.itemWidget(item)
    assert widget.action_button.isEnabled()
    assert not widget.warning_tooltip.isVisible()


def test_filter_available_plugins(plugin_dialog):
    """
    Test the dialog is correctly filtering plugins in the available plugins
    list (the bottom one).
    """
    plugin_dialog.filter("")
    assert plugin_dialog.available_list.count() == 2
    assert plugin_dialog.available_list.count_visible() == 2

    plugin_dialog.filter("no-match@123")
    assert plugin_dialog.available_list.count_visible() == 0

    plugin_dialog.filter("")
    plugin_dialog.filter("requests")
    assert plugin_dialog.available_list.count_visible() == 1


def test_filter_installed_plugins(plugin_dialog):
    """
    Test the dialog is correctly filtering plugins in the installed plugins
    list (the top one).
    """
    plugin_dialog.filter("")
    assert plugin_dialog.installed_list.count_visible() >= 0

    plugin_dialog.filter("no-match@123")
    assert plugin_dialog.installed_list.count_visible() == 0


def test_visible_widgets(request, plugin_dialog):
    """
    Test that the direct entry button and textbox are visible
    """
    if "no-constructor" not in request.node.name:
        pytest.skip(
            reason="Tested functionality not available in constructor-based installs"
        )
    assert plugin_dialog.direct_entry_edit.isVisible()
    assert plugin_dialog.direct_entry_btn.isVisible()


def test_version_dropdown(plugin_dialog):
    """
    Test that when the source drop down is changed, it displays the other versions properly.
    """
    widget = plugin_dialog.available_list.item(1).widget
    assert widget.version_choice_dropdown.currentText() == "3"
    # switch from PyPI source to conda one.
    widget.source_choice_dropdown.setCurrentIndex(1)
    assert widget.version_choice_dropdown.currentText() == "4.5"


def test_plugin_list_count_items(plugin_dialog):
    assert plugin_dialog.installed_list.count_visible() == 2


def test_plugin_list_handle_action(plugin_dialog, qtbot):
    item = plugin_dialog.installed_list.item(0)
    with patch.object(qt_plugin_dialog.PluginListItem, "set_busy") as mock:
        plugin_dialog.installed_list.handle_action(
            item,
            'test-name-1',
            InstallerActions.UPGRADE,
        )
        mock.assert_called_with(
            trans._("updating..."), InstallerActions.UPGRADE
        )

    with patch.object(qt_plugin_dialog.WarnPopup, "exec_") as mock:
        plugin_dialog.installed_list.handle_action(
            item,
            'test-name-1',
            InstallerActions.UNINSTALL,
        )
        assert mock.called

    item = plugin_dialog.available_list.item(0)
    with patch.object(qt_plugin_dialog.PluginListItem, "set_busy") as mock:

        plugin_dialog.available_list.handle_action(
            item,
            'test-name-1',
            InstallerActions.INSTALL,
            version='3',
        )
        mock.assert_called_with(
            trans._("installing..."), InstallerActions.INSTALL
        )

        plugin_dialog.available_list.handle_action(
            item, 'test-name-1', InstallerActions.CANCEL, version='3'
        )
        mock.assert_called_with(
            trans._("cancelling..."), InstallerActions.CANCEL
        )

    qtbot.waitUntil(lambda: not plugin_dialog.worker.is_running)


def test_on_enabled_checkbox(plugin_dialog, qtbot, plugins, old_plugins):
    # checks npe2 lines
    item = plugin_dialog.installed_list.item(0)
    widget = plugin_dialog.installed_list.itemWidget(item)

    assert plugins.plugins['my-plugin'] is True
    with qtbot.waitSignal(widget.enabled_checkbox.stateChanged, timeout=500):
        widget.enabled_checkbox.setChecked(False)
    assert plugins.plugins['my-plugin'] is False

    # checks npe1 lines
    item = plugin_dialog.installed_list.item(1)
    widget = plugin_dialog.installed_list.itemWidget(item)

    assert old_plugins.enabled[0] is True
    with qtbot.waitSignal(widget.enabled_checkbox.stateChanged, timeout=500):
        widget.enabled_checkbox.setChecked(False)
    assert old_plugins.enabled[0] is False


def test_add_items_outdated(plugin_dialog):
    """Test that a plugin is tagged as outdated (a newer version is available), the update button becomes visible."""

    # The plugin is being added to the available plugins list.  When the dialog is being built
    # this one will be listed as available, and it will be found as already installed.
    # Then, it will check if the installed version is a lower version than the one available.
    # In this case, pydantic is installed with version 0.1.0, so the one we are trying to install
    # is newer, so the update button should pop up.
    new_plugin = (
        npe2.PackageMetadata(name="my-plugin", version="0.4.0"),
        True,
        {
            "home_page": 'www.mywebsite.com',
            "pypi_versions": ['0.4.0'],
            "conda_versions": ['0.4.0'],
        },
    )

    plugin_dialog._plugin_data = [new_plugin]

    plugin_dialog._add_items()
    item = plugin_dialog.installed_list.item(0)
    widget = plugin_dialog.installed_list.itemWidget(item)

    assert widget.update_btn.isVisible()


def test_refresh(qtbot, plugin_dialog):
    with qtbot.waitSignal(plugin_dialog._add_items_timer.timeout, timeout=500):
        plugin_dialog.refresh(clear_cache=False)

    with qtbot.waitSignal(plugin_dialog._add_items_timer.timeout, timeout=500):
        plugin_dialog.refresh(clear_cache=True)

    with qtbot.waitSignal(plugin_dialog._add_items_timer.timeout, timeout=500):
        plugin_dialog._refresh_and_clear_cache()


def test_toggle_status(plugin_dialog):
    plugin_dialog.toggle_status(True)
    assert plugin_dialog.stdout_text.isVisible()
    plugin_dialog.toggle_status(False)
    assert not plugin_dialog.stdout_text.isVisible()


def test_exec(plugin_dialog):
    plugin_dialog.exec_()


def test_search_in_available(plugin_dialog):
    idxs = plugin_dialog._search_in_available("test")
    assert idxs == [0, 1]
    idxs = plugin_dialog._search_in_available("*&%$")
    assert idxs == []


def test_drop_event(plugin_dialog, tmp_path):
    path_1 = tmp_path / "example-1.txt"
    path_2 = tmp_path / "example-2.txt"
    url_prefix = 'file:///' if os.name == 'nt' else 'file://'
    data = QMimeData()
    data.setUrls(
        [QUrl(f'{url_prefix}{path_1}'), QUrl(f'{url_prefix}{path_2}')]
    )
    event = QDropEvent(
        QPointF(5.0, 5.0), Qt.CopyAction, data, Qt.LeftButton, Qt.NoModifier
    )
    plugin_dialog.dropEvent(event)
    assert plugin_dialog.direct_entry_edit.text() == str(path_1)


def test_installs(qtbot, tmp_virtualenv, plugin_dialog, request):
    if "[constructor]" in request.node.name:
        pytest.skip(
            reason="This test is only relevant for constructor-based installs"
        )

    plugin_dialog.set_prefix(str(tmp_virtualenv))
    item = plugin_dialog.available_list.item(1)
    widget = plugin_dialog.available_list.itemWidget(item)
    with qtbot.waitSignal(
        plugin_dialog.installer.processFinished, timeout=60_000
    ) as blocker:
        widget.action_button.click()

    assert blocker.args[2] == InstallerActions.INSTALL
    assert blocker.args[3][0].startswith("requests")

    qtbot.wait(5000)
    assert plugin_dialog.available_list.count() == 1
    assert plugin_dialog.installed_list.count() == 2


def test_cancel(qtbot, tmp_virtualenv, plugin_dialog, request):
    if "[constructor]" in request.node.name:
        pytest.skip(
            reason="This test is only relevant for constructor-based installs"
        )

    plugin_dialog.set_prefix(str(tmp_virtualenv))
    item = plugin_dialog.available_list.item(1)
    widget = plugin_dialog.available_list.itemWidget(item)
    with qtbot.waitSignal(
        plugin_dialog.installer.processFinished, timeout=60_000
    ) as blocker:
        widget.action_button.click()
        widget.cancel_btn.click()

    assert blocker.args[2] == InstallerActions.CANCEL
    assert blocker.args[3][0].startswith("requests")
    assert plugin_dialog.available_list.count() == 2
    assert plugin_dialog.installed_list.count() == 2


def test_cancel_all(qtbot, tmp_virtualenv, plugin_dialog, request):
    if "[constructor]" in request.node.name:
        pytest.skip(
            reason="This test is only relevant for constructor-based installs"
        )

    plugin_dialog.set_prefix(str(tmp_virtualenv))
    item_1 = plugin_dialog.available_list.item(0)
    item_2 = plugin_dialog.available_list.item(1)
    widget_1 = plugin_dialog.available_list.itemWidget(item_1)
    widget_2 = plugin_dialog.available_list.itemWidget(item_2)
    with qtbot.waitSignal(plugin_dialog.installer.allFinished, timeout=60_000):
        widget_1.action_button.click()
        widget_2.action_button.click()
        plugin_dialog.cancel_all_btn.click()

    assert plugin_dialog.available_list.count() == 2
    assert plugin_dialog.installed_list.count() == 2
