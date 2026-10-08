"""One session, two project directories, counted twice by anything that globs.

A working directory gets RENAMED. Claude Code opens a project directory for the
new path; the old one keeps its copy of the transcript. Both are then matched by
`<projects>/*/*.jsonl`, and a tool that sums per FILE counts that session twice.

Live on this fleet since 2026-10-02, when `~/Sync/mendeley` became
`~/Sync/library`: three transcripts under both slugs, byte-identical, same
sha256, different inodes. `fleetgantt` drew three sessions twice until ef89336;
`fleetcost` read 101 transcripts where there are 98 and reported 2,528 peer
messages where there are 2,353.

The reusable part is how it was caught, and it was not by reading code: a
recount disagreed with a figure already published for a week that had already
finished. **A completed week whose count moves between two runs is the symptom,
and the earlier number is the control.**
"""
import os
import tempfile
import unittest

from fleet import transcripts


class DedupePaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, project, name, body):
        d = os.path.join(self.root, project)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name)
        with open(p, "w") as f:
            f.write(body)
        return p

    def test_one_session_in_two_projects_is_returned_once(self):
        a = self.write("-home-u-Sync-library", "uuid-1.jsonl", "x" * 100)
        b = self.write("-home-u-Sync-mendeley", "uuid-1.jsonl", "x" * 100)
        got = transcripts.dedupe_paths([a, b])
        self.assertEqual(len(got), 1)
        self.assertIn(got[0], (a, b))

    def test_distinct_sessions_are_all_kept(self):
        a = self.write("-home-u-a", "uuid-1.jsonl", "x" * 10)
        b = self.write("-home-u-a", "uuid-2.jsonl", "x" * 10)
        self.assertEqual(transcripts.dedupe_paths([a, b]), sorted([a, b]))

    def test_the_longer_copy_wins(self):
        """A session that continued under the new path left the old copy short.
        Identical copies make this moot, which is the case on this fleet today --
        so the rule has to be right for the case nobody has seen yet."""
        short = self.write("-home-u-old", "uuid-1.jsonl", "x" * 10)
        long = self.write("-home-u-new", "uuid-1.jsonl", "x" * 500)
        self.assertEqual(transcripts.dedupe_paths([short, long]), [long])
        self.assertEqual(transcripts.dedupe_paths([long, short]), [long])

    def test_the_answer_does_not_depend_on_input_order(self):
        """Two equal copies must not make the count depend on how the glob
        happened to walk the directories: a figure that moves between runs with
        nothing changed is the exact symptom this was found by."""
        a = self.write("-home-u-aaa", "uuid-1.jsonl", "x" * 100)
        b = self.write("-home-u-zzz", "uuid-1.jsonl", "x" * 100)
        self.assertEqual(transcripts.dedupe_paths([a, b]),
                         transcripts.dedupe_paths([b, a]))

    def test_an_unreadable_path_is_kept_and_loses(self):
        """It may be the only copy, so dropping it would undercount -- the error
        in the direction nobody checks. It loses a tie because a file that cannot
        be sized cannot be shown to be the more complete one."""
        gone = os.path.join(self.root, "-home-u-x", "uuid-1.jsonl")
        self.assertEqual(transcripts.dedupe_paths([gone]), [gone])
        real = self.write("-home-u-y", "uuid-1.jsonl", "x" * 10)
        self.assertEqual(transcripts.dedupe_paths([gone, real]), [real])

    def test_nothing_in_nothing_out(self):
        self.assertEqual(transcripts.dedupe_paths([]), [])


class FleetcostUsesIt(unittest.TestCase):
    def test_the_scan_dedupes_before_it_sums(self):
        """A source check, because `scan()` reads every transcript on the machine
        and there is no fixture for that. It asserts the glob is not summed
        directly, which is the shape the bug had."""
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "bin", "fleetcost")).read()
        self.assertIn("dedupe_paths", src)
        self.assertNotIn("files = [f for f in glob.glob(PAT)", src)


class FleetlogUsesItToo(unittest.TestCase):
    """`fleetlog`'s EDGES were already safe; its session table was not.

    Two identical copies yield identical edges and `dedupe(edges)` collapses
    them, so the message graph was right -- measured invariant at 3,007 edges
    with the dedupe on and off. But `sessions` is keyed by PATH, so the table
    listed the same transcript once per project directory: 81 rows where there
    are 79, two of `library`'s shown twice.

    Safe by a route that would not survive the two copies differing is not the
    same as safe, which is why this is pinned rather than left to the edge
    dedupe.
    """
    def test_the_session_scan_dedupes(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "bin", "fleetlog")).read()
        self.assertIn("dedupe_paths", src)
        self.assertNotIn('for path in sorted(glob.glob(f"{PROJECTS}/*/*.jsonl")):', src)


if __name__ == "__main__":
    unittest.main()
