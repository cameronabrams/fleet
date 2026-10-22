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


# How long a release must have been on disk before this fleet will start a
# session on it. Lives here, not in one tool, because every launcher needs the
# same answer: `fleetupgrade` to decide who may roll, `fleetspawn` and
# `fleetrestore` to decide what to launch. A second copy would be a second policy.
SOAK_HOURS = 24


def target(hours=None, claude=None):
    """(version, path) the fleet should be running, or (None, None).

    **Not the newest version -- the newest one that has soaked.** Releases land
    here about every 25 hours (median gap 25.2 h, measured 2026-10-17) and a gate
    reading the newest version's age was reset by each one: two fires, two days,
    zero sessions eligible, with the log filling up with clean lines that read as
    a mechanism waiting for its moment rather than one that could not open.

    This is also what "stale" must be measured against. A session correctly rolled
    to the target is BEHIND the installed version by design, every day, so
    comparing it with `installed()` would mark the whole fleet stale permanently --
    a report that is wrong whenever it is working.
    """
    return soaked(SOAK_HOURS if hours is None else hours, claude)


def _key(v):
    """Sort key for a version string. Unparseable sorts lowest, never highest: an
    oddly named file in the store must not be chosen as the newest thing there."""
    try:
        return (1, tuple(int(x) for x in v.split("-")[0].split(".")))
    except (AttributeError, ValueError):
        return (0, ())


def store(claude=None):
    """The directory the native installer keeps versions side by side in, or None.

    Derived from the resolved binary rather than hardcoded, and only accepted when
    the directory is actually named `versions`: on an npm install the binary's
    parent is `bin/`, there is no history to choose from, and the honest answer is
    that this layout has none.
    """
    try:
        d = os.path.dirname(os.path.realpath(claude or CLAUDE))
    except OSError:
        return None
    return d if os.path.basename(d) == "versions" and os.path.isdir(d) else None


def soaked(hours, claude=None, now=None):
    """(version, path) of the newest version that has been on disk for `hours`.

    (None, None) when there is no such version, which includes every npm install
    and a fresh machine with one release on it. The caller then launches plain
    `claude`: refusing to start a session because no version has soaked would be a
    far worse outcome than starting one on a fresh binary.

    **Newest by version number, among those old enough by mtime.** The two orders
    normally agree and must not be assumed to: a re-download touches the file, and
    a version that was just rewritten has not soaked whatever its number says.

    **Never newer than what `claude` resolves to.** If the installer's symlink has
    been moved back deliberately, rolling past it would overrule that choice with
    a file left on disk.
    """
    d = store(claude)
    if not d:
        return None, None
    now = time.time() if now is None else now
    cap = installed(claude, ask_binary=False)
    best = None
    for name in os.listdir(d):
        path = os.path.join(d, name)
        try:
            if (now - os.path.getmtime(path)) / 3600.0 < hours:
                continue
        except OSError:
            continue
        if _key(name)[1] == ():
            continue                       # not a version; not a candidate
        if cap and _key(name) > _key(cap):
            continue                       # newer than the installer's choice
        if best is None or _key(name) > _key(best[0]):
            best = (name, path)
    return best or (None, None)


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
_LINE = "%s  installed=%s kind=%s rolled=%s from=%s to=%s note=%s\n"

# What put a session onto a binary. The log records all of them and they are NOT
# interchangeable: only `roll` is the auto-roll acting.
#
# Added 2026-10-22, after a proposed daily cap -- "stop if `autoroll.log` already
# has a `rolled=` line dated today" -- turned out to be unimplementable against
# the log as written. Of the six `rolled=` lines then present, ONE was a roll: two
# were a restore converging the fleet, one an unpark, and two were spawns from
# testing. The cap would have blocked the roll on two days for reasons that had
# nothing to do with rolling, and worst on the day after a reboot -- exactly when
# the ladder is already stalled because a restore flattened every version.
KINDS = ("roll", "spawn", "unpark", "restore", "adopt")

