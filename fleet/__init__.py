"""fleet — tools and skills for running a fleet of long-lived Claude Code sessions.

The one place the version is written. `scripts/release.sh` rewrites this line,
`docs/source/conf.py` imports it, and `tests/test_version.py` checks it against
the newest entry in CHANGELOG.md — a version bumped in one place and not the
other is the failure that looks like nothing at all.

There is no package metadata to read it from: fleet is not installed with pip,
because the tools are the recovery path after a disk loss and a recovery tool
that needs a package installed first fails exactly when it is needed.
"""

__version__ = "0.2.0"


def version_flag(argv=None, prog=None):
    """Answer `--version` and exit, before the caller parses anything else.

    Every tool ships from this repository at one version, so there is one number
    and one place it is written. The awkward part was never the flag: five tools
    parse `sys.argv` by hand and the rest use argparse, and `fleetwatch` now
    REFUSES an argument it does not recognise -- so a flag added per tool would be
    five different shapes and one new refusal to remember. Answering it first
    costs each tool one line and changes no exit code.

    Called before argparse deliberately: argparse's own `--version` action would
    need a separate registration in nine files, and would still leave the hand-
    rolled five out."""
    import os, sys
    argv = sys.argv[1:] if argv is None else list(argv)
    if "--version" not in argv and "-V" not in argv:
        return
    prog = prog or os.path.basename(sys.argv[0] or "fleet")
    print(f"{prog} (fleet {__version__})")
    raise SystemExit(0)
