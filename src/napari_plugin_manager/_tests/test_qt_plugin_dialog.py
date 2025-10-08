import importlib.metadata
import os
import sys
from collections.abc import Generator
from unittest.mock import MagicMock, call, patch

import napari.plugins
import npe2
import pytest
import qtpy
from napari.plugins._tests.test_npe2 import mock_pm  # noqa
from napari.utils.translations import trans
from qtpy.QtCore import QMimeData, QPointF, Qt, QTimer, QUrl
from qtpy.QtGui import QDropEvent
from qtpy.QtWidgets import (
    QApplication,
    QMessageBox,
)

if qtpy.API_NAME == 'PySide2' and sys.version_info[:2] > (3, 10):
    pytest.skip(
        'Known PySide2 x Python incompatibility: '
        '... object cannot be interpreted as an integer',
        allow_module_level=True,
    )

from napari_plugin_manager import base_qt_plugin_dialog, qt_plugin_dialog
from napari_plugin_manager.base_qt_package_installer import (
    InstallerActions,
    InstallerTools,
)

N_MOCKED_PLUGINS = 2


def _iter_napari_pypi_plugin_info(
    conda_forge: bool = True,
) -> Generator[
    tuple[npe2.PackageMetadata | None, bool], None, None
]:  # pragma: no cover  (this function is used in thread and codecov has a problem with the collection of coverage in such cases)
    """Mock the pypi method to collect available plugins.

    This will mock napari.plugins.pypi.iter_napari_plugin_info` for pypi.

    It will return two fake plugins that will populate the available plugins
    list (the bottom one).
    """
    # This mock `base_data`` will be the same for both fake plugins.
    packages = ['packaging', 'requests', 'my-plugin', 'my-test-old-plugin-1']
    base_data = {
        'metadata_version': '1.0',
        'version': '0.1.0',
        'summary': 'some test package',
        'home_page': 'http://napari.org',
        'author': 'test author',
        'license': 'UNKNOWN',
    }
    for i in range(len(packages)):
        yield (
            npe2.PackageMetadata(name=f'{packages[i]}', **base_data),
            bool(i),
            {
                'home_page': 'www.mywebsite.com',
                'pypi_versions': ['2.31.0'],
                'conda_versions': ['2.32.1'],
                'display_name': packages[i].upper(),
            },
        )


class PluginsMock:
    def __init__(self):
        self.plugins = {
            'requests': True,
            'packaging': True,
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


@pytest.fixture(params=[True, False], ids=['constructor', 'no-constructor'])
def plugin_dialog(
    request,
    qtbot,
    monkeypatch,
    mock_pm,  # noqa
    plugins,
    old_plugins,
):
    """Fixture that provides a plugin dialog for a normal napari install."""
    from napari.settings import get_settings

    original_setting = get_settings().plugins.use_npe2_adaptor
    get_settings().plugins.use_npe2_adaptor = False

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

        def discover(self, include_npe1=False):
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
        'iter_napari_plugin_info',
        _iter_napari_pypi_plugin_info,
    )

    monkeypatch.setattr(
        base_qt_plugin_dialog, 'RestartWarningDialog', MagicMock()
    )

    # This is patching `napari.utils.misc.running_as_constructor_app` function
    # to mock a normal napari install.
    monkeypatch.setattr(
        qt_plugin_dialog, 'running_as_constructor_app', lambda: request.param
    )
    monkeypatch.setattr(
        napari.plugins, 'plugin_manager', OldPluginManagerMock()
    )

    monkeypatch.setattr(importlib.metadata, 'metadata', mock_metadata)

    monkeypatch.setattr(npe2, 'PluginManager', PluginManagerMock())

    widget = qt_plugin_dialog.QtPluginDialog()
    monkeypatch.setattr(
        widget, '_is_main_app_conda_package', lambda: request.param
    )
    # monkeypatch.setattr(widget, '_tag_outdated_plugins', lambda: None)
    with qtbot.waitExposed(widget):
        widget.show()

    assert widget.isVisible()
    assert widget.available_list.count_visible() == 0
    assert widget.available_list.count() == 0
    qtbot.add_widget(widget)
    yield widget
    widget.hide()
    widget._add_items_timer.stop()
    if widget.worker is not None:
        widget.worker.quit()
    assert not widget._add_items_timer.isActive()
    get_settings().plugins.use_npe2_adaptor = original_setting


