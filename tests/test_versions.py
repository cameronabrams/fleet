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
import time
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


class RecordingThatASessionMovedOntoABinary(unittest.TestCase):
    """Every route onto a new binary has to reach one file, or the file lies by
    omission.

    `fleetspawn` launches with whatever `claude` resolves to -- there is no version
    argument and none is wanted -- so an unpark silently adopts the newest release.
    On 2026-10-16 the auto-roll log recorded `rolled=none skipped=15` at 09:50 and
    a session went onto an 18-hour-old release at 09:51, by a route the log could
    not see. The fleet's entire version spread was unparks, not rolls.

    It is the auto-roll's own log and not a new one, deliberately: a second file
    would have said `rolled=none` twice.
    """
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def lines(self):
        with open(os.path.join(self.tmp.name, versions.ADOPTION_LOG)) as f:
            return [l.strip() for l in f if l.strip()]

    def test_it_appends_rather_than_replacing(self):
        """A log that forgets the last adoption cannot answer the question it
        exists for."""
        for n in ("alpha", "beta"):
            self.assertIsNone(versions.record_adoption(
                self.tmp.name, n, "2.1.301", "parked", "unpark",
                installed_version="2.1.301"))
        self.assertEqual(len(self.lines()), 2)
        self.assertIn("rolled=beta", self.lines()[1])

    def test_the_line_carries_what_a_reader_greps_for(self):
        versions.record_adoption(self.tmp.name, "alpha", "2.1.301", "parked",
                                 "unpark", installed_version="2.1.301")
        line = self.lines()[0]
        for field in ("installed=2.1.301", "rolled=alpha", "from=parked",
                      "to=2.1.301", "note=unpark"):
            self.assertIn(field, line, line)

    def test_an_unknown_version_is_a_question_mark_not_an_omission(self):
        """A missing `to=` would read as a line somebody forgot to finish. `?` is
        this repository's word for a source that could not be read, and the field
        order has to survive a reader that splits on it."""
        versions.record_adoption(self.tmp.name, "alpha", None, None, "unpark",
                                 installed_version="2.1.301")
        self.assertIn("to=?", self.lines()[0])
        self.assertIn("from=?", self.lines()[0])

    def test_a_log_that_cannot_be_written_is_reported_not_raised(self):
        """The caller is a tool that has just brought a session up. Failing the
        launch over a bookkeeping fault would turn it into a fleet fault, and the
        obvious repair -- launch again -- is the damaging one."""
        problem = versions.record_adoption("/proc/nowhere/at/all", "alpha",
                                           "2.1.301", "parked", "unpark")
        self.assertIsNotNone(problem)
        self.assertIn("could not write", problem)

    def test_it_creates_the_state_directory(self):
        d = os.path.join(self.tmp.name, "state-not-made-yet")
        self.assertIsNone(versions.record_adoption(d, "alpha", "2.1.301", "new",
                                                   "spawn", installed_version="x"))
        self.assertTrue(os.path.exists(os.path.join(d, versions.ADOPTION_LOG)))


class SomeCallersMayNotLaunchAProcess(unittest.TestCase):
    """`installed()`'s last resort is running `claude --version`. Two callers must
    never do that, and neither is obvious from the call site.

    `fleetrestore` is the recovery path, where the repository's first rule is that
    nothing may need anything else to work first; `record_adoption` writes one log
    line, which is never worth an exec. Both were added on 2026-10-16 calling the
    executing form, and the restore's end-to-end test caught it -- its fake
    `claude` recorded a `--version` call that displaced a real launch.
    """
    def setUp(self):
        versions._spoken_cache.clear()
        self.addCleanup(versions._spoken_cache.clear)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.exe = os.path.join(self.tmp.name, "claude")
        open(self.exe, "w").close()

    def test_ask_binary_false_returns_none_rather_than_running_it(self):
        run = mock.Mock(return_value=mock.Mock(stdout="2.1.301\n"))
        with mock.patch.object(versions.shutil, "which", lambda n: self.exe), \
             mock.patch.object(versions.subprocess, "run", run):
            self.assertIsNone(versions.installed(ask_binary=False))
        run.assert_not_called()

    def test_the_layout_still_answers_without_asking(self):
        """Pure does not mean blind: a path that names its version needs no exec,
        and that is the common case."""
        with mock.patch.object(versions.shutil, "which",
                               lambda n: "/s/versions/2.1.301/claude"):
            self.assertEqual(versions.installed(ask_binary=False), "2.1.301")

    def test_recording_an_adoption_never_execs(self):
        run = mock.Mock(return_value=mock.Mock(stdout="2.1.301\n"))
        with mock.patch.object(versions.shutil, "which", lambda n: self.exe), \
             mock.patch.object(versions.subprocess, "run", run):
            versions.record_adoption(self.tmp.name, "alpha", "2.1.301", "parked",
                                     "unpark")
        run.assert_not_called()
        with open(os.path.join(self.tmp.name, versions.ADOPTION_LOG)) as f:
            self.assertIn("installed=?", f.read())

    def test_the_default_still_asks(self):
        """The flag is opt-out, not a change of behavior: `fleetboard` and
        `fleetupgrade` want the answer and an npm install only has it from the
        binary."""
        run = mock.Mock(return_value=mock.Mock(stdout="2.1.301\n"))
        with mock.patch.object(versions.shutil, "which", lambda n: self.exe), \
             mock.patch.object(versions.subprocess, "run", run):
            self.assertEqual(versions.installed(), "2.1.301")
        run.assert_called_once()

    def test_the_recovery_path_does_not_call_the_executing_form(self):
        """Stated as the invariant, not as a count.

        It was `count(...) == 2`, which broke the moment the two call sites were
        collapsed into one -- for a change that did not touch this property at
        all. A test that fails when correct code is rearranged gets loosened by
        whoever is in a hurry, and then it guards nothing.
        """
        import ast
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "bin", "fleetrestore")).read()
        calls = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)
                 and ast.unparse(n.func) == "versions.installed"]
        self.assertTrue(calls, "fleetrestore stopped reading the installed version")
        for c in calls:
            kw = {k.arg: ast.literal_eval(k.value) for k in c.keywords
                  if k.arg and isinstance(k.value, ast.Constant)}
            self.assertIs(kw.get("ask_binary"), False,
                          "the recovery path may not run `claude --version`: "
                          + ast.unparse(c))


