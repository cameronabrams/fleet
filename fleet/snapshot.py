"""Whether the pending-updates document still describes this machine.

Two claims in it can go out of date while the file itself sits unchanged, and
both are answered the same way -- by asking the machine what it is now, rather
than by asking how old the document is. An age says when something was written;
it never says whether it is still true. `superseded` answers that for the
pending COUNT, against `/etc/os-release`; `rebooted_since` answers it for the
`reboot_needed` flag, against the boot clock.

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

from fleet import kernels

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


def rebooted_since(doc, booted=None):
    """True when this machine has booted since `doc` was written.

    The document's `reboot_needed` is a claim about a moment: the producer
    compared the running kernel against the newest installed one, asked the
    package manager whether core libraries had moved under it, and wrote down
    what was true then. A boot after that moment answers every one of those
    reasons, and the document has no way to notice.

    Observed 2026-11-05. The 06:15 check recorded `reboot_needed: true` with
    both reasons -- kernel 7.3.0 running against 7.3.1 installed, and
    `needs-rebooting` reporting updated libraries. The machine was rebooted at
    09:01 onto 7.3.1. The board went on printing REBOOT NEEDED beside the clock,
    because it read that field and the next check was not due until the morning.

    **An alarm nothing can clear is how a true one gets missed**, which is the
    reason this is not merely cosmetic. `fleetboard` already reads the KERNEL
    half live for the mirror-image case -- a kernel unpacked hours after the
    document was written, which it would otherwise not mention until the next
    day -- and this is the same fact approached from the other side.

    It does not make the machine's reboot state knowable; it only retires a
    claim that has been overtaken. Anything a reboot owes from AFTER the boot is
    the next check's to find, and the board goes on showing the document's age
    so a reader can see how long ago that was. The live kernel comparison is
    unaffected and still speaks for itself -- a reader who rebooted into an older
    kernel from the boot menu is told so by that half, not by this one.

    **None means it cannot be told**, as everywhere else here: no readable
    `checked_epoch`, or no boot time (`/proc/stat` is Linux's, and this is the
    one fact in this module a container can be odd about). A caller then keeps
    saying what it said before, which leaves the alarm up. That is the direction
    this must fail in: a reboot wrongly still demanded costs a reader a glance at
    `uname`, and one wrongly retired costs them the next reboot.
    """
    if not isinstance(doc, dict):
        return None
    try:
        checked = float(doc["checked_epoch"])
    except (KeyError, TypeError, ValueError):
        return None
    when = kernels.booted() if booted is None else booted
    try:
        when = float(when)
    except (TypeError, ValueError):
        return None
    # A boot clock of zero is not an epoch in 1970, it is a machine that could
    # not tell us -- and read as a timestamp it would be older than every
    # document ever written, which answers "has it rebooted since" with a
    # confident no for ever.
    return None if when <= 0 else when > checked
