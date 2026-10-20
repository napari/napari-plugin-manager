import sys
from unittest.mock import patch

import pytest

from napari_plugin_manager.utils import get_homepage_url, is_conda_package


@pytest.mark.parametrize(
    ('pkg_name', 'expected'),
    [
        ('some-package', True),
        ('some-other-package', False),
        ('some-package-other', False),
        ('other-some-package', False),
        ('package', False),
        ('some', False),
    ],
)
def test_is_conda_package(pkg_name, expected, tmp_path):
    mocked_conda_meta = tmp_path / 'conda-meta'
    mocked_conda_meta.mkdir()
    mocked_package = mocked_conda_meta / 'some-package-0.1.1-0.json'
    mocked_package.touch()

    with patch.object(sys, 'prefix', tmp_path):
        assert is_conda_package(pkg_name) is expected


def test_get_homepage_url():
    assert get_homepage_url({}) == ''

    meta = {
        'Home-page': None,
    }
    assert get_homepage_url(meta) == ''

    meta['Home-page'] = 'http://example.com'
    assert get_homepage_url(meta) == 'http://example.com'

    meta['Project-URL'] = ['Home Page, http://projurl.com']
    assert get_homepage_url(meta) == 'http://example.com'

    meta['home_page'] = meta.pop('Home-page')
    meta['project_url'] = meta.pop('Project-URL')
    assert get_homepage_url(meta) == 'http://example.com'

    meta['home_page'] = None
    assert get_homepage_url(meta) == 'http://projurl.com'

    meta['project_url'] = ['Source Code, http://projurl.com']
    assert get_homepage_url(meta) == 'http://projurl.com'

    meta['project_url'] = ['Source, http://projurl.com']
    assert get_homepage_url(meta) == 'http://projurl.com'

    meta['project_url'] = None
    assert get_homepage_url(meta) == ''
