"""fleetboard renders derived state, and must never render a failure as a pass.

The board was written outside this repository and moved in on 2026-10-04. It had
no tests, and the dependency it most needed one for crossed a repository
boundary: on 2026-10-03 `fleetsnap`'s housekeeping renamed its cache and the
board went blind, with CI on only one side of the seam.

Both regressions pinned here are of one kind -- a source that fails must reach
the screen as unknown. That is the board's own stated rule, and it was broken in
two places on arrival.
"""
import json, os, time, unittest
from unittest import mock
from tests.support import APP, BASE_TOML, FakeConfig, load_tool


class SourceFailureIsNeverAPass(unittest.TestCase):
    """The rule the board states in its own docstring, tested on both sources."""

    def setUp(self):
        self.cfg = FakeConfig()
        self.b = load_tool("fleetboard")

    def tearDown(self):
        self.cfg.close()

    def watch_json(self, payload):
        """Stand in for `fleetwatch --json`, leaving fleetcontext unreadable."""
        def run_json(cmd, timeout=120):
            if "fleetwatch" in cmd[0]:
                return payload
            return None
        return mock.patch.object(self.b, "run_json", run_json)

    def test_a_failed_cluster_query_is_unknown_work_not_no_work(self):
        """The defect the move was worth doing for, and it needed nobody to
        change anything -- it was wrong whenever the cluster was unreachable.

        `fleetwatch` prints a banner and exits 0 when its ssh query fails. The
        board used to read the DISPLAY table by column, found no rows that began
        with a digit, and recorded an empty job list. An unreachable cluster drew
        as a blank work column for every session: a calm fleet. `cluster_ok` is a
        field in `--json`; a banner is not."""
        with self.watch_json({"cluster_ok": False, "jobs": []}):
            jobs, notes = self.b.jobs_and_notes()
        self.assertIsNone(jobs, "a failed cluster query must be UNKNOWN, not []")
        self.assertTrue(any("UNKNOWN" in n or "unknown" in n for n in notes), notes)

    def test_live_work_with_no_watcher_is_still_reported(self):
        with self.watch_json({"cluster_ok": True,
                              "jobs": [{"job": "1", "tasks": 4, "owner": "a",
                                        "watched_by": []}]}):
            jobs, notes = self.b.jobs_and_notes()
        self.assertEqual(jobs, [{"job": "1", "tasks": 4, "owner": "a", "watched": False}])
        self.assertIn("live work with no watcher", notes)

    def test_a_job_that_ended_badly_is_surfaced(self):
        """It is over, so it holds no watcher and appears in no live row. The
        only trace is `finished_watchers`, and `_states` is part of that
        contract -- prefixed to stay out of the registration file's own key
        namespace, not because it is private."""
        with self.watch_json({"cluster_ok": True, "jobs": [],
                              "finished_watchers": [{"session": "s", "job": "9",
                                                     "_states": "FAILED"}]}):
            _, notes = self.b.jobs_and_notes()
        self.assertTrue(any("ended FAILED" in n for n in notes), notes)

    def test_a_completed_job_is_not_an_alarm(self):
        """Crying about every finished campaign trains everyone to ignore it."""
        with self.watch_json({"cluster_ok": True, "jobs": [],
                              "finished_watchers": [{"session": "s", "job": "9",
                                                     "_states": "COMPLETED"}]}):
            _, notes = self.b.jobs_and_notes()
        self.assertEqual(notes, [])

    def test_an_unreadable_source_is_unknown(self):
        with mock.patch.object(self.b, "run_json", lambda *a, **k: None):
            jobs, notes = self.b.jobs_and_notes()
            self.assertIsNone(jobs)
            self.assertIsNone(self.b.context())


class CacheIsEvidenceNotTruth(unittest.TestCase):
    """The regression coord asked to see pinned first: a cache that is missing or
    unreadable renders `?` and never a pass."""

    def setUp(self):
        self.cfg = FakeConfig()
        self.b = load_tool("fleetboard")

    def tearDown(self):
        self.cfg.close()

    def test_a_missing_cache_loads_as_none(self):
        self.assertIsNone(self.b.load_cache())

    def test_an_unreadable_cache_loads_as_none_not_empty(self):
        """`{}` would mean "asked and there is nothing"; None means "did not
        ask". Only the second is true here, and only the second draws `?`."""
        os.makedirs(os.path.dirname(self.b.CACHE), exist_ok=True)
        with open(self.b.CACHE, "w") as f:
            f.write("{not json")
        self.assertIsNone(self.b.load_cache())

    def test_the_cache_is_under_a_subdirectory_it_owns(self):
        """The state directory root is shared. The cache sat in it until
        2026-10-03, when another tool's housekeeping renamed it."""
        self.assertEqual(os.path.basename(os.path.dirname(self.b.CACHE)), "cache")
        self.assertTrue(self.b.CACHE.startswith(self.cfg.state))

    def test_a_watched_board_refreshes_a_cache_older_than_the_window(self):
        """A watched display that ages one measurement forever survives its own
        data loss -- which is how the 2026-10-03 blinding went an hour without
        being noticed. It re-runs the slow sources instead."""
        self.assertLessEqual(self.b.REFRESH, 900)
        os.makedirs(os.path.dirname(self.b.CACHE), exist_ok=True)
        with open(self.b.CACHE, "w") as f:
            json.dump({"at": time.time() - (self.b.REFRESH + 60),
                       "jobs": [], "ctx": {}, "notes": []}, f)
        called = []
        with mock.patch.object(self.b, "refresh_cache",
                               lambda: called.append(1) or {"at": time.time(), "jobs": [],
                                                            "ctx": {}, "notes": []}), \
             mock.patch.object(self.b, "panes", lambda: {}), \
             mock.patch.object(self.b, "agents", lambda: {}):
            self.b.draw(full=False, auto=True)
        self.assertEqual(called, [1], "a stale cache under --watch must be refreshed")


class ItDeclaresNothing(unittest.TestCase):
    """The board renders state the fleet already derives. A design where sessions
    declare and register their own status was refused on 2026-10-03, and moving
    this tool into the app must not become a way back to it."""

    def test_it_only_reads(self):
        src = open(os.path.join(APP, "bin", "fleetboard")).read()
        # Its own cache is the one thing it writes, and that is a cache: derived,
        # stamped, and rebuilt from the sources whenever it is missing or old.
        writes = [l.strip() for l in src.splitlines()
                  if ('open(' in l and '"w"' in l) or "makedirs" in l]
        self.assertTrue(all("CACHE" in w or "os.path.dirname(CACHE)" in w for w in writes),
                        f"fleetboard may only write its own cache: {writes}")
        for forbidden in ("tmux set", "send-keys", "kill-pane", "--go"):
            self.assertNotIn(forbidden, src,
                             f"a board renders; it does not {forbidden!r}")


