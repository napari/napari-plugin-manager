from urllib.error import HTTPError, URLError

from flaky import flaky

from napari_plugin_manager.npe2api import (
    _user_agent,
    cache_clear,
    conda_map,
    iter_napari_plugin_info,
    plugin_summaries,
)


def test_user_agent():
    assert _user_agent()


@flaky(max_runs=4, min_passes=2)
def test_plugin_summaries():
    keys = [
        'name',
        'normalized_name',
        'version',
        'display_name',
        'summary',
        'author',
        'license',
        'home_page',
        'pypi_versions',
        'conda_versions',
        'project_url',
    ]
    try:
        data = plugin_summaries()
        test_data = dict(data[0])
        for key in keys:
            assert key in test_data
            test_data.pop(key)

        assert not test_data
    except (HTTPError, URLError):
        pass


def test_conda_map():
    pkgs = ['napari-svg']
    try:
        data = conda_map()
        for pkg in pkgs:
            assert pkg in data
    except (HTTPError, URLError):
        pass


def test_iter_napari_plugin_info():
    data = iter_napari_plugin_info()
    for item in data:
        assert item


def test_clear_cache():
    assert _user_agent.cache_info().hits >= 1
    cache_clear()
    assert _user_agent.cache_info().hits == 0
