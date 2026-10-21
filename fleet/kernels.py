"""Which kernel is running, which is installed, and whether those differ.

A reboot ends every session on the machine, so "a newer kernel is installed than
the one running" is a fleet-level fact, not a packaging detail -- and it is one
the owner may sit on for days, because the reboot has to wait for whatever the
fleet is in the middle of.

Read live, from the filesystem, with no subprocess and nothing installed. The
reason is timing rather than purity: the machine's update document is written by a
DAILY timer, and this fact flips the instant a `zypper dup` unpacks a kernel. On
2026-10-19 a kernel landed at 08:42 and the next check was due at 06:21 the
following morning -- twenty-two hours in which the board, reading only that
document, would have said nothing at all. A fact that is true *now* has to be read
now.

An installed kernel is a directory under `/lib/modules` that CONTAINS A KERNEL
IMAGE. The directory alone is not enough: `/lib/modules/7.0.3-1-default` on this
machine is owned by no package at all, left behind when its kernel went, and a
plain newest-directory-wins scan would eventually read a leftover as a pending
reboot. Checked rather than assumed -- `rpm -qf` on each candidate, 2026-10-21:
the orphan has no `vmlinuz` and both real kernels do. That makes the image the
test, which costs one `stat` and no knowledge of the package manager.

ABSENCE IS NOT A PASS. If `/lib/modules` cannot be read, or holds no image at
all, the answer is `unknown` and never `current`: a board that cannot see the
kernels must not report a quiet machine, which is the whole doctrine of
`docs/checks-that-reassure.md` applied to the one fact here that ends every
session at once.
"""
import os
import re

MODULES = "/lib/modules"
IMAGES = ("vmlinuz", "vmlinux", "Image", "zImage", "bzImage")


def running():
    """The running kernel's release string, as `uname -r` gives it."""
    return os.uname().release


def _key(release):
    """A sortable key in which 11 is newer than 9.

    Every part is wrapped so that mixed numeric and alphabetic parts never
    compare int against str: `7.2.11-1-default` is not sortable against
    `7.2.9-1-default` by string, and raises by naive tuple if the parts are
    converted individually.
    """
    out = []
    for p in re.split(r"[.\-_+~]", release):
        if p.isdigit():
            out.append((0, int(p), ""))
        else:
            out.append((1, 0, p))
    return tuple(out)


def installed(root=MODULES):
    """`[(release, mtime)]` for each kernel that has an image on disk, newest first.

    The mtime is the module directory's, which `depmod` touches as the kernel is
    unpacked -- measured against `rpm`'s own install time on 2026-10-21, 08:43:43
    against 08:42:40. It answers "how long has this been waiting", which is the
    question an owner who cannot reboot yet actually has.
    """
    out = []
    try:
        names = os.listdir(root)
    except OSError:
        return out
    for name in names:
        d = os.path.join(root, name)
        if not any(os.path.exists(os.path.join(d, i)) for i in IMAGES):
            continue
        try:
            out.append((name, os.stat(d).st_mtime))
        except OSError:
            continue
    out.sort(key=lambda r: _key(r[0]), reverse=True)
    return out


def state(root=MODULES):
    """`(state, info)` where state is "current", "pending" or "unknown".

    * **pending** -- the newest installed kernel is not the running one. `info`
      carries `running`, `newest`, `since` (when the newer kernel was unpacked)
      and `booted` (when the running one started), so a caller can say how long
      the reboot has been owed rather than only that it is.
    * **current** -- the running kernel IS the newest installed.
    * **unknown** -- nothing could be read. Never reported as current.

    A running kernel that is not installed at all also reads as **pending**, and
    that is deliberate: it means the running kernel has been removed from under
    the machine, which a reboot is equally the answer to.
    """
    now = running()
    have = installed(root)
    if not have:
        return "unknown", {"running": now,
                           "error": f"no kernel image found under {root}"}
    newest, since = have[0]
    info = {"running": now, "newest": newest, "since": since,
            "booted": _booted(), "installed": [r for r, _ in have]}
    return ("current" if newest == now else "pending"), info


def differing(a, b):
    """`(a, b)` with any shared trailing release components dropped.

    `7.2.11-1-default -> 7.2.14-1-default` becomes `7.2.11 -> 7.2.14`. The suffix
    is identical in the ordinary case and carries nothing, while the header it
    appears in is already long enough to wrap a narrow pane -- and a reminder that
    wraps is a reminder read as noise.

    Shared components only, never a fixed number of them: `7.2.11-1-default`
    against `7.2.11-1-rt` differs in the FLAVOR, which is then the whole point of
    the line, and both come back untouched.
    """
    if a == b:
        # Never reached from a pending state, which means they differ. Guarded
        # anyway because the trim would otherwise reduce both to their shared
        # stem, printing `(kernel 7.2.11 -> 7.2.11)` -- a reboot notice between a
        # release and itself, which reads as a bug in the board rather than in
        # what it was given.
        return a, b
    pa, pb = a.split("-"), b.split("-")
    n = 0
    while n < min(len(pa), len(pb)) - 1 and pa[-1 - n] == pb[-1 - n]:
        n += 1
    return ("-".join(pa[:len(pa) - n] or pa),
            "-".join(pb[:len(pb) - n] or pb))


def _booted():
    """When the running kernel started, from `/proc/stat`, or None.

    Corroborates the version comparison from a second direction: a newer kernel
    whose directory is younger than this boot is one that arrived after it.
    """
    try:
        with open("/proc/stat") as fh:
            for line in fh:
                if line.startswith("btime "):
                    return float(line.split()[1])
    except (OSError, ValueError):
        pass
    return None
