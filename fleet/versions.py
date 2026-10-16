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

**There are two install layouts, and only one of them names the version in the
path.** The native installer keeps versions side by side under
`.../versions/<v>/...`. The npm install (`npm install -g
@anthropic-ai/claude-code`) puts one binary under
`node_modules/@anthropic-ai/claude-code/bin/` and upgrades it IN PLACE, so the
path says nothing and only the `package.json` beside it does. Everything here
read the path alone until 2026-10-13: on an npm machine `fleetsnap` recorded the
installed claude as `claude`, every session's version as `claude.exe`, and
`fleetupgrade`'s staleness check could not fail. Found in `pkgyasi/fleet`, a fork
that hit it on its own machine and fixed it there first.

**Unknown is returned as None, never as a guess.** A version this cannot parse is
a layout this module has not seen, and a wrong version number is worse than no
version number in both directions: it marks a stale session current, and it marks
a current fleet stale.
"""
import json
import os
import re
import shutil
import subprocess
import time

# `~/.local/bin/claude` is the native installer's symlink into the versioned
# store, and the fallback when nothing named `claude` is on PATH. It is resolved
# rather than executed wherever the layout can answer: running the binary costs a
# process launch per call, and cannot answer the question for a session that is
# running a DIFFERENT binary from the one now installed -- which is the entire
# question `fleetupgrade` exists to ask.
CLAUDE = os.path.expanduser("~/.local/bin/claude")

# The version is the component after `versions/`, not the last component.
_VERSION = re.compile(r"versions/([0-9][0-9A-Za-z.\-]*)")

# The npm package, checked by name. The first `package.json` found decides: a
# stray one further up the tree describes something else, and its version number
# would be a confident wrong answer rather than an absent one.
_PKG = "@anthropic-ai/claude-code"

# `/proc/<pid>/exe` grows this when the binary has been replaced on disk since
# the process started, which is what an npm upgrade does.
_DELETED = " (deleted)"

# `claude --version` prints the number first. Anchored, so a line of banner text
# cannot donate a version from the middle of a sentence.
_SPOKEN = re.compile(r"\s*(\d+\.\d+\.\d+\S*)")

# `--version` costs a process launch, and `fleetboard --watch` calls `installed()`
# every redraw -- on an npm machine, where the layout never answers, that is a
# subprocess every 15 seconds for as long as the board is up. The answer is cached
# against the binary's identity, so an in-place upgrade (which changes both size
# and mtime, by construction) invalidates it and nothing else does. One `stat` per
# draw instead of one `exec`, and a board that still notices an upgrade under it.
_spoken_cache = {}


def from_path(path):
    """The version named in a resolved binary path, or None.

    Pure, and deliberately so: the tests pin the layouts this understands, and
    the layouts it does not, without needing a Claude Code installation. It knows
    only the native layout -- `of_binary` is the one that reads a package.
    """
    if not path:
        return None
    m = _VERSION.search(path)
    return m.group(1) if m else None


def of_binary(path):
    """The version of the binary at `path`, from either layout, or None.

    The path first, then the `package.json` of the package the binary sits in --
    and only that package's. A path that says neither is None, never its
    basename: `claude.exe` is not a version number, and recording it as one is
    how this went unnoticed on an npm machine for as long as it did.
    """
    if not path:
        return None
    v = from_path(path)
    if v:
        return v
    d = os.path.dirname(os.path.realpath(path))
    for _ in range(3):           # bin/ -> the package root, with one to spare
        pj = os.path.join(d, "package.json")
        if os.path.isfile(pj):
            try:
                with open(pj) as f:
                    j = json.load(f)
            except (OSError, ValueError):
                return None
            return j.get("version") if j.get("name") == _PKG else None
        parent = os.path.dirname(d)
        if parent == d:          # reached the root
            break
        d = parent
    return None


def _spoken(cand):
    """Ask the binary. Cached against its size and mtime, so an upgrade in place
    is re-read and a quiet board is not re-execed."""
    try:
        st = os.stat(cand)
        key = (cand, st.st_mtime_ns, st.st_size)
    except OSError:
        return None
    if key in _spoken_cache:
        return _spoken_cache[key]
    try:
        out = subprocess.run([cand, "--version"], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    m = _SPOKEN.match(out)
    v = m.group(1) if m else None
    _spoken_cache.clear()        # only ever one binary; do not grow across upgrades
    _spoken_cache[key] = v
    return v


def installed(claude=None, ask_binary=True):
    """The version `claude` would start now, or None if it cannot be read.

    This is "the most recent available version" as a session experiences it: the
    one it gets on its next restart. It is deliberately NOT the newest release
    published upstream -- that needs the network, and every caller here is either
    a recovery tool or a board whose whole contract is local sources.

    With no argument it takes the `claude` a new session would actually launch --
    `shutil.which`, then the native default. A path given explicitly is used as
    given, which is how the tests pin a layout without installing one.

    **`ask_binary=False` makes this pure.** The last resort is running
    `claude --version`, which is a process launch, and some callers must not do
    that: `fleetrestore` is the recovery path, where the rule is that nothing may
    need anything else to work first, and `record_adoption` writes a log line,
    which is never worth an exec. They get None where the layout is silent, and
    None is written `?`. Found by the restore end-to-end test, whose fake `claude`
    recorded a `--version` call this had no business making.
    """
    cands = [claude] if claude else [shutil.which("claude"), CLAUDE]
    for cand in cands:
        if not cand:
            continue
        v = of_binary(os.path.realpath(cand))
        if v:
            return v
        if not os.path.exists(cand):
            continue             # nothing there; the next candidate may be real
        if not ask_binary:
            return None          # the layout said nothing and we may not ask
        # It exists, so THIS is the binary a new session launches. The layout said
        # nothing about it, so ask it -- and whatever it answers is the answer,
        # including None. Falling through to the next candidate here would report
        # the version of a binary that no new session would run, which is this
        # module's one forbidden outcome: a confident number in place of an
        # absent one. The list is a search for the binary, not for a version.
        return _spoken(cand)
    return None


def of_pid(pid):
    """The version a running process is on, or None.

    Read from `/proc/<pid>/exe`, which is the binary actually executing -- not
    what the session was launched with, and not what is installed now. A session
    started before an upgrade keeps running the old binary with no outward sign,
    which is the fact this whole module exists to surface.

    A ` (deleted)` link means the binary was replaced on disk since this process
    started, which is exactly what an npm upgrade does. The `package.json` beside
    it now describes the NEW binary, so reading it would report a straggler as
    already upgraded -- the one error an upgrade roll must not make. It reads
    None instead. The native layout is unaffected: it keeps versions side by
    side, so a deleted path still names the version it named before.
    """
    if not pid:
        return None
    try:
        exe = os.readlink("/proc/%s/exe" % pid)
    except (OSError, ValueError):
        return None
    v = from_path(exe)
    if v:
        return v
    if exe.endswith(_DELETED):
        return None
    return of_binary(exe)


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


# The fleet's record of sessions moving onto a binary. It is the auto-roll's log
# because an adoption is an adoption however it happened, and a second file would
# reproduce the defect this exists to fix: on 2026-10-16 that log said
# `rolled=none` at 09:50 and a session went onto an 18-hour-old release at 09:51,
# by a route the log could not see. Two files would have said `rolled=none` twice.
ADOPTION_LOG = "autoroll.log"

# The field order `fleetupgrade`'s driver writes, so one grep reads both. Fields
# that mean nothing on this route are left out rather than filled with `-`: an
# absent key is readable as "not applicable here", a dash is readable as "nobody
# looked".
_LINE = "%s  installed=%s rolled=%s from=%s to=%s note=%s\n"


def record_adoption(state_dir, session, to, frm, note, installed_version=None):
    """Append one line saying `session` has been put onto a binary, or say why not.

    Returns None on success and a reason otherwise. **The caller must not fail on
    it.** A session that came up correctly has come up correctly; refusing to
    report that because a log could not be written would turn a bookkeeping fault
    into a fleet one, and the obvious repair -- try the launch again -- is the
    damaging one.

    `to` is what the process is OBSERVED running, not what was installed when the
    command was composed: between those two reads a human can have upgraded, and
    the question this log answers is which binary the session is on. Unknown is
    written as `?`, never omitted and never guessed.
    """
    path = os.path.join(state_dir, ADOPTION_LOG)
    # `ask_binary=False`: a log line is never worth launching a process for, and
    # one of this function's callers is the recovery path.
    line = _LINE % (time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    installed_version or installed(ask_binary=False) or "?",
                    session, frm or "?", to or "?", note)
    try:
        os.makedirs(state_dir, exist_ok=True)
        with open(path, "a") as f:
            f.write(line)
    except OSError as e:
        return "could not write %s (%s)" % (path, e.strerror or e)
    return None
