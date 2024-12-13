"""
A tool-agnostic installation logic for the plugin manager.

The main object is `InstallerQueue`, a `QProcess` subclass
with the notion of a job queue. The queued jobs are represented
by a `deque` of `*InstallerTool` dataclasses that contain the
executable path, arguments and environment modifications.
Available actions for each tool are `install`, `uninstall`
and `cancel`.
"""
