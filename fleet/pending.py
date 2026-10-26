"""Undelivered nudge CONTENT, left where its intended reader will find it.

`<state>/nudges.log` records that a nudge failed. It is a log: a reader has to go
looking, and the session that was supposed to get the news is not a reader of it.
So when both of `fleetnudge`'s channels are shut -- the pane will not take the
keystrokes and the phone push is muted -- the result exists only in a log nobody
opens, and the caller that was holding it has already exited. A detached
watcher's last act IS the nudge, so exiting non-zero tells a caller that is gone.
Measured on one fleet's log: every give-up that exhausted its wait window, three
for three, had the push muted as well, and one of those was inbound cross-fleet
mail. The longest sat finished and unreported for 7h47m and surfaced only because
a human asked.

A pending record is therefore not a second log. It is addressed TO the session,
holds the text itself rather than a pointer to it, and is cleared when the news
is acknowledged -- which `fleetnudge --delivered` already means, and already makes
the caller say how it knows.

ONE module writes and parses the format, because a reader that reimplements the
header is the family this repository keeps finding: two derivations of one fact,
agreeing for a reason nobody wrote down.
"""
import datetime
import os
import re

DIRNAME = "pending"
# Single-line values, split on the FIRST colon so a reason may contain one.
_FIELD = re.compile(r"^- ([a-z-]+): ?(.*)$")
_BODY = "## What was not delivered"

def pending_dir(state):
    return os.path.join(state, DIRNAME)

def slug(session, job):
    """A filename that cannot escape the directory or collide across jobs."""
    safe = lambda s: re.sub(r"[^A-Za-z0-9_.-]", "_", str(s)) or "_"
    return f"{safe(session)}__{safe(job)}.md"

def path(state, session, job):
    return os.path.join(pending_dir(state), slug(session, job))

def write(state, session, job, text, reason, code, mail_from=None, now=None):
    """Record that `text` never reached `session`. Returns the path written.

    Whitespace in every header value is collapsed: the format gives each field one
    line, and a reason that wrapped would otherwise be read back as the end of the
    header -- the body would then start mid-sentence and the rest would be lost
    silently, which is the failure this file exists to stop repeating one level
    down.
    """
    one = lambda v: " ".join(str(v).split())
    when = (now or datetime.datetime.now().astimezone()).strftime("%Y-%m-%dT%H:%M:%S%z")
    head = [f"# Undelivered: {one(session)} job {one(job)}", "",
            f"- session: {one(session)}", f"- job: {one(job)}",
            f"- written: {when}", f"- code: {int(code)}",
            f"- reason: {one(reason)}"]
    if mail_from:
        head.append(f"- mail-from: {one(mail_from)}")
    doc = "\n".join(head + ["", _BODY, "", str(text).rstrip("\n"), ""])
    os.makedirs(pending_dir(state), exist_ok=True)
    p = path(state, session, job)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        f.write(doc)
    os.replace(tmp, p)          # a reader never sees a half-written record
    return p

def parse(doc, p=None):
    """A record from one file's text, or None when the header is not readable."""
    head, body, seen_body = {}, [], False
    for line in doc.splitlines():
        if line.strip() == _BODY:
            seen_body = True
            continue
        if seen_body:
            body.append(line)
            continue
        m = _FIELD.match(line)
        if m:
            head[m.group(1)] = m.group(2).strip()
    if not seen_body or "session" not in head or "job" not in head:
        return None
    head["text"] = "\n".join(body).strip("\n")
    head["path"] = p
    return head

def read_all(state):
    """(records oldest first, unreadable count). `None` records when the
    directory cannot be read at all -- which is NOT the same as none pending, and
    callers must say so rather than print a reassuring zero."""
    d = pending_dir(state)
    try:
        names = sorted(os.listdir(d))
    except FileNotFoundError:
        return [], 0            # created on first give-up; absent means none
    except OSError:
        return None, 0
    recs, bad = [], 0
    for n in names:
        if not n.endswith(".md"):
            continue
        p = os.path.join(d, n)
        try:
            with open(p) as f:
                r = parse(f.read(), p)
        except OSError:
            r = None
        if r is None:
            bad += 1
        else:
            recs.append(r)
    recs.sort(key=lambda r: r.get("written") or "")
    return recs, bad

def for_session(state, session):
    recs, bad = read_all(state)
    if recs is None:
        return None, bad
    return [r for r in recs if r.get("session") == session], bad

def clear(state, session, job):
    """Remove the record, if there was one. True when a file went away."""
    try:
        os.remove(path(state, session, job))
        return True
    except OSError:
        return False
