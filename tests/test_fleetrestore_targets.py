"""Pane targeting and the post-restore check.

On 2026-09-30, after a reboot, `fleetrestore --all --go` sent every session one
pane to the LEFT: five never started and seven launched in another session's
working directory. Targets were computed as ``<window>.<index + pane-base-index>``
and the base index was read from tmux *before* the first ``new-session`` -- so with
no server running the query returned nothing and the code fell back to 0, while the
config sets 1.

The function that read it was added to fix exactly that class of failure after an
earlier restore. It could not hold in the one case this tool exists for: a machine
that has just come back, with no server.

These tests do not run a real restore. A `--go` restore types ``claude --resume``
into panes, and a test that does that on a throwaway server still launches real
sessions; sandboxing that safely (a fake `claude` earlier on PATH, a temp HOME so
tmux reads a test config) is on the roadmap. What is checked here is the part that
was wrong: that no pane target is computed from an index at all.
"""
import json, os, shutil, subprocess, tempfile, unittest
from unittest import mock

from tests.support import APP, BASE_TOML, FakeConfig, load_tool

TOOL = os.path.join(APP, "bin", "fleetrestore")
SRC = open(TOOL).read()


class NoComputedTargets(unittest.TestCase):
    def test_the_base_index_reader_is_gone_entirely(self):
        """Not repaired -- removed. A pane id cannot be off by one, so there is
        nothing left to read at the wrong moment."""
        self.assertNotIn("def pane_base_index", SRC)
        # Deliberately NOT asserting the string "pane-base-index" is absent: the
        # comment explaining why the function went should name it, and an
        # assertion that cannot tell code from comment would forbid that.
        self.assertNotIn("show-window-options", SRC)

    def test_no_target_is_built_from_an_index(self):
        self.assertNotIn('f"{key}.{i + pbi}"', SRC)
        self.assertNotIn("pbi", SRC)

    def test_pane_ids_are_captured_as_each_pane_is_made(self):
        self.assertIn('"#{pane_id}"', SRC)
        self.assertIn("pane_ids", SRC)

    def test_a_pane_without_an_id_is_never_typed_into(self):
        """The failure mode that matters: if tmux does not report an id, the tool
        must not fall back to guessing a target. Silence beats a wrong pane."""
        self.assertIn('not target.startswith("%")', SRC)

    def test_the_directory_is_checked_before_anything_is_typed(self):
        """Issue 2: tmux failures never stopped the run, so seven `claude --resume`
        lines went into the wrong panes. Comparing the pane's cwd to the manifest
        catches a pane-mapping bug whatever its cause."""
        self.assertIn("pane_current_path", SRC)
        # the comparison itself, not just the words near it: "NOT launching it"
        # also appears in the missing-id branch, so grepping for it proved nothing
        self.assertIn('if here != s_["cwd"]:', SRC)


class Verify(unittest.TestCase):
    """Issue 3: the run used to end by telling the human to go and check. It built
    the thing; it can say whether what it built is what was asked for."""

    def setUp(self):
        self.cfg = FakeConfig(toml=BASE_TOML)
        self.r = load_tool("fleetrestore")

    def tearDown(self):
        self.cfg.close()

    def panes(self, rows, legacy=False):
        """rows are (label, cwd, pane_id). The label goes in `@agent`, or in the
        old `@repo` when `legacy` -- panes carry both during the rename.

        The mock SUPPLIES the rows, so nothing here exercises the format string
        the tool hands tmux. That is the half that actually breaks: ask for
        `@agent` alone and a legacy pane comes back empty no matter how well the
        parse handles it. `self.asked` keeps the argv so a test can check it."""
        self.asked = []
        def run(argv, *a, **kw):
            self.asked.append(list(argv))
            return subprocess.CompletedProcess([], 0, out, "")
        out = "\n".join("\t".join(("", r[0]) if legacy else (r[0], "")) + "\t"
                         + "\t".join(r[1:]) for r in rows)
        return mock.patch.object(self.r.subprocess, "run", run)

    def sessions(self, *pairs):
        return [{"label": l, "cwd": c} for l, c in pairs]

    def test_a_matching_restore_reports_nothing(self):
        with self.panes([("alpha", "/w/a", "%1"), ("beta", "/w/b", "%2")]):
            self.assertEqual(self.r.verify(self.sessions(("alpha", "/w/a"),
                                                         ("beta", "/w/b"))), [])

    def test_a_session_in_the_wrong_directory_is_named(self):
        """The 2026-09-30 shape: the label is on a pane, and the pane is somebody
        else's. --resume still found the right transcript, so context was right and
        the shell was wrong -- which is why nothing looked broken."""
        with self.panes([("alpha", "/w/b", "%2")]):
            bad = self.r.verify(self.sessions(("alpha", "/w/a")))
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0][0], "alpha")
        self.assertIn("/w/b", bad[0][1])
        self.assertIn("/w/a", bad[0][1])

    def test_a_pane_still_labelled_the_old_way_is_found(self):
        """Mid-rename a pane may carry only `@repo`. Reading `@agent` alone would
        report every such session as missing -- and `verify` runs right after a
        --go, so that reads as a restore that failed when it worked.

        Both halves: the format it ASKS tmux for, and the parse of what comes
        back. The first version of this test checked only the second, and passed
        unchanged with the format narrowed to `@agent` -- the mock was answering
        a question the tool had stopped asking."""
        with self.panes([("alpha", "/w/a", "%1")], legacy=True):
            self.assertEqual(self.r.verify(self.sessions(("alpha", "/w/a"))), [])
        fmt = self.asked[0][self.asked[0].index("-F") + 1]
        self.assertIn("#{@agent}", fmt)
        self.assertIn("#{@repo}", fmt)

    def test_a_session_that_never_started_is_named(self):
        """Five of them, with `no such pane`."""
        with self.panes([("beta", "/w/b", "%2")]):
            bad = self.r.verify(self.sessions(("alpha", "/w/a"), ("beta", "/w/b")))
        self.assertEqual([b[0] for b in bad], ["alpha"])
        self.assertIn("no pane", bad[0][1])

    def test_a_failed_listing_is_reported_not_read_as_success(self):
        """An empty pane list and a broken tmux look identical, and only one of
        them means the restore worked."""
        with mock.patch.object(
                self.r.subprocess, "run",
                return_value=subprocess.CompletedProcess([], 1, "", "no server")):
            bad = self.r.verify(self.sessions(("alpha", "/w/a")))
        self.assertEqual(len(bad), 1)
        self.assertIn("could not list panes", bad[0][1])


if __name__ == "__main__":
    unittest.main()
