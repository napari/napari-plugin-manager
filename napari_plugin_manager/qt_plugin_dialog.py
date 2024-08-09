import contextlib
import importlib.metadata
import os
import sys
import webbrowser
from functools import partial
from pathlib import Path
from typing import Dict, List, Literal, NamedTuple, Optional, Sequence, Tuple

import napari.plugins
import napari.resources
import npe2
from napari._qt.qt_resources import QColoredSVGIcon, get_current_stylesheet
from napari._qt.qthreading import create_worker
from napari._qt.widgets.qt_message_popup import WarnPopup
from napari._qt.widgets.qt_tooltip import QtToolTipLabel
from napari.plugins.utils import normalized_name
from napari.settings import get_settings
from napari.utils.misc import (
    parse_version,
    running_as_constructor_app,
)
from napari.utils.notifications import show_info, show_warning
from napari.utils.translations import trans
from qtpy.QtCore import QPoint, QSize, Qt, QTimer, Signal, Slot
from qtpy.QtGui import QAction, QFont, QKeySequence, QMovie, QShortcut
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from superqt import QCollapsible, QElidingLabel

from napari_plugin_manager.npe2api import (
    cache_clear,
    iter_napari_plugin_info,
)
from napari_plugin_manager.qt_package_installer import (
    InstallerActions,
    InstallerQueue,
    InstallerTools,
    ProcessFinishedData,
)
from napari_plugin_manager.qt_widgets import ClickableLabel
from napari_plugin_manager.utils import is_conda_package

# Scaling factor for each list widget item when expanding.
CONDA = 'Conda'
PYPI = 'PyPI'
ON_BUNDLE = running_as_constructor_app()
IS_NAPARI_CONDA_INSTALLED = is_conda_package('napari')
STYLES_PATH = Path(__file__).parent / 'styles.qss'


def _show_message(widget):
    message = trans._(
        'When installing/uninstalling npe2 plugins, '
        'you must restart napari for UI changes to take effect.'
    )
    if widget.isVisible():
        button = widget.action_button
        warn_dialog = WarnPopup(text=message)
        global_point = widget.action_button.mapToGlobal(
            button.rect().topRight()
        )
        global_point = QPoint(
            global_point.x() - button.width(), global_point.y()
        )
        warn_dialog.move(global_point)
        warn_dialog.exec_()


class ProjectInfoVersions(NamedTuple):
    metadata: npe2.PackageMetadata
    display_name: str
    pypi_versions: List[str]
    conda_versions: List[str]


