"""fleetcost had no tests. It reported a number that was wrong by half and
labeled it as wrong in the other direction, and nothing caught that.

The tool reads `~/.claude/projects`, so every test here points `PAT` at a
throwaway directory instead: no test may read the real transcripts.
"""
import json, os, tempfile, unittest
from unittest import mock

from tests.support import FakeConfig, load_tool


def turn(read=0, cache=0, out=0, text="hello"):
    """One assistant turn with the usage the platform records."""
    return {"type": "assistant", "message": {
        "role": "assistant", "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": read, "cache_read_input_tokens": cache,
                  "cache_creation_input_tokens": 0, "output_tokens": out}}}


def peer(sender="coord", body="x"):
    env = f'<cross-session-message from="uds:/s.sock" from-name="{sender}">{body}</cross-session-message>'
    return {"type": "user", "message": {"role": "user", "content": env}}


class Base(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig()
        self.c = load_tool("fleetcost")
        self.tmp = tempfile.TemporaryDirectory(prefix="fleetcost-")
        self.dir = os.path.join(self.tmp.name, "proj")
        os.makedirs(self.dir)

    def tearDown(self):
        self.tmp.cleanup()
        self.cfg.close()

    def write(self, *records, name="t.jsonl"):
        path = os.path.join(self.dir, name)
        with open(path, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
            # scan() skips files under 10 kB, so pad past it without adding turns
            f.write(json.dumps({"type": "padding", "_": "." * 11000}) + "\n")
        return path

    def scan(self, *records):
        self.write(*records)
        with mock.patch.object(self.c, "PAT", os.path.join(self.dir, "*.jsonl")):
            return self.c.scan()


class Usage(Base):
    def test_read_is_input_plus_cache_reads_plus_cache_writes(self):
        d = turn(read=10, cache=90)
        d["message"]["usage"]["cache_creation_input_tokens"] = 5
        self.assertEqual(self.c.usage_of(d), (105, 0))

    def test_a_user_record_has_no_usage(self):
        self.assertIsNone(self.c.usage_of(peer()))

    def test_an_assistant_turn_without_usage_is_not_counted(self):
        self.assertIsNone(self.c.usage_of(
            {"message": {"role": "assistant", "content": "x"}}))


class Boundary(Base):
    def test_both_markers_count(self):
        self.assertTrue(self.c.is_boundary({"subtype": "compact_boundary"}))
        self.assertTrue(self.c.is_boundary({"compactMetadata": {"trigger": "manual"}}))

    def test_an_ordinary_record_is_not_a_boundary(self):
        self.assertFalse(self.c.is_boundary({"subtype": "turn_duration"}))
        self.assertFalse(self.c.is_boundary({}))


class Bill(Base):
    def test_the_bill_is_read_off_usage_not_estimated_from_bytes(self):
        """The old estimate was bytes/4 with each turn capped at 800k chars, which
        under-counted by about half once contexts outgrew the cap. These turns are
        tiny in bytes and huge in tokens: only a usage-based bill can tell."""
        _, _, bill, turns = self.scan(turn(read=1_000_000, cache=9_000_000, out=500),
                                      turn(read=2_000_000, cache=0, out=100))
        self.assertEqual(turns, 2)
        self.assertEqual(bill["read"], 12_000_000)
        self.assertEqual(bill["cache_read"], 9_000_000)
        self.assertEqual(bill["fresh"], 3_000_000)
        self.assertEqual(bill["written"], 600)

    def test_a_padding_record_is_bytes_without_being_a_turn(self):
        _, _, bill, turns = self.scan(turn(read=5))
        self.assertEqual((turns, bill["read"]), (1, 5))


class Survival(Base):
    def test_a_message_is_re_read_until_the_context_is_compacted(self):
        _, msgs, _, _ = self.scan(peer(), turn(), turn(),
                                  {"subtype": "compact_boundary"},
                                  turn(), turn(), turn())
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0][2], 2, "should stop at the boundary, not run to EOF")

    def test_with_no_compaction_it_survives_to_the_end(self):
        _, msgs, _, _ = self.scan(peer(), turn(), turn(), turn())
        self.assertEqual(msgs[0][2], 3)

    def test_survival_is_not_cut_short_by_transcript_size(self):
        """The 800k-char window used to stop the count here. A long transcript is
        the case where a message is re-read MOST, so truncating it understated the
        very number the convention rests on."""
        big = turn(text="y" * 40_000)
        _, msgs, _, _ = self.scan(peer(), *[big] * 40)
        self.assertEqual(msgs[0][2], 40)

    def test_a_queued_duplicate_of_the_envelope_is_not_a_second_message(self):
        dup = dict(peer(), type="queue-operation")
        _, msgs, _, _ = self.scan(peer(), dup, turn())
        self.assertEqual(len(msgs), 1)

    def test_the_sender_is_taken_from_the_envelope(self):
        _, msgs, _, _ = self.scan(peer(sender="htpolynet-study"), turn())
        self.assertEqual(msgs[0][0], "htpolynet-study")


if __name__ == "__main__":
    unittest.main()


