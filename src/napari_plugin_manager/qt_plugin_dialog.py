import sys
from pathlib import Path

import napari.plugins
import napari.resources
import npe2
from napari._qt.qt_resources import (
    QColoredSVGIcon,
    get_stylesheet,
)
from napari._qt.qthreading import create_worker
from napari._qt.widgets.qt_tooltip import QtToolTipLabel
from napari.plugins.utils import normalized_name
from napari.settings import get_settings
from napari.utils.misc import (
    running_as_constructor_app,
)
from napari.utils.notifications import show_info, show_warning
from napari.utils.translations import trans
from qtpy.QtCore import QSize
from qtpy.QtGui import (
    QMovie,
)
from qtpy.QtWidgets import QCheckBox, QMessageBox

from napari_plugin_manager.base_qt_package_installer import (
    InstallerActions,
    InstallerTools,
)
from napari_plugin_manager.base_qt_plugin_dialog import (
    BasePluginListItem,
    BaseProjectInfoVersions,
    BaseQPluginList,
    BaseQtPluginDialog,
)
from napari_plugin_manager.npe2api import (
    cache_clear,
    iter_napari_plugin_info,
)
from napari_plugin_manager.qt_package_installer import NapariInstallerQueue
from napari_plugin_manager.utils import is_conda_package

# Scaling factor for each list widget item when expanding.
STYLES_PATH = Path(__file__).parent / 'styles.qss'
DISMISS_WARN_PYPI_INSTALL_DLG = False


class ProjectInfoVersions(BaseProjectInfoVersions):
    metadata: npe2.PackageMetadata


class PluginListItem(BasePluginListItem):
    """An entry in the plugin dialog.  This will include the package name, summary,
    author, source, version, and buttons to update, install/uninstall, etc."""

    BASE_PACKAGE_NAME: str = 'napari'

    def _warning_icon(self) -> QColoredSVGIcon:
        # TODO: This color should come from the theme but the theme needs
        # to provide the right color. Default warning should be orange, not
        # red. Code example:
        # theme_name = get_settings().appearance.theme
        # napari.utils.theme.get_theme(theme_name, as_dict=False).warning.as_hex()
        return QColoredSVGIcon.from_resources('warning').colored(
            color='#E3B617'
        )

    def _collapsed_icon(self) -> QColoredSVGIcon:
        return QColoredSVGIcon.from_resources('right_arrow').colored(
            color='white'
        )

    def _expanded_icon(self) -> QColoredSVGIcon:
        return QColoredSVGIcon.from_resources('down_arrow').colored(
            color='white'
        )

    def _warning_tooltip(self) -> QtToolTipLabel:
        return QtToolTipLabel(self)

    def _trans(self, text, **kwargs) -> str:
        return trans._(text, **kwargs)

    def _handle_plugin_api_version(self, plugin_api_version: str) -> None:
        if plugin_api_version in (None, 1):
            return

        opacity = 0.4 if plugin_api_version == 'shim' else 1
        text = (
            self._trans('npe1 (adapted)')
            if plugin_api_version == 'shim'
            else 'npe2'
        )
        icon = QColoredSVGIcon.from_resources('logo_silhouette').colored(
            color='#33F0FF', opacity=opacity
        )
        self.set_status(icon.pixmap(20, 20), text)

    def _on_enabled_checkbox(self, state: int) -> None:
        """Called with `state` when checkbox is clicked."""
        enabled = bool(state)
        plugin_name = self.plugin_name.text()
        pm2 = npe2.PluginManager.instance()
        if plugin_name in pm2:
            pm2.enable(plugin_name) if state else pm2.disable(plugin_name)
            return

        for (
            npe1_name,
            _,
            distname,
        ) in napari.plugins.plugin_manager.iter_available():
            if distname and (normalized_name(distname) == plugin_name):
                napari.plugins.plugin_manager.set_blocked(
                    npe1_name, not enabled
                )
                return

    def _warn_pypi_install(self) -> bool:
        return running_as_constructor_app() or is_conda_package(
            'napari'
        )  # or True

    def _action_validation(
        self, tool: InstallerTools, action: InstallerActions
    ) -> bool:
        global DISMISS_WARN_PYPI_INSTALL_DLG
        if (
            tool == InstallerTools.PYPI
            and action == InstallerActions.INSTALL
            and self._warn_pypi_install()
            and not DISMISS_WARN_PYPI_INSTALL_DLG
        ):
            warn_msgbox = QMessageBox(self)
            warn_msgbox.setWindowTitle(
                self._trans('PyPI installation on bundle/conda')
            )
            warn_msgbox.setText(
                self._trans(
                    'Installing from PyPI does not take into account existing installed packages, '
                    'so it can break existing installations. '
                    'If this happens the only solution is to reinstall the bundle/create a new conda environment.\n\n'
                    'Are you sure you want to install from PyPI?'
                )
            )
            warn_checkbox = QCheckBox(
                self._trans(
                    "Don't show this message again in the current session"
                )
            )
            warn_msgbox.setCheckBox(warn_checkbox)
            warn_msgbox.setIcon(QMessageBox.Icon.Warning)
            warn_msgbox.setStandardButtons(
                QMessageBox.StandardButton.Ok
                | QMessageBox.StandardButton.Cancel
            )
            button_clicked = warn_msgbox.exec_()
            DISMISS_WARN_PYPI_INSTALL_DLG = warn_checkbox.isChecked()
            if button_clicked != QMessageBox.StandardButton.Ok:
                return False
        return True