def test_filter_not_available_plugins(request, plugin_dialog, qtbot):
    """
    Check that the plugins listed under available plugins are
    enabled and disabled accordingly.
    """
    if 'no-constructor' in request.node.name:
        pytest.skip(
            reason='This test is only relevant for constructor-based installs'
        )
    plugin_dialog.search('e')
    qtbot.wait(500)
    item = plugin_dialog.available_list.item(0)
    widget = plugin_dialog.available_list.itemWidget(item)
    if widget:
        assert not widget.action_button.isEnabled()
        assert widget.warning_tooltip.isVisible()

    item = plugin_dialog.available_list.item(1)
    widget = plugin_dialog.available_list.itemWidget(item)
    assert widget.action_button.isEnabled()
    assert not widget.warning_tooltip.isVisible()


def test_filter_available_plugins(plugin_dialog, qtbot):
    """
    Test the dialog is correctly filtering plugins in the available plugins
    list (the bottom one).
    """
    plugin_dialog.search('')
    qtbot.wait(500)
    assert plugin_dialog.available_list.count() == 0
    assert plugin_dialog.available_list.count_visible() == 0

    plugin_dialog.search('no-match@123')
    qtbot.wait(500)
    assert plugin_dialog.available_list.count_visible() == 0

    plugin_dialog.search('')
    plugin_dialog.search('requests')
    qtbot.wait(500)
    assert plugin_dialog.available_list.count_visible() == 1


def test_filter_installed_plugins(plugin_dialog, qtbot):
    """
    Test the dialog is correctly filtering plugins in the installed plugins
    list (the top one).
    """
    plugin_dialog.search('')
    qtbot.wait(500)
    assert plugin_dialog.installed_list.count_visible() == 2

    plugin_dialog.search('no-match@123')
    qtbot.wait(500)
    assert plugin_dialog.installed_list.count_visible() == 0


def test_visible_widgets(request, plugin_dialog):
    """
    Test that the direct entry button and textbox are visible
    """
    if 'constructor' in request.node.name:
        pytest.skip(
            reason='Tested functionality not available in constructor-based installs'
        )
    assert plugin_dialog.direct_entry_edit.isVisible()
    assert plugin_dialog.direct_entry_btn.isVisible()


def test_version_dropdown(plugin_dialog, qtbot):
    """
    Test that when the source drop down is changed, it displays the other versions properly.
    """
    plugin_dialog.search('requests')
    qtbot.wait(500)
    widget = plugin_dialog.available_list.item(0).widget
    count = widget.version_choice_dropdown.count()
    if count == 2:
        assert widget.version_choice_dropdown.currentText() == '2.31.0'
        # switch from PyPI source to conda one.
        widget.source_choice_dropdown.setCurrentIndex(1)
        assert widget.version_choice_dropdown.currentText() == '2.32.1'


def test_plugin_list_count_items(plugin_dialog):
    assert plugin_dialog.installed_list.count_visible() == 2


