"""One derivation of "which claude", shared by the three tools that need it.

`fleetupgrade` decided staleness from it, `fleetsnap` recorded it in the manifest
and `fleetboard` now shows it -- and each read it for itself. The two that existed
before this module already disagreed in shape: a regex for the component after
`versions/`, against `os.path.basename` of the resolved symlink. Both return
"2.1.292" today, because that is the last component of the current layout. Only
one of them still does when the binary sits one level deeper.

That is the whole family this repository keeps finding: two derivations of one
fact, agreeing for a reason nobody wrote down, in a value that is read later as
authoritative -- here the manifest a restore is rebuilt from.
"""
import os
import unittest
from unittest import mock

from fleet import versions
from tests.support import APP


class ParsingALayout(unittest.TestCase):
    def test_the_current_layout(self):
        self.assertEqual(
            versions.from_path("/home/u/.local/share/claude/versions/2.1.292"),
            "2.1.292")

    def test_a_binary_one_level_deeper_still_parses(self):
        """The case that separates this from `basename`, and the reason the
        module exists rather than the one-liner it replaces."""
        self.assertEqual(
            versions.from_path("/home/u/.local/share/claude/versions/2.1.292/bin/claude"),
            "2.1.292")
        self.assertEqual(
            os.path.basename("/home/u/.local/share/claude/versions/2.1.292/bin/claude"),
            "claude", "basename would have recorded this as the version")

    def test_a_prerelease_suffix_survives(self):
        self.assertEqual(versions.from_path("/x/versions/2.2.0-rc.1"), "2.2.0-rc.1")

    def test_a_layout_with_no_version_is_unknown_not_a_guess(self):
        """None, not the last component and not a default. A wrong version number
        is worse than no version number in BOTH directions: it marks a stale
        session current, and it marks a current fleet stale."""
        for p in ("/usr/bin/claude", "/home/u/.local/bin/claude", "", None):
            self.assertIsNone(versions.from_path(p), p)


class UnknownIsNeitherStaleNorCurrent(unittest.TestCase):
    def test_two_known_versions_compare(self):
        self.assertTrue(versions.is_stale("2.1.291", "2.1.292"))
        self.assertFalse(versions.is_stale("2.1.292", "2.1.292"))

    def test_an_unknown_on_either_side_is_none(self):
        """Not False. A caller that folded unknown into "current" would draw a
        board that lost its source as a fleet that is fully up to date -- the
        board's own stated rule, one level down."""
        self.assertIsNone(versions.is_stale(None, "2.1.292"))
        self.assertIsNone(versions.is_stale("2.1.291", None))
        self.assertIsNone(versions.is_stale(None, None))


class ReadingTheMachine(unittest.TestCase):
    def test_installed_resolves_the_symlink_it_is_given(self):
        with mock.patch.object(os.path, "realpath",
                               lambda p: "/s/claude/versions/9.9.9"):
            self.assertEqual(versions.installed("/anywhere"), "9.9.9")

    def test_a_missing_binary_is_unknown(self):
        self.assertIsNone(versions.installed("/nonexistent/claude/binary"))

    def test_of_pid_reads_the_running_binary(self):
        with mock.patch.object(os, "readlink",
                               lambda p: "/s/claude/versions/1.2.3"):
            self.assertEqual(versions.of_pid(1234), "1.2.3")

    def test_a_pid_that_is_gone_is_unknown(self):
        self.assertIsNone(versions.of_pid(0))
        self.assertIsNone(versions.of_pid(None))
        self.assertIsNone(versions.of_pid(2 ** 30))      # no such process


class NoToolDerivesItAlone(unittest.TestCase):
    def test_no_tool_in_bin_parses_the_version_path_itself(self):
        """Exhaustive over `bin/`, not a list of three.

        The list-of-names version of this test is what let the two copies drift
        in the first place: whoever added the second was not on anyone's list.
        A tool that needs a version imports `fleet.versions`; a tool that writes
        the pattern again is what this catches, including the one nobody thought
        to add here.
        """
        offenders = []
        for tool in sorted(os.listdir(os.path.join(APP, "bin"))):
            path = os.path.join(APP, "bin", tool)
            if not os.path.isfile(path):
                continue
            try:
                src = open(path).read()
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(src.splitlines(), 1):
                code = line.split("#")[0]           # prose about it is not a read
                # The signature is a CAPTURE after `versions/`, not the substring.
                # Matching `versions/` beside any regex call was the first rule
                # here and it flagged two lines in `fleetupgrade` that ask whether
                # a process is claude at all (`"/versions/" in cmd`) -- a test that
                # convicts the innocent gets narrowed or deleted, and either way
                # stops being read.
                if "versions/(" in code:
                    offenders.append(f"{tool}:{i} parses the version path itself")
                if "basename" in code and "realpath" in code:
                    offenders.append(f"{tool}:{i} takes basename(realpath(...))")
        self.assertEqual(offenders, [], "; ".join(offenders))


if __name__ == "__main__":
    unittest.main()
