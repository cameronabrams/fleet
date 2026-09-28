"""Live claude processes and process identity, read from /proc.

Shared by fleetspawn, fleetwatch, fleetretire and fleetcontext, so "is this session running"
and "is this the same process" have one answer.
"""
import json
import os
import re
import shutil
import subprocess

def claude_procs():
    """(pid, cwd, argv) for every live claude process, from /proc -- not from any
    record, and not only from tmux: a session outside tmux still takes a name."""
    out = []
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            argv = open(f"/proc/{d}/cmdline", "rb").read().decode(errors="replace").split("\0")
            cwd = os.readlink(f"/proc/{d}/cwd")
        except OSError:
            continue
        if argv and os.path.basename(argv[0]) == "claude":
            out.append((int(d), cwd, [x for x in argv if x]))
    return out

def named(argv, name):
    return any(a == "--name" and i + 1 < len(argv) and argv[i + 1] == name
               for i, a in enumerate(argv))

def alive(pid, want_start=None):
    """Live means RUNNING, AND still the same process we registered.

    `kill -0` SUCCEEDS on a zombie -- a process that has exited but whose parent
    has not wait()ed. So a SIGKILLed watcher awaiting reaping reads ALIVE, and its
    job reads WATCHED while nothing is watching: the fail-toward-fine direction
    this registry exists to eliminate.

    Reproduced 2026-09-12: a forked child whose parent
    never waits shows /proc/<pid>/stat field 3 == 'Z' while `kill -0` returns
    success. Rare in practice -- the harness reaps promptly and orphans reparent
    to a reaper -- but it bites when the watcher's parent is itself stuck, which
    is exactly when you most want the alarm.

    And a pid is not an identity: the kernel reuses them (pid_max 4194304 on the
    host measured, 2.6-5.9/s -> wrap in 8-19 days), so an uncleared registration is
    eventually GUARANTEED to name an unrelated live process, which reads healthy.
    starttime alone is not an identity either -- 10 ms ticks, and two back-to-back
    processes collided on it in test. The PAIR (pid, starttime) is sound: a pid is
    only reused after its holder is reaped, and wrap takes days.

    So test the STATE and the IDENTITY, not addressability."""
    try:
        raw = open("/proc/%s/stat" % int(pid)).read()
        tail = raw[raw.rindex(")") + 2:].split()   # after the LAST ')': comm may contain spaces
        st, start = tail[0], tail[19]              # field 3 (state), field 22 (starttime)
    except Exception:
        return False            # no /proc entry at all -> gone
    if st == "Z":
        return False
    if want_start is not None and str(want_start) != start:
        return False            # pid reused by an unrelated process
    return True

def starttime(pid):
    """Field 22 of /proc/<pid>/stat (clock ticks since boot), or None."""
    try:
        raw = open("/proc/%s/stat" % int(pid)).read()
        return raw[raw.rindex(")") + 2:].split()[19]
    except (OSError, ValueError, IndexError):
        return None

def proc_cwd(pid):
    """The working directory of `pid`, or None.

    The authority on where a session runs. tmux's `pane_current_path` is not: it
    follows whatever process the pane is running, so a `cd` in one of the
    session's own shell calls moves it -- OBSERVED 2026-09-18, when a restart
    command was printed with the wrong directory, which would have resumed
    nothing."""
    try:
        return os.readlink("/proc/%s/cwd" % int(pid))
    except (OSError, ValueError):
        return None

def children(pid):
    """Pids of the direct children of `pid`."""
    try:
        out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout
    except OSError:
        return []
    return [int(x) for x in out.split()]

def ppid(pid):
    """The parent pid of `pid`, or None."""
    try:
        raw = open("/proc/%d/stat" % pid).read()
        return int(raw[raw.rindex(")") + 2:].split()[1])
    except (OSError, ValueError, IndexError):
        return None

def ancestors(pid):
    """The set of ancestor pids of `pid`."""
    out = set()
    while pid and pid > 1 and len(out) < 64:
        pid = ppid(pid)
        if pid:
            out.add(pid)
    return out

# ---- which Claude Code version a binary, a process and the machine carry ----
#
# Two install layouts. The native installer keeps versions side by side under
# `.../versions/<v>/...`, so the path names the version. The npm install puts one
# `claude.exe` under `node_modules/@anthropic-ai/claude-code/bin/` and upgrades it
# IN PLACE, so only the package.json beside it says. OBSERVED 2026-09-28: on an
# npm-installed machine the manifest read `claude.exe` for every session and
# `claude` for the install, and the "every version matches" check could not fail.

_NATIVE_VER = re.compile(r"versions/([0-9][0-9A-Za-z.\-]*)")
_PKG = "@anthropic-ai/claude-code"

def version_of_binary(path):
    """The Claude Code version of the binary at `path`, or None.

    Native layout: from the path. npm layout: from the package.json of the
    package the binary sits in -- and only that package's, so a stray
    package.json higher up cannot pass as a version. A path that says neither
    is None, never its basename: `claude.exe` is not a version."""
    if not path:
        return None
    m = _NATIVE_VER.search(path)
    if m:
        return m.group(1)
    d = os.path.dirname(os.path.realpath(path))
    for _ in range(3):
        pj = os.path.join(d, "package.json")
        if os.path.isfile(pj):
            try:
                with open(pj) as f:
                    j = json.load(f)
            except (OSError, ValueError):
                j = {}
            return j.get("version") if j.get("name") == _PKG else None
        d = os.path.dirname(d)
    return None

def proc_version(pid):
    """The version of the binary `pid` is running, or None.

    A ` (deleted)` exe means the binary was replaced in place since launch (npm
    upgrades do this; native installs keep versions side by side). Then the
    package.json describes the NEW binary, and reporting it would make a
    straggler read as already upgraded -- the one thing an upgrade roll must not
    get wrong. So it reads None, and the caller may fall back to what the
    process itself wrote (fleet.transcripts.last_version)."""
    try:
        exe = os.readlink("/proc/%s/exe" % int(pid))
    except (OSError, ValueError):
        return None
    m = _NATIVE_VER.search(exe)
    if m:
        return m.group(1)
    if exe.endswith(" (deleted)"):
        return None
    return version_of_binary(exe)

def installed_version():
    """The version the next launch would run: the `claude` on PATH, else the
    native default path. Read from the layout first; when the layout says
    nothing, ask the binary (`claude --version`). None when nothing is installed."""
    for cand in (shutil.which("claude"), os.path.expanduser("~/.local/bin/claude")):
        if not cand or not os.path.exists(cand):
            continue
        v = version_of_binary(os.path.realpath(cand))
        if v:
            return v
        try:
            out = subprocess.run([cand, "--version"], capture_output=True, text=True,
                                 timeout=20).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        m = re.match(r"\s*(\d+\.\d+\.\d+\S*)", out)
        if m:
            return m.group(1)
    return None
