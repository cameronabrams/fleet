"""What the nudge log means: which records are a delivery hole, and which are not.

Shared by `fleetwatch`, which reports holes, and `fleetnudge`, which can now
clear one. They have to agree exactly -- a tool offering to clear a line must
show the same lines the report shows, or the dry run lies about what it is about
to silence. Reimplementing the rule in the second tool was the obvious thing and
is the family this repository keeps finding: two derivations of one fact,
agreeing for a reason nobody wrote down.
"""
import datetime
import json

# A retry loop still going is normal; this old, it was killed mid-retry.
DANGLING_AFTER = 2 * 3600

def _when(rec):
    """The record's own timestamp, offset and all. None if it has none worth trusting."""
    try:
        return datetime.datetime.strptime(rec["time"], "%Y-%m-%dT%H:%M:%S%z")
    except (KeyError, TypeError, ValueError):
        return None


# A nudge that was not delivered is not automatically news that was LOST.
# `fleetnudge` declines when it is running inside the session it would type into:
# the in-session task doing the running already notifies it, so the content reaches
# its reader by another route and nothing is missing.
#
# That is recorded structurally, as `notified_otherwise`, by the one program that
# can know it. **Exit code cannot stand in for it.** The decline shares code 2 with
# caller errors that ARE holes -- a line over the 200-character limit (2026-09-30),
# a malformed job id (2026-10-04) -- so bucketing on the code would trade this
# defect for its mirror image, and the mirror image is the dangerous one: a real
# hole rendered as fine.
#
# LEGACY, and it is a parse of prose: records written before 2026-10-15 carry no
# such field, only the sentence. The sentence is matched exactly and pinned by a
# test against the string `fleetnudge` emits, so a reworded refusal fails loudly
# here rather than silently becoming a hole again. `NUDGE_DAYS` is 7, so no record
# in the window can predate the field after 2026-10-22 and this may then be
# deleted along with its test.
INFORMED_LEGACY = ("this is running inside the session itself; "
                   "an in-session task already notifies it")


# An outcome written by a HUMAN or by the session itself, saying the result
# reached its reader some other way. It is not a delivery and does not claim to
# be one: `fleetnudge` never produces it.
INFORMED_OUTCOME = "informed"


def informed_times(recs):
    """{(session, job): earliest assertion} that the news arrived another way."""
    out = {}
    for r in recs:
        if r.get("outcome") != INFORMED_OUTCOME:
            continue
        k = (r.get("session"), str(r.get("job")))
        t = _when(r)
        if k not in out or t < out[k]:
            out[k] = t
    return out


def resolved_by_hand(r, informed):
    """Whether someone has asserted that THIS result reached its reader.

    The assertion must come after the trouble it answers: a claim recorded before
    a nudge failed says nothing about that failure.

    **This suppresses, where a later ordinary delivery only annotates**, and the
    difference is deliberate. A later nudge about the same job is a DIFFERENT
    message, so treating it as proof would make the check fail toward fine. An
    `informed` record is a direct statement about this result, by someone who
    could know. It is weaker evidence than a delivery and stronger than an
    inference, so it carries `by` and a reason into the log and is counted in the
    report rather than vanishing.
    """
    t = informed.get((r.get("session"), str(r.get("job"))))
    return t is not None and t >= _when(r)


def lost_the_news(r):
    """Whether a `not delivered` record means nobody was told.

    False only on positive evidence that the content arrived another way. An
    absent field and an unrecognized reason both read as a hole, which is the
    direction that keeps a real one visible.
    """
    if r.get("notified_otherwise") is not None:
        return not r["notified_otherwise"]
    return (r.get("reason") or "").strip() != INFORMED_LEGACY



def read(path):
    """Every parseable record in the log, plus the count that was not."""
    recs, bad = [], 0
    try:
        with open(path) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    bad += 1
                    continue
                if _when(r) is None:
                    bad += 1
                    continue
                recs.append(r)
    except OSError:
        return None, 0
    return recs, bad


def last_nudge_word(recs):
    """The last record `fleetnudge` itself wrote, per session and job.

    `informed` records are excluded, and that is not bookkeeping. They are
    assertions ABOUT a nudge, not outcomes OF one, so letting one count as the
    last word would mean a cleared hole stopped being recognizable as the kind
    of hole it was -- and a genuine dangling that arrived AFTER an assertion
    would be masked by it, which is the dangerous direction.
    """
    last = {}
    for r in recs:
        if r.get("outcome") == INFORMED_OUTCOME:
            continue
        last[(r.get("session"), str(r.get("job")))] = r
    return last


def open_trouble(recs, session=None, job=None, now=None,
                 dangling_after=DANGLING_AFTER):
    """The records a report would currently be unhappy about.

    One rule, used by the reporter and by the tool that clears. A `waiting`
    counts only when it is the LAST word for its session and job and old enough
    to mean the retry loop was killed -- the dozens of ordinary retry lines
    before it are not trouble, and listing them in a clearing tool's dry run
    would make two flagged rows look like thirty.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    last = last_nudge_word(recs)
    informed = informed_times(recs)
    out = []
    for r in recs:
        if session is not None and r.get("session") != session:
            continue
        if job is not None and str(r.get("job")) != str(job):
            continue
        if resolved_by_hand(r, informed):
            continue
        o = r.get("outcome")
        if o == "not delivered" and lost_the_news(r):
            out.append(r)
        elif (o == "waiting"
              and last.get((r.get("session"), str(r.get("job")))) is r
              and (now - _when(r)).total_seconds() > dangling_after):
            out.append(r)
    return out
