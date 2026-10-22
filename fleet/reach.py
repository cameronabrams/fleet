"""When a cluster was last readable, and what its reservation table said.

`fleetwatch` computes whether its cluster query succeeded on every run and, until
2026-10-22, recorded nothing. So a failure read as

    !! CLUSTER QUERY FAILED -- live work is UNKNOWN, not none

which is honest and carries no DURATION. A two-minute blip and a two-day outage
print the same sentence, and so does a cluster that was never reachable at all --
three states a reader has to tell apart and cannot. Stamping the last good read
turns it into "unreachable for 1h 20m, last good 08:35 EDT", which is the
difference between ignoring it and looking into it. The cluster was down for a
maintenance window on the morning of 2026-10-22 and nothing in the fleet could
say when it had started.

ABSENCE IS NOT ZERO. A cluster with no recorded good read is `None`, never a
duration of nothing -- a fleet whose state directory was just created has not
observed a cluster that is unreachable for 0 seconds.

The reservation log is an EXPERIMENT, not a feature, and is deliberately a
recorder rather than a parser. SLURM holds planned maintenance as a reservation
readable while the cluster is still up, which is exactly when a warning would be
worth having -- but whether this site creates them is unknown. `scontrol show
reservation` answered "No reservations in the system" when the cluster returned,
and that is weaker evidence than it looks: a completed MAINT reservation is removed,
so an empty table just after a window is what you would see whether or not the
site uses them. One look after the fact cannot tell the two cases apart.

So this keeps what the table said and parses none of it. If a MAINT entry ever
appears AHEAD of an outage the mechanism is real and the feature can be built on
evidence; if months pass with nothing, that is the answer too. Recorded only when
the output CHANGES, so the log stays short enough to read by eye.
"""
import json
import os
import time

REACH = "cluster-reach.json"
RESERVATIONS = "cluster-reservations.log"


def reach_path(state_dir):
    return os.path.join(state_dir, REACH)


def reservations_path(state_dir):
    return os.path.join(state_dir, RESERVATIONS)


def read(path):
    """`{cluster: {"last_good": epoch|None, "last_checked": epoch}}`, or `{}`.

    An unreadable or corrupt file is `{}` and never an exception: this is a
    convenience on top of the cluster query, and a tool that could not report the
    cluster because it could not report how long the cluster had been down would
    have made things worse.
    """
    try:
        with open(path) as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def record(path, cluster, ok, now=None):
    """Note a read of `cluster`. Returns the entry as it now stands.

    Written whether the read succeeded or not -- `last_checked` moves either way,
    and only a success moves `last_good`. A caller that recorded failures only
    could not tell "down since 08:35" from "nobody has looked since 08:35".
    """
    now = time.time() if now is None else now
    d = read(path)
    e = d.get(cluster) if isinstance(d.get(cluster), dict) else {}
    e = {"last_good": e.get("last_good"), "last_checked": now}
    if ok:
        e["last_good"] = now
    d[cluster] = e
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w") as fh:
            json.dump(d, fh, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except OSError:
        # Best effort. Losing the stamp costs a duration on one line; failing the
        # run would cost the cluster report that line is attached to.
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return e


def down_for(entry, now=None):
    """Seconds since this cluster was last readable, or None if never recorded.

    None is the honest answer for a fleet that has never had a good read: a
    duration would say the outage began when the state directory was created.
    """
    if not entry or not entry.get("last_good"):
        return None
    now = time.time() if now is None else now
    return max(0.0, now - entry["last_good"])


def record_reservations(path, cluster, text, now=None):
    """Append `text` for `cluster` if it differs from the last thing recorded.

    Returns True when something was written. Change-only, because the whole point
    is to notice a MAINT entry appearing: a log that repeated the same
    "No reservations in the system" every quarter hour would bury the one line
    that matters under thousands that do not.
    """
    now = time.time() if now is None else now
    text = (text or "").strip()
    if not text:
        return False
    if text == last_reservation_text(path, cluster):
        return False
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now))
    block = "=== %s %s\n%s\n" % (stamp, cluster, text)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as fh:
            fh.write(block)
    except OSError:
        return False
    return True


def last_reservation_text(path, cluster):
    """The most recent recorded table for `cluster`, or None."""
    try:
        with open(path) as fh:
            raw = fh.read()
    except OSError:
        return None
    out = None
    for block in raw.split("=== "):
        if not block.strip():
            continue
        head, _, body = block.partition("\n")
        parts = head.split()
        if len(parts) >= 2 and parts[1] == cluster:
            out = body.strip()
    return out