# Lines written before `kind=` existed. A reader cannot ask them what they were,
# so it infers from the note and SAYS it is inferring -- the same read-both-then-
# drop-the-fallback shape as the `@repo` -> `@agent` rename. Delete this once no
# line without `kind=` is still being read.
_LEGACY_NOT_A_ROLL = ("spawn", "unpark", "restore")


def adoptions(state_dir):
    """Every line of the adoption log, parsed: `[{date, kind, session, note}]`.

    Unparseable lines are skipped rather than raising. This log is written by
    several tools and read to answer "has the auto-roll already acted today"; a
    reader that died on one malformed line would take the gate with it, and a
    gate that cannot be evaluated is a gate that gets bypassed.
    """
    path = os.path.join(state_dir, ADOPTION_LOG)
    out = []
    try:
        with open(path) as fh:
            lines = fh.readlines()
    except OSError:
        return out
    for ln in lines:
        m = re.match(r"(\d{4}-\d{2}-\d{2})\S*\s+(.*)", ln)
        if not m:
            continue
        day, rest = m.group(1), m.group(2)
        kind = re.search(r"\bkind=(\S+)", rest)
        rolled = re.search(r"\brolled=(\S+)", rest)
        note = re.search(r"\bnote=(.*)", rest)
        out.append({"date": day,
                    "kind": kind.group(1) if kind else None,
                    "session": rolled.group(1) if rolled else None,
                    "note": (note.group(1).strip() if note else "")})
    return out


def is_roll(rec):
    """Whether a log record is the AUTO-ROLL having acted.

    `kind=roll` when the writer said so. For a line written before that field
    existed the kind is inferred from the note and the inference is conservative
    -- a spawn, an unpark or a restore is not a roll, and anything else recording
    a session is taken as one. Conservative in the direction that SUPPRESSES a
    roll rather than permitting a second one, because the cap exists to stop the
    fleet being restarted twice in a day.
    """
    # A session must actually have been rolled. The driver writes `kind=roll`
    # on its REFUSALS too -- `rolled=none` with a note saying which gate closed --
    # and counting one of those would have the mechanism cap itself on the days
    # it decided to do nothing, which is most days.
    if not rec.get("session") or rec["session"] == "none":
        return False
    if rec.get("kind"):
        return rec["kind"] == "roll"
    first = (rec.get("note") or "").strip().split()[:1]
    return not (first and first[0].lower().strip(":,") in _LEGACY_NOT_A_ROLL)


def rolled_on(state_dir, date):
    """Sessions the auto-roll put onto a binary on `date` (a `YYYY-MM-DD` string).

    This is the computable form of "at most one roll per calendar day". The cap
    was previously implied by the SCHEDULE -- one roll per fire, one fire a day --
    which welded how often the gates are sampled to how often they may act, and
    cost up to 24 hours of latency every time a gate opened just after a fire.
    Separating them needs the cap to be a fact about the log rather than about
    the cron, and this is that fact.
    """
    return [r["session"] for r in adoptions(state_dir)
            if r["date"] == date and is_roll(r)]


def rolled_today(state_dir, now=None):
    """Sessions the auto-roll acted on today, in LOCAL time.

    Local, because "once a calendar day" is a claim about the day the human is
    living in -- a UTC boundary would let a second roll through at 20:00 EDT and
    refuse one at 19:00, for a reason nobody reading the log could see.
    """
    stamp = time.strftime("%Y-%m-%d", time.localtime(now))
    return rolled_on(state_dir, stamp)


def record_adoption(state_dir, session, to, frm, note, installed_version=None,
                    kind="adopt"):
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
                    kind if kind in KINDS else "adopt",
                    session, frm or "?", to or "?", note)
    try:
        os.makedirs(state_dir, exist_ok=True)
        with open(path, "a") as f:
            f.write(line)
    except OSError as e:
        return "could not write %s (%s)" % (path, e.strerror or e)
    return None
