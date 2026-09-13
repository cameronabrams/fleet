"""Which transcript a live session is actually writing to.

Shared by fleetsnap and fleetupgrade, because both print a `--resume` handle and
a handle that is right in one tool and wrong in the other is worse than either.
"""
import datetime, glob, os, re, subprocess, time

PROJECTS = os.path.expanduser("~/.claude/projects")
_NAME_RE = re.compile(r'"agentName"\s*:\s*"([^"]+)"')

def project_slug(cwd):
    """The directory name Claude Code gives a working directory, under both
    ~/.claude/projects and the per-user scratch root: every character other than
    [A-Za-z0-9] becomes '-'. Mapping only '/' agrees on most paths and silently
    finds nothing for a dotted one -- OBSERVED 2026-09-13, cwd ~/.local/state/fleet
    lives in -home-<user>--local-state-fleet. Dots and slashes are observed;
    other punctuation is assumed to follow the same rule."""
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)

def uuid_from_descendants(claude_pid):
    """The session uuid carried by the scratchpad path a descendant process runs
    from, or None. A scratchpad path is HANDED to a session by its environment,
    not inferred about it from outside, so it cannot belong to a different
    session -- unlike the newest file in a directory, a name in a listing or a
    pane label. Needs a live descendant: a session with no child process at the
    moment of the check yields None, and callers must fall back.

    Shared by fleetsnap and fleetupgrade: until 2026-09-13 only fleetsnap had it,
    and the two tools disagreed about the coordinator's handle."""
    seen, stack = set(), [str(claude_pid)]
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        try:
            stack += subprocess.run(["pgrep", "-P", pid], capture_output=True,
                                    text=True).stdout.split()
        except OSError:
            pass
        try:
            cmd = open(f"/proc/{pid}/cmdline", "rb").read().decode(errors="replace")
        except OSError:
            continue
        m = re.search(r"/tmp/claude-\d+/[^/\0]+/([0-9a-f-]{36})", cmd)
        if m:
            return m.group(1)
    return None

def _norm(x):
    return (x or "").replace("-", " ").strip().lower()

def agent_color(uuid):
    """The LAST agent-color record in transcript `uuid`, or None. A /clear rolls the
    transcript and does not copy the colour forward, so None is common and means
    "not set in this file", not "never set"."""
    if not uuid:
        return None
    last = None
    for f in glob.glob(f"{PROJECTS}/*/{uuid}.jsonl"):
        try:
            with open(f, errors="replace") as fh:
                for line in fh:
                    if '"agent-color"' in line:
                        m = re.search(r'"agentColor"\s*:\s*"([^"]+)"', line)
                        if m:
                            last = m.group(1)
        except OSError:
            pass
    return last

def first_timestamp(path):
    """Epoch of the first timestamped record in a transcript, or None."""
    try:
        with open(path, errors="replace") as f:
            for line in f:
                m = re.search(r'"timestamp"\s*:\s*"([^"]+)"', line)
                if m:
                    return datetime.datetime.fromisoformat(
                        m.group(1).replace("Z", "+00:00")).timestamp()
    except (OSError, ValueError):
        pass
    return None

def process_start(pid):
    """Epoch at which `pid` started, or None."""
    try:
        et = subprocess.run(["ps", "-o", "etimes=", "-p", str(pid)],
                            capture_output=True, text=True).stdout.strip()
        return time.time() - int(et)
    except (OSError, ValueError):
        return None

def cleared_successor(argv_uuid, label, pid):
    """(uuid, n_candidates) of the transcript a /clear moved this session onto, or
    (None, 0) if it has not been cleared since launch.

    `--resume <uuid>` in argv says where the process STARTED. A /clear rolls the
    session onto a new transcript file and leaves argv untouched, so argv alone
    reads "verified" for a handle that would resume the pre-clear context.
    Observed 2026-09-12 on the coordinator: argv and live transcript differed.

    A successor must (a) sit in the same project directory, (b) self-report the
    same name, (c) have its FIRST record after this process started -- a resumed
    file's first record predates the launch, a /clear's cannot -- and (d) be
    written more recently than the argv transcript. Several candidates -> newest,
    and the count is returned so the caller can say so rather than hide it."""
    old = glob.glob(f"{PROJECTS}/*/{argv_uuid}.jsonl")
    started = process_start(pid)
    if not old or not label or started is None:
        return None, 0
    old = old[0]
    cands = []
    for f in glob.glob(os.path.join(os.path.dirname(old), "*.jsonl")):
        if f == old or os.path.getmtime(f) <= os.path.getmtime(old):
            continue
        t0 = first_timestamp(f)
        if t0 is None or t0 < started:
            continue
        try:
            names = _NAME_RE.findall(open(f, errors="replace").read())
        except OSError:
            continue
        if names and _norm(names[-1]) == _norm(label):
            cands.append(f)
    if not cands:
        return None, 0
    return os.path.basename(max(cands, key=os.path.getmtime))[:-6], len(cands)
