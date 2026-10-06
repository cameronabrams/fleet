"""Which Claude Code binary is installed, and which one a running session is on.

Two facts, derived one way. `fleetupgrade` decides staleness from them,
`fleetsnap` records the installed one in the manifest, and `fleetboard` shows
both -- and before this module each tool read them for itself.

They had already drifted. `fleetupgrade` matched `versions/<v>` with a regex;
`fleetsnap` took `os.path.basename` of the resolved symlink. Today those agree,
because the version happens to be the last component of
`~/.local/share/claude/versions/2.1.292`. They agree for that reason alone: a
layout that put the binary one level deeper (`versions/2.1.292/bin/claude`) would
leave the regex right and make `fleetsnap` record `installed_claude: "claude"` --
in the manifest a restore is rebuilt from, where it is read as a version number
and nothing would question it.

**Unknown is returned as None, never as a guess.** A version this cannot parse is
a layout this module has not seen, and a wrong version number is worse than no
version number in both directions: it marks a stale session current, and it marks
a current fleet stale.
"""
import os
import re

# `~/.local/bin/claude` is the installer's symlink into the versioned store. It is
# resolved rather than executed: `claude --version` would be the obvious reading
# and it is the wrong one here, because it runs whatever is on PATH, costs a
# process launch per call, and cannot answer the question for a session that is
# running a DIFFERENT binary from the one now installed -- which is the entire
# question `fleetupgrade` exists to ask.
CLAUDE = os.path.expanduser("~/.local/bin/claude")

# The version is the component after `versions/`, not the last component.
_VERSION = re.compile(r"versions/([0-9][0-9A-Za-z.\-]*)")


def from_path(path):
    """The version named in a resolved binary path, or None.

    Pure, so the tests do not need a Claude Code installation to pin the layouts
    this understands -- and the layouts it does not.
    """
    if not path:
        return None
    m = _VERSION.search(path)
    return m.group(1) if m else None


def installed(claude=CLAUDE):
    """The version `claude` would start now, or None if it cannot be read.

    This is "the most recent available version" as a session experiences it: the
    one it gets on its next restart. It is deliberately NOT the newest release
    published upstream -- that needs the network, and every caller here is either
    a recovery tool or a board whose whole contract is local sources.
    """
    try:
        return from_path(os.path.realpath(claude))
    except OSError:
        return None


def of_pid(pid):
    """The version a running process is on, or None.

    Read from `/proc/<pid>/exe`, which is the binary actually executing -- not
    what the session was launched with, and not what is installed now. A session
    started before an upgrade keeps running the old binary with no outward sign,
    which is the fact this whole module exists to surface.
    """
    if not pid:
        return None
    try:
        return from_path(os.readlink("/proc/%s/exe" % pid))
    except OSError:
        return None


def is_stale(session_version, installed_version):
    """True only when both are known AND they differ.

    An unknown version is not stale and not current; it is unknown, and a caller
    that renders this as a boolean must render None as `?` rather than folding it
    into either answer. Returning False for unknown would make a board that lost
    its source look like a fleet that is fully up to date.
    """
    if not session_version or not installed_version:
        return None
    return session_version != installed_version
