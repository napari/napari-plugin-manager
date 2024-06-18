import re
import sys
from pathlib import Path
from typing import Optional


def is_conda_package(pkg: str, prefix: Optional[str] = None) -> bool:
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
        re.match(rf"{pkg}-[^-]+-[^-]+.json", p.name)
        for p in conda_meta_dir.glob(f"{pkg}-*-*.json")
    )
