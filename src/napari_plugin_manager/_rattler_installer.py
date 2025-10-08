"""
An internal CLI interface to py-rattler installation routines.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import rattler

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Literal

log = logging.getLogger(__name__)


def cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='rattler-for-napari')
    p.add_argument(
        'specs',
        nargs='+',
        help='Packages to handle',
    )
    p.add_argument(
        '--action',
        choices=('install', 'remove', 'update', 'uninstall', 'upgrade'),
        help='Action to perform: install (also creates), remove/uninstall, update/upgrade.',
    )
    p.add_argument(
        '-p',
        '--prefix',
        type=Path,
        required=True,
        help='Target prefix',
    )
    p.add_argument(
        '--constraint',
        dest='constraints',
        action='append',
        help='Solver constraints, as a spec',
    )
    p.add_argument(
        '-c',
        '--channel',
        dest='channels',
        action='append',
        help='Conda channel(s) to pull from.',
    )
    p.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help='Increase amount of output',
    )
    p.add_argument(
        '--dry-run',
        action='store_true',
        help='Only solve environment, do not modify.',
    )
    return p


def _installed(prefix: Path) -> list[rattler.prefix.PrefixRecord]:
    if not (prefix / 'conda-meta' / 'history').is_file():
        return []
    return [
        rattler.prefix.PrefixRecord.from_path(path)
        for path in prefix.glob('conda-meta/*-*-*.json')
    ]


async def solve_records(
    action: Literal['install', 'update', 'upgrade', 'remove', 'uninstall'],
    specs: Iterable[rattler.MatchSpec],
    channels: Iterable[str] = (),
    constraints: Iterable[rattler.MatchSpec | str] = (),
    installed: Iterable[rattler.prefix.PrefixRecord] = (),
) -> tuple[list[rattler.RepoDataRecord], list[rattler.MatchSpec]]:
    specs = list(specs)
    names = {spec.name for spec in specs}
    installed = list(installed)
    locked = installed.copy()
    channels = channels or ('conda-forge',)
    constraints = constraints or []
    if action in ('remove', 'uninstall'):
        specs = [
            record.requested_spec
            for record in installed
            if record.requested_spec and record.name not in names
        ]
        constraints.extend([f'{name.source}<0' for name in names])
    elif action in ('install', 'update', 'upgrade'):
        for record in installed:
            if record.requested_spec and record.name not in names:
                specs.append(record.requested_spec)
        if action in ('update', 'upgrade'):
            locked = [record for record in locked if record.name not in names]
    else:
        raise ValueError("'action' must be 'install', 'update', or 'remove'.")
    for channel in channels:
        log.info('Channel: %s', channel)
    for spec in specs:
        log.info('Spec: %s', spec)
    for constraint in constraints:
        log.info('Constraint: %s', constraint)

    return await rattler.solve(
        channels,
        specs,
        virtual_packages=rattler.VirtualPackage.detect(),
        timeout=timedelta(seconds=90),
        constraints=constraints,
        locked_packages=locked,
    ), specs


def validate_solution(records: Iterable[rattler.RepoDataRecord]):
    """
    Here we can apply some logic to make sure the application is ok with it
    (e.g. no napari updates)
    """


async def main(argv: Iterable[str] | None = None) -> int:
    args = cli().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING
    )

    specs = [rattler.MatchSpec(spec) for spec in args.specs]
    installed = _installed(args.prefix)
    installed_names = {record.name.normalized for record in installed}
    if args.action in ('remove', 'update'):
        notpresent = []
        for spec in specs:
            if spec.name.normalized not in installed_names:
                notpresent.append(str(spec))
        if notpresent:
            raise argparse.ArgumentError(
                None,
                message='Some packages are not present in '
                f'the environment and cannot be {args.action}d: {", ".join(notpresent)}',
            )
    records, requested = await solve_records(
        args.action,
        specs,
        args.channels,
        args.constraints,
        installed=installed,
    )
    validate_solution(records)
    for record in records:
        log.info('Solution: %s', record)

    if args.dry_run:
        log.info('Dry run. Exiting.')
        return 0

    log.info('Applying solution to %s', args.prefix.resolve())
    await rattler.install(
        records=records,
        target_prefix=args.prefix,
        show_progress=args.verbose,
    )

    # Patch 'requested_spec' in 'conda-meta/*.json'
    # Workaround for https://github.com/conda/rattler/issues/1595
    for spec in requested:
        for conda_meta_json in args.prefix.glob(
            f'conda-meta/{spec.name.normalized}-*-*.json'
        ):
            name, _, _ = conda_meta_json.stem.rsplit('-', 2)
            if name.lower() in (
                spec.name.source.lower(),
                spec.name.normalized,
            ):
                data = json.loads(conda_meta_json.read_text())
                data['requested_spec'] = str(spec)
                conda_meta_json.write_text(json.dumps(data, indent=2))
                break

    log.info('Done.')

    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
