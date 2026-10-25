"""Whether a newer kernel is installed than the one running.

A reboot ends every session on the machine, so this is a fleet fact rather than a
packaging detail -- and the owner may owe the reboot for days, because it has to
wait for whatever the fleet is in the middle of.
"""
import os
import time
import unittest

from fleet import kernels


class Modules(unittest.TestCase):
    """A fake `/lib/modules`. Nothing here reads the real one: the running kernel
    is whatever the test host happens to boot, so a test that compared against it
    would pass or fail by accident."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory(prefix="fleet-kernels-")
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def kernel(self, release, image="vmlinuz", age_s=0):
        d = os.path.join(self.root, release)
        os.makedirs(d, exist_ok=True)
        if image:
            open(os.path.join(d, image), "w").close()
        if age_s:
            os.utime(d, (time.time() - age_s,) * 2)
        return d

    def state(self, running):
        from unittest import mock
        with mock.patch.object(kernels, "running", lambda: running):
            return kernels.state(self.root)


class NewerThanRunning(Modules):
    def test_a_newer_installed_kernel_is_pending(self):
        self.kernel("7.2.11-1-default")
        self.kernel("7.2.14-1-default")
        st, info = self.state("7.2.11-1-default")
        self.assertEqual(st, "pending")
        self.assertEqual(info["newest"], "7.2.14-1-default")
        self.assertEqual(info["running"], "7.2.11-1-default")

    def test_running_the_newest_is_current(self):
        self.kernel("7.2.9-1-default")
        self.kernel("7.2.11-1-default")
        self.assertEqual(self.state("7.2.11-1-default")[0], "current")

    def test_eleven_is_newer_than_nine(self):
        """The reason this needs a key at all. `7.2.9-1-default` sorts ABOVE
        `7.2.11-1-default` as a string, so a plain `max()` would report a pending
        reboot on a machine that is running the newest kernel it has -- an alarm
        that can never be cleared, on every openSUSE box past its tenth point
        release."""
        self.kernel("7.2.9-1-default")
        self.kernel("7.2.11-1-default")
        st, info = self.state("7.2.11-1-default")
        self.assertEqual(info["installed"][0], "7.2.11-1-default")
        self.assertEqual(st, "current")

    def test_a_mixed_numeric_and_word_release_does_not_raise(self):
        """`7.2.11-1-default` splits into both ints and words, and comparing those
        positionally raises TypeError on a naive tuple key -- which would take the
        whole board down rather than mis-sort one line."""
        self.kernel("7.2.11-1-default")
        self.kernel("7.2.11-1-rt")
        self.kernel("6.0.0-1-default")
        st, info = self.state("7.2.11-1-default")
        self.assertEqual(len(info["installed"]), 3)

    def test_a_running_kernel_that_is_no_longer_installed_is_pending(self):
        """The running kernel has been removed from under the machine. A reboot is
        equally the answer, and reporting `current` here would be reporting that
        the machine is running something it does not have."""
        self.kernel("7.2.14-1-default")
        st, info = self.state("7.2.11-1-default")
        self.assertEqual(st, "pending")
        self.assertNotIn("7.2.11-1-default", info["installed"])


class LeftoverDirectories(Modules):
    """`/lib/modules/7.0.3-1-default` on the machine this was written for is owned
    by no package at all (checked with `rpm -qf`, 2026-10-21) -- left behind when
    its kernel went. A newest-directory-wins scan reads a leftover as an installed
    kernel, and the dangerous leftover is a NEWER one: it produces a permanent
    reboot warning for a reboot that would change nothing."""

    def test_a_directory_with_no_kernel_image_is_not_an_installed_kernel(self):
        self.kernel("7.2.11-1-default")
        self.kernel("9.9.9-1-default", image=None)        # the leftover
        st, info = self.state("7.2.11-1-default")
        self.assertEqual(st, "current", "a leftover must not raise a reboot alarm")
        self.assertEqual(info["installed"], ["7.2.11-1-default"])

    def test_any_known_image_name_counts(self):
        """Not every architecture calls it `vmlinuz`. Getting this wrong fails
        toward `unknown`, which is reported rather than passed over."""
        for img in ("vmlinuz", "vmlinux", "Image", "zImage", "bzImage"):
            with self.subTest(image=img):
                import tempfile
                with tempfile.TemporaryDirectory() as d:
                    os.makedirs(os.path.join(d, "1.0.0-1-default"))
                    open(os.path.join(d, "1.0.0-1-default", img), "w").close()
                    self.assertEqual([r for r, _ in kernels.installed(d)],
                                     ["1.0.0-1-default"])


class OnlyTheDifferingPart(unittest.TestCase):
    """What the header prints. The releases are long and nearly identical, and the
    line they go in is already long enough to wrap a narrow pane."""

    def test_the_shared_tail_is_dropped(self):
        self.assertEqual(kernels.differing("7.2.11-1-default", "7.2.14-1-default"),
                         ("7.2.11", "7.2.14"))

    def test_a_differing_flavor_is_kept_in_full(self):
        """Shared components only, never a fixed count: when the FLAVOR differs
        that is the whole point of the line, and trimming it would print
        `7.2.11 -> 7.2.11` -- a reboot notice that appears to be between a release
        and itself."""
        self.assertEqual(kernels.differing("7.2.11-1-default", "7.2.11-1-rt"),
                         ("7.2.11-1-default", "7.2.11-1-rt"))

    def test_identical_releases_are_not_trimmed_to_nothing(self):
        """Never reached from a pending state, since pending means they differ --
        but a helper that returns empty strings would print `(kernel  -> )` if it
        ever were, and an empty field reads as a bug in the board rather than in
        its input."""
        self.assertEqual(kernels.differing("7.2.11-1-default", "7.2.11-1-default"),
                         ("7.2.11-1-default", "7.2.11-1-default"))

    def test_a_release_with_no_components_survives(self):
        self.assertEqual(kernels.differing("a", "b"), ("a", "b"))


class UnderWSL(Modules):
    """WSL2, where Windows supplies the kernel from one image `wsl --update`
    replaces. Fake releases throughout: the real one is whatever WSL the test
    host happens to run, if any."""

    OLD = "9.1.2.1-microsoft-standard-WSL2"
    NEW = "9.1.5.1-microsoft-standard-WSL2"

    def image(self, release, magic=b"HdrS", version=0x20F, ptr=0x300):
        """A file laid out as the x86 boot protocol lays out a bzImage header:
        only the fields `image_release` reads, the rest zeros."""
        import struct
        buf = bytearray(0x600)
        buf[0x202:0x206] = magic
        struct.pack_into("<H", buf, 0x206, version)
        struct.pack_into("<H", buf, 0x20E, ptr)
        banner = (release + " (builder@host) #1 SMP PREEMPT_DYNAMIC").encode()
        buf[ptr + 0x200:ptr + 0x200 + len(banner)] = banner
        path = os.path.join(self.root, "wsl-kernel")
        with open(path, "wb") as fh:
            fh.write(buf)
        return path

    def state(self, running, path=None):
        from unittest import mock
        path = path or os.path.join(self.root, "wsl-kernel")
        with mock.patch.object(kernels, "running", lambda: running):
            return kernels.state(os.path.join(self.root, "modules"), path)

    def test_the_image_matching_the_running_kernel_is_current(self):
        self.image(self.OLD)
        st, info = self.state(self.OLD)
        self.assertEqual(st, "current")
        self.assertEqual(info["newest"], self.OLD)

    def test_a_different_image_is_pending_and_names_the_shutdown(self):
        """A reboot of the distribution does not load the new kernel; only
        `wsl --shutdown` does, so the remedy travels with the state."""
        path = self.image(self.NEW)
        st, info = self.state(self.OLD)
        self.assertEqual(st, "pending")
        self.assertEqual((info["running"], info["newest"]), (self.OLD, self.NEW))
        self.assertEqual(info["remedy"], "wsl --shutdown")

    def test_since_is_the_change_time_not_the_build_date(self):
        """The WSL package keeps the build date as the image's mtime, months
        before it was installed; the change time is when it arrived."""
        path = self.image(self.NEW)
        os.utime(path, (time.time() - 90 * 86400,) * 2)
        info = self.state(self.OLD)[1]
        self.assertEqual(info["since"], os.stat(path).st_ctime)
        self.assertGreater(info["since"], time.time() - 3600)

    def test_lib_modules_is_not_consulted(self):
        """A distribution kernel package sorts above the Microsoft release, and
        under WSL it is never booted: read, it would be a reboot owed forever."""
        d = os.path.join(self.root, "modules", "10.0.1-1-default")
        os.makedirs(d)
        open(os.path.join(d, "vmlinuz"), "w").close()
        self.image(self.OLD)
        self.assertEqual(self.state(self.OLD)[0], "current")

    def test_a_missing_image_is_unknown_not_current(self):
        st, info = self.state(self.OLD, os.path.join(self.root, "absent"))
        self.assertEqual(st, "unknown")
        self.assertTrue(info["wsl"])

    def test_a_file_without_the_boot_header_is_unknown(self):
        """An ARM64 `Image`, a truncated copy, anything else: not a guess."""
        self.image(self.OLD, magic=b"\0\0\0\0")
        self.assertEqual(self.state(self.OLD)[0], "unknown")

    def test_a_header_too_old_to_carry_a_banner_is_unknown(self):
        self.image(self.OLD, version=0x1FF)
        self.assertEqual(self.state(self.OLD)[0], "unknown")

    def test_a_null_banner_pointer_is_unknown(self):
        """Caught by the release check, not a guard of its own: a pointer of 0
        lands on the header itself, which is not a release."""
        self.image(self.OLD, ptr=0)
        self.assertEqual(self.state(self.OLD)[0], "unknown")

    def test_a_banner_that_is_not_a_release_is_unknown(self):
        self.image("<garbage!>")
        self.assertEqual(self.state(self.OLD)[0], "unknown")

    def test_an_ordinary_kernel_ignores_the_wsl_image(self):
        """Only a WSL2 release is compared against the Windows image; WSL1's
        release is a Windows build and has no kernel to replace."""
        self.image(self.NEW)
        self.assertEqual(self.state("7.2.11-1-default")[0], "unknown")
        self.assertEqual(self.state("4.4.0-19041-Microsoft")[0], "unknown")


class AbsenceIsNotAPass(Modules):
    """The doctrine, on the one fact here that ends every session at once."""

    def test_an_unreadable_modules_directory_is_unknown_not_current(self):
        st, info = self.state("7.2.11-1-default")      # empty root
        self.assertEqual(st, "unknown")
        self.assertIn("no kernel image", info["error"])

    def test_a_missing_modules_directory_is_unknown(self):
        from unittest import mock
        with mock.patch.object(kernels, "running", lambda: "7.2.11-1-default"):
            st, _ = kernels.state(os.path.join(self.root, "nope"))
        self.assertEqual(st, "unknown")

    def test_installed_on_an_unreadable_root_is_empty_not_an_exception(self):
        self.assertEqual(kernels.installed(os.path.join(self.root, "nope")), [])


class HowLongTheRebootHasBeenOwed(Modules):
    """The number the owner actually decides on. They already know a reboot is
    due; what they do not know is how long they have been putting it off."""

    def test_since_is_the_newer_kernels_own_mtime(self):
        self.kernel("7.2.11-1-default", age_s=20 * 86400)
        self.kernel("7.2.14-1-default", age_s=3 * 86400)
        _, info = self.state("7.2.11-1-default")
        waited = time.time() - info["since"]
        self.assertAlmostEqual(waited / 86400, 3, delta=0.1,
                               msg="since must be the PENDING kernel's mtime, "
                                   "not the running one's")

    def test_booted_is_read_or_none_never_invented(self):
        self.kernel("7.2.11-1-default")
        _, info = self.state("7.2.11-1-default")
        self.assertTrue(info["booted"] is None or info["booted"] > 0)
