"""fleet — tools and skills for running a fleet of long-lived Claude Code sessions.

The one place the version is written. `scripts/release.sh` rewrites this line,
`docs/source/conf.py` imports it, and `tests/test_version.py` checks it against
the newest entry in CHANGELOG.md — a version bumped in one place and not the
other is the failure that looks like nothing at all.

There is no package metadata to read it from: fleet is not installed with pip,
because the tools are the recovery path after a disk loss and a recovery tool
that needs a package installed first fails exactly when it is needed.
"""

__version__ = "0.1.1"
