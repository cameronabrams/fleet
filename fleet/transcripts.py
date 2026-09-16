"""Which transcript a live session is actually writing to.

Shared by fleetsnap and fleetupgrade, because both print a `--resume` handle and
a handle that is right in one tool and wrong in the other is worse than either.
"""
import datetime, glob, json, os, re, subprocess, time

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

def _epoch(ts):
    try:
        return datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None

def context_stats(uuid):
    """How much context session `uuid` carries now, from its own transcript, or None.

    `tokens` is the last main-thread assistant turn's input + cache_read +
    cache_creation: what the model was sent on that turn. A compaction writes a
    `system` record with subtype `compact_boundary` into the SAME file, carrying
    `compactMetadata` {preTokens, postTokens, trigger} (OBSERVED on manual /compact,
    2026-09-02); until the next assistant turn, postTokens is the size. `turns` counts
    `turn_duration` records since the last boundary -- None when the file has none
    at all, since older binaries did not write them."""
    path = next(iter(glob.glob(f"{PROJECTS}/*/{uuid}.jsonl")), None) if uuid else None
    if not path:
        return None
    out = {"path": path, "tokens": None, "compactions": 0, "last_compact": None,
           "turns": 0, "since": first_timestamp(path), "mtime": None}
    any_turns = False
    try:
        out["mtime"] = os.path.getmtime(path)
        with open(path, errors="replace") as fh:
            for line in fh:
                if not ('"compact_boundary"' in line or '"turn_duration"' in line
                        or ('"assistant"' in line and '"usage"' in line)):
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                kind, sub = r.get("type"), r.get("subtype")
                if kind == "system" and sub == "compact_boundary":
                    meta = r.get("compactMetadata") or {}
                    out["compactions"] += 1
                    out["last_compact"] = {"at": _epoch(r.get("timestamp")),
                                           "pre": meta.get("preTokens"),
                                           "post": meta.get("postTokens"),
                                           "trigger": meta.get("trigger")}
                    out["since"] = out["last_compact"]["at"]
                    out["tokens"] = meta.get("postTokens")
                    out["turns"] = 0
                elif kind == "system" and sub == "turn_duration":
                    any_turns = True
                    out["turns"] += 1
                elif kind == "assistant" and not r.get("isSidechain"):
                    msg = r.get("message")
                    u = msg.get("usage") if isinstance(msg, dict) else None
                    if isinstance(u, dict):
                        n = sum(int(u.get(k) or 0) for k in (
                            "input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
                        if n:                      # a synthetic message carries zeros
                            out["tokens"] = n
    except OSError:
        return None
    if not any_turns:
        out["turns"] = None
    return out

def compactions(uuid):
    """The compact_boundary records in transcript `uuid`, oldest first: [dict]."""
    found = []
    for f in glob.glob(f"{PROJECTS}/*/{uuid}.jsonl") if uuid else []:
        try:
            with open(f, errors="replace") as fh:
                for line in fh:
                    if '"compact_boundary"' not in line:
                        continue
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if r.get("type") == "system" and r.get("subtype") == "compact_boundary":
                        meta = r.get("compactMetadata") or {}
                        found.append({"uuid": r.get("uuid"), "at": _epoch(r.get("timestamp")),
                                      "pre": meta.get("preTokens"), "post": meta.get("postTokens")})
        except OSError:
            pass
    return found

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

def newest_transcript(cwd, label=None):
    """Prefer a transcript that identifies itself as `label`; fall back to newest."""
    key = project_slug(cwd)
    files = sorted(glob.glob(f"{PROJECTS}/{key}/*.jsonl"),
                   key=os.path.getmtime, reverse=True)
    if not files:
        return None, "no transcript found"
    # Two independent self-reports, both scanned over the WHOLE file:
    #
    #   agentName  - written by `--name` and by `/rename`. AUTHORITATIVE and
    #                always present. /rename writes it MID-file, so take the
    #                LAST, not the first: an earlier one is a superseded name.
    #   "This session is X [ref]" - only appears once the session has called
    #                ListAgents. A new session has none, which is why a fresh
    #                or freshly-renamed session used to fall through to
    #                "corroborated ... (no self-report)" despite carrying a
    #                perfectly good agentName. Observed 2026-09-10: a session
    #                renamed twice had 0 of the ListAgents marker, 3 agentName
    #                records.
    self_re = re.compile(r"This session is (\S+) \[[0-9a-f]{6}\]")
    name_re = re.compile(r'"agentName"\s*:\s*"([^"]+)"')
    norm = lambda x: (x or "").replace("-", " ").strip().lower()
    found = {}
    for f in files:
        try:
            body = open(f, errors="replace").read()
        except OSError:
            continue
        names = name_re.findall(body) or self_re.findall(body)
        if not names:
            continue
        last = names[-1]
        found[f] = last
        # No alias table: a transcript's LAST self-reported name is its current name,
        # because `agentName` follows `/rename`. The table this replaced was
        # hand-synced across two tools, had drifted, and was verified unnecessary
        # 2026-09-12 -- identical manifest with it removed, fresh-launch path included.
        resolved = last
        if label and norm(resolved) == norm(label):
            how = "verified: transcript self-reports this name"
            return os.path.basename(f)[:-6], how
    if found:
        f = max(found, key=os.path.getmtime)
        return (os.path.basename(f)[:-6],
                f"UNVERIFIED: newest self-reports as {found[f]!r}, label is {label!r}")
    f = files[0]
    try:
        peer = "cross-session-message" in open(f, errors="replace").read()
    except OSError:
        peer = False
    if peer:
        return (os.path.basename(f)[:-6],
                "corroborated: newest in cwd and carries peer traffic (no self-report)")
    return os.path.basename(f)[:-6], "UNVERIFIED: no self-report in any transcript"

def resume_handle(proc, cwd, label):
    """(uuid, how) for the transcript `claude --resume` should reopen."""
    if proc["resume_uuid"]:
        succ, n = cleared_successor(proc["resume_uuid"], label, proc["pid"])
        if succ:
            extra = f"; {n} candidates, newest taken" if n > 1 else ""
            return succ, (f"verified: /clear since launch -- argv {proc['resume_uuid'][:8]} "
                          f"superseded by a transcript that self-reports this name and "
                          f"began after the process started{extra}")
        return proc["resume_uuid"], "verified: --resume in process argv, no /clear since launch"
    u = uuid_from_descendants(proc["pid"])
    if u:
        return u, "verified: session's own scratchpad path, via a child process"
    return newest_transcript(cwd, label)

def last_agent_name(uuid):
    """The last agent-name record in transcript `uuid`, or None."""
    last = None
    for f in glob.glob(f"{PROJECTS}/*/{uuid}.jsonl") if uuid else []:
        try:
            with open(f, errors="replace") as fh:
                for line in fh:
                    if '"agent-name"' in line:
                        found = _NAME_RE.findall(line)
                        if found:
                            last = found[-1]
        except OSError:
            pass
    return last

def session_name(pid, cwd, argv):
    """(name, uuid, how) for a live claude process: the name it answers to NOW.

    `--name` in argv is the name it was LAUNCHED with. `/rename` writes a new
    agent-name record and leaves argv alone, so a tool matching argv cannot find
    a renamed session under its real name -- OBSERVED 2026-09-15, fleetretire
    reported a live, renamed session as not running. The transcript's last
    agent-name record wins; argv is the fallback when no transcript resolves."""
    launched = next((argv[i + 1] for i, x in enumerate(argv[:-1]) if x == "--name"), None)
    resume = next((argv[i + 1] for i, x in enumerate(argv[:-1]) if x == "--resume"), None)
    uuid, how = resume_handle({"resume_uuid": resume, "pid": pid}, cwd, launched)
    current = last_agent_name(uuid)
    if current and current != launched:
        # A /clear after the rename rolled to a successor that self-reports the NEW
        # name, which the lookup keyed on the launch name could not see.
        again, how2 = resume_handle({"resume_uuid": resume, "pid": pid}, cwd, current)
        if again and again != uuid and last_agent_name(again) == current:
            uuid, how = again, how2
        # keep `how` first: callers test it for "verified"
        return current, uuid, f"{how}; renamed since launch (--name {launched})"
    return launched or current, uuid, how