def test_plugin_list_handle_action(plugin_dialog, qtbot):
    item = plugin_dialog.installed_list.item(0)
    with patch.object(qt_plugin_dialog.PluginListItem, 'set_busy') as mock:
        plugin_dialog.installed_list.handle_action(
            item,
            'my-test-old-plugin-1',
            InstallerActions.UPGRADE,
        )
        mock.assert_called_with(
            trans._('updating...'), InstallerActions.UPGRADE
        )

    plugin_dialog.search('requests')
    qtbot.wait(500)
    item = plugin_dialog.available_list.item(0)
    if item is not None:
        with patch.object(qt_plugin_dialog.PluginListItem, 'set_busy') as mock:
            plugin_dialog.available_list.handle_action(
                item,
                'my-test-old-plugin-1',
                InstallerActions.INSTALL,
                version='3',
            )
            mock.assert_called_once_with(
                trans._('installing...'), InstallerActions.INSTALL
            )

            plugin_dialog.available_list.handle_action(
                item,
                'my-test-old-plugin-1',
                InstallerActions.CANCEL,
                version='3',
            )
            assert mock.call_count >= 2
            assert mock.call_args_list[1] == call(
                'cancelling...', InstallerActions.CANCEL
            )

    qtbot.waitUntil(lambda: not plugin_dialog.worker.is_running)


def test_plugin_restart_warning(plugin_dialog, monkeypatch):
    dialog_mock = MagicMock()
    monkeypatch.setattr(
        base_qt_plugin_dialog, 'RestartWarningDialog', dialog_mock
    )
    plugin_dialog.exec_()
    plugin_dialog.modified_set.add('added-removed-updated-plugin')
    plugin_dialog.hide()
    dialog_mock.assert_called_once()
    assert len(plugin_dialog.modified_set) == 0


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


def test_add_items_outdated_and_update(plugin_dialog, qtbot):
    """
    Test that a plugin is tagged as outdated (a newer version is available), the update button becomes visible.

    Also check that after doing an update the update button gets hidden.
    """

    # The plugin is being added to the available plugins list.  When the dialog is being built
    # this one will be listed as available, and it will be found as already installed.
    # Then, it will check if the installed version is a lower version than the one available.
    # In this case, my-plugin is installed with version 0.1.0, so the one we are trying to install
    # is newer, so the update button should pop up.
    new_plugin = (
        npe2.PackageMetadata(name='my-plugin', version='0.4.0'),
        True,
        {
            'home_page': 'www.mywebsite.com',
            'pypi_versions': ['0.4.0', '0.1.0'],
            'conda_versions': ['0.4.0', '0.1.0'],
        },
    )
    plugin_dialog._plugin_data_map['my-plugin'] = new_plugin
    plugin_dialog._plugin_queue = [new_plugin]
    plugin_dialog._add_items()
    item = plugin_dialog.installed_list.item(0)
    widget = plugin_dialog.installed_list.itemWidget(item)
    initial_version = '0.1.0'
    mod_initial_version = initial_version.replace('.', '․')  # noqa: RUF001
    assert widget.update_btn.isVisible()
    assert widget.version.text() == mod_initial_version
    assert widget.version.toolTip() == initial_version

    # Trigger process finished handler to simulated that an update was done
    plugin_dialog._on_process_finished(
        {
            'exit_code': 1,
            'exit_status': 0,
            'action': InstallerActions.UPGRADE,
            'pkgs': ['my-plugin==0.4.0'],
        }
    )
    updated_version = '0.4.0'
    mod_updated_version = updated_version.replace('.', '․')  # noqa: RUF001
    assert not widget.update_btn.isVisible()
    assert widget.version.text() == mod_updated_version
    assert widget.version.toolTip() == updated_version


def test_refresh(qtbot, plugin_dialog):
    with qtbot.waitSignal(plugin_dialog.finished, timeout=500):
        plugin_dialog.refresh(clear_cache=False)

    with qtbot.waitSignal(plugin_dialog.finished, timeout=500):
        plugin_dialog.refresh(clear_cache=True)

    with qtbot.waitSignal(plugin_dialog.finished, timeout=500):
        plugin_dialog._refresh_and_clear_cache()


def test_toggle_status(plugin_dialog):
    plugin_dialog.toggle_status(True)
    assert plugin_dialog.stdout_text.isVisible()
    plugin_dialog.toggle_status(False)
    assert not plugin_dialog.stdout_text.isVisible()