class PluginListItem(QFrame):
    """An entry in the plugin dialog.  This will include the package name, summary,
    author, source, version, and buttons to update, install/uninstall, etc."""

    # item, package_name, action_name, version, installer_choice
    actionRequested = Signal(
        QListWidgetItem, str, InstallerActions, str, InstallerTools
    )

    def __init__(
        self,
        item: QListWidgetItem,
        package_name: str,
        display_name: str,
        version: str = '',
        url: str = '',
        summary: str = '',
        author: str = '',
        license: str = "UNKNOWN",  # noqa: A002
        *,
        plugin_name: Optional[str] = None,
        parent: QWidget = None,
        enabled: bool = True,
        installed: bool = False,
        npe_version=1,
        versions_conda: Optional[List[str]] = None,
        versions_pypi: Optional[List[str]] = None,
        prefix=None,
    ) -> None:
        super().__init__(parent)
        self.prefix = prefix
        self.item = item
        self.url = url
        self.name = package_name
        self.npe_version = npe_version
        self._version = version
        self._versions_conda = versions_conda
        self._versions_pypi = versions_pypi
        self.setup_ui(enabled)

        if package_name == display_name:
            name = package_name
        else:
            name = f"{display_name} <small>({package_name})</small>"

        self.plugin_name.setText(name)

        if len(versions_pypi) > 0:
            self._populate_version_dropdown(PYPI)
        else:
            self._populate_version_dropdown(CONDA)

        mod_version = version.replace('.', '․')  # noqa: RUF001
        self.version.setWordWrap(True)
        self.version.setText(mod_version)
        self.version.setToolTip(version)

        if summary:
            self.summary.setText(summary)

        if author:
            self.package_author.setText(author)

        self.package_author.setWordWrap(True)
        self.cancel_btn.setVisible(False)

        self._handle_npe2_plugin(npe_version)
        self._set_installed(installed, package_name)
        self._populate_version_dropdown(self.get_installer_source())

    def _set_installed(self, installed: bool, package_name):
        if installed:
            if is_conda_package(package_name):
                self.source.setText(CONDA)

            self.enabled_checkbox.show()
            self.action_button.setText(trans._("Uninstall"))
            self.action_button.setObjectName("remove_button")
            self.info_choice_wdg.hide()
            self.install_info_button.addWidget(self.info_widget)
            self.info_widget.show()
        else:
            self.enabled_checkbox.hide()
            self.action_button.setText(trans._("Install"))
            self.action_button.setObjectName("install_button")
            self.info_widget.hide()
            self.install_info_button.addWidget(self.info_choice_wdg)
            self.info_choice_wdg.show()

    def _handle_npe2_plugin(self, npe_version):
        if npe_version in (None, 1):
            return

        opacity = 0.4 if npe_version == 'shim' else 1
        text = trans._('npe1 (adapted)') if npe_version == 'shim' else 'npe2'
        icon = QColoredSVGIcon.from_resources('logo_silhouette')
        self.set_status(
            icon.colored(color='#33F0FF', opacity=opacity).pixmap(20, 20), text
        )

    def set_status(self, icon=None, text=''):
        """Set the status icon and text. next to the package name."""
        if icon:
            self.status_icon.setPixmap(icon)

        if text:
            self.status_label.setText(text)

        self.status_icon.setVisible(bool(icon))
        self.status_label.setVisible(bool(text))

    def set_busy(
        self,
        text: str,
        action_name: Optional[
            Literal['install', 'uninstall', 'cancel', 'upgrade']
        ] = None,
    ):
        """Updates status text and what buttons are visible when any button is pushed.

        Parameters
        ----------
        text: str
            The new string to be displayed as the status.
        action_name: str
            The action of the button pressed.

        """
        self.item_status.setText(text)
        if action_name == 'upgrade':
            self.cancel_btn.setVisible(True)
            self.action_button.setVisible(False)
        elif action_name in {'uninstall', 'install'}:
            self.action_button.setVisible(False)
            self.cancel_btn.setVisible(True)
        elif action_name == 'cancel':
            self.action_button.setVisible(True)
            self.action_button.setDisabled(False)
            self.cancel_btn.setVisible(False)
        else:  # pragma: no cover
            raise ValueError(f"Not supported {action_name}")

    def setup_ui(self, enabled=True):
        """Define the layout of the PluginListItem"""
        # Enabled checkbox
        self.enabled_checkbox = QCheckBox(self)
        self.enabled_checkbox.setChecked(enabled)
        self.enabled_checkbox.setToolTip(trans._("enable/disable"))
        self.enabled_checkbox.setText("")
        self.enabled_checkbox.stateChanged.connect(self._on_enabled_checkbox)

        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(
            self.enabled_checkbox.sizePolicy().hasHeightForWidth()
        )
        self.enabled_checkbox.setSizePolicy(sizePolicy)
        self.enabled_checkbox.setMinimumSize(QSize(20, 0))

        # Plugin name
        self.plugin_name = ClickableLabel(self)  # To style content
        font_plugin_name = QFont()
        font_plugin_name.setPointSize(15)
        font_plugin_name.setUnderline(True)
        self.plugin_name.setFont(font_plugin_name)

        # Status
        self.status_icon = QLabel(self)
        self.status_icon.setVisible(False)
        self.status_label = QLabel(self)
        self.status_label.setVisible(False)

        if self.url and self.url != 'UNKNOWN':
            # Do not want to highlight on hover unless there is a website.
            self.plugin_name.setObjectName('plugin_name_web')
        else:
            self.plugin_name.setObjectName('plugin_name')

        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(
            self.plugin_name.sizePolicy().hasHeightForWidth()
        )
        self.plugin_name.setSizePolicy(sizePolicy)

        # Warning icon
        icon = QColoredSVGIcon.from_resources("warning")
        self.warning_tooltip = QtToolTipLabel(self)

        # TODO: This color should come from the theme but the theme needs
        # to provide the right color. Default warning should be orange, not
        # red. Code example:
        # theme_name = get_settings().appearance.theme
        # napari.utils.theme.get_theme(theme_name, as_dict=False).warning.as_hex()
        self.warning_tooltip.setPixmap(
            icon.colored(color="#E3B617").pixmap(15, 15)
        )
        self.warning_tooltip.setVisible(False)

        # Item status
        self.item_status = QLabel(self)
        self.item_status.setObjectName("small_italic_text")
        self.item_status.setSizePolicy(sizePolicy)

        # Summary
        self.summary = QElidingLabel(parent=self)
        self.summary.setObjectName('summary_text')
        self.summary.setWordWrap(True)

        font_summary = QFont()
        font_summary.setPointSize(10)
        self.summary.setFont(font_summary)

        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        self.summary.setSizePolicy(sizePolicy)
        self.summary.setContentsMargins(0, -2, 0, -2)

        # Package author
        self.package_author = QElidingLabel(self)
        self.package_author.setObjectName('author_text')
        self.package_author.setWordWrap(True)
        self.package_author.setSizePolicy(sizePolicy)

        # Update button
        self.update_btn = QPushButton('Update', self)
        self.update_btn.setObjectName("install_button")
        self.update_btn.setVisible(False)
        self.update_btn.clicked.connect(self._update_requested)
        sizePolicy.setRetainSizeWhenHidden(True)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.update_btn.setSizePolicy(sizePolicy)
        self.update_btn.clicked.connect(self._update_requested)

        # Action Button
        self.action_button = QPushButton(self)
        self.action_button.setFixedWidth(70)
        sizePolicy1 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.action_button.setSizePolicy(sizePolicy1)
        self.action_button.clicked.connect(self._action_requested)

        # Cancel
        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.setObjectName("remove_button")
        self.cancel_btn.setSizePolicy(sizePolicy)
        self.cancel_btn.setFixedWidth(70)
        self.cancel_btn.clicked.connect(self._cancel_requested)

        # Collapsible button
        coll_icon = QColoredSVGIcon.from_resources('right_arrow').colored(
            color='white',
        )
        exp_icon = QColoredSVGIcon.from_resources('down_arrow').colored(
            color='white',
        )
        self.install_info_button = QCollapsible(
            "Installation Info", collapsedIcon=coll_icon, expandedIcon=exp_icon
        )
        self.install_info_button.setLayoutDirection(
            Qt.RightToLeft
        )  # Make icon appear on the right
        self.install_info_button.setObjectName("install_info_button")
        self.install_info_button.setFixedWidth(180)
        self.install_info_button.content().layout().setContentsMargins(
            0, 0, 0, 0
        )
        self.install_info_button.content().setContentsMargins(0, 0, 0, 0)
        self.install_info_button.content().layout().setSpacing(0)
        self.install_info_button.layout().setContentsMargins(0, 0, 0, 0)
        self.install_info_button.layout().setSpacing(2)
        self.install_info_button.setSizePolicy(sizePolicy)

        # Information widget for available packages
        self.info_choice_wdg = QWidget(self)
        self.info_choice_wdg.setObjectName('install_choice')

        self.source_choice_text = QLabel('Source:')
        self.version_choice_text = QLabel('Version:')
        self.source_choice_dropdown = QComboBox()
        self.version_choice_dropdown = QComboBox()

        if IS_NAPARI_CONDA_INSTALLED and self._versions_conda:
            self.source_choice_dropdown.addItem(CONDA)

        if self._versions_pypi:
            self.source_choice_dropdown.addItem(PYPI)

        source = self.get_installer_source()
        self.source_choice_dropdown.setCurrentText(source)
        self._populate_version_dropdown(source)
        self.source_choice_dropdown.currentTextChanged.connect(
            self._populate_version_dropdown
        )

        # Information widget for installed packages
        self.info_widget = QWidget(self)
        self.info_widget.setLayoutDirection(Qt.LeftToRight)
        self.info_widget.setObjectName("info_widget")
        self.info_widget.setFixedWidth(180)

        self.source_text = QLabel('Source:')
        self.source = QLabel(PYPI)
        self.version_text = QLabel('Version:')
        self.version = QElidingLabel()
        self.version.setWordWrap(True)

        info_layout = QGridLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setVerticalSpacing(0)
        info_layout.addWidget(self.source_text, 0, 0)
        info_layout.addWidget(self.source, 1, 0)
        info_layout.addWidget(self.version_text, 0, 1)
        info_layout.addWidget(self.version, 1, 1)
        self.info_widget.setLayout(info_layout)

        # Error indicator
        self.error_indicator = QPushButton()
        self.error_indicator.setObjectName("warning_icon")
        self.error_indicator.setCursor(Qt.CursorShape.PointingHandCursor)
        self.error_indicator.hide()

        # region - Layout
        # -----------------------------------------------------------------
        layout = QHBoxLayout()
        layout.setSpacing(2)
        layout_left = QVBoxLayout()
        layout_right = QVBoxLayout()
        layout_top = QHBoxLayout()
        layout_bottom = QHBoxLayout()
        layout_bottom.setSpacing(4)

        layout_left.addWidget(
            self.enabled_checkbox, alignment=Qt.AlignmentFlag.AlignTop
        )

        layout_right.addLayout(layout_top, 1)
        layout_right.addLayout(layout_bottom, 100)

        layout.addLayout(layout_left)
        layout.addLayout(layout_right)

        self.setLayout(layout)

        layout_top.addWidget(self.plugin_name)
        layout_top.addWidget(self.status_icon)
        layout_top.addWidget(self.status_label)
        layout_top.addWidget(self.item_status)
        layout_top.addStretch()

        layout_bottom.addWidget(
            self.summary, alignment=Qt.AlignmentFlag.AlignTop, stretch=3
        )
        layout_bottom.addWidget(
            self.package_author, alignment=Qt.AlignmentFlag.AlignTop, stretch=1
        )
        layout_bottom.addWidget(
            self.update_btn, alignment=Qt.AlignmentFlag.AlignTop
        )
        layout_bottom.addWidget(
            self.install_info_button, alignment=Qt.AlignmentFlag.AlignTop
        )
        layout_bottom.addWidget(
            self.action_button, alignment=Qt.AlignmentFlag.AlignTop
        )
        layout_bottom.addWidget(
            self.cancel_btn, alignment=Qt.AlignmentFlag.AlignTop
        )

        info_layout = QGridLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setVerticalSpacing(0)
        info_layout.addWidget(self.source_choice_text, 0, 0, 1, 1)
        info_layout.addWidget(self.source_choice_dropdown, 1, 0, 1, 1)
        info_layout.addWidget(self.version_choice_text, 0, 1, 1, 1)
        info_layout.addWidget(self.version_choice_dropdown, 1, 1, 1, 1)

        # endregion - Layout

        self.info_choice_wdg.setLayout(info_layout)
        self.info_choice_wdg.setLayoutDirection(Qt.LeftToRight)
        self.info_choice_wdg.setObjectName("install_choice_widget")
        self.info_choice_wdg.hide()

    def _populate_version_dropdown(self, source: Literal["PyPI", "Conda"]):
        """Display the versions available after selecting a source: pypi or conda."""
        if source == PYPI:
            versions = self._versions_pypi
        else:
            versions = self._versions_conda
        self.version_choice_dropdown.clear()
        for version in versions:
            self.version_choice_dropdown.addItem(version)

    def _on_enabled_checkbox(self, state: int):
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

    def _cancel_requested(self):
        version = self.version_choice_dropdown.currentText()
        tool = self.get_installer_tool()
        self.actionRequested.emit(
            self.item, self.name, InstallerActions.CANCEL, version, tool
        )

    def _action_requested(self):
        version = self.version_choice_dropdown.currentText()
        tool = self.get_installer_tool()
        action = (
            InstallerActions.INSTALL
            if self.action_button.objectName() == 'install_button'
            else InstallerActions.UNINSTALL
        )
        self.actionRequested.emit(self.item, self.name, action, version, tool)

    def _update_requested(self):
        version = self.version_choice_dropdown.currentText()
        tool = self.get_installer_tool()
        self.actionRequested.emit(
            self.item, self.name, InstallerActions.UPGRADE, version, tool
        )

    def show_warning(self, message: str = ""):
        """Show warning icon and tooltip."""
        self.warning_tooltip.setVisible(bool(message))
        self.warning_tooltip.setToolTip(message)

    def get_installer_source(self):
        return (
            CONDA
            if self.source_choice_dropdown.currentText() == CONDA
            or is_conda_package(self.name)
            else PYPI
        )

    def get_installer_tool(self):
        return (
            InstallerTools.CONDA
            if self.source_choice_dropdown.currentText() == CONDA
            or is_conda_package(self.name, prefix=self.prefix)
            else InstallerTools.PIP
        )


