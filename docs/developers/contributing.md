# Contributing Guide

We welcome your contributions! Please see the provided steps below and never hesitate to contact us.

If you are a new user, we recommend checking out the detailed [Github Guides](https://guides.github.com).

## Setting up a development installation

In order to make changes to `napari-plugin-manager`, you will need to [fork](https://guides.github.com/activities/forking/#fork) the
[repository](https://github.com/napari/napari-plugin-manager).

If you are not familiar with `git`, we recommend reading up on [this guide](https://guides.github.com/introduction/git-handbook/#basic-git).

Clone the forked repository to your local machine and change directories:
```sh
git clone https://github.com/your-username/napari-plugin-manager.git
cd napari-plugin-manager
```

Set the `upstream` remote to the base `napari` repository:
```sh
git remote add upstream https://github.com/napari/napari-plugin-manager.git
```

Install the package in editable mode, along with all of the developer tools:
```sh
pip install -e ".[dev]"
```

We use [`pre-commit`](https://pre-commit.com) to sort imports with
[`isort`](https://github.com/timothycrosley/isort), format code with
[`black`](https://github.com/psf/black), and lint with
[`flake8`](https://github.com/PyCQA/flake8) automatically prior to each commit
as implemented in `ruff`.
To minimize test errors when submitting pull requests, please install `pre-commit`
in your environment as follows:

```sh
pre-commit install
```

Upon committing, your code will be formatted and linted according to our [`ruff`
configuration](https://github.com/napari/napari-plugin-manager/blob/main/pyproject.toml). To learn
more, see [`ruff`'s documentation](https://docs.astral.sh/ruff/).

You can also execute `pre-commit` at any moment by running the following:

```sh
pre-commit run -a
```

If you wish to tell the linter to ignore a specific line use the `# noqa`
comment along with the specific error code (e.g. `import sys  # noqa: E402`) but
please do not ignore errors lightly.

## Translations

Starting with version 0.4.7, napari codebase include internationalization
(i18n) and now offers the possibility of installing language packs, which
provide localization (l10n) enabling the user interface to be displayed in
different languages.

To learn more about the current languages that are in the process of
translation, visit the [language packs repository](https://github.com/napari/napari-language-packs).

To make your code translatable (localizable), please use the `trans` helper
provided by the napari utilities.

```python
from napari.utils.translations import trans

some_string = trans._("Localizable string")
```

To learn more, please see the [translations guide](https://napari.org/guides/stable/translations.html).

## Making changes

Create a new feature branch:

```sh
git checkout main -b your-branch-name
```

`git` will automatically detect changes to a repository.
You can view them with:

```sh
git status
```

Add and commit your changed files:
```sh
git add my-file-or-directory
git commit -m "my message"
```

## Tests

We use unit tests and integration tests to ensure that
napari-plugin-manager works as intended. Writing tests for new code is a critical part of
keeping napari-plugin-manager maintainable as it grows.

Check out the dedicated documentation on testing over at [napari.org](https://napari.org/dev/developers/testing.html) that we recommend you
read as you're working on your first contribution.

Run this command to ensure the testing dependencies are available:

```sh
pip install -e ".[testing]"
```

### Help us make sure it's you

Each commit you make must have a [GitHub-registered email](https://github.com/settings/emails)
as the `author`. You can read more [here](https://help.github.com/en/github/setting-up-and-managing-your-github-user-account/setting-your-commit-email-address).

To set it, use `git config --global user.email your-address@example.com`.

## Keeping your branches up-to-date

Switch to the `main` branch:
```sh
git checkout main
```

Fetch changes and update `main`:
```sh
git pull upstream main --tags
```

This is shorthand for:
```sh
git fetch upstream main --tags
git merge upstream/main
```

Update your other branches:
```sh
git checkout your-branch-name
git merge main
```

## Sharing your changes

Update your remote branch:
```sh
git push -u origin your-branch-name
```

You can then make a [pull-request](https://guides.github.com/activities/forking/#making-a-pull-request) to `napari-plugin-manager`'s `main` branch.

## Building the docs

First, make sure the documentation dependencies are up-to-date:

```sh
pip install -e ".[docs]"
```

Then, from the project root
```sh
make docs
```

The docs will be built at `docs/_build/html`. You can see them in your browser by running

```sh
make serve
```

and opening a new tab for `http://localhost:8000`.

Most web browsers will also allow you to preview HTML pages directly.
Try entering `file:///absolute/path/to/napari-plugin-manager/docs/_build/html/index.html` in your address bar.

## Code of conduct

`napari` has a [Code of Conduct](https://napari.org/stable/community/code_of_conduct.html) that should be honored by everyone who participates in the `napari` community, including `napari-plugin-manager`.

## Questions, comments, and feedback

If you have questions, comments, suggestions for improvement, or any other inquiries
regarding the project, feel free to open an [issue](https://github.com/napari/napari-plugin-manager/issues).

Issues and pull-requests are written in [Markdown](https://guides.github.com/features/mastering-markdown/#what). You can find a comprehensive guide [here](https://guides.github.com/features/mastering-markdown/#syntax).
