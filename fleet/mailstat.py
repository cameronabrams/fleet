"""Cross-fleet mail as a board reads it: what never reached a session, and
whether anything is still fetching.

`fleetmail inbox` answers this for someone who went and asked. Nobody asks on
the morning it matters -- the whole reason inbound mail is nudged into a pane is
that a message sitting in a repository is a message nobody reads. So the two
facts that say whether that machinery is working belong where a human is already
looking.

**The two facts are a pair, and either one alone is a check that reassures.**

*Nothing is stuck* comes from `<state>/mail-delivered.json`, which `fleetmail`
writes per message: a quarantined message was kept and never delivered, and a
message whose nudge did not land was written to a drop file that its session was
never told about. Both need a human. But that record only ever describes mail
that was FETCHED, so a fetcher that stopped produces a perfectly clean record --
which is the reassuring direction, and the reason the second fact is not
optional.

*Something is still fetching* comes from systemd, because nothing else knows.
`fleetmail fetch` writes no trace at all when there is no new mail, so the
quietest possible evidence -- an untouched delivery record -- is identical for a
mailbox with nothing in it and a timer that has been dead for a week. The timer
unit is asked instead: it records its last trigger whatever the fetch found.
Asking systemd rather than the tool also means this still reports on a DEPLOYED
copy of `fleetmail` older than this module, which is the normal arrangement --
the timer runs a pinned checkout, not the working tree.

Costs two `systemctl --user show` calls, about 25 ms together, measured
2026-11-18. That is the whole budget of this source; nothing here reads the
network, pulls the mailbox, or parses a message.

ABSENCE IS RENDERED UNKNOWN. A delivery record that cannot be read is not an
empty one, a systemctl that cannot be run is not a healthy timer, and a timer
that has never triggered is not a timer that just ran.
"""
import datetime
import json
import os
import re
import subprocess
import time

# Both unit names come from the fleet's own name, exactly as `fleetmail timer`
# generates them. One derivation, so a renamed fleet moves both ends together.
def unit(fleet, suffix):
    return "fleetmail-%s.%s" % (fleet, suffix)


def delivered_path(state):
    """Where `fleetmail` records what became of each message it fetched."""
    return os.path.join(state, "mail-delivered.json")


def read_delivered(state):
    """(records, error). `records` is None when there is a file and it could not
    be read -- which is NOT the same as no mail, and a caller must say so.

    A missing file is `{}` and no error: it is written on the first delivery, so
    a fleet that has never received anything has none, and that is the ordinary
    state of a new correspondent rather than a fault.
    """
    p = delivered_path(state)
    try:
        with open(p) as f:
            d = json.load(f)
    except FileNotFoundError:
        return {}, None
    except OSError as e:
        return None, "cannot read %s (%s)" % (p, e.strerror or e)
    except ValueError as e:
        return None, "%s is not readable JSON (%s)" % (p, e)
    if not isinstance(d, dict):
        return None, "%s does not hold an object" % p
    return d, None


def needs_human(recs):
    """[(key, what, detail)] for mail that arrived and reached nobody.

    Two outcomes, kept apart because the sentence differs. QUARANTINED is mail
    this machine refused to deliver -- an unlisted fleet, a bad address, a body
    claiming authority -- and it is held deliberately. NOT DELIVERED is mail that
    passed every check, was written to a drop file, and whose session was never
    told it was there; the news exists on disk and its reader does not know.

    `nudged is False`, not `not nudged`: a record written before that field
    existed says nothing about whether the session was told, and guessing would
    turn every old message into an alarm nothing can clear. An `acked` record is
    resolved however the nudge went -- the session can only have acked by having
    read it.
    """
    out = []
    for key in sorted(recs):
        v = recs[key] if isinstance(recs.get(key), dict) else {}
        if v.get("outcome") == "quarantined":
            what, why = "quarantined", v.get("reason") or v.get("detail")
        elif v.get("nudged") is False and not v.get("acked"):
            what, why = "not delivered", v.get("detail") or v.get("reason")
        else:
            continue
        # Dicts rather than a tuple that grows: the renderers want different
        # fields from this -- a screen wants the reason, a one-line summary wants
        # the session that was not told -- and a positional fourth element is how
        # the two come to disagree about which is which.
        out.append({"key": key, "what": what, "why": why or "",
                    "session": v.get("session"), "sender": v.get("sender")})
    return out


def _at(rec):
    """A record's arrival time as an epoch, or None if it has none this can read."""
    try:
        return datetime.datetime.fromisoformat(str(rec.get("at"))).timestamp()
    except (TypeError, ValueError):
        return None


def last_arrival(recs):
    """(epoch, sender) of the newest message fetched, or (None, None).

    Sender is a field the producer writes, not a name taken back out of the
    filename it also built: one fact, one derivation. It is absent from every
    record written before 2026-11-18, and absent is `None` here rather than a
    guess -- the time is still worth having on its own.
    """
    best, who = None, None
    for v in recs.values():
        if not isinstance(v, dict):
            continue
        t = _at(v)
        if t is not None and (best is None or t > best):
            best, who = t, v.get("sender")
    return best, who


