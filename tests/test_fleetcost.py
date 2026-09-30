"""fleetcost had no tests. It reported a number that was wrong by half and
labelled it as wrong in the other direction, and nothing caught that.

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
