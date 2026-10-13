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
import json
import os
import tempfile
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


class TheOtherInstallLayout(unittest.TestCase):
    """The npm install names no version in any path, and the old code read paths.

    `npm install -g @anthropic-ai/claude-code` puts one binary under
    `node_modules/@anthropic-ai/claude-code/bin/` and upgrades it IN PLACE. The
    path says nothing; only the `package.json` beside it does. Everything here
    read the path alone until 2026-10-13, so on an npm machine `fleetsnap`
    recorded the installed claude as `claude`, every session's version as
    `claude.exe`, and `fleetupgrade`'s staleness check could not fail -- the
    board's own rule inverted, since a source that said nothing drew as a fleet
    with nothing to say.

    Reported by `pkgyasi/fleet`, a fork that hit it on its own machine.
    """
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def npm(self, version, name="@anthropic-ai/claude-code"):
        pkg = os.path.join(self.tmp.name, "node_modules", "@anthropic-ai", "claude-code")
        os.makedirs(os.path.join(pkg, "bin"), exist_ok=True)
        with open(os.path.join(pkg, "package.json"), "w") as f:
            json.dump({"name": name, "version": version}, f)
        exe = os.path.join(pkg, "bin", "claude.exe")
        open(exe, "w").close()
        return exe

    def test_the_package_json_names_the_version(self):
        self.assertEqual(versions.of_binary(self.npm("2.1.284")), "2.1.284")

    def test_the_native_layout_still_wins_from_the_path(self):
        self.assertEqual(
            versions.of_binary("/home/u/.local/share/claude/versions/2.1.9-beta/claude"),
            "2.1.9-beta")

    def test_a_package_json_for_something_else_is_not_a_version(self):
        """It is checked by NAME. A stray manifest further up the tree describes
        something else, and its version would be a confident wrong answer where
        None is the honest one."""
        self.assertIsNone(versions.of_binary(self.npm("9.9.9", name="left-pad")))

    def test_a_bare_binary_is_unknown_not_its_basename(self):
        exe = os.path.join(self.tmp.name, "claude.exe")
        open(exe, "w").close()
        self.assertIsNone(versions.of_binary(exe))

    def test_a_corrupt_package_json_is_unknown(self):
        exe = self.npm("2.1.284")
        with open(os.path.join(os.path.dirname(os.path.dirname(exe)),
                               "package.json"), "w") as f:
            f.write("{not json")
        self.assertIsNone(versions.of_binary(exe))

    def test_from_path_stays_pure(self):
        """`of_binary` reads the filesystem; `from_path` must not start to. The
        tests above pin layouts that do not exist on the machine running them,
        which only works while the pure one stays pure."""
        self.assertIsNone(versions.from_path(self.npm("2.1.284")))