class QPluginList(QListWidget):

    _SORT_ORDER_PREFIX = '0-'

    def __init__(self, parent: QWidget, installer: InstallerQueue) -> None:
        super().__init__(parent)
        self.installer = installer
        self._remove_list = []
        self._data = []
        self._initial_height = None

        self.setSortingEnabled(True)

    def count_visible(self) -> int:
        """Return the number of visible items.

        Visible items are the result of the normal `count` method minus
        any hidden items.
        """
        hidden = 0
        count = self.count()
        for i in range(count):
            item = self.item(i)
            hidden += item.isHidden()

        return count - hidden

    @Slot(tuple)
    def addItem(
        self,
        project_info: ProjectInfoVersions,
        installed=False,
        plugin_name=None,
        enabled=True,
        npe_version=None,
    ):
        pkg_name = project_info.metadata.name
        # don't add duplicates
        if (
            self.findItems(pkg_name, Qt.MatchFlag.MatchFixedString)
            and not plugin_name
        ):
            return

        # including summary here for sake of filtering below.
        searchable_text = f"{pkg_name} {project_info.display_name} {project_info.metadata.summary}"
        item = QListWidgetItem(searchable_text, self)
        item.version = project_info.metadata.version
        super().addItem(item)
        widg = PluginListItem(
            item=item,
            package_name=pkg_name,
            display_name=project_info.display_name,
            version=project_info.metadata.version,
            url=project_info.metadata.home_page,
            summary=project_info.metadata.summary,
            author=project_info.metadata.author,
            license=project_info.metadata.license,
            parent=self,
            plugin_name=plugin_name,
            enabled=enabled,
            installed=installed,
            npe_version=npe_version,
            versions_conda=project_info.conda_versions,
            versions_pypi=project_info.pypi_versions,
        )
        item.widget = widg
        item.npe_version = npe_version
        item.setSizeHint(widg.sizeHint())
        self.setItemWidget(item, widg)

        if project_info.metadata.home_page:
            widg.plugin_name.clicked.connect(
                partial(webbrowser.open, project_info.metadata.home_page)
            )

        widg.actionRequested.connect(self.handle_action)
        item.setSizeHint(item.widget.size())
        if self._initial_height is None:
            self._initial_height = item.widget.size().height()

        widg.install_info_button.setDuration(0)
        widg.install_info_button.toggled.connect(
            lambda: self._resize_pluginlistitem(item)
        )

    def removeItem(self, name):
        count = self.count()
        for i in range(count):
            item = self.item(i)
            if item.widget.name == name:
                self.takeItem(i)
                break

    def refreshItem(self, name, version=None):
        count = self.count()
        for i in range(count):
            item = self.item(i)
            if item.widget.name == name:
                if version is not None:
                    item.version = version
                    mod_version = version.replace('.', '․')  # noqa: RUF001
                    item.widget.version.setText(mod_version)
                    item.widget.version.setToolTip(version)
                item.widget.set_busy('', InstallerActions.CANCEL)
                if item.text().startswith(self._SORT_ORDER_PREFIX):
                    item.setText(item.text()[len(self._SORT_ORDER_PREFIX) :])
                break

    def _resize_pluginlistitem(self, item):
        """Resize the plugin list item, especially after toggling QCollapsible."""
        if item.widget.install_info_button.isExpanded():
            item.widget.setFixedHeight(self._initial_height + 35)
        else:
            item.widget.setFixedHeight(self._initial_height)

        item.setSizeHint(QSize(0, item.widget.height()))

    def handle_action(
        self,
        item: QListWidgetItem,
        pkg_name: str,
        action_name: InstallerActions,
        version: Optional[str] = None,
        installer_choice: Optional[str] = None,
    ):
        """Determine which action is called (install, uninstall, update, cancel).
        Update buttons appropriately and run the action."""
        widget = item.widget
        tool = installer_choice or widget.get_installer_tool()
        self._remove_list.append((pkg_name, item))
        self._warn_dialog = None
        if not item.text().startswith(self._SORT_ORDER_PREFIX):
            item.setText(f"{self._SORT_ORDER_PREFIX}{item.text()}")

        # TODO: NPE version unknown before installing
        if (
            widget.npe_version != 1
            and action_name == InstallerActions.UNINSTALL
        ):
            _show_message(widget)

        if action_name == InstallerActions.INSTALL:
            if version:
                pkg_name += (
                    f"=={item.widget.version_choice_dropdown.currentText()}"
                )
            widget.set_busy(trans._("installing..."), action_name)

            job_id = self.installer.install(
                tool=tool,
                pkgs=[pkg_name],
                # origins="TODO",
            )
            widget.setProperty("current_job_id", job_id)
            if self._warn_dialog:
                self._warn_dialog.exec_()
            self.scrollToTop()

        if action_name == InstallerActions.UPGRADE:
            if hasattr(item, 'latest_version'):
                pkg_name += f"=={item.latest_version}"

            widget.set_busy(trans._("updating..."), action_name)
            widget.update_btn.setDisabled(True)
            widget.action_button.setDisabled(True)

            job_id = self.installer.upgrade(
                tool=tool,
                pkgs=[pkg_name],
                # origins="TODO",
            )
            widget.setProperty("current_job_id", job_id)
            if self._warn_dialog:
                self._warn_dialog.exec_()
            self.scrollToTop()

        elif action_name == InstallerActions.UNINSTALL:
            widget.set_busy(trans._("uninstalling..."), action_name)
            widget.update_btn.setDisabled(True)
            job_id = self.installer.uninstall(
                tool=tool,
                pkgs=[pkg_name],
                # origins="TODO",
                # upgrade=False,
            )
            widget.setProperty("current_job_id", job_id)
            if self._warn_dialog:
                self._warn_dialog.exec_()
            self.scrollToTop()
        elif action_name == InstallerActions.CANCEL:
            widget.set_busy(trans._("cancelling..."), action_name)
            try:
                job_id = widget.property("current_job_id")
                self.installer.cancel(job_id)
            finally:
                widget.setProperty("current_job_id", None)

    def set_data(self, data):
        self._data = data

    def is_running(self):
        return self.count() != len(self._data)

    def packages(self):
        return [self.item(idx).widget.name for idx in range(self.count())]

    @Slot(npe2.PackageMetadata, bool)
    def tag_outdated(self, metadata: npe2.PackageMetadata, is_available: bool):
        """Determines if an installed plugin is up to date with the latest version.
        If it is not, the latest version will be displayed on the update button.
        """
        if not is_available:
            return

        for item in self.findItems(
            metadata.name, Qt.MatchFlag.MatchStartsWith
        ):
            current = item.version
            latest = metadata.version
            is_marked_outdated = getattr(item, 'outdated', False)
            if parse_version(current) >= parse_version(latest):
                # currently is up to date
                if is_marked_outdated:
                    # previously marked as outdated, need to update item
                    # `outdated` state and hide item widget `update_btn`
                    item.outdated = False
                    widg = self.itemWidget(item)
                    widg.update_btn.setVisible(False)
                continue
            if is_marked_outdated:
                # already tagged it
                continue

            item.outdated = True
            item.latest_version = latest
            widg = self.itemWidget(item)
            widg.update_btn.setVisible(True)
            widg.update_btn.setText(
                trans._("update (v{latest})", latest=latest)
            )

    def tag_unavailable(self, metadata: npe2.PackageMetadata):
        """
        Tag list items as unavailable for install with conda-forge.

        This will disable the item and the install button and add a warning
        icon with a hover tooltip.
        """
        for item in self.findItems(
            metadata.name, Qt.MatchFlag.MatchStartsWith
        ):
            widget = self.itemWidget(item)
            widget.show_warning(
                trans._(
                    "Plugin not yet available for installation within the bundle application"
                )
            )
            widget.setObjectName("unavailable")
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.action_button.setEnabled(False)
            widget.warning_tooltip.setVisible(True)

    def filter(self, text: str, starts_with_chars: int = 1):
        """Filter items to those containing `text`."""
        if text:
            # PySide has some issues, so we compare using id
            # See: https://bugreports.qt.io/browse/PYSIDE-74
            flag = (
                Qt.MatchFlag.MatchStartsWith
                if len(text) <= starts_with_chars
                else Qt.MatchFlag.MatchContains
            )
            if len(text) <= starts_with_chars:
                flag = Qt.MatchFlag.MatchStartsWith
                queries = (text, f'napari-{text}')
            else:
                flag = Qt.MatchFlag.MatchContains
                queries = (text,)

            shown = {
                id(it)
                for query in queries
                for it in self.findItems(query, flag)
            }
            for i in range(self.count()):
                item = self.item(i)
                item.setHidden(id(item) not in shown)
        else:
            for i in range(self.count()):
                item = self.item(i)
                item.setHidden(False)


