# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
# import os
# import sys
# sys.path.insert(0, os.path.abspath('.'))

from napari_plugin_manager._version import (
    version as napari_plugin_manager_version,
)

release = napari_plugin_manager_version
if 'dev' in release:  # noqa: SIM108
    version = 'dev'
else:
    version = release

# -- Project information -----------------------------------------------------

project = 'napari-plugin-manager'
copyright = '2024, The napari team'  # noqa: A001
author = 'The napari team'

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.

extensions = [
    'sphinx.ext.intersphinx',
    'sphinx_external_toc',
    'myst_nb',
    'sphinx.ext.viewcode',
    'sphinx_favicon',
    'sphinx_copybutton',
]

external_toc_path = '_toc.yml'

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = 'napari_sphinx_theme'

# # Define the json_url for our version switcher.
# json_url = "https://napari.org/dev/_static/version_switcher.json"

# if version == "dev":
#     version_match = "latest"
# else:
#     version_match = release

html_theme_options = {
    'external_links': [{'name': 'napari', 'url': 'https://napari.org'}],
    'github_url': 'https://github.com/napari/napari-plugin-manager',
    'navbar_start': ['navbar-logo', 'navbar-project'],
    'navbar_end': ['navbar-icon-links'],
    # "switcher": {
    #     "json_url": json_url,
    #     "version_match": version_match,
    # },
    'navbar_persistent': [],
    'header_links_before_dropdown': 6,
    'secondary_sidebar_items': ['page-toc'],
    'pygments_light_style': 'napari',
    'pygments_dark_style': 'napari',
}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']
html_logo = 'images/logo.png'
html_sourcelink_suffix = ''
html_title = 'napari plugin manager'

favicons = [
    {
        # the SVG is the "best" and contains code to detect OS light/dark mode
        'static-file': 'favicon/logo-silhouette-dark-light.svg',
        'type': 'image/svg+xml',
    },
    {
        # Safari in Oct. 2022 does not support SVG
        # an ICO would work as well, but PNG should be just as good
        # setting sizes="any" is needed for Chrome to prefer the SVG
        'sizes': 'any',
        'static-file': 'favicon/logo-silhouette-192.png',
    },
    {
        # this is used on iPad/iPhone for "Save to Home Screen"
        # apparently some other apps use it as well
        'rel': 'apple-touch-icon',
        'sizes': '180x180',
        'static-file': 'favicon/logo-noborder-180.png',
    },
]

html_css_files = [
    'custom.css',
]

intersphinx_mapping = {
    'python': ['https://docs.python.org/3', None],
    'numpy': ['https://numpy.org/doc/stable/', None],
    'napari_plugin_engine': [
        'https://napari-plugin-engine.readthedocs.io/en/latest/',
        'https://napari-plugin-engine.readthedocs.io/en/latest/objects.inv',
    ],
    'napari': [
        'https://napari.org/dev',
        'https://napari.org/dev/objects.inv',
    ],
}

myst_enable_extensions = [
    'colon_fence',
    'dollarmath',
    'substitution',
    'tasklist',
]

myst_heading_anchors = 4
suppress_warnings = ['etoc.toctree']

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = [
    '_build',
    'Thumbs.db',
    '.DS_Store',
    '.jupyter_cache',
    'jupyter_execute',
]
