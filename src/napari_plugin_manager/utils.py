import re
import string
import sys
from pathlib import Path


def is_conda_package(pkg: str, prefix: str | None = None) -> bool:
    """Determines if plugin was installed through conda.

    Returns
    -------
    bool
        ``True` if a conda package, ``False`` if not.
    """
    # Installed conda packages within a conda installation and environment can
    # be identified as files with the template ``<package-name>-<version>-<build-string>.json``
    # saved within a ``conda-meta`` folder within the given environment of interest.
    conda_meta_dir = Path(prefix or sys.prefix) / 'conda-meta'
    return any(
        re.match(rf'{pkg}-[^-]+-[^-]+.json', p.name)
        for p in conda_meta_dir.glob(f'{pkg}-*-*.json')
    )


def normalize_label(label: str) -> str:
    """Normalize project URL label.

    Code reproduced from:
    https://packaging.python.org/en/latest/specifications/well-known-project-urls/#label-normalization
    """
    chars_to_remove = string.punctuation + string.whitespace
    removal_map = str.maketrans('', '', chars_to_remove)
    return label.translate(removal_map).lower()


def get_homepage_url(metadata: dict[str, str | list[str] | None]) -> str:
    """Get URL for package homepage, if available.

    Checks metadata first for `Home-page` field before
    looking for `Project-URL` 'homepage' label and finally
    'source'/'sourcecode' label.

    Parameters
    ----------
    metadata : dict[str, str | list[str] | None]
        Package metadata information.

    Returns
    -------
    str
        Returns homepage URL if present, otherwise empty string.
    """
    if not len(metadata):
        return ''

    homepage = metadata.get('Home-page', '') or metadata.get('home_page', '')
    if isinstance(homepage, str) and len(homepage):
        return homepage

    urls = {}
    project_urls = metadata.get('Project-URL', []) or metadata.get(
        'project_url', []
    )
    if project_urls is None:
        return ''

    for url_info in project_urls:
        label, url = url_info.split(', ')
        urls[normalize_label(label)] = url

    homepage = (
        urls.get('homepage', '')
        or urls.get('source', '')
        or urls.get('sourcecode', '')
    )
    return homepage