if __name__ == "__main__":
    unittest.main()


class TheVersionColumn(unittest.TestCase):
    """Which binary each session runs, against the one installed.

    A session keeps running the binary it started with; upgrading `claude`
    changes nothing for a session already up. There is no outward sign of that
    from inside the session, which is why it belongs on a board rather than in
    anyone's memory.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.b = load_tool("fleetboard")
        # Named colors, so an assertion says WHICH color rather than matching
        # an escape code. The real table is empty off a tty, which would make
        # every color assertion below pass against uncolored output.
        self.b.C = dict.fromkeys(self.b.C, "")
        self.b.C.update({"yel": "<STALE>", "dim": "<DIM>", "r": "<->", "b": "",
                         "red": "<RED>"})

    def tearDown(self):
        self.cfg.close()

    def board(self, agents, installed, per_pid, target=-1):
        """Draw with every slow source absent; only versions are under test.

        `target` defaults to `installed`, which is what every test written before
        2026-10-17 assumed. The two are different every day now, and staleness is
        measured against the TARGET -- the newest release that has soaked."""
        if target == -1:
            target = installed
        panes = {n: {"win": "1", "winname": "w", "pane": "%1",
                     "quiet": False, "current": False} for n in agents}
        import io, contextlib
        with mock.patch.object(self.b, "panes", lambda: panes), \
             mock.patch.object(self.b, "agents", lambda: agents), \
             mock.patch.object(self.b, "load_cache", lambda: None), \
             mock.patch.object(self.b.versions, "installed", lambda *a, **k: installed), \
             mock.patch.object(self.b.versions, "target",
                               lambda *a, **k: (target, "/v/%s" % target)), \
             mock.patch.object(self.b.versions, "of_pid", lambda pid: per_pid.get(pid)):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.b.draw()
            return buf.getvalue()

    @staticmethod
    def plain(text):
        """The output with the color markers removed -- what a reader sees.

        Asserting on the raw string tests byte adjacency instead: the header
        renders `claude <->2.1.292<DIM> installed<->`, so a literal
        `"2.1.292 installed"` is absent from output that displays exactly that.
        """
        import re as _re
        return _re.sub(r"<[A-Za-z>-]*>", "", text)

    AGENTS = {"alpha": {"status": "idle", "pid": 11},
              "beta":  {"status": "idle", "pid": 22}}

    def test_the_installed_version_is_stated_once_at_the_top(self):
        out = self.plain(self.board(self.AGENTS, "2.1.292",
                                    {11: "2.1.292", 22: "2.1.292"}))
        self.assertIn("2.1.292 installed", out)
        self.assertEqual(out.count("installed"), 1,
                         "the installed version is stated once, not per row")

    def test_a_session_on_the_target_is_not_stale_though_it_is_behind_installed(self):
        """The whole point of the 2026-10-17 change, and the trap in it.

        The fleet runs the newest SOAKED release, so a correctly rolled session is
        behind `installed` every single day. Measuring staleness against
        `installed` would mark the entire fleet stale permanently -- a column that
        is wrong exactly when the mechanism is working.
        """
        out = self.board(self.AGENTS, "2.1.302", {11: "2.1.301", 22: "2.1.299"},
                         target="2.1.301")
        on_target = [l for l in out.splitlines() if l.strip().startswith("alpha")][0]
        behind = [l for l in out.splitlines() if l.strip().startswith("beta")][0]
        self.assertNotIn("<STALE>", on_target, on_target)
        self.assertIn("<STALE>2.1.299", behind)

    def test_the_header_names_both_numbers(self):
        """They answer different questions and neither stands in for the other.
        Printing only `installed` is how a gate that could never open stayed
        invisible for two days."""
        out = self.board(self.AGENTS, "2.1.302", {11: "2.1.301"}, target="2.1.301")
        head = out.splitlines()[1]
        self.assertIn("2.1.302", head)
        self.assertIn("2.1.301", head)
        self.assertIn("target", head)

    def test_a_session_behind_the_installed_binary_is_colored(self):
        out = self.board(self.AGENTS, "2.1.292", {11: "2.1.291", 22: "2.1.292"})
        stale = [l for l in out.splitlines() if l.strip().startswith("alpha")][0]
        fresh = [l for l in out.splitlines() if l.strip().startswith("beta")][0]
        self.assertIn("<STALE>2.1.291", stale)
        self.assertNotIn("<STALE>", fresh)
        self.assertIn("2.1.292", fresh)

    def test_an_unknown_version_is_a_question_mark_and_not_an_alarm(self):
        """Absence is `?`, the board's rule. It is also not colored as stale:
        coloring it would send someone to upgrade a session over a source that
        failed, and the palette's red is reserved for a source that failed."""
        out = self.board(self.AGENTS, "2.1.292", {11: None, 22: "2.1.292"})
        row = [l for l in out.splitlines() if l.strip().startswith("alpha")][0]
        self.assertIn("?", row)
        self.assertNotIn("<STALE>", row)

    def test_an_unreadable_installed_version_colors_nothing_stale(self):
        """If the installed version cannot be read, every comparison is unknown.
        Marking the whole fleet stale on a failed readlink is the same class of
        error as marking it current -- a board acting on a source it did not get."""
        out = self.board(self.AGENTS, None, {11: "2.1.291", 22: "2.1.292"})
        self.assertNotIn("<STALE>", out)
        self.assertIn("? installed", self.plain(out))


PARKED_TOML = BASE_TOML + '''
[parked.old-talk]
uuid  = "aaaaaaaa-1111-4111-8111-111111111111"
since = "2026-09-22"
cwd   = "/home/u/Git/talks/old"

[retired.gone-for-good]
uuid  = "bbbbbbbb-2222-4222-8222-222222222222"
since = "2026-09-01"
cwd   = "/home/u/Git/gone"
'''