class QtPluginDialog(QDialog):
    def __init__(self, parent=None, prefix=None) -> None:
        super().__init__(parent)

        self._parent = parent
        if (
            parent is not None
            and getattr(parent, '_plugin_dialog', None) is None
        ):
            self._parent._plugin_dialog = self

        self.already_installed = set()
        self.available_set = set()
        self._prefix = prefix
        self._first_open = True
        self._plugin_queue = []  # Store plugin data to be added
        self._plugin_data = []  # Store all plugin data
        self._filter_texts = []
        self._filter_idxs_cache = set()
        self._filter_timer = QTimer(self)
        self.worker = None

        # timer to avoid triggering a filter for every keystroke
        self._filter_timer.setInterval(140)  # ms
        self._filter_timer.timeout.connect(self.filter)
        self._filter_timer.setSingleShot(True)
        self._plugin_data_map = {}
        self._add_items_timer = QTimer(self)

        # Timer to avoid race conditions and incorrect count of plugins when
        # refreshing multiple times in a row. After click we disable the
        # `Refresh` button and re-enable it after 3 seconds.
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(3000)  # ms
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._enable_refresh_button)

        # Add items in batches with a pause to avoid blocking the UI
        self._add_items_timer.setInterval(61)  # ms
        self._add_items_timer.timeout.connect(self._add_items)

        self.installer = InstallerQueue(parent=self, prefix=prefix)
        self.setWindowTitle(trans._('Plugin Manager'))
        self._setup_ui()
        self.installer.set_output_widget(self.stdout_text)
        self.installer.started.connect(self._on_installer_start)
        self.installer.processFinished.connect(self._on_process_finished)
        self.installer.allFinished.connect(self._on_installer_all_finished)
        self.setAcceptDrops(True)

        if (
            parent is not None and parent._plugin_dialog is self
        ) or parent is None:
            self.refresh()
            self._setup_shortcuts()

    # region - Private methods
    # ------------------------------------------------------------------------
    def _enable_refresh_button(self):
        self.refresh_button.setEnabled(True)

    def _quit(self):
        self.close()
        with contextlib.suppress(AttributeError):
            self._parent.close(quit_app=True, confirm_need=True)

    def _setup_shortcuts(self):
        self._quit_action = QAction(trans._('Exit'), self)
        self._quit_action.setShortcut('Ctrl+Q')
        self._quit_action.setMenuRole(QAction.QuitRole)
        self._quit_action.triggered.connect(self._quit)
        self.addAction(self._quit_action)

        self._close_shortcut = QShortcut(
            QKeySequence(Qt.CTRL | Qt.Key_W), self
        )
        self._close_shortcut.activated.connect(self.close)
        get_settings().appearance.events.theme.connect(self._update_theme)

    def _update_theme(self, event):
        stylesheet = get_current_stylesheet([STYLES_PATH])
        self.setStyleSheet(stylesheet)

    def _on_installer_start(self):
        """Updates dialog buttons and status when installing a plugin."""
        self.cancel_all_btn.setVisible(True)
        self.working_indicator.show()
        self.process_success_indicator.hide()
        self.process_error_indicator.hide()
        self.refresh_button.setDisabled(True)

    def _on_process_finished(self, process_finished_data: ProcessFinishedData):
        action = process_finished_data['action']
        exit_code = process_finished_data['exit_code']
        pkg_names = [
            pkg.split('==')[0] for pkg in process_finished_data['pkgs']
        ]
        if action == InstallerActions.INSTALL:
            if exit_code == 0:
                for pkg_name in pkg_names:
                    if pkg_name in self.available_set:
                        self.available_set.remove(pkg_name)

                    self.available_list.removeItem(pkg_name)
                    self._add_installed(pkg_name)
                    self._tag_outdated_plugins()
            else:
                for pkg_name in pkg_names:
                    self.available_list.refreshItem(pkg_name)
        elif action == InstallerActions.UNINSTALL:
            if exit_code == 0:
                for pkg_name in pkg_names:
                    if pkg_name in self.already_installed:
                        self.already_installed.remove(pkg_name)

                    self.installed_list.removeItem(pkg_name)
                    self._add_to_available(pkg_name)
            else:
                for pkg_name in pkg_names:
                    self.installed_list.refreshItem(pkg_name)
        elif action == InstallerActions.UPGRADE:
            pkg_info = [
                (pkg.split('==')[0], pkg.split('==')[1])
                for pkg in process_finished_data['pkgs']
            ]
            for pkg_name, pkg_version in pkg_info:
                self.installed_list.refreshItem(pkg_name, version=pkg_version)
                self._tag_outdated_plugins()
        elif action in [InstallerActions.CANCEL, InstallerActions.CANCEL_ALL]:
            for pkg_name in pkg_names:
                self.installed_list.refreshItem(pkg_name)
                self.available_list.refreshItem(pkg_name)
                self._tag_outdated_plugins()

        self.working_indicator.hide()
        if exit_code:
            self.process_error_indicator.show()
        else:
            self.process_success_indicator.show()

    def _on_installer_all_finished(self, exit_codes):
        self.working_indicator.hide()
        self.cancel_all_btn.setVisible(False)
        self.refresh_button.setDisabled(False)

        if not self.isVisible():
            if sum(exit_codes) > 0:
                show_warning(
                    trans._('Plugin Manager: process completed with errors\n')
                )
            else:
                show_info(trans._('Plugin Manager: process completed\n'))

    def _add_to_available(self, pkg_name):
        self._add_items_timer.stop()
        self._plugin_queue.insert(0, self._plugin_data_map[pkg_name])
        self._add_items_timer.start()
        self._update_plugin_count()

    def _add_to_installed(self, distname, enabled, npe_version=1):
        norm_name = normalized_name(distname or '')
        if distname:
            try:
                meta = importlib.metadata.metadata(distname)

            except importlib.metadata.PackageNotFoundError:
                return  # a race condition has occurred and the package is uninstalled by another thread
            if len(meta) == 0:
                # will not add builtins.
                return
            self.already_installed.add(norm_name)
        else:
            meta = {}

        self.installed_list.addItem(
            ProjectInfoVersions(
                npe2.PackageMetadata(
                    metadata_version="1.0",
                    name=norm_name,
                    version=meta.get('version', ''),
                    summary=meta.get('summary', ''),
                    home_page=meta.get('Home-page', ''),
                    author=meta.get('author', ''),
                    license=meta.get('license', ''),
                ),
                norm_name,
                [],
                [],
            ),
            installed=True,
            enabled=enabled,
            npe_version=npe_version,
        )

    def _add_installed(self, pkg_name=None):
        pm2 = npe2.PluginManager.instance()
        pm2.discover()
        for manifest in pm2.iter_manifests():
            distname = normalized_name(manifest.name or '')
            if distname in self.already_installed or distname == 'napari':
                continue
            enabled = not pm2.is_disabled(manifest.name)
            # if it's an Npe1 adaptor, call it v1
            npev = 'shim' if manifest.npe1_shim else 2
            if distname == pkg_name or pkg_name is None:
                self._add_to_installed(distname, enabled, npe_version=npev)

        napari.plugins.plugin_manager.discover()  # since they might not be loaded yet
        for (
            plugin_name,
            _,
            distname,
        ) in napari.plugins.plugin_manager.iter_available():
            # not showing these in the plugin dialog
            if plugin_name in ('napari_plugin_engine',):
                continue
            if normalized_name(distname or '') in self.already_installed:
                continue
            if normalized_name(distname or '') == pkg_name or pkg_name is None:
                self._add_to_installed(
                    distname,
                    not napari.plugins.plugin_manager.is_blocked(plugin_name),
                )
        self._update_plugin_count()

        for i in range(self.installed_list.count()):
            item = self.installed_list.item(i)
            widget = item.widget
            if widget.name == pkg_name:
                self.installed_list.scrollToItem(item)
                self.installed_list.setCurrentItem(item)
                if widget.npe_version != 1:
                    self._show_status_message(
                        'When (un)installing npe2 plugins, you must restart napari for UI changes to take effect.',
                        10000,
                    )
                    # _show_message(widget)
                break

    def _fetch_available_plugins(self, clear_cache: bool = False):
        get_settings()

        if clear_cache:
            cache_clear()

        self.worker = create_worker(iter_napari_plugin_info)
        self.worker.yielded.connect(self._handle_yield)
        self.worker.started.connect(self.working_indicator.show)
        self.worker.finished.connect(self.working_indicator.hide)
        self.worker.finished.connect(self._add_items_timer.start)
        self.worker.start()

        pm2 = npe2.PluginManager.instance()
        pm2.discover()

    def _setup_ui(self):
        """Defines the layout for the PluginDialog."""
        # Widgets
        self.v_splitter = QSplitter(self)
        self.v_splitter.setOrientation(Qt.Orientation.Vertical)
        self.v_splitter.setStretchFactor(1, 2)

        installed = QWidget(self.v_splitter)

        self.installed_label = QLabel(trans._("Installed Plugins"))

        self.packages_filter = QLineEdit()
        self.packages_filter.setPlaceholderText(trans._("filter..."))
        self.packages_filter.setMaximumWidth(350)
        self.packages_filter.setClearButtonEnabled(True)
        self.packages_filter.setFocus()
        self.packages_filter.textChanged.connect(self._filter_timer.start)

        self.refresh_button = QPushButton(trans._('Refresh'), self)
        self.refresh_button.setObjectName("refresh_button")
        self.refresh_button.setToolTip(
            trans._(
                'This will clear and refresh the available and installed plugins lists.'
            )
        )
        self.refresh_button.clicked.connect(self._refresh_and_clear_cache)

        uninstalled = QWidget(self.v_splitter)

        self.installed_list = QPluginList(installed, self.installer)
        self.avail_label = QLabel(trans._("Available Plugins"))
        self.available_list = QPluginList(uninstalled, self.installer)

        self.stdout_text = QTextEdit(self)
        self.stdout_text.setReadOnly(True)
        self.stdout_text.setObjectName("plugin_manager_process_status")
        self.stdout_text.hide()

        self.working_indicator = QLabel(trans._("loading ..."), self)
        sp = self.working_indicator.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        self.working_indicator.setSizePolicy(sp)

        self.process_error_indicator = QLabel(self)
        self.process_error_indicator.setObjectName("error_label")
        self.process_error_indicator.hide()
        self.process_success_indicator = QLabel(self)
        self.process_success_indicator.setObjectName("success_label")
        self.process_success_indicator.hide()
        load_gif = str(Path(napari.resources.__file__).parent / "loading.gif")
        mov = QMovie(load_gif)
        mov.setScaledSize(QSize(18, 18))
        self.working_indicator.setMovie(mov)
        mov.start()

        visibility_direct_entry = not running_as_constructor_app()
        self.direct_entry_edit = QLineEdit(self)
        self.direct_entry_edit.installEventFilter(self)
        self.direct_entry_edit.setPlaceholderText(
            trans._('install by name/url, or drop file...')
        )
        self.direct_entry_edit.setVisible(visibility_direct_entry)
        self.direct_entry_btn = QPushButton(trans._("Install"), self)
        self.direct_entry_btn.setVisible(visibility_direct_entry)
        self.direct_entry_btn.clicked.connect(self._install_packages)

        self.show_status_btn = QPushButton(trans._("Show Status"), self)
        self.show_status_btn.setFixedWidth(100)
        self.show_status_btn.setCheckable(True)
        self.show_status_btn.setChecked(False)
        self.show_status_btn.toggled.connect(self.toggle_status)

        self.cancel_all_btn = QPushButton(trans._("cancel all actions"), self)
        self.cancel_all_btn.setObjectName("remove_button")
        self.cancel_all_btn.setVisible(False)
        self.cancel_all_btn.clicked.connect(self.installer.cancel_all)

        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy.setRetainSizeWhenHidden(True)
        self.cancel_all_btn.setSizePolicy(sizePolicy)

        self.status_bar = QStatusBar(self)
        self.status_bar.setObjectName("plugin_manager_status_bar")
        self.status_bar.addPermanentWidget(self.process_success_indicator)
        self.status_bar.addPermanentWidget(self.process_error_indicator)
        self.status_bar.addPermanentWidget(self.working_indicator)
        self.status_bar.setSizeGripEnabled(True)
        self.status_bar.addPermanentWidget(self.show_status_btn)
        # layout_bottom.addWidget(self.working_indicator)

        # Layout
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.packages_filter)
        top_layout.addStretch()
        top_layout.addWidget(self.refresh_button)

        layout_installed = QVBoxLayout(installed)
        layout_installed.setContentsMargins(0, 2, 0, 2)
        layout_installed.addWidget(self.installed_label)
        layout_installed.addWidget(self.installed_list)

        layout_uninstalled = QVBoxLayout(uninstalled)
        layout_uninstalled.setContentsMargins(0, 2, 0, 2)
        layout_uninstalled.addWidget(self.avail_label)
        layout_uninstalled.addWidget(self.available_list)

        layout_bottom = QHBoxLayout()
        layout_bottom.addWidget(self.direct_entry_edit)
        layout_bottom.addWidget(self.direct_entry_btn)

        if not visibility_direct_entry:
            layout_bottom.addStretch()

        # layout_bottom.addWidget(self.working_indicator)
        # layout_bottom.addWidget(self.process_success_indicator)
        # layout_bottom.addWidget(self.process_error_indicator)
        layout_bottom.addSpacing(20)
        layout_bottom.addWidget(self.cancel_all_btn)
        layout_bottom.setContentsMargins(0, 0, 4, 0)

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.v_splitter)
        main_layout.addLayout(layout_bottom)
        main_layout.addWidget(self.stdout_text)
        # main_layout.addWidget(self.show_status_btn)
        main_layout.addSpacing(20)
        main_layout.addWidget(self.status_bar)
        margins = main_layout.contentsMargins()
        main_layout.setContentsMargins(
            margins.left(),
            margins.top(),
            margins.right(),
            margins.bottom() // 2,
        )

        self.resize(900, 600)

    def _update_plugin_count(self):
        """Update count labels for both installed and available plugin lists.
        Displays also amount of visible plugins out of total when filtering.
        """
        installed_count = self.installed_list.count()
        installed_count_visible = self.installed_list.count_visible()
        if installed_count == installed_count_visible:
            self.installed_label.setText(
                trans._(
                    "Installed Plugins ({amount})",
                    amount=installed_count,
                )
            )
        else:
            self.installed_label.setText(
                trans._(
                    "Installed Plugins ({count}/{amount})",
                    count=installed_count_visible,
                    amount=installed_count,
                )
            )

        available_count = len(self._plugin_data) - self.installed_list.count()
        available_count = available_count if available_count >= 0 else 0
        available_count_visible = self.available_list.count_visible()
        if available_count == available_count_visible:
            self.avail_label.setText(
                trans._(
                    "Available Plugins ({amount})",
                    amount=available_count,
                )
            )
        else:
            self.avail_label.setText(
                trans._(
                    "Available Plugins ({count}/{amount})",
                    count=available_count_visible,
                    amount=available_count,
                )
            )

    def _install_packages(
        self,
        packages: Sequence[str] = (),
    ):
        if not packages:
            _packages = self.direct_entry_edit.text()
            packages = (
                [_packages] if os.path.exists(_packages) else _packages.split()
            )
            self.direct_entry_edit.clear()

        if packages:
            self.installer.install(InstallerTools.PIP, packages)

    def _tag_outdated_plugins(self):
        """Tag installed plugins that might be outdated."""
        for pkg_name in self.installed_list.packages():
            _data = self._plugin_data_map.get(pkg_name)
            if _data is not None:
                metadata, is_available_in_conda, _ = _data
                self.installed_list.tag_outdated(
                    metadata, is_available_in_conda
                )

    def _add_items(self):
        """
        Add items to the lists by `batch_size` using a timer to add a pause
        and prevent freezing the UI.
        """
        if len(self._plugin_queue) == 0:
            if (
                self.installed_list.count() + self.available_list.count()
                == len(self._plugin_data)
                and self.available_list.count() != 0
            ):
                self._add_items_timer.stop()
                if not self.isVisible():
                    show_info(
                        trans._(
                            'Plugin Manager: All available plugins loaded\n'
                        )
                    )

            return

        batch_size = 2
        for _ in range(batch_size):
            data = self._plugin_queue.pop(0)
            metadata, is_available_in_conda, extra_info = data
            display_name = extra_info.get('display_name', metadata.name)
            if metadata.name in self.already_installed:
                self.installed_list.tag_outdated(
                    metadata, is_available_in_conda
                )
            else:
                if metadata.name not in self.available_set:
                    self.available_set.add(metadata.name)
                    self.available_list.addItem(
                        ProjectInfoVersions(
                            metadata,
                            display_name,
                            extra_info['pypi_versions'],
                            extra_info['conda_versions'],
                        )
                    )
                if ON_BUNDLE and not is_available_in_conda:
                    self.available_list.tag_unavailable(metadata)

            if len(self._plugin_queue) == 0:
                self._tag_outdated_plugins()
                break

        if not self._filter_timer.isActive():
            self.filter(None, skip=True)

    def _handle_yield(self, data: Tuple[npe2.PackageMetadata, bool, Dict]):
        """Output from a worker process.

        Includes information about the plugin, including available versions on conda and pypi.

        The data is stored but the actual items are added via a timer in the `_add_items`
        method to prevent the UI from freezing by adding all items at once.
        """
        self._plugin_data.append(data)
        self._plugin_queue.append(data)
        self._filter_texts = [
            f"{i[0].name} {i[-1].get('display_name', '')} {i[0].summary}".lower()
            for i in self._plugin_data
        ]
        metadata, _, _ = data
        self._plugin_data_map[metadata.name] = data
        self.available_list.set_data(self._plugin_data)

    def _search_in_available(self, text):
        idxs = []
        for idx, item in enumerate(self._filter_texts):
            if text.lower() in item and idx not in self._filter_idxs_cache:
                idxs.append(idx)
                self._filter_idxs_cache.add(idx)

        return idxs

    def _refresh_and_clear_cache(self):
        self.refresh(clear_cache=True)

    def _show_status_message(self, message, timeout=0):
        self.status_bar.showMessage(message, timeout)
        self.process_success_indicator.show()

    # endregion - Private methods

    # region - Qt overrides
    # ------------------------------------------------------------------------
    def closeEvent(self, event):
        if self._parent is not None:
            plugin_dialog = getattr(self._parent, '_plugin_dialog', self)
            if self != plugin_dialog:
                self.destroy(True, True)
                super().closeEvent(event)
            else:
                plugin_dialog.hide()
        else:
            super().closeEvent(event)

    def dragEnterEvent(self, event):
        event.accept()

    def dropEvent(self, event):
        md = event.mimeData()
        if md.hasUrls():
            files = [url.toLocalFile() for url in md.urls()]
            self.direct_entry_edit.setText(files[0])
            return True

        return super().dropEvent(event)

    def exec_(self):
        plugin_dialog = getattr(self._parent, '_plugin_dialog', self)
        if plugin_dialog != self:
            self.close()

        plugin_dialog.setModal(True)
        plugin_dialog.show()

        if self._first_open:
            self._update_theme(None)
            self._first_open = False

    def hideEvent(self, event):
        self.packages_filter.clear()
        self.toggle_status(False)
        super().hideEvent(event)

    # endregion - Qt overrides

    # region - Public methods
    # ------------------------------------------------------------------------
    def filter(self, text: Optional[str] = None, skip=False) -> None:
        """Filter by text or set current text as filter."""
        if text is None:
            text = self.packages_filter.text()
        else:
            self.packages_filter.setText(text)

        if not skip and self.available_list.is_running() and len(text) >= 1:
            items = [
                self._plugin_data[idx]
                for idx in self._search_in_available(text)
            ]
            if items:
                for item in items:
                    if item in self._plugin_queue:
                        self._plugin_queue.remove(item)

                self._plugin_queue = items + self._plugin_queue

        self.installed_list.filter(text)
        self.available_list.filter(text)
        self._update_plugin_count()

    def refresh(self, clear_cache: bool = False):
        self.refresh_button.setDisabled(True)

        if self.worker is not None:
            self.worker.quit()

        if self._add_items_timer.isActive():
            self._add_items_timer.stop()

        self._filter_texts = []
        self._plugin_queue = []
        self._plugin_data = []
        self._plugin_data_map = {}

        self.installed_list.clear()
        self.available_list.clear()
        self.already_installed = set()
        self.available_set = set()

        self._add_installed()
        self._fetch_available_plugins(clear_cache=clear_cache)

        self._refresh_timer.start()

    def toggle_status(self, show=None):
        show = not self.stdout_text.isVisible() if show is None else show
        if show:
            self.show_status_btn.setText(trans._("Hide Status"))
            self.stdout_text.show()
        else:
            self.show_status_btn.setText(trans._("Show Status"))
            self.stdout_text.hide()

    def set_prefix(self, prefix):
        self._prefix = prefix
        self.installer._prefix = prefix
        for idx in range(self.available_list.count()):
            item = self.available_list.item(idx)
            item.widget.prefix = prefix

        for idx in range(self.installed_list.count()):
            item = self.installed_list.item(idx)
            item.widget.prefix = prefix

    # endregion - Public methods


if __name__ == "__main__":
    from qtpy.QtWidgets import QApplication

    app = QApplication([])
    widget = QtPluginDialog()
    widget.exec_()
    sys.exit(app.exec_())
