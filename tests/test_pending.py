import datetime, os, tempfile, unittest
from fleet import pending


class Format(unittest.TestCase):
    """One module writes the record and one module parses it, so what survives
    the round trip is pinned here rather than discovered by a reader."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="fleet-pending-")
        self.state = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_the_text_survives_the_round_trip(self):
        pending.write(self.state, "alpha", "123456", "sweep terminal: 93 ok / 2 failed",
                      "still not typeable after 1800s", 4)
        recs, bad = pending.read_all(self.state)
        self.assertEqual(bad, 0)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["text"], "sweep terminal: 93 ok / 2 failed")
        self.assertEqual(recs[0]["session"], "alpha")
        self.assertEqual(recs[0]["job"], "123456")
        self.assertEqual(recs[0]["code"], "4")

    def test_a_reason_that_wrapped_does_not_eat_the_body(self):
        """Every header value gets ONE line. A reason carrying a newline would
        otherwise be read back as the end of the header, the body would start
        mid-sentence, and the undelivered text -- the only thing here that cannot
        be reconstructed -- would be the part that was lost."""
        pending.write(self.state, "alpha", "123456", "the result",
                      "still not typeable after 1800s:\nalpha is mid-turn", 4)
        recs, bad = pending.read_all(self.state)
        self.assertEqual((len(recs), bad), (1, 0))
        self.assertEqual(recs[0]["text"], "the result")
        self.assertIn("alpha is mid-turn", recs[0]["reason"])
        self.assertNotIn("\n", recs[0]["reason"])

    def test_a_multi_line_result_keeps_its_lines(self):
        pending.write(self.state, "alpha", "1", "line one\nline two", "why", 4)
        recs, _ = pending.read_all(self.state)
        self.assertEqual(recs[0]["text"], "line one\nline two")

    def test_mail_travels_with_the_failure(self):
        """The 2026-10-05 give-up lost inbound cross-fleet mail, and mail that
        never arrived is the case a reader most needs to identify as mail."""
        pending.write(self.state, "alpha", "1", "connection test", "why", 4,
                      mail_from="beta/beta-coord")
        recs, _ = pending.read_all(self.state)
        self.assertEqual(recs[0]["mail-from"], "beta/beta-coord")

    def test_a_name_cannot_escape_the_directory(self):
        """Session and job reach this from a caller's argv."""
        p = pending.write(self.state, "../../etc/alpha", "../x", "t", "why", 2)
        self.assertEqual(os.path.dirname(p), pending.pending_dir(self.state))
        recs, bad = pending.read_all(self.state)
        self.assertEqual((len(recs), bad), (1, 0))

    def test_two_jobs_for_one_session_do_not_overwrite_each_other(self):
        pending.write(self.state, "alpha", "1", "first", "why", 4)
        pending.write(self.state, "alpha", "2", "second", "why", 4)
        recs, _ = pending.read_all(self.state)
        self.assertEqual(sorted(r["text"] for r in recs), ["first", "second"])


class Absence(unittest.TestCase):
    """Nothing pending, a directory that cannot be read, and a file that cannot
    be parsed are three different answers. Collapsing them is how a report comes
    back reassuring about a question it never asked."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="fleet-pending-")
        self.state = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_directory_yet_is_nothing_pending(self):
        """It is created on the first give-up, so absent genuinely means none."""
        self.assertEqual(pending.read_all(self.state), ([], 0))

    def test_an_unreadable_directory_is_unknown_not_empty(self):
        d = pending.pending_dir(self.state)
        os.makedirs(d)
        os.chmod(d, 0)
        try:
            recs, _ = pending.read_all(self.state)
        finally:
            os.chmod(d, 0o700)
        if os.geteuid() == 0:
            self.skipTest("root reads an unreadable directory")
        self.assertIsNone(recs, "an unreadable directory read as nothing pending")

    def test_an_unparsable_file_is_counted_not_skipped(self):
        """A file whose header is gone still means news did not arrive. Skipping
        it quietly would turn a lost result into a clean report."""
        pending.write(self.state, "alpha", "1", "the result", "why", 4)
        with open(os.path.join(pending.pending_dir(self.state), "junk.md"), "w") as f:
            f.write("not a record at all\n")
        recs, bad = pending.read_all(self.state)
        self.assertEqual((len(recs), bad), (1, 1))

    def test_clearing_nothing_says_so(self):
        self.assertFalse(pending.clear(self.state, "alpha", "1"))
        pending.write(self.state, "alpha", "1", "t", "why", 4)
        self.assertTrue(pending.clear(self.state, "alpha", "1"))
        self.assertEqual(pending.read_all(self.state), ([], 0))

    def test_for_session_filters_without_losing_the_unknown(self):
        pending.write(self.state, "alpha", "1", "a", "why", 4)
        pending.write(self.state, "beta", "1", "b", "why", 4)
        recs, _ = pending.for_session(self.state, "alpha")
        self.assertEqual([r["text"] for r in recs], ["a"])

    def test_oldest_first(self):
        t = datetime.datetime(2026, 10, 5, 21, 15).astimezone()
        pending.write(self.state, "alpha", "2", "newer", "why", 4)
        pending.write(self.state, "alpha", "1", "older", "why", 4, now=t)
        recs, _ = pending.read_all(self.state)
        self.assertEqual([r["text"] for r in recs], ["older", "newer"])


if __name__ == "__main__":
    unittest.main()