class QPluginList(BaseQPluginList):
    PLUGIN_LIST_ITEM_CLASS = PluginListItem

    def _trans(self, text: str, **kwargs) -> str:
        return trans._(text, **kwargs)


class QtPluginDialog(BaseQtPluginDialog):
    PACKAGE_METADATA_CLASS = npe2.PackageMetadata
    PROJECT_INFO_VERSION_CLASS = ProjectInfoVersions
    PLUGIN_LIST_CLASS = QPluginList
    INSTALLER_QUEUE_CLASS = NapariInstallerQueue
    BASE_PACKAGE_NAME = 'napari'

    def _setup_theme_update(self) -> None:
        settings = get_settings()
        settings.appearance.events.theme.connect(self._update_theme)
        settings.appearance.events.font_size.connect(self._update_theme)

    def _update_theme(self, event) -> None:
        settings = get_settings()
        theme = settings.appearance.theme
        font_variable = {'font_size': f'{settings.appearance.font_size}pt'}
        stylesheet = get_stylesheet(
            theme, extra=[STYLES_PATH], extra_variables=font_variable
        )
        self.setStyleSheet(stylesheet)

    def _add_installed(self, pkg_name: str | None = None) -> None:
        use_npe2_adaptor = get_settings().plugins.use_npe2_adaptor
        pm2 = npe2.PluginManager.instance()
        pm2.discover(include_npe1=use_npe2_adaptor)
        for manifest in pm2.iter_manifests():
            distname = normalized_name(manifest.name or '')
            if distname in self.already_installed or distname == 'napari':
                continue
            enabled = not pm2.is_disabled(manifest.name)
            # if it's an Npe1 adaptor, call it v1
            npev = 'shim' if manifest.npe1_shim else 2
            if distname == pkg_name or pkg_name is None:
                self._add_to_installed(
                    distname, enabled, distname, plugin_api_version=npev
                )

        if not use_npe2_adaptor:
            napari.plugins.plugin_manager.discover()  # since they might not be loaded yet
            for (
                plugin_name,
                _,
                distname,
            ) in napari.plugins.plugin_manager.iter_available():
                # not showing these in the plugin dialog
                if plugin_name in (
                    'napari_plugin_engine',
                    'napari_plugin_manager',
                ):
                    continue
                if normalized_name(distname or '') in self.already_installed:
                    continue
                if (
                    normalized_name(distname or '') == pkg_name
                    or pkg_name is None
                ):
                    self._add_to_installed(
                        distname,
                        not napari.plugins.plugin_manager.is_blocked(
                            plugin_name
                        ),
                        normalized_name(distname or ''),
                    )
        self._update_plugin_count()

        for i in range(self.installed_list.count()):
            item = self.installed_list.item(i)
            widget = item.widget
            if widget.name == pkg_name:
                self.installed_list.scrollToItem(item)
                self.installed_list.setCurrentItem(item)
                break

    def _fetch_available_plugins(self, clear_cache: bool = False) -> None:
        settings = get_settings()
        use_npe2_adaptor = settings.plugins.use_npe2_adaptor

        if clear_cache:
            cache_clear()

        self.worker = create_worker(iter_napari_plugin_info)
        self.worker.yielded.connect(self._handle_yield)
        self.worker.started.connect(self.working_indicator.show)
        self.worker.finished.connect(self.working_indicator.hide)
        self.worker.finished.connect(self.finished)
        self.worker.finished.connect(self.search)
        self.worker.start()

        pm2 = npe2.PluginManager.instance()
        pm2.discover(include_npe1=use_npe2_adaptor)

    def _loading_gif(self) -> QMovie:
        load_gif = str(Path(napari.resources.__file__).parent / 'loading.gif')
        mov = QMovie(load_gif)
        mov.setScaledSize(QSize(18, 18))
        return mov

    def _on_bundle(self) -> bool:
        return running_as_constructor_app()

    def _show_info(self, info: str) -> None:
        show_info(info)

    def _show_warning(self, warning: str) -> None:
        show_warning(warning)

    def _trans(self, text: str, **kwargs) -> str:
        return trans._(text, **kwargs)


if __name__ == '__main__':
    from qtpy.QtWidgets import QApplication

    app = QApplication([])
    widget = QtPluginDialog()
    widget.exec_()
    sys.exit(app.exec_())