class CwdAndParked(unittest.TestCase):
    """A directory column, and the parked sessions under a rule below the table.

    Parked is a DECLARATION -- `[parked.<name>]` in the configuration -- which is
    why it can be shown for a session with no process and no pane. That also makes
    it a different kind of row from everything above the rule, and the two must
    not read as one list whose last entries happen to be quiet.
    """
    def setUp(self):
        self.cfg = FakeConfig(toml=PARKED_TOML)
        self.b = load_tool("fleetboard")
        self.b.C = dict.fromkeys(self.b.C, "")

    def tearDown(self):
        self.cfg.close()

    def board(self, agents, cols=170, show_parked=True):
        """`show_parked=True` by default HERE, because this class is about the
        parked rows themselves. The board counts them instead since 2026-10-21 --
        twelve of them were fourteen lines of a thirty-six-line board, all of it
        durable, while the rows that change sat below the fold."""
        panes = {n: {"win": "1", "winname": "w", "pane": "%1",
                     "quiet": False, "current": False} for n in agents}
        import io, contextlib
        with mock.patch.object(self.b, "panes", lambda: panes), \
             mock.patch.object(self.b, "agents", lambda: agents), \
             mock.patch.object(self.b, "load_cache", lambda: None), \
             mock.patch.object(self.b.shutil, "get_terminal_size",
                               lambda d=None: os.terminal_size((cols, 24))), \
             mock.patch.object(self.b.versions, "installed", lambda *a, **k: "2.1.0"), \
             mock.patch.object(self.b.versions, "of_pid", lambda pid: "2.1.0"):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.b.draw(show_parked=show_parked)
            return buf.getvalue()

    LIVE = {"alpha": {"status": "idle", "pid": 11, "cwd": "/home/u/Git/alpha"}}

    def test_the_cwd_column_shows_each_agents_directory(self):
        out = self.board(self.LIVE)
        # Found, not indexed. This read `splitlines()[2]` and broke the day the
        # time-sensitive lines moved above the table -- an assertion that depends
        # on how many rows happen to precede the one it means.
        self.assertTrue(any("cwd" in l and "session" in l for l in out.splitlines()),
                        "the live table's column header is missing")
        row = next(l for l in out.splitlines() if l.strip().startswith("alpha"))
        self.assertIn("/home/u/Git/alpha", row)

    def test_a_home_directory_is_abbreviated(self):
        with mock.patch.object(self.b, "HOME", "/home/u"):
            out = self.board({"alpha": {"status": "idle", "pid": 11,
                                        "cwd": "/home/u/Git/alpha"}})
        row = next(l for l in out.splitlines() if l.strip().startswith("alpha"))
        self.assertIn("~/Git/alpha", row)

    def test_a_long_path_is_cut_from_the_left(self):
        """Paths are distinctive at the end. Two sessions under one project dir
        agree in the first components and differ in the last, so a right-hand cut
        makes the column widest exactly where it stops telling them apart."""
        got = self.b.short_path("/mnt/storage1/u/research/cyanate-esters", 20)
        self.assertEqual(len(got), 20)
        self.assertTrue(got.endswith("cyanate-esters"), got)
        self.assertTrue(got.startswith("…"), got)

    def test_an_agent_with_no_reported_cwd_is_blank_not_a_question_mark(self):
        """`?` is this board's word for a source that failed, and that has already
        been said in `state` for an agent the listing does not hold. Repeating it
        here would claim a second failure."""
        out = self.board({"alpha": {"status": "idle", "pid": 11}})
        row = next(l for l in out.splitlines() if l.strip().startswith("alpha"))
        # The cwd FIELD, not the whole row: `ctx` and `work` legitimately print
        # `?` here, because no cache was loaded. Asserting over the whole row
        # caught those and said the cwd column was at fault.
        head = next(l for l in out.splitlines() if l.lstrip().startswith("session"))
        start = head.index("cwd")
        self.assertEqual(row[start:start + 42].strip(), "", repr(row))

    def test_parked_survives_another_fleets_panes_being_on_screen(self):
        """The parked ROWS live in the same block as their heading, and that block
        used to be an `elif` on a dim line about panes with no `@fleet` -- so one
        unstamped pane would have taken the whole parked section off the board,
        heading and all, for a reason that had nothing to do with parking.

        Honest about what this proves: by the time the coupling was found the
        branch above it was already unreachable, because strict membership means
        there is no "assumed ours" line left to print. This is a guard against
        putting the coupling back, not a reproduction of a live failure."""
        self.b.foreign[:] = [("stranger", "teaching"), ("nameless", "")]
        out = self.board(self.LIVE)
        self.assertIn("parked (", out)
        self.assertIn("not this fleet (2)", out)
        self.assertIn("nameless@(no @fleet)", out,
                      "an unstamped pane must not render as a fleet named ''")

    def test_parked_sessions_appear_under_a_rule(self):
        out = self.board(self.LIVE)
        lines = out.splitlines()
        rule = next(i for i, l in enumerate(lines) if set(l.strip()) == {"─"})
        head = next(i for i, l in enumerate(lines) if l.strip().startswith("parked ("))
        live = next(i for i, l in enumerate(lines) if l.strip().startswith("alpha"))
        park = next(i for i, l in enumerate(lines) if l.strip().startswith("old-talk"))
        self.assertLess(live, rule, "the rule must come after the live table")
        self.assertLess(rule, head)
        self.assertLess(head, park)
        self.assertIn("/home/u/Git/talks/old", lines[park])
        self.assertIn("2026-09-22", lines[park])

    def test_a_parked_row_claims_no_runtime(self):
        """It has none, and `?` would say it was unknown rather than absent."""
        out = self.board(self.LIVE)
        row = next(l for l in out.splitlines() if l.strip().startswith("old-talk"))
        for word in ("?", "idle", "busy", "2.1.0"):
            self.assertNotIn(word, row, f"{word!r} in {row!r}")
        # A context figure, matched as one. The first version of this looked for
        # the substring "k " and found it in "talks/old" -- a test that fails on
        # the data rather than on the behavior.
        import re as _re
        self.assertIsNone(_re.search(r"\b\d+k\b", row), row)

    def test_a_retired_session_is_not_listed(self):
        """Retired is not coming back; a board is about what might."""
        out = self.board(self.LIVE)
        self.assertNotIn("gone-for-good", out)
        self.assertIn("parked (1)", out)

    def test_a_session_both_running_and_declared_parked_is_flagged(self):
        """Two sources disagreeing. Drawing it in both places without a word would
        let an undeclared unpark look like an ordinary board."""
        out = self.board({"old-talk": {"status": "idle", "pid": 11,
                                       "cwd": "/home/u/Git/talks/old"}})
        self.assertIn("ALSO RUNNING", out)

    def test_an_unreadable_configuration_says_so(self):
        """Not an empty list. `{}` would draw as "nothing is parked", which is the
        board's own rule about a failed source read backwards."""
        with mock.patch.object(self.b.fc, "stopped",
                               mock.Mock(side_effect=OSError("boom"))):
            out = self.board(self.LIVE)
        self.assertIn("could not be read", out)
        self.assertNotIn("parked (", out)


