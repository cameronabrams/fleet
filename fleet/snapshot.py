"""Whether the pending-updates document still describes this machine.

`fleetboard` reads a document written by a daily timer and prints what it says:
`updates: 47 updates -> 20261021 - checked 6h ago`. The age is honest and the
COUNT is not, once a human has installed the updates in between -- the line then
reports work that no longer exists, and it does so for up to a day.

Observed 2026-10-23: the document recorded snapshot 20261020 with 47 pending
toward 20261021, Cameron installed them that morning, and `/etc/os-release` read
`VERSION_ID="20261021"`. The board went on advertising 47 pending updates for
nearly seven hours. His own suggestion was that an install should reset the flag,
which means hooking the package manager; it is not needed. **The machine already
says which snapshot it is on, and the document already says which one it was
aiming at.** Comparing the two costs one file read.

The rule is deliberately narrow: a document is SUPERSEDED only when the machine
has reached the `target_snapshot` the document itself named. Not "the ids
differ" -- on a distribution whose `VERSION_ID` is something like `15.5` while
the producer records a date, they would differ permanently and the board would
cry supersession for ever. Reaching the stated target cannot false-alarm,
because it is the document's own definition of done.

Unknown is never "fine". If `/etc/os-release` cannot be read, or carries no
`VERSION_ID`, or the document names no target, the answer is None and the caller
keeps saying what it said before.
"""
import os

OS_RELEASE = "/etc/os-release"


def current(path=OS_RELEASE):
    """This machine's `VERSION_ID`, or None.

    Quotes stripped; `VERSION_ID="20261021"` and `VERSION_ID=20261021` are the
    same answer, because os-release permits both and a reader that honored the
    quotes would compare `"20261021"` against `20261021` and find them different.
    """
    try:
        with open(path) as fh:
            lines = fh.readlines()
    except OSError:
        return None
    for line in lines:
        k, _, v = line.partition("=")
        if k.strip() == "VERSION_ID":
            return v.strip().strip('"').strip("'") or None
    return None


def superseded(doc, now_id=None, path=OS_RELEASE):
    """True when `doc` describes a machine that has since been updated past it.

    `(doc)` is the parsed updates document. True means its pending count is about
    a state this machine has left; False means it still describes this machine;
    **None means it cannot be told**, and a caller must then report what it
    reported before rather than guessing in either direction.
    """
    if not isinstance(doc, dict):
        return None
    target = doc.get("target_snapshot")
    was = doc.get("snapshot")
    if not target or not was:
        return None
    if str(target) == str(was):
        # Nothing was pending in the first place: the document's target IS where
        # the machine already was, so reaching it proves nothing.
        return False
    have = now_id if now_id is not None else current(path)
    if not have:
        return None
    return str(have) == str(target)