class ABinaryReplacedUnderARunningSession(unittest.TestCase):
    """An npm upgrade overwrites the binary in place, and `/proc/<pid>/exe` then
    reads `... (deleted)`.

    The `package.json` beside it now describes the NEW binary. Reading it would
    report a session still running the old one as already upgraded -- a straggler
    rendered current, which is the single error an upgrade roll must not make.
    It is None instead.

    The native layout is unaffected and must stay so: it keeps versions side by
    side, so a deleted path still names the version it always named, and folding
    the two together would lose a fact that is still available.
    """
    def test_an_npm_binary_replaced_in_place_is_unknown(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        pkg = os.path.join(tmp.name, "node_modules", "@anthropic-ai", "claude-code")
        os.makedirs(os.path.join(pkg, "bin"))
        with open(os.path.join(pkg, "package.json"), "w") as f:
            json.dump({"name": "@anthropic-ai/claude-code", "version": "2.1.296"}, f)
        exe = os.path.join(pkg, "bin", "claude.exe")
        open(exe, "w").close()
        with mock.patch.object(os, "readlink", lambda p: exe + " (deleted)"):
            self.assertIsNone(versions.of_pid(1234))
        # and the same binary, not deleted, still answers
        with mock.patch.object(os, "readlink", lambda p: exe):
            self.assertEqual(versions.of_pid(1234), "2.1.296")

    def test_a_deleted_native_path_still_names_its_version(self):
        with mock.patch.object(os, "readlink",
                               lambda p: "/s/claude/versions/2.1.270 (deleted)"):
            self.assertEqual(versions.of_pid(1234), "2.1.270")


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


class WhichClaudeAFreshSessionWouldLaunch(unittest.TestCase):
    """`installed()` with no argument searches, because the native symlink is not
    the answer on every machine -- on an npm install there is no
    `~/.local/bin/claude` at all. `fleetupgrade` passed that path explicitly and
    so reported nothing rather than the version sitting on PATH.
    """
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        versions._spoken_cache.clear()
        self.addCleanup(versions._spoken_cache.clear)

    def exe(self, name="claude"):
        p = os.path.join(self.tmp.name, name)
        open(p, "w").close()
        return p

    def test_the_binary_on_path_is_preferred_to_the_native_default(self):
        native = "/home/u/.local/share/claude/versions/1.0.0/claude"
        with mock.patch.object(versions.shutil, "which",
                               lambda n: "/n/versions/2.1.296/claude"), \
             mock.patch.object(versions, "CLAUDE", native):
            self.assertEqual(versions.installed(), "2.1.296")

    def test_it_falls_back_to_the_native_default(self):
        with mock.patch.object(versions.shutil, "which", lambda n: None), \
             mock.patch.object(versions, "CLAUDE", "/n/versions/2.1.280/claude"):
            self.assertEqual(versions.installed(), "2.1.280")

    def test_the_binary_is_asked_only_when_the_layout_says_nothing(self):
        """A process launch per call, and `fleetboard --watch` calls this every
        redraw -- so it is the last source, not the first."""
        run = mock.Mock(return_value=mock.Mock(stdout="2.1.284 (Claude Code)\n"))
        with mock.patch.object(versions.shutil, "which", lambda n: None), \
             mock.patch.object(versions, "CLAUDE", "/n/versions/2.1.280/claude"), \
             mock.patch.object(versions.subprocess, "run", run):
            self.assertEqual(versions.installed(), "2.1.280")
        run.assert_not_called()

    def test_asking_the_binary_when_the_layout_is_silent(self):
        exe = self.exe()
        run = mock.Mock(return_value=mock.Mock(stdout="2.1.284 (Claude Code)\n"))
        with mock.patch.object(versions.shutil, "which", lambda n: exe), \
             mock.patch.object(versions.subprocess, "run", run):
            self.assertEqual(versions.installed(), "2.1.284")
        self.assertEqual(run.call_args[0][0], [exe, "--version"])

    def test_the_spoken_version_is_cached_against_the_binary(self):
        """One `stat` per draw instead of one `exec`. The cache is keyed on size
        and mtime, which an in-place upgrade changes by construction -- so a
        watched board still notices an upgrade under it, which is the whole
        lesson of the configuration it used to hold at import."""
        exe = self.exe()
        run = mock.Mock(return_value=mock.Mock(stdout="2.1.284\n"))
        with mock.patch.object(versions.shutil, "which", lambda n: exe), \
             mock.patch.object(versions.subprocess, "run", run):
            self.assertEqual(versions.installed(), "2.1.284")
            self.assertEqual(versions.installed(), "2.1.284")
            self.assertEqual(run.call_count, 1, "re-execed a binary that had not changed")

            # the upgrade lands in place: same path, new content
            with open(exe, "w") as f:
                f.write("newer")
            os.utime(exe, (0, 0))
            run.return_value = mock.Mock(stdout="2.1.296\n")
            self.assertEqual(versions.installed(), "2.1.296",
                             "an in-place upgrade was served from the cache")

    def test_a_banner_without_a_version_is_unknown(self):
        """Anchored at the start, so prose cannot donate a number from the middle
        of a sentence."""
        exe = self.exe()
        run = mock.Mock(return_value=mock.Mock(stdout="error: run 2.1.284 to fix\n"))
        with mock.patch.object(versions.shutil, "which", lambda n: exe), \
             mock.patch.object(versions.subprocess, "run", run):
            self.assertIsNone(versions.installed())

    def test_a_binary_that_hangs_or_dies_is_unknown_not_a_crash(self):
        exe = self.exe()
        for boom in (OSError("no"), versions.subprocess.TimeoutExpired("claude", 10)):
            versions._spoken_cache.clear()
            with mock.patch.object(versions.shutil, "which", lambda n: exe), \
                 mock.patch.object(versions.subprocess, "run",
                                   mock.Mock(side_effect=boom)):
                self.assertIsNone(versions.installed(), boom)

    def test_an_explicit_path_is_used_as_given(self):
        """The tests above pin layouts that are not installed on this machine,
        which only works while an explicit argument bypasses the search."""
        with mock.patch.object(versions.shutil, "which",
                               lambda n: "/n/versions/9.9.9/claude"):
            self.assertEqual(versions.installed("/s/versions/1.2.3"), "1.2.3")


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