class TheRecordIsNotTheMessage(Base):
    """What a peer message costs is the whole arrival record, and the record is
    bigger than the message by a near-constant 723 characters.

    Every arrival carries an envelope the receiver re-reads exactly like the body:
    a line of prose, the `<cross-session-message ...>` tag naming the sender's
    socket, name and mode, the close tag, and a paragraph of handling advice after
    it -- 543 of the 723 is that trailing paragraph alone.

    `scan()` always counted it, because it measures `len(c)`. The two printed
    EXAMPLES did not: they read the character count the reader supplies as the
    size of the whole record, so a message written to the 800-character
    convention was quoted at 55,600 tokens where it costs ~106,000. Understated
    1.9x at 800 characters and 1.2x at 4,000. Reported 2026-10-13 by a session
    recounting the figure for a talk.

    `AMPLIFICATION` is unaffected and is not changed here: the envelope is in
    both of its sums and divides out -- the same reason the ratio survived the
    duplicate-transcript bug that moved every count.
    """
    def test_the_body_is_split_from_the_envelope(self):
        c = ('Another Claude session sent a message:\n'
             '<cross-session-message from="uds:/s.sock" from-name="coord">'
             'hello</cross-session-message>\nhandling advice follows.')
        body, env = self.c.split_envelope(c)
        self.assertEqual(body, len("hello"))
        self.assertEqual(body + env, len(c), "the two parts must account for all of it")

    def test_an_unsplittable_record_is_unknown_not_zero(self):
        """A truncated or re-quoted copy. Zero envelope would understate the cost
        in precisely the direction this correction goes, so it is None and the
        message is left out of the envelope median rather than dragging it down."""
        for c in ("no envelope here",
                  '<cross-session-message from="x">unterminated'):
            self.assertEqual(self.c.split_envelope(c), (None, None), c)

    def test_the_example_cost_includes_the_envelope(self):
        """The defect, at the only place it reached a reader. One message, one
        turn, so the median survival is 1 and the arithmetic is checkable by hand:
        the quoted cost must be (800 + envelope)/4, not 800/4."""
        import io, contextlib
        body = "y" * 10
        recs = [peer(body=body), turn()]
        self.write(*recs)
        with mock.patch.object(self.c, "PAT", os.path.join(self.dir, "*.jsonl")):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.c.main()
        out = buf.getvalue()
        env = len(peer(body=body)["message"]["content"]) - len(body)
        self.assertIn("~%d tok" % ((800 + env) / 4 * 1), out, out)
        self.assertNotIn("~%d tok" % (200 * 1), out,
                         "the 800-char example still reads the body as the whole record")
        self.assertIn("envelope", out)

    def test_compliance_is_measured_on_the_body(self):
        """Measured on the record the answer is 0% on this fleet and always will
        be, because the envelope alone exceeds the ceiling. A rule about what a
        session writes, scored against something it does not write, is not a
        measurement.

        The sizes here are the whole test. One body of 750 characters OBEYS the
        rule and its record does NOT -- and a body anywhere from 78 to 800
        characters has that property on the real fleet, where the envelope is 723,
        so this is the ordinary case and not a contrived one. A fixture of 10 and
        5,000 cannot tell the two readings apart: both score 1 of 2 either way,
        and the first version of this test did exactly that and passed against the
        record.
        """
        import io, contextlib
        self.write(peer(body="y" * 750), peer(body="y" * 5000), turn())
        self.assertGreater(len(peer(body="y" * 750)["message"]["content"]), 800,
                           "the obeying body must have a record that does not obey")
        with mock.patch.object(self.c, "PAT", os.path.join(self.dir, "*.jsonl")):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.c.main()
        out = buf.getvalue()
        self.assertIn("50% of BODIES obey it (1 of 2)", out, out)

    def test_the_share_reported_is_the_share_that_OBEYS(self):
        """Pinned because the first report of this figure gave the complement
        under the name compliance -- 55% where 45% obey -- and a convention that
        is being missed more often than not then reads as one that is working.
        Three of four bodies here are over the ceiling, so any reading of 75%
        is the number upside down."""
        import io, contextlib
        self.write(peer(body="y" * 10), *([peer(body="y" * 5000)] * 3), turn())
        with mock.patch.object(self.c, "PAT", os.path.join(self.dir, "*.jsonl")):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.c.main()
        out = buf.getvalue()
        self.assertIn("25% of BODIES obey it (1 of 4)", out, out)
        self.assertNotIn("75% of BODIES", out)

    def test_an_unmeasurable_envelope_prints_floors_not_the_old_number(self):
        """`?` has no place in an arithmetic line, so the fallback states the
        figures as FLOORS and says the envelope is unknown. Printing the old
        number silently would be reporting the defect as the answer."""
        import io, contextlib
        rec = {"type": "user", "message": {"role": "user",
               "content": "cross-session-message with no tag at all"}}
        self.write(rec, turn())
        with mock.patch.object(self.c, "PAT", os.path.join(self.dir, "*.jsonl")):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.c.main()
        out = buf.getvalue()
        self.assertIn("envelope UNKNOWN", out, out)
        self.assertIn("at least", out)
        self.assertNotIn("obey it", out, "compliance needs a body it could not find")

    def test_amplification_does_not_move(self):
        """The envelope is in both sums, so it divides out. Changed here only to
        make that explicit: the ratio is the robust figure and the counts are the
        fragile ones."""
        _, msgs, _, _ = self.scan(peer(body="y" * 100), turn(), turn())
        w = sum(m[1] for m in msgs)
        r = sum(m[1] * m[2] for m in msgs)
        self.assertEqual(r / w, 2.0)
