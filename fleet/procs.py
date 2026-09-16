"""Live claude processes and process identity, read from /proc.

Shared by fleetspawn, fleetwatch, fleetretire and fleetcontext, so "is this session running"
and "is this the same process" have one answer.
"""
import os
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