class TheConfigurationIsReReadEachDraw(unittest.TestCase):
    """Parking is a human DECLARATION, and a watched board outlives it.

    `fleetboard --watch` redraws every N seconds for as long as it is left up.
    The configuration was read once, at import, so a session unparked after the
    board started stayed in the parked list for the life of the process. Found
    2026-10-09 on a watcher 21h50m old: `site-repo` had been unparked, was drawn
    correctly in the live table, and was still listed under `parked (10)`.

    **The `ALSO RUNNING` flag fired on it** -- which is the flag for a session
    running while declared parked, a disagreement between two sources. The
    disagreement was real and both sources were the board's: a live reading of
    tmux against a 22-hour-old reading of a file. A check that reports its own
    staleness as the fleet's is worse than no check, because it looks like
    evidence about something else.

    The slow sources here are cached ON PURPOSE and shown with their age. A
    configuration file is neither slow nor observed, so it gets neither treatment.
    """
    def setUp(self):
        self.cfg = FakeConfig(toml=PARKED_TOML)
        self.b = load_tool("fleetboard")
        self.b.C = dict.fromkeys(self.b.C, "")

    def tearDown(self):
        self.cfg.close()

    def draw(self, show_parked=True):
        """Lists the parked rows, because what this class checks is that a session
        parked WHILE a `--watch` board is running shows up on the next draw --
        which is about re-reading the configuration, not about the count."""
        import io, contextlib
        agents = {"old-talk": {"status": "idle", "pid": 11, "cwd": "/home/u/x"}}
        panes = {"old-talk": {"win": "1", "winname": "w", "pane": "%1",
                              "quiet": False, "current": False}}
        with mock.patch.object(self.b, "panes", lambda: panes), \
             mock.patch.object(self.b, "agents", lambda: agents), \
             mock.patch.object(self.b, "load_cache", lambda: None), \
             mock.patch.object(self.b.versions, "installed", lambda *a, **k: "2.1.0"), \
             mock.patch.object(self.b.versions, "of_pid", lambda pid: "2.1.0"):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.b.draw(show_parked=show_parked)
            return buf.getvalue()

    def unpark_everything(self):
        """Rewrite fleet.toml exactly as a human unparking a session would."""
        import textwrap
        path = os.path.join(self.cfg.config, "fleet.toml")
        with open(path, "w") as f:
            f.write(textwrap.dedent(BASE_TOML).format(state=self.cfg.state))

    def test_a_session_unparked_after_the_board_started_leaves_the_list(self):
        first = self.draw()
        self.assertIn("old-talk", first)
        self.assertIn("parked (1)", first)
        self.assertIn("ALSO RUNNING", first)

        self.unpark_everything()
        again = self.draw()
        self.assertNotIn("parked (", again,
                         "the parked list was not re-read from the configuration")
        self.assertNotIn("ALSO RUNNING", again,
                         "the board flagged a disagreement it had created itself")
        self.assertIn("old-talk", again, "it must still be in the live table")

    def test_a_session_parked_after_the_board_started_appears(self):
        """The other direction, which no cache would catch either."""
        self.unpark_everything()
        self.assertNotIn("parked (", self.draw())
        with open(os.path.join(self.cfg.config, "fleet.toml"), "a") as f:
            f.write('\n[parked.late-one]\n'
                    'uuid  = "cccccccc-3333-4333-8333-333333333333"\n'
                    'since = "2026-10-09"\ncwd = "/home/u/late"\n')
        out = self.draw()
        self.assertIn("parked (1)", out)
        self.assertIn("late-one", out)

    def test_a_configuration_broken_mid_edit_does_not_crash_the_watcher(self):
        """Re-reading means reading a file a human may be halfway through saving.
        A watched board must survive that and say so, not exit on a parse error
        and take the screen down with it."""
        with open(os.path.join(self.cfg.config, "fleet.toml"), "w") as f:
            f.write("[parked.broken\nthis is not toml")
        out = self.draw()
        self.assertIn("could not be read", out)
        self.assertIn("old-talk", out, "the live table must still draw")