def test_exec(plugin_dialog):
    plugin_dialog.exec_()


def test_search_in_available(plugin_dialog):
    idxs = plugin_dialog._search_in_available('test')
    if idxs:
        assert idxs == [0, 1, 2, 3]

    idxs = plugin_dialog._search_in_available('*&%$')
    assert idxs == []


def test_drop_event(plugin_dialog, tmp_path):
    path_1 = tmp_path / 'example-1.txt'
    path_2 = tmp_path / 'example-2.txt'
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


@pytest.mark.skipif(
    'napari_latest' in os.getenv('TOX_ENV_NAME', '')
    and 'PySide2' in os.getenv('TOX_ENV_NAME', ''),
    reason='PySide2 flaky with latest released napari',
)
def test_installs(qtbot, tmp_virtualenv, plugin_dialog, request):
    if '[constructor]' in request.node.name:
        pytest.skip(
            reason='This test is only relevant for non-constructor-based installs'
        )

    plugin_dialog.set_prefix(str(tmp_virtualenv))
    plugin_dialog.search('requests')
    qtbot.wait(500)
    item = plugin_dialog.available_list.item(0)
    widget = plugin_dialog.available_list.itemWidget(item)
    with qtbot.waitSignal(
        plugin_dialog.installer.processFinished, timeout=60_000
    ) as blocker:
        widget.action_button.click()

    process_finished_data = blocker.args[0]
    assert process_finished_data['action'] == InstallerActions.INSTALL
    assert process_finished_data['pkgs'][0].startswith('requests')
    qtbot.wait(5000)


@pytest.mark.parametrize(
    'message_return',
    [QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Ok],
)
def test_install_pypi_constructor(
    qtbot, tmp_virtualenv, plugin_dialog, request, message_return, monkeypatch
):
    if 'no-constructor' in request.node.name:
        pytest.skip(
            reason='This test is to test pip in constructor-based installs'
        )
    # ensure pip is the installer tool, so that the warning will trigger
    monkeypatch.setattr(
        qt_plugin_dialog.PluginListItem,
        'get_installer_tool',
        lambda self: InstallerTools.PYPI,
    )
    monkeypatch.setattr(
        qt_plugin_dialog.PluginListItem,
        'get_installer_source',
        lambda self: 'PyPI',
    )

    plugin_dialog.set_prefix(str(tmp_virtualenv))
    plugin_dialog.search('requests')
    qtbot.wait(500)
    item = plugin_dialog.available_list.item(0)
    widget = plugin_dialog.available_list.itemWidget(item)
    with patch.object(qt_plugin_dialog.QMessageBox, 'exec_') as mock:
        mock.return_value = message_return
        if message_return == QMessageBox.StandardButton.Ok:
            with qtbot.waitSignal(
                plugin_dialog.installer.processFinished, timeout=60_000
            ):
                widget.action_button.click()
            qtbot.wait(5000)
        else:
            widget.action_button.click()
        assert mock.called


def test_cancel(qtbot, tmp_virtualenv, plugin_dialog, request):
    if '[constructor]' in request.node.name:
        pytest.skip(
            reason='This test is only relevant for non-constructor-based installs'
        )

    plugin_dialog.set_prefix(str(tmp_virtualenv))
    plugin_dialog.search('requests')
    qtbot.wait(500)
    item = plugin_dialog.available_list.item(0)
    widget = plugin_dialog.available_list.itemWidget(item)
    with qtbot.waitSignal(
        plugin_dialog.installer.processFinished, timeout=60_000
    ) as blocker:
        widget.action_button.click()
        widget.cancel_btn.click()

    process_finished_data = blocker.args[0]
    assert process_finished_data['action'] == InstallerActions.CANCEL
    assert process_finished_data['pkgs'][0].startswith('requests')
    assert plugin_dialog.available_list.count() == 1
    assert plugin_dialog.installed_list.count() == 2


