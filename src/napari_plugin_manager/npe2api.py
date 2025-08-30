"""
These convenience functions will be useful for searching pypi for packages
that match the plugin naming convention, and retrieving related metadata.
"""

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import (
    TypedDict,
    cast,
)
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from napari.plugins.utils import normalized_name
from napari.utils.notifications import show_warning
from npe2 import PackageMetadata
from typing_extensions import NotRequired

from napari_plugin_manager.utils import get_homepage_url

PyPIname = str


@lru_cache
def _user_agent() -> str:
    """Return a user agent string for use in http requests."""
    import platform

    from napari import __version__
    from napari.utils import misc

    if misc.running_as_constructor_app():
        env = 'constructor'
    elif misc.in_jupyter():
        env = 'jupyter'
    elif misc.in_ipython():
        env = 'ipython'
    else:
        env = 'python'

    parts = [
        ('napari', __version__),
        ('runtime', env),
        (platform.python_implementation(), platform.python_version()),
        (platform.system(), platform.release()),
    ]
    return ' '.join(f'{k}/{v}' for k, v in parts)


class _ShortSummaryDict(TypedDict):
    """Objects returned at https://npe2api.vercel.app/api/extended_summary ."""

    name: NotRequired[PyPIname]
    version: str
    summary: str
    author: str
    license: str
    home_page: str


class SummaryDict(_ShortSummaryDict):
    display_name: NotRequired[str]
    pypi_versions: NotRequired[list[str]]
    conda_versions: NotRequired[list[str]]


@lru_cache
def plugin_summaries() -> list[SummaryDict]:
    """Return PackageMetadata object for all known napari plugins."""
    url = 'https://npe2api.vercel.app/api/extended_summary'
    with urlopen(Request(url, headers={'User-Agent': _user_agent()})) as resp:
        return json.load(resp)


@lru_cache
def conda_map() -> dict[PyPIname, str | None]:
    """Return map of PyPI package name to conda_channel/package_name ()."""
    url = 'https://npe2api.vercel.app/api/conda'
    with urlopen(Request(url, headers={'User-Agent': _user_agent()})) as resp:
        return json.load(resp)


def iter_napari_plugin_info() -> Iterator[tuple[PackageMetadata, bool, dict]]:
    """Iterator of tuples of ProjectInfo, Conda availability for all napari plugins."""
    try:
        with ThreadPoolExecutor() as executor:
            data = executor.submit(plugin_summaries)
            _conda = executor.submit(conda_map)
        conda = _conda.result()
        data_set = data.result()
    except (HTTPError, URLError):
        show_warning(
            'Plugin manager: There seems to be an issue with network connectivity. '
            'Remote plugins cannot be installed, only local ones.\n'
        )
        return

    conda_set = {normalized_name(x) for x in conda}
    for info in data_set:
        info_copy: dict[str, str | list[str]] = dict(info)
        info_copy.pop('display_name', None)
        pypi_versions = info_copy.pop('pypi_versions')
        conda_versions = info_copy.pop('conda_versions')
        info_ = cast('_ShortSummaryDict', info_copy)
        home_page = get_homepage_url(info_copy)
        # this URL is used for the widget, so we have to replace the home_page
        # link here as well as returning it in extra_info
        info_['home_page'] = home_page
        # TODO: use this better.
        # this would require changing the api that qt_plugin_dialog expects to
        # receive

        # TODO: once the new version of npe2 is out, this can be refactored
        # to all the metadata includes the conda and pypi versions.
        extra_info = {
            'home_page': home_page,
            'display_name': info.get('display_name', ''),
            'pypi_versions': pypi_versions,
            'conda_versions': conda_versions,
        }
        info_['name'] = normalized_name(info_['name'])
        meta = PackageMetadata(**info_)

        yield meta, (info_['name'] in conda_set), extra_info


def cache_clear() -> None:
    """Clear the cache for all cached functions in this module."""
    plugin_summaries.cache_clear()
    conda_map.cache_clear()
    _user_agent.cache_clear()
