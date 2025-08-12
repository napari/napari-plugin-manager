# napari-plugin-manager

[![License](https://img.shields.io/pypi/l/napari-plugin-manager.svg?color=green)](https://github.com/napari/napari-plugin-manager/raw/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/napari-plugin-manager.svg?color=green)](https://pypi.org/project/napari-plugin-manager)
[![Python Version](https://img.shields.io/pypi/pyversions/napari-plugin-manager.svg?color=green)](https://python.org)
[![tests](https://github.com/napari/napari-plugin-manager/actions/workflows/test_and_deploy.yml/badge.svg)](https://github.com/napari/napari-plugin-manager/actions/workflows/test_and_deploy.yml)
[![codecov](https://codecov.io/gh/napari/napari-plugin-manager/branch/main/graph/badge.svg)](https://codecov.io/gh/napari/napari-plugin-manager)

[napari] plugin manager to provide a graphical user interface for installing
[napari] plugins.

You can read the documentation at [napari.org/napari-plugin-manager](https://napari.org/napari-plugin-manager).

## Overview

The `napari-plugin-manager` used to be part of the [napari] codebase before the 0.5.x release
series. It's now maintained as a separate project and package to allow uncoupled iterations outside
of the `napari` release cycle.

Future work will allow other applications with a plugin ecosytem to customize and
use the `plugin-manager`. This package remains under active development and contributions
are very welcome. Please [open an issue] to discuss potential improvements.

This package currently provides:

- A package installer process queue that supports both [pip] and [conda] installs.
- An easy to use GUI for searching, installing, uninstalling and updating plugins that make part of
  the napari ecosystem. Each plugin entry provides a summary and information on the authors that
  created the package. The REST API used to query for plugins and plugin information is provided by
  the [npe2api service](https://api.napari.org).
- The ability to install other packages via URL of by dragging and dropping artifacts from [PyPI].

![Screenshot of the napari-plugin-manager interface, showcasing the plugin descriptions](https://raw.githubusercontent.com/napari/napari-plugin-manager/refs/heads/main/images/description.png)

`napari-plugin-manager` knows how to detect if napari was installed using `conda` or `pip` and
provide the appropriate default installer tool on the `Installation Info` dropdown for each plugin.

`conda` provides an efficient dependency solver that guarantees the stability and correctness of
the napari installation and work environment. This is the reason why `conda` is the default tool
used for the [napari
bundle](https://napari.org/stable/tutorials/fundamentals/installation_bundle_conda.html), a 1-click
installer available for Mac, Linux and Windows. This installation method is best if you mainly want
to use napari as a standalone GUI app. However, certain plugins may not be supported.

## Installation

### PyPI

`napari-plugin-manager` is available through the Python Package Index and can be installed using [pip].

```bash
pip install napari-plugin-manager
```

### Conda

`napari-plugin-manager` is also available for install using [conda] through the [conda-forge channel](https://conda-forge.org/docs/#what-is-conda-forge).


```bash
conda install napari-plugin-manager -c conda-forge
```

## Using the napari plugin manager

### Enabling/Disabling plugins

Installed plugins found on the current napari installation are displayed on the top list of the UI.

Users of napari can choose to enable/disable a specific plugin by checking/unchecking the checkbox
to the left of each plugin item in the list.

### Filtering

You can filter available plugins by name or description by typing on the search box
on the top left corner of the UI. Only plugins that match the filter criteria will be shown.

In the image below filtering by the word `arcos` yields a single plugin, the
`arcos-gui` plugin. Notice that plugins that provide a display name, will show
the package name to the right in parenthesis.

![Screenshot of the napari-plugin-manager interface showcasing the filtering features with the query 'arcos'](https://raw.githubusercontent.com/napari/napari-plugin-manager/main/images/filter.png)

### Refreshing

If a new plugin has been released but it is not available on the list, you can click on the
`Refresh` button located at the top right corner, to clear the cache and load all newly
available plugins.

### Installing a plugin

To install a plugin:

1. Select it by scrolling the available plugins list on the bottom, or by directly
filtering by name or description.
2. Select the tool (`conda` or `pip`) and version on the `Installation Info` dropdown.
3. Start the installation process by clicking on the `Install` button.

You can cancel the process at any time by clicking the `Cancel` button of each plugin.

**Note**: Not all napari plugins are currently available on conda via the
[conda-forge channel](https://anaconda.org/conda-forge/). Some plugins will require
a restart to be properly configured.

![Screenshot of the napari-plugin-manager showing the process of installing a plugin](https://raw.githubusercontent.com/napari/napari-plugin-manager/main/images/install.png)

### Installing a plugin via direct entry

You can also install a napari plugin or any other package via the direct entry option. The following steps
correspond to the options and buttons located at the **bottom of the dialog**.

1. You can type either the name of the package, a url to the resource or drag and drop a compressed file
   of a previously downloaded package.
2. Select the tool (`conda` or `pip`) by clicking on the arrow dorpdown of the `Install` button.
3. Start the installation process by clicking on the `Install` button.

You can cancel the process at any time by clicking the `Cancel all` button.

![Screenshot of the napari-plugin-manager showing the direct entry options](https://raw.githubusercontent.com/napari/napari-plugin-manager/main/images/direct-entry.png)

### Uninstalling a plugin

To uninstall a plugin:

1. Select it by scrolling the installed plugins list on the top, or by directly
filtering by name or description.
2. Start the removal process by clicking on the `Uninstall` button.

You can cancel the process at any time by clicking the `Cancel` button of each plugin.

**Note**: Some plugins will require a restart to be properly removed.

![Screenshot of the napari-plugin-manager showing the process of uninstalling a plugin](https://raw.githubusercontent.com/napari/napari-plugin-manager/main/images/uninstall.png)

### Updating a plugin

When a new version of an installed plugin is available, an `Update (vX.Y.Z)`
button will appear to the left of the `Installation Info` dropdown.

To update a plugin:

1. Select it by scrolling the install plugins list on the top, or by directly
filtering by name or description.
2. Start the update process by clicking on the `Update (vX.Y.Z)` button.

You can cancel the process at any time by clicking the `Cancel` button of each plugin.

![Screenshot of the napari-plugin-manager showing the process of updating a plugin](https://raw.githubusercontent.com/napari/napari-plugin-manager/main/images/update.png)

### Export/Import plugins

You can export the list of install plugins by clicking on the `Export` button located on the top right
corner of the UI. This will prompt a dialog to select the location and name of the text file where
the installed plugin list will be saved.

The file is plain text and plugins are listed in the [requirements.txt](https://pip.pypa.io/en/stable/reference/requirements-file-format/) format:
```
plugin_name==0.1.2
```

This file can be shared and then imported by clicking on the `Import` button located on the top right
corner of the UI. This will prompt a dialog to select the location of the text file to import.

After selecting the file, the plugin manager will attempt to install all the listed plugins using the auto-detected default installer.

![Screenshot of the napari-plugin-manager showing the process of import/export](https://raw.githubusercontent.com/napari/napari-plugin-manager/main/images/import-export.png)

### Batch actions

You don't need wait for one action to finish before you can start another one. You can add more
tasks to the queue (install/uninstall/update) by clicking on the corresponding action buttons
plugin by plugin. The actions will be carried out sequentially and in the order in which you
started them.

You can cancel all the started installer actions at any time by clicking `Cancel all`
button at the bottom of the UI.

## Troubleshooting

In order to visualize more detailed information on the installer process output, you can
click on the `Show status` button located at the bottom left corner of the UI. To hide
this detailed information you can click on the `Hide status` button.

Some issues that you might experience when using the installer include:

* Incompatible packages due to conflicting dependencies.
* Network connectivity errors.

![Screenshot of the napari-plugin-manager interface showcasing the status information, which is initially hidden by default.](https://raw.githubusercontent.com/napari/napari-plugin-manager/main/images/status.png)

## License

Distributed under the terms of the [BSD-3] license, "napari-plugin-manager" is free and open source
software.

## Issues

If you encounter any problems, please [file an issue] along with a detailed description.

[napari]: https://github.com/napari/napari
[@napari]: https://github.com/napari
[BSD-3]: http://opensource.org/licenses/BSD-3-Clause
[file an issue]: https://github.com/napari/napari-plugin-manager/issues
[open an issue]: https://github.com/napari/napari-plugin-manager/issues
[pip]: https://pypi.org/project/pip/
[conda]: https://conda.org
[PyPI]: https://pypi.org/