def test_cancel_all(qtbot, tmp_virtualenv, plugin_dialog, request):
    if '[constructor]' in request.node.name:
        pytest.skip(
            reason='This test is only relevant for non-constructor-based installs'
        )

    plugin_dialog.set_prefix(str(tmp_virtualenv))
    plugin_dialog.search('requests')
    qtbot.wait(500)
    item_1 = plugin_dialog.available_list.item(0)
    plugin_dialog.search('packaging')
    qtbot.wait(500)
    item_2 = plugin_dialog.available_list.item(0)
    widget_1 = plugin_dialog.available_list.itemWidget(item_1)
    widget_2 = plugin_dialog.available_list.itemWidget(item_2)
    with qtbot.waitSignal(plugin_dialog.installer.allFinished, timeout=60_000):
        widget_1.action_button.click()
        widget_2.action_button.click()
        plugin_dialog.cancel_all_btn.click()

    plugin_dialog.search('')
    qtbot.wait(500)

    assert plugin_dialog.available_list.count() == 2
    assert plugin_dialog.installed_list.count() == 2


def test_direct_entry_installs(qtbot, tmp_virtualenv, plugin_dialog, request):
    if '[constructor]' in request.node.name:
        pytest.skip(
            reason='The tested functionality is not available in constructor-based installs'
        )

    plugin_dialog.set_prefix(str(tmp_virtualenv))
    with qtbot.waitSignal(
        plugin_dialog.installer.processFinished, timeout=60_000
    ) as blocker:
        plugin_dialog.direct_entry_edit.setText('requests')
        plugin_dialog.direct_entry_btn.click()

    process_finished_data = blocker.args[0]
    assert process_finished_data['action'] == InstallerActions.INSTALL
    assert process_finished_data['pkgs'][0].startswith('requests')
    qtbot.wait(5000)


@pytest.mark.skipif(
    sys.platform.startswith('linux'), reason='Test fails on linux randomly'
)
def test_shortcut_close(plugin_dialog, qtbot):
    qtbot.keyClicks(
        plugin_dialog, 'W', modifier=Qt.KeyboardModifier.ControlModifier
    )
    qtbot.wait(500)
    assert not plugin_dialog.isVisible()


@pytest.mark.skipif(
    sys.platform.startswith('linux'), reason='Test fails on linux randomly'
)
def test_shortcut_quit(plugin_dialog, qtbot):
    qtbot.keyClicks(
        plugin_dialog, 'Q', modifier=Qt.KeyboardModifier.ControlModifier
    )
    qtbot.wait(500)
    assert not plugin_dialog.isVisible()


@pytest.mark.skipif(
    not sys.platform.startswith('linux'), reason='Test works only on linux'
)
def test_export_plugins_button(plugin_dialog):
    def _timer():
        dialog = QApplication.activeModalWidget()
        dialog.reject()

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(_timer)
    timer.start(4_000)
    plugin_dialog.export_button.click()


def test_export_plugins(plugin_dialog, tmp_path):
    plugins_file = 'plugins.txt'
    plugin_dialog.export_plugins(str(tmp_path / plugins_file))
    assert (tmp_path / plugins_file).exists()


@pytest.mark.skipif(
    not sys.platform.startswith('linux'), reason='Test works only on linux'
)
def test_import_plugins_button(plugin_dialog):
    def _timer():
        dialog = QApplication.activeModalWidget()
        dialog.reject()

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(_timer)
    timer.start(4_000)
    plugin_dialog.import_button.click()


def test_import_plugins(plugin_dialog, tmp_path, qtbot):
    path = tmp_path / 'plugins.txt'
    path.write_text('requests\npackaging\n')
    with qtbot.waitSignal(plugin_dialog.installer.allFinished, timeout=60_000):
        plugin_dialog.import_plugins(str(path))