class TheNewestVersionThatHasSoaked(unittest.TestCase):
    """The soak gate could not open. Releases land about every 25 hours here
    (median gap 25.2 h, measured 2026-10-17) and eligibility read the age of the
    NEWEST version, so each release reset the clock the 24-hour gate was reading.
    Two fires, two days, zero eligible -- a log accumulating clean lines that read
    as a healthy mechanism waiting for its moment, with nothing saying the moment
    could not arrive.

    The soak's intent is *do not be the first here to run a fresh binary*. That is
    satisfied by some version every day, just not by the newest one. So the target
    is the newest version that HAS soaked, which keeps the intent, opens the gate
    daily, and degrades when releases speed up rather than latching shut.
    """
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = os.path.join(self.tmp.name, "share", "claude", "versions")
        os.makedirs(self.dir)
        self.link = os.path.join(self.tmp.name, "claude")

    def put(self, name, age_h):
        p = os.path.join(self.dir, name)
        open(p, "w").close()
        t = time.time() - age_h * 3600
        os.utime(p, (t, t))
        return p

    def point_at(self, name):
        if os.path.lexists(self.link):
            os.remove(self.link)
        os.symlink(os.path.join(self.dir, name), self.link)

    def test_it_skips_the_newest_and_takes_the_one_behind_it(self):
        self.put("2.1.301", 43.7)
        self.put("2.1.302", 17.9)                  # the real machine, 2026-10-17
        self.point_at("2.1.302")
        self.assertEqual(versions.soaked(24, self.link)[0], "2.1.301")

    def test_newest_by_version_number_not_by_mtime(self):
        """The two orders normally agree and must not be assumed to. A re-download
        touches the file, so a high version number can be the youngest thing in
        the directory -- and a file just rewritten has not soaked.

        The directory order is FORCED, because `os.listdir` order is arbitrary:
        a version of this that relied on it passed against code taking whatever
        it saw first, which is the bug and not the fix.
        """
        self.put("2.1.299", 200.0)
        self.put("2.1.300", 30.0)
        self.put("2.1.301", 1.0)                   # re-downloaded an hour ago
        self.point_at("2.1.301")
        with mock.patch.object(versions.os, "listdir",
                               lambda d: ["2.1.299", "2.1.300", "2.1.301"]):
            self.assertEqual(versions.soaked(24, self.link)[0], "2.1.300")
        # and the other way round, so neither order can carry the answer
        with mock.patch.object(versions.os, "listdir",
                               lambda d: ["2.1.301", "2.1.300", "2.1.299"]):
            self.assertEqual(versions.soaked(24, self.link)[0], "2.1.300")

    def test_it_never_goes_newer_than_the_installer_points_at(self):
        """A symlink moved back is a deliberate downgrade. Rolling past it would
        overrule that choice with a file left lying in the directory."""
        self.put("2.1.299", 200.0)
        self.put("2.1.302", 200.0)
        self.point_at("2.1.299")
        self.assertEqual(versions.soaked(24, self.link)[0], "2.1.299")

    def test_nothing_soaked_is_none_not_the_newest_anyway(self):
        """A fresh machine with one release on it. The caller launches plain
        `claude`: refusing to start a session because nothing has soaked is a far
        worse outcome than starting one on a fresh binary."""
        self.put("2.1.302", 2.0)
        self.point_at("2.1.302")
        self.assertEqual(versions.soaked(24, self.link), (None, None))

    def test_a_file_that_is_not_a_version_is_never_chosen(self):
        self.put("2.1.299", 200.0)
        self.put("README", 200.0)
        self.put("tmp-download", 200.0)
        self.point_at("2.1.299")
        self.assertEqual(versions.soaked(24, self.link)[0], "2.1.299")

    def test_the_path_returned_is_the_one_to_launch(self):
        p = self.put("2.1.299", 200.0)
        self.point_at("2.1.299")
        self.assertEqual(versions.soaked(24, self.link)[1], p)

    def test_an_npm_install_has_no_store_and_no_target(self):
        """One binary, upgraded in place: there is no history to choose from, and
        the honest answer is that this layout has none."""
        pkg = os.path.join(self.tmp.name, "node_modules", "@anthropic-ai",
                           "claude-code", "bin")
        os.makedirs(pkg)
        exe = os.path.join(pkg, "claude")
        open(exe, "w").close()
        self.assertIsNone(versions.store(exe))
        self.assertEqual(versions.soaked(24, exe), (None, None))

    def test_a_missing_store_is_none_not_a_crash(self):
        self.assertIsNone(versions.store("/nowhere/at/all/claude"))
        self.assertEqual(versions.soaked(24, "/nowhere/at/all/claude"), (None, None))