class TheStampCarriesTheDate(unittest.TestCase):
    """A clock alone cannot say whether a watched board is still drawing.

    The board is normally read on a long-lived `--watch` pane, glanced at rather
    than run. `14:22` on such a pane reads as current at 14:22 on any day, so a
    board that stopped redrawing looks exactly like one that just did -- and this
    board has frozen before (f5c7201, where a 22-hour-old read was presented as a
    live fact about the fleet).

    Two things are pinned: the date is in the stamp, and the stamp is taken on the
    draw. The second is the one that matters, and it is the same defect in a new
    place -- a value computed at import looks right for as long as anyone tests it
    in a fresh process.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.b = load_tool("fleetboard")
        self.b.C = dict.fromkeys(self.b.C, "")

    def tearDown(self):
        self.cfg.close()

    def draw(self):
        import io, contextlib
        with mock.patch.object(self.b, "panes", lambda: {}), \
             mock.patch.object(self.b, "agents", lambda: {}), \
             mock.patch.object(self.b, "load_cache", lambda: None), \
             mock.patch.object(self.b.versions, "installed", lambda *a, **k: "2.1.0"):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.b.draw()
            return buf.getvalue()

    def test_the_header_carries_the_date(self):
        head = self.draw().splitlines()[1]
        self.assertIn(time.strftime("%Y-%m-%d"), head, head)
        self.assertIn(time.strftime("%H:%M"), head, head)

    def test_the_stamp_is_taken_on_the_draw_not_at_import(self):
        """A board left up overnight must say so. Held still here by moving the
        clock between two draws of ONE already-imported module, which is what a
        `--watch` process does and what no fresh-process test can catch."""
        stamps = iter(["2026-10-13 14:22 EDT", "2026-10-14 14:22 EDT"])
        with mock.patch.object(self.b.time, "strftime",
                               lambda *a, **k: next(stamps)):
            first, second = self.draw(), self.draw()
        self.assertIn("2026-10-13", first)
        self.assertIn("2026-10-14", second,
                      "the stamp was frozen at the value of the first draw")
        self.assertNotIn("2026-10-13", second)


class PendingUpdatesAreASourceLikeAnyOther(unittest.TestCase):
    """A file some other program derives this machine's pending updates into.

    The board reads it and declares nothing, which is the same contract it holds
    for every other source -- a design in which the producer pushes status was
    considered and refused on 2026-10-03. The PATH is configuration, because it
    names a host and this repository may not.

    Every test here is about the same thing: **no failure may render as "up to
    date."** A missing file, an unparseable one, a schema this board has not been
    taught, a check that ran and failed, a check that stopped running -- each is a
    reason the board cannot say what is pending, and a board that answers
    "nothing" because its source went away is worse than one that says it does not
    know. Requested by a peer session 2026-10-19.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.b = load_tool("fleetboard")
        self.path = os.path.join(self.cfg.state, "status.json")
        self.addCleanup(self.cfg.close)

    def write(self, doc):
        with open(self.path, "w") as f:
            json.dump(doc, f)
        return self.path

    def read(self, doc=None, stale_hours=36, now=None):
        if doc is not None:
            self.write(doc)
        return self.b.read_updates(self.path, stale_hours, now=now)

    def fresh(self, **kw):
        d = {"schema": 1, "ok": True, "total": 0, "snapshot": "20261017",
             "checked_epoch": time.time() - 3600}
        d.update(kw)
        return d

    # -- the source failing ---------------------------------------------------

    def test_a_missing_file_is_unknown_not_up_to_date(self):
        state, data = self.b.read_updates(self.path, 36)
        self.assertEqual(state, "unknown")
        self.assertIn("cannot read", data["error"])

    def test_an_unparseable_file_is_unknown(self):
        with open(self.path, "w") as f:
            f.write("{not json")
        state, data = self.b.read_updates(self.path, 36)
        self.assertEqual(state, "unknown")
        self.assertIn("not readable JSON", data["error"])

    def test_a_file_that_is_not_an_object_is_unknown(self):
        state, _ = self.read([1, 2, 3])
        self.assertEqual(state, "unknown")

    def test_an_unknown_schema_is_unknown_not_read_anyway(self):
        """A producer this board has not been taught to read. Rendering its
        fields as "nothing pending" is the failure the whole tool is written
        against."""
        state, data = self.read(self.fresh(schema=2, total=0))
        self.assertEqual(state, "unknown")
        self.assertIn("schema 2", data["error"])

    def test_a_missing_schema_key_is_read_as_the_first_one(self):
        """The first producer's own example omits it. Treating absence as a
        mismatch would break the feature on the day it arrives, and absence here
        is a contract rather than a failed read.

        The key is REMOVED explicitly: `fresh()` supplies `schema: 1`, so a
        version of this that just called it asserted nothing and passed with
        absence treated as a mismatch.
        """
        d = self.fresh(total=4)
        d.pop("schema")
        self.assertNotIn("schema", d)
        self.assertEqual(self.read(d)[0], "ok")

    def test_a_check_that_failed_is_not_up_to_date(self):
        state, data = self.read({"schema": 1, "ok": False, "error": "repo unreachable"})
        self.assertEqual(state, "failed")
        self.assertEqual(data["error"], "repo unreachable")

    def test_no_readable_timestamp_is_unknown(self):
        """Without one there is no age, and an age is what separates a current
        answer from one that stopped being produced."""
        d = self.fresh(); d.pop("checked_epoch")
        state, _ = self.read(d)
        self.assertEqual(state, "unknown")

    # -- the check stopping, which is the quiet one ---------------------------

    def test_a_check_older_than_the_window_is_stale(self):
        now = time.time()
        self.assertEqual(self.read(self.fresh(checked_epoch=now - 50 * 3600),
                                   now=now)[0], "stale")
        self.assertEqual(self.read(self.fresh(checked_epoch=now - 2 * 3600),
                                   now=now)[0], "ok")

    def test_stale_is_said_on_the_line_not_left_to_arithmetic(self):
        out = self.draw(self.fresh(total=3, checked_epoch=time.time() - 50 * 3600))
        self.assertIn("STALE", out)

    # -- rendering -------------------------------------------------------------

    def draw(self, doc=None, kernel=("current", {"running": "7.2.11-1-default"}),
             superseded=False):
        """`superseded` is PINNED for the same reason `kernel` is. Left to the
        host, `snapshot.superseded` reads the real `/etc/os-release` -- and the
        moment a fixture's `target_snapshot` happened to equal this machine's
        actual VERSION_ID, an unrelated test about counts and ages started
        getting the supersession line instead. Which is exactly how it was
        found."""
        """`kernel` is PINNED, because the board now reads the running kernel
        live. Left to the host, every assertion about the reboot marker would be
        answered by whichever kernel the test machine happens to have booted:
        green here, and green for the wrong reason on a machine with a pending
        kernel or -- in a container with no `/lib/modules` at all -- on the
        `unknown` branch. That is the same shape as the version-store tests that
        passed in two places and failed in the only one that mattered."""
        import io, contextlib
        if doc is not None:
            self.write(doc)
            with open(os.path.join(self.cfg.config, "fleet.toml"), "a") as f:
                f.write('\n[updates]\nstatus = "%s"\n' % self.path)
        with mock.patch.object(self.b, "panes", lambda: {}), \
             mock.patch.object(self.b, "agents", lambda: {}), \
             mock.patch.object(self.b, "load_cache", lambda: None), \
             mock.patch.object(self.b.kernels, "state", lambda *a, **k: kernel), \
             mock.patch.object(self.b.snapshot, "superseded", lambda d, **k: superseded), \
             mock.patch.object(self.b.versions, "installed", lambda *a, **k: "2.1.303"), \
             mock.patch.object(self.b.versions, "target", lambda *a, **k: ("2.1.302", "/v")):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.b.draw()
        return buf.getvalue()

    def test_no_configured_source_prints_nothing_about_updates(self):
        """The one absence here that is not a failure: it was never asked for.
        A board that nagged about updates on a machine with no checker would be
        reporting its own configuration as the machine's state."""
        self.assertNotIn("updates:", self.draw())

    def test_a_reboot_is_flagged_in_the_header(self):
        """It is true NOW and it ends every session on the machine, which makes
        it a fact about the fleet rather than about a package list."""
        out = self.draw(self.fresh(total=5, reboot_needed=True))
        head = [l for l in out.splitlines() if "FLEET" in l][0]
        self.assertIn("REBOOT NEEDED", head)

    def test_no_reboot_flag_when_none_is_needed(self):
        out = self.draw(self.fresh(total=5, reboot_needed=False))
        self.assertNotIn("REBOOT NEEDED", out)

    # -- the kernel, read live rather than from the daily document --------------

    def test_a_newer_installed_kernel_is_flagged_even_when_the_document_is_calm(self):
        """The gap this closes. The update document is written by a daily timer
        and says `reboot_needed: false`; a `dup` then unpacks a kernel. Measured
        on the machine this was written for: a kernel landed at 08:42 with the
        next check due 06:21 the following morning -- twenty-two hours in which a
        board reading only that document would have said nothing at all."""
        out = self.draw(self.fresh(total=5, reboot_needed=False),
                        kernel=("pending", {"running": "7.2.11-1-default",
                                            "newest": "7.2.14-1-default",
                                            "since": time.time() - 3 * 86400}))
        head = [l for l in out.splitlines() if "FLEET" in l][0]
        self.assertIn("REBOOT NEEDED", head)
        # Trimmed to the part that differs: the `-1-default` tail is identical and
        # this header already runs long enough to wrap a narrow pane.
        self.assertIn("kernel 7.2.11 -> 7.2.14", head)

    def test_the_header_says_how_long_the_reboot_has_been_owed(self):
        """The owner already knows a reboot is due; the number they decide on is
        how long they have been putting it off. 72h, not an epoch -- `age` takes a
        timestamp and subtracts it from now, so handing it a duration prints the
        wait as half a million hours."""
        out = self.draw(self.fresh(total=5),
                        kernel=("pending", {"running": "a", "newest": "b",
                                            "since": time.time() - 72 * 3600}))
        head = [l for l in out.splitlines() if "FLEET" in l][0]
        self.assertIn("waiting 72h", head)

    def test_a_pending_kernel_with_no_timestamp_still_flags(self):
        """`since` can be absent when the directory could not be stat'ed. The
        reboot is still owed, and dropping the marker for want of its age would
        withhold the fact to avoid admitting one detail is missing."""
        out = self.draw(self.fresh(total=5),
                        kernel=("pending", {"running": "a", "newest": "b"}))
        self.assertIn("REBOOT NEEDED", out)
        self.assertNotIn("waiting", out)

    def test_a_pending_kernel_flags_with_no_update_source_configured_at_all(self):
        """The reminder does not depend on the producer existing. A machine with no
        update checker configured gets `(None, None)` from `updates()` -- silence by
        choice, not a failure -- and the kernel comparison is read locally, so it
        still answers. This is the property that makes the feature portable to a
        machine that never had the daily timer."""
        out = self.draw(kernel=("pending", {"running": "7.2.11-1-default",
                                            "newest": "7.2.14-1-default",
                                            "since": time.time() - 86400}))
        self.assertNotIn("updates:", out, "no source was configured")
        head = [l for l in out.splitlines() if "FLEET" in l][0]
        self.assertIn("REBOOT NEEDED", head)
        self.assertIn("kernel 7.2.11 -> 7.2.14", head)

    def test_an_unreadable_kernel_state_is_a_question_mark_not_silence(self):
        """Read live and locally, so failing means something odd about the machine
        itself -- and a silent omission reads exactly like a machine with nothing
        to report. Absence is rendered `?`, never as a pass."""
        out = self.draw(self.fresh(total=5, reboot_needed=False),
                        kernel=("unknown", {"error": "no kernel image found"}))
        head = [l for l in out.splitlines() if "FLEET" in l][0]
        self.assertIn("kernel: ?", head)
        self.assertNotIn("REBOOT NEEDED", head)

    def test_a_current_kernel_says_so_rather_than_saying_nothing(self):
        """Found by a reader, not by a test. Cameron checked the board for a
        pending reboot the day after this landed, saw nothing, and could not tell
        "checked, and you are on the newest kernel" from "this board does not
        report kernels" -- so he ran the comparison by hand. A silent pass is
        indistinguishable from an absent feature, which is the doctrine of
        rendering `?` seen from its other side: there the board cannot answer,
        here it can and the answer is good news."""
        out = self.draw(self.fresh(total=5, reboot_needed=False),
                        kernel=("current", {"running": "7.2.11-1-default",
                                            "newest": "7.2.11-1-default"}))
        head = [l for l in out.splitlines() if "FLEET" in l][0]
        self.assertIn("kernel 7.2.11-1-default", head)
        self.assertNotIn("REBOOT NEEDED", out)

    def test_the_quiet_case_is_not_dressed_as_an_alarm(self):
        """Dim, not red, and no `!`. A board that shouts good news teaches its
        reader to skim the line that will one day carry bad news -- the sibling of
        the permanent-red-line case already in the catalog."""
        out = self.draw(self.fresh(total=5, reboot_needed=False),
                        kernel=("current", {"running": "7.2.11-1-default"}))
        self.assertNotIn("REBOOT", out)
        self.assertNotIn("!", [l for l in out.splitlines() if "FLEET" in l][0])

    def test_a_failed_check_still_reports_a_reboot(self):
        """The opposite of what this board first did, and the fix came from
        reading the producer rather than trusting the fixture.

        `reboot_needed` is derived OUTSIDE the branch that can fail -- the
        producer computes it from the running kernel and `zypper
        needs-rebooting`, deliberately so that it survives a failed package
        preview. Suppressing it on `ok: false` hid a true, current,
        fleet-ending fact at exactly the moment the other half of the check
        broke. The earlier reasoning -- "a failed check may carry fields from
        its last good run" -- is sound about STALE data and wrong about this
        field, which is fresh every run.
        """
        out = self.draw({"schema": 1, "ok": False, "error": "repo unreachable",
                         "reboot_needed": True,
                         "reboot_reasons": ["core libraries updated"]})
        self.assertIn("REBOOT NEEDED", out)
        self.assertIn("THE CHECK FAILED", out,
                      "the failure must still be reported beside it")

    def test_a_failed_check_with_no_reboot_does_not_invent_one(self):
        out = self.draw({"schema": 1, "ok": False, "error": "repo unreachable",
                         "reboot_needed": False})
        self.assertNotIn("REBOOT NEEDED", out)

    def test_an_unknown_source_withholds_the_reboot_flag(self):
        """The one state that does, and the fixture has to be the one where the
        fields SURVIVE to the renderer.

        An unknown `schema` is rejected before the document is kept, so its
        `reboot_needed` never reaches the header and a test using it passes
        whatever the guard says. The undatable document is the discriminating
        case: well-formed, schema 1, every field present, and no timestamp -- so
        the board holds the whole document at arm's length rather than picking
        the one field it likes out of a source it has just called unknown.
        """
        d = {"schema": 1, "ok": True, "total": 3, "reboot_needed": True}
        self.assertNotIn("checked_epoch", d)
        out = self.draw(d)
        self.assertIn("UNKNOWN", out)
        self.assertNotIn("REBOOT NEEDED", out)

    def test_the_count_and_the_age_are_both_shown(self):
        out = self.draw(self.fresh(total=214, kernel_update=["kernel-default-7.2"],
                                   target_snapshot="20261021"))
        line = [l for l in out.splitlines() if "updates:" in l][0]
        self.assertIn("214 updates", line)
        self.assertIn("kernel", line)
        self.assertIn("20261021", line)
        self.assertIn("ago", line, "a count with no age reads as current")

    def test_nothing_pending_says_so_with_its_snapshot(self):
        line = [l for l in self.draw(self.fresh(total=0)).splitlines()
                if "updates:" in l][0]
        self.assertIn("up to date", line)
        self.assertIn("20261017", line)


