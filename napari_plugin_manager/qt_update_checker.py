import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import date
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import packaging
import packaging.version
from napari import __version__
from napari._qt.qthreading import create_worker
from napari.utils.notifications import show_warning
from qtpy.QtWidgets import QMessageBox, QWidget
from superqt import ensure_main_thread

IGNORE_DAYS = 21
IGNORE_FILE = "ignore.txt"


@lru_cache
def github_tags():
    url = 'https://api.github.com/repos/napari/napari/tags'
    with urlopen(url) as r:
        data = json.load(r)

    versions = []
    for item in data:
        version = item.get('name', None)
        if version:
            if version.startswith('v'):
                version = version[1:]

            versions.append(version)

    return list(reversed(versions))


@lru_cache
def conda_forge_releases():
    url = 'https://api.anaconda.org/package/conda-forge/napari/'
    with urlopen(url) as r:
        data = json.load(r)
    versions = data.get('versions', [])
    return versions


def get_latest_version():
    """Check latest version between tags and conda forge."""
    try:
        with ThreadPoolExecutor() as executor:
            tags = executor.submit(github_tags)
            cf = executor.submit(conda_forge_releases)

        gh_tags = tags.result()
        cf_versions = cf.result()
    except (HTTPError, URLError):
        show_warning(
            'Plugin manager: There seems to be an issue with network connectivity. '
        )
        return

    latest_version = packaging.version.parse(cf_versions[-1])
    latest_tag = packaging.version.parse(gh_tags[-1])
    if latest_version > latest_tag:
        yield latest_version
    else:
        yield latest_tag


class UpdateChecker(QWidget):

    FIRST_TIME = False

    # def __init__(self):
    #     super().__init__()
    #     print("hello!")
    #     self.label = QLabel("Hello, world!")
    #     layout = QVBoxLayout()
    #     layout.addWidget(self.label)
    #     self.setLayout(layout)
    #     self._timer = QTimer()
    #     self._timer.setInterval(5000)
    #     self._timer.timeout.connect(self.run)
    #     self._timer.setSingleShot(True)
    #     self._timer.start()

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self._current_version = packaging.version.parse(__version__)
        self._latest_version = None
        self._worker = None
        self._base_folder = sys.prefix

    def check(self):

        if os.path.exists(os.path.join(self._base_folder, IGNORE_FILE)):
            with (
                open(
                    os.path.join(self._base_folder, IGNORE_FILE),
                    encoding="utf-8",
                ) as f_p,
                suppress(ValueError),
            ):
                old_date = date.fromisoformat(f_p.read())
                if (date.today() - old_date).days < IGNORE_DAYS:
                    return

            os.remove(os.path.join(self._base_folder, IGNORE_FILE))

        self._worker = create_worker(get_latest_version)
        self._worker.yielded.connect(self.show_version_info)
        self._worker.start()

    @ensure_main_thread
    def show_version_info(self, latest_version):
        my_version = self._current_version
        remote_version = latest_version
        if remote_version > my_version:
            message = QMessageBox(
                QMessageBox.Icon.Information,
                "New release",
                f"You use outdated version of napari. "
                f"Your version is {my_version} and current is {remote_version}.",
                QMessageBox.StandardButton.Ok
                | QMessageBox.StandardButton.Ignore,
            )

            if message.exec_() == QMessageBox.StandardButton.Ignore:
                os.makedirs(self._base_folder, exist_ok=True)
                with open(
                    os.path.join(self._base_folder, IGNORE_FILE),
                    "w",
                    encoding="utf-8",
                ) as f_p:
                    f_p.write(date.today().isoformat())

    def run(self):
        parent = self.parent()
        parent.hide()
        QMessageBox.information(None, "Hello!", "Hello, world!")


if __name__ == '__main__':
    from qtpy.QtWidgets import QApplication

    app = QApplication([])
    checker = UpdateChecker()
    checker.check()
    sys.exit(app.exec_())
