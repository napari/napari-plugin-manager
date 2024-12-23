# Release Procedure

Here you can find some information about how to trigger a new release over PyPI and subsequent `conda-forge` update.

## PyPI

To release on PyPI you will need to create a new tag. To do so you can:

* Create a [new GitHub release](https://github.com/napari/napari-plugin-manager/releases/new)
* Use over the new release GitHub page the `Choose a tag` dropdown to create a new tag (it should be something like `vX.Y.Z` incrementing the major, minor or patch number as required).
* Once the tag is defined you should be able to click `Generate release notes`.
* Put as release title the tag that was created (`vX.Y.Z`).
* Publish the release, check that the deploy step was run successfully and that the new version is available at [PyPI](https://pypi.org/project/napari-plugin-manager/#history)

## conda-forge

To update the `conda-forge` package you will need to update the [`napari-plugin-manager` feedstock](https://github.com/conda-forge/napari-plugin-manager-feedstock). **If a new version is already available from PyPI**, you can either wait for the automated PR or trigger one manually:

* Create an issue over the feedstock with the title: [`@conda-forge-admin, please update version`](https://conda-forge.org/docs/maintainer/infrastructure/#conda-forge-admin-please-update-version)
* Tweak the generated PR if necessary (dependencies changes for example).
* Merge the generated PR.