class WhatScrollsOffIsWhatDoesNotChange(unittest.TestCase):
    """The ordering rule, after the board's most urgent line spent a day below the
    fold.

    The board was 36 lines; eight of the fleet's seventeen panes are under 40
    rows. Of those 36, fourteen were the parked list -- every entry durable, none
    of it changing between draws -- and three were the footer carrying pending
    updates, the cluster/context stamp and every `!` warning. The largest block
    was sessions that are not running; the smallest was everything time-sensitive,
    and the parked block grew each time a session was parked, pushing the footer
    further down.

    Cameron went looking for a kernel reboot warning on 2026-10-21 and ran the
    comparison by hand rather than find it here. Same family as the permanent red
    line already in the catalog, one step earlier: there a true alarm is read
    past, here it never reaches the reader at all.
    """

    # FIVE parked sessions, not the one the sibling fixture declares. With a
    # single entry the collapse saves nothing and a test of it compares two equal
    # numbers -- which is how the first version of `test_the_board_fits_a_short_pane`
    # passed on a fixture that could not show the behavior it named.
    MANY_PARKED = PARKED_TOML + "".join(
        '\n[parked.%s]\nuuid  = "cccccccc-%04d-4333-8333-333333333333"\n'
        'since = "2026-10-0%d"\ncwd   = "/home/u/Git/%s"\n' % (n, i, i, n)
        for i, n in enumerate(("beta-talk", "gamma-repo", "delta-sweep",
                               "epsilon-notes"), start=1))

    def setUp(self):
        self.cfg = FakeConfig(toml=self.MANY_PARKED)
        self.b = load_tool("fleetboard")
        self.b.C = dict.fromkeys(self.b.C, "")

    def tearDown(self):
        self.cfg.close()

    def board(self, show_parked=False, notes=(), running=True):
        import io, contextlib
        agents = {"alpha": {"status": "idle", "pid": 11, "cwd": "/home/u/a"}}
        if running:
            agents["old-talk"] = {"status": "idle", "pid": 12, "cwd": "/home/u/x"}
        panes = {n: {"win": "1", "winname": "w", "pane": "%1",
                     "quiet": False, "current": False} for n in agents}
        cache = {"at": time.time() - 120, "notes": list(notes)}
        with mock.patch.object(self.b, "panes", lambda: panes), \
             mock.patch.object(self.b, "agents", lambda: agents), \
             mock.patch.object(self.b, "load_cache", lambda: cache), \
             mock.patch.object(self.b.kernels, "state",
                               lambda *a, **k: ("current", {"running": "1.0-1-default"})), \
             mock.patch.object(self.b.versions, "installed", lambda *a, **k: "2.1.0"), \
             mock.patch.object(self.b.versions, "of_pid", lambda pid: "2.1.0"):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.b.draw(show_parked=show_parked)
            return buf.getvalue()

    @staticmethod
    def row_of(out, needle):
        return next(i for i, l in enumerate(out.splitlines()) if needle in l)

    def test_the_cluster_stamp_is_above_the_session_table(self):
        out = self.board()
        self.assertLess(self.row_of(out, "cluster + context"),
                        self.row_of(out, "cwd"))

    def test_a_red_warning_is_above_the_session_table(self):
        """The `!` notes were the LAST thing the board printed, below even the
        stamp. They are the most urgent rows on it."""
        out = self.board(notes=["a job died"])
        self.assertLess(self.row_of(out, "! a job died"),
                        self.row_of(out, "cwd"))

    def test_the_warning_stays_with_the_stamp_that_dates_it(self):
        """Above the table, but not hoisted above its own provenance: each note is
        true as of that moment and no later, and a red line with no age beside it
        invites being read as current when its source stopped hours ago."""
        out = self.board(notes=["a job died"])
        self.assertEqual(self.row_of(out, "! a job died"),
                         self.row_of(out, "cluster + context") + 1)

    def test_parked_is_counted_not_listed(self):
        out = self.board()
        self.assertIn("parked (5)", out)
        self.assertIn("--parked to list", out)
        self.assertNotIn("/home/u/Git/talks/old", out)

    def test_parked_lists_on_request(self):
        out = self.board(show_parked=True)
        self.assertIn("/home/u/Git/talks/old", out)
        self.assertNotIn("--parked to list", out)

    def test_the_collapse_still_shows_a_session_both_parked_and_running(self):
        """The one parked fact that is NOT durable, and so the one the count must
        not swallow. A session declared parked in `fleet.toml` and running at the
        same time means a human's decision and the machine disagree -- which is
        what this board is for. It survives the collapse as its own `!` line."""
        out = self.board()
        self.assertIn("parked and ALSO RUNNING: old-talk", out)

    def test_no_clash_line_when_nothing_clashes(self):
        out = self.board(running=False)
        self.assertIn("parked (5)", out)
        self.assertNotIn("ALSO RUNNING", out)

    def test_the_board_fits_a_short_pane(self):
        """The measurement that started this. Not a fixed budget -- the live
        roster is as long as the fleet is -- but the parked list must no longer
        add a line per parked session to the default draw."""
        short = len(self.board().splitlines())
        listed = len(self.board(show_parked=True).splitlines())
        self.assertEqual(listed - short, 4,
                         "five parked sessions must cost four lines more when "
                         "listed than when counted (the clash line is printed "
                         "either way)")


