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
from tests.support import APP, FakeConfig, load_tool


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
        # Named colours, so an assertion says WHICH colour rather than matching
        # an escape code. The real table is empty off a tty, which would make
        # every colour assertion below pass against uncoloured output.
        self.b.C = dict.fromkeys(self.b.C, "")
        self.b.C.update({"yel": "<STALE>", "dim": "<DIM>", "r": "<->", "b": "",
                         "red": "<RED>"})

    def tearDown(self):
        self.cfg.close()

    def board(self, agents, installed, per_pid):
        """Draw with every slow source absent; only versions are under test."""
        panes = {n: {"win": "1", "winname": "w", "pane": "%1",
                     "quiet": False, "current": False} for n in agents}
        import io, contextlib
        with mock.patch.object(self.b, "panes", lambda: panes), \
             mock.patch.object(self.b, "agents", lambda: agents), \
             mock.patch.object(self.b, "load_cache", lambda: None), \
             mock.patch.object(self.b.versions, "installed", lambda *a: installed), \
             mock.patch.object(self.b.versions, "of_pid", lambda pid: per_pid.get(pid)):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.b.draw()
            return buf.getvalue()

    @staticmethod
    def plain(text):
        """The output with the colour markers removed -- what a reader sees.

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

    def test_a_session_behind_the_installed_binary_is_coloured(self):
        out = self.board(self.AGENTS, "2.1.292", {11: "2.1.291", 22: "2.1.292"})
        stale = [l for l in out.splitlines() if l.strip().startswith("alpha")][0]
        fresh = [l for l in out.splitlines() if l.strip().startswith("beta")][0]
        self.assertIn("<STALE>2.1.291", stale)
        self.assertNotIn("<STALE>", fresh)
        self.assertIn("2.1.292", fresh)

    def test_an_unknown_version_is_a_question_mark_and_not_an_alarm(self):
        """Absence is `?`, the board's rule. It is also not coloured as stale:
        colouring it would send someone to upgrade a session over a source that
        failed, and the palette's red is reserved for a source that failed."""
        out = self.board(self.AGENTS, "2.1.292", {11: None, 22: "2.1.292"})
        row = [l for l in out.splitlines() if l.strip().startswith("alpha")][0]
        self.assertIn("?", row)
        self.assertNotIn("<STALE>", row)

    def test_an_unreadable_installed_version_colours_nothing_stale(self):
        """If the installed version cannot be read, every comparison is unknown.
        Marking the whole fleet stale on a failed readlink is the same class of
        error as marking it current -- a board acting on a source it did not get."""
        out = self.board(self.AGENTS, None, {11: "2.1.291", 22: "2.1.292"})
        self.assertNotIn("<STALE>", out)
        self.assertIn("? installed", self.plain(out))