def _systemctl(name, props, timeout=10):
    """{property: value} from `systemctl --user show`, or None if it could not
    be asked. `--timestamp=unix` so a timestamp is an epoch rather than a
    localized string this would have to parse back.
    """
    argv = ["systemctl", "--user", "show", "--timestamp=unix", name]
    for p in props:
        argv += ["-p", p]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    out = {}
    for line in r.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v.strip()
    return out


def _epoch(v):
    """`@1795012757` as an int, or None -- including for the empty value systemd
    gives a timer that has never fired, and for any format this does not know."""
    m = re.fullmatch(r"@(\d+)(?:\.\d+)?", str(v or "").strip())
    return int(m.group(1)) if m else None


# What each exit code of `fleetmail fetch` means, in the words the tool's own
# docstring uses. A bare number on a board is a number somebody has to go look
# up, and the one that matters most -- 4 -- reads as success to anyone who
# assumes the usual convention that only 1 is failure.
CODES = {2: "refused", 4: "the mailbox could not be reached",
         5: "delivered as files, but a session could not be told"}


def fetch(fleet, poll_minutes, show=None, now=None):
    """(state, info) for the scheduled fetch. State is one of:

      "ok"       -- the timer is active and triggered within the window
      "stale"    -- active, and it has not triggered for three polls
      "never"    -- active, and it has not triggered at all yet
      "failed"   -- it is running, and the last fetch exited non-zero
      "off"      -- the unit is installed and not active
      "none"     -- no timer unit on this machine; mail arrives only by hand
      "unknown"  -- systemctl could not be asked

    Staleness is checked BEFORE the exit code. A timer that stopped triggering
    leaves its last exit code behind unchanged, so a fetcher dead for a day would
    otherwise report the cheerful status of its final run, which is the one
    reading that must not be possible here.

    Three polls, and never under thirty minutes. One missed tick is a suspend or
    a slow boot; three in a row is a fetcher that is not coming back. The floor
    is for a short poll -- at `poll_minutes = 1` a window of three minutes would
    spend most of its time red for no reason, and a line that is usually red is a
    line nobody reads on the day it is true.
    """
    now = time.time() if now is None else now
    # Resolved HERE and not as a default argument. A default binds the function
    # object at import, so `mock.patch.object(mailstat, "_systemctl", ...)` would
    # leave it pointing at the original -- and a test that believes it replaced
    # the probe, and did not, runs `systemctl` against the real machine and
    # passes or fails on what that machine happens to be doing.
    show = _systemctl if show is None else show
    t = show(unit(fleet, "timer"), ["LoadState", "ActiveState", "LastTriggerUSec"])
    if t is None:
        return "unknown", {"why": "systemctl --user could not be asked"}
    info = {"timer": unit(fleet, "timer"), "service": unit(fleet, "service")}
    if t.get("LoadState") != "loaded":
        return "none", info
    if t.get("ActiveState") != "active":
        return "off", dict(info, active=t.get("ActiveState") or "?")
    last = _epoch(t.get("LastTriggerUSec"))
    if last is None:
        return "never", info
    info["last"] = last
    info["age_s"] = now - last
    window = max(3 * int(poll_minutes or 1), 30) * 60
    if info["age_s"] > window:
        return "stale", dict(info, window_s=window)
    s = show(unit(fleet, "service"), ["ExecMainStatus", "ExecMainExitTimestamp"])
    if s is None:
        # The timer answered and the service did not. Say so rather than letting
        # the timer's health speak for a run this never saw: half an answer is
        # how a source failure reaches a screen as a pass.
        return "unknown", dict(info, why="the timer answered and %s did not"
                                          % unit(fleet, "service"))
    try:
        code = int(s.get("ExecMainStatus"))
    except (TypeError, ValueError):
        return "unknown", dict(info, why="%s reports no exit status"
                                         % unit(fleet, "service"))
    # The service's own timestamp, not the timer's: a fetch that is still running
    # has not exited, and reading the trigger time as a finish time would date a
    # failure to the attempt that replaced it.
    ran = _epoch(s.get("ExecMainExitTimestamp"))
    if code:
        return "failed", dict(info, code=code, ran=ran,
                              meaning=CODES.get(code, "exit %d" % code))
    return "ok", info


def read(mail, state, show=None, now=None):
    """(state, data) for this fleet's cross-fleet mail.

    State is "unknown" when the delivery record could not be read, "stuck" when
    something arrived and reached nobody, and otherwise whatever the fetch is
    doing -- because once nothing is stuck, the only question left about mail is
    whether anything is still bringing it in.
    """
    now = time.time() if now is None else now
    f_state, f_info = fetch(mail["fleet"], mail.get("poll_minutes", 5),
                            show=show, now=now)
    data = {"fleet": mail["fleet"], "fetch": f_state, "fetch_info": f_info}
    recs, err = read_delivered(state)
    if recs is None:
        return "unknown", dict(data, why=err)
    stuck = needs_human(recs)
    data["stuck"] = stuck
    data["received"] = len(recs)
    at, who = last_arrival(recs)
    data["last_at"], data["last_from"] = at, who
    if at is not None:
        data["last_age_s"] = now - at
    if stuck:
        return "stuck", data
    return f_state, data