class AFailedClusterQueryCarriesItsLength(unittest.TestCase):
    """"cluster query failed" is honest and says nothing about duration, so a
    two-minute blip, a two-day maintenance window and a cluster nobody ever
    reached all print the same words. The cluster was down on the morning of
    2026-10-22 and nothing in the fleet could say when it had started."""

    def setUp(self):
        self.cfg = FakeConfig()
        self.b = load_tool("fleetboard")

    def tearDown(self):
        self.cfg.close()

    def notes(self, payload):
        with mock.patch.object(self.b, "run_json", lambda *a, **k: payload):
            return self.b.jobs_and_notes()[1]

    def test_the_note_says_how_long(self):
        n = self.notes({"cluster_ok": False, "cluster_down_for_s": 4800})
        self.assertEqual(n, ["cluster query failed for 1h 20m -- live work is "
                             "UNKNOWN, not none"])

    def test_a_long_outage_reads_in_days(self):
        n = self.notes({"cluster_ok": False, "cluster_down_for_s": 200000})
        self.assertIn("2d 7h", n[0])

    def test_no_recorded_duration_says_nothing_rather_than_zero(self):
        """Absence is not zero. A fleet with no recorded good read has not
        observed an outage of no length, and "failed for 0s" would invent one."""
        n = self.notes({"cluster_ok": False, "cluster_down_for_s": None})
        self.assertEqual(n, ["cluster query failed -- live work is UNKNOWN, not none"])

    def test_an_older_fleetwatch_without_the_field_still_renders(self):
        """The board and `fleetwatch` are separately installed scripts, and a
        board reading an older one must not lose the warning over a missing key."""
        n = self.notes({"cluster_ok": False})
        self.assertEqual(n, ["cluster query failed -- live work is UNKNOWN, not none"])

    def test_a_working_cluster_gets_no_such_note(self):
        n = self.notes({"cluster_ok": True, "jobs": [], "cluster_down_for_s": None})
        self.assertNotIn("cluster query failed", " ".join(n))

    def test_the_duration_switches_to_hours_at_one_hour(self):
        """`age` below it is the age of a cached reading, where coarseness is
        right. An outage is read at the moment someone decides whether to care."""
        self.assertEqual(self.b.short_duration(3599), "59m")
        self.assertEqual(self.b.short_duration(3600), "1h 0m")


