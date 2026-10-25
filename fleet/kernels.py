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

UNDER WSL2 NONE OF THAT HOLDS. The kernel is not the distribution's: Windows
supplies it, from one file on the Windows side that `wsl --update` replaces, and
the new one is loaded only by `wsl --shutdown` -- a reboot of the distribution
does not do it. `/lib/modules` holds one empty directory per kernel WSL has ever
booted, plus the running one's modules mounted in at boot, and no image in any of
them; so the scan above said `unknown` on every WSL machine, permanently. And a
`kernel-default` package installed in the distribution would sort above the
Microsoft release and read as a reboot owed forever, a reboot that cannot clear
it. So under WSL2 the scan is not run at all, and the comparison is against the
Windows-side image instead, whose release is read from its x86 boot header: one
`read` of a few hundred bytes, still no subprocess.

A custom kernel set by `kernel=` in `.wslconfig` is NOT supported: finding that
file means knowing the Windows user's profile, which takes a call into Windows.
Such a machine reads as `pending` for as long as it runs the custom kernel, which
is loud and wrong rather than quiet and wrong, and is the reason it is said here.
"""
import os
import re
import struct

MODULES = "/lib/modules"
IMAGES = ("vmlinuz", "vmlinux", "Image", "zImage", "bzImage")
WSL_IMAGE = "/mnt/c/Program Files/WSL/tools/kernel"


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


def state(root=MODULES, wsl_image=WSL_IMAGE):
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

    Under WSL2 the comparison is against `wsl_image` instead (see the module
    docstring), and `info` also carries `remedy`, because the answer there is
    `wsl --shutdown` and not a reboot.
    """
    now = running()
    if is_wsl(now):
        return _wsl_state(now, wsl_image)
    have = installed(root)
    if not have:
        return "unknown", {"running": now,
                           "error": f"no kernel image found under {root}"}
    newest, since = have[0]
    info = {"running": now, "newest": newest, "since": since,
            "booted": _booted(), "installed": [r for r, _ in have]}
    return ("current" if newest == now else "pending"), info


def is_wsl(release):
    """Whether `release` is a WSL2 kernel, whose image Windows supplies.

    By the release alone, which every WSL2 kernel Microsoft ships ends in. WSL1
    has no Linux kernel at all -- its "release" is a Windows build in costume --
    and is deliberately not matched: comparing it against the WSL2 image would
    report a restart owed that no restart clears.
    """
    return release.endswith("-WSL2")


def image_release(path):
    """The release string an x86 kernel image announces in its boot header, or None.

    The boot protocol puts the magic `HdrS` at 0x202, its version at 0x206, and
    from version 2.00 a pointer at 0x20E to a NUL-terminated banner whose first
    word is the release -- the same string `uname -r` will print once it boots.
    Anything that does not look like that is None, never a guess: an unreadable
    image must come back `unknown`, not compared as if it said something.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(0x210)
            if len(head) < 0x210 or head[0x202:0x206] != b"HdrS" \
                    or struct.unpack_from("<H", head, 0x206)[0] < 0x200:
                return None
            # A null pointer needs no guard of its own: it points at 0x200,
            # the header's own jump instruction, which the release check below
            # rejects like any other banner that is not a release.
            fh.seek(struct.unpack_from("<H", head, 0x20E)[0] + 0x200)
            banner = fh.read(256).split(b"\0")[0]
    except OSError:
        return None
    words = banner.decode("ascii", "replace").split()
    if not words or not re.fullmatch(r"[\w.+~-]+", words[0]):
        return None
    return words[0]


def _wsl_state(now, path):
    """`state()` for WSL2: the running kernel against the Windows-side image.

    `since` is the image's CHANGE time, not its modification time. The file is
    copied in by the WSL package with its build date preserved as the mtime --
    on the machine this was written for, built 31 Jul and installed 30 Sep -- so
    the mtime would overstate the wait by two months.
    """
    newest = image_release(path)
    if newest is None:
        return "unknown", {"running": now, "wsl": True,
                           "error": f"WSL kernel image unreadable: {path}"}
    try:
        since = os.stat(path).st_ctime
    except OSError:
        since = None
    info = {"running": now, "newest": newest, "since": since,
            "booted": _booted(), "installed": [newest], "wsl": True,
            "remedy": "wsl --shutdown"}
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