class ASupersededUpdateCountIsNotNews(unittest.TestCase):
    """The board printed `updates: 47 updates -> 20261021` for nearly seven hours
    after those 47 were installed. The age beside it was honest and the count was
    about a machine that no longer existed."""

    def setUp(self):
        self.cfg = FakeConfig()
        self.b = load_tool("fleetboard")
        self.b.C = dict.fromkeys(self.b.C, "")

    def tearDown(self):
        self.cfg.close()

    def line(self, doc, sup, now_id="20261021"):
        with mock.patch.object(self.b.snapshot, "superseded", lambda d, **k: sup), \
             mock.patch.object(self.b.snapshot, "current", lambda *a, **k: now_id):
            return self.b.updates_line("ok", dict(doc, _age_s=6 * 3600))

    DOC = {"total": 47, "snapshot": "20261020", "target_snapshot": "20261021"}

    def test_a_superseded_document_says_so_instead_of_its_count(self):
        out = self.line(self.DOC, True)
        self.assertIn("SUPERSEDED", out)
        self.assertIn("20261021", out)
        self.assertIn("the check has not re-run", out)

    def test_it_does_not_advertise_the_count_as_pending(self):
        """`47 updates -> 20261021` reads as work to do. That is the whole
        complaint: the line was not wrong about its age, it was wrong about
        what it was describing."""
        out = self.line(self.DOC, True)
        self.assertNotIn("-> 20261021", out)

    def test_a_current_document_is_unchanged(self):
        out = self.line(self.DOC, False)
        self.assertNotIn("SUPERSEDED", out)
        self.assertIn("47 updates", out)

    def test_unknown_leaves_the_line_exactly_as_it_was(self):
        """None means it could not be told. The caller keeps saying what it said
        before rather than guessing in either direction."""
        out = self.line(self.DOC, None)
        self.assertNotIn("SUPERSEDED", out)
        self.assertIn("47 updates", out)

    def test_the_age_is_still_carried(self):
        """Supersession replaces the claim, not the provenance: a reader still
        needs to know how old the thing being dismissed was."""
        self.assertIn("6h", self.line(self.DOC, True))

    def test_one_update_reads_as_one(self):
        out = self.line(dict(self.DOC, total=1), True)
        self.assertIn("1 update was pending", out)


class NoClusterConfigured(unittest.TestCase):
    """A fleet.toml with no `[cluster.<name>]` is a choice, not a failure.

    `fleetwatch` used to crash without one, and the board drew that as `?` in
    the work column of every session -- "could not tell" about a question whose
    answer is known: no cluster, so no cluster work. `fleetwatch` now says so
    itself; the board's part is the stamp, which says why the column is blank."""

    def setUp(self):
        import re
        from tests.support import BASE_TOML
        self.cfg = FakeConfig(toml=re.sub(r"\[cluster\.testcluster\]\n(?:[^\[\n].*\n|\n)*", "",
                                          BASE_TOML))
        self.b = load_tool("fleetboard")
        self.calls = []

    def tearDown(self):
        self.cfg.close()

    # What `fleetwatch --json` says with no cluster configured.
    WATCH = {"cluster_ok": True, "cluster_configured": False, "jobs": [],
             "dead_watchers": [{"session": "alpha", "job": "1"}]}

    def run_json(self, cmd, timeout=120):
        self.calls.append(os.path.basename(cmd[0]))
        return self.WATCH if "fleetwatch" in cmd[0] else None

    def draw(self):
        import io, contextlib
        panes = {"alpha": {"win": "1", "winname": "w", "pane": "%1",
                           "quiet": False, "current": False}}
        with mock.patch.object(self.b, "run_json", self.run_json), \
             mock.patch.object(self.b, "panes", lambda: panes), \
             mock.patch.object(self.b, "agents", lambda: {"alpha": {"name": "alpha"}}), \
             mock.patch.object(self.b.kernels, "state",
                               lambda *a, **k: ("current", {"running": "7.2.11-1-default"})), \
             mock.patch.object(self.b.snapshot, "superseded", lambda d, **k: False), \
             mock.patch.object(self.b.versions, "installed", lambda *a, **k: "2.1.303"), \
             mock.patch.object(self.b.versions, "target", lambda *a, **k: ("2.1.303", "/v")):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.b.draw(full=True)
        return buf.getvalue()

    def test_fleetwatch_is_still_asked_and_its_warnings_kept(self):
        """Skipping it would blank the work column just as well, and silently
        drop every warning that needs no cluster -- a dead watcher among them."""
        with mock.patch.object(self.b, "run_json", self.run_json):
            jobs, notes = self.b.jobs_and_notes()
        self.assertIn("fleetwatch", self.calls)
        self.assertEqual(jobs, [], "no cluster declared: no work, not None")
        self.assertIn("a registered watcher is dead", notes)

    def test_the_work_column_is_blank_and_the_stamp_says_why(self):
        import re
        out = re.sub(r"\x1b\[[0-9;]*m", "", self.draw())
        lines = out.splitlines()
        col = [l for l in lines if "session" in l and "work" in l][0].index("work")
        row = [l for l in lines if "alpha" in l][0]
        self.assertEqual(row[col:].strip(), "", row)
        self.assertIn("no [cluster] configured, so no cluster work", out)
        self.assertNotIn("cluster + context as of", out)

    def test_a_cache_from_before_the_field_keeps_the_old_stamp(self):
        """Written by a board that predates `cluster` in the cache: it says
        nothing about the cluster, so it must not be read as "none configured"."""
        lines = self.b.cache_lines({"at": time.time(), "jobs": None, "notes": []},
                                   full=True, auto=False)
        self.assertIn("cluster + context as of", lines[0])

    def test_a_cluster_added_under_watch_is_picked_up(self):
        """Re-read per draw: `--watch` outlives an edit to fleet.toml."""
        self.assertFalse(self.b.cluster_configured())
        with open(os.path.join(self.cfg.config, "fleet.toml"), "a") as f:
            f.write('\n[cluster.testcluster]\nssh_host = "nowhere.invalid"\n'
                    'user = "tester"\njob_id_re = "[0-9]+"\n')
        self.assertTrue(self.b.cluster_configured())
