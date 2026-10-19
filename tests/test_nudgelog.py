"""Which nudge records are a delivery hole -- one rule, two readers.

`fleetwatch` reports holes and `fleetnudge --delivered` clears one, and they have
to agree exactly: a tool offering to clear a line must show the same lines the
report shows, or its dry run lies about what it is about to silence. The first
version restated the rule in the clearing tool and listed thirty ordinary retry
records as though each were a hole, when the report flagged two.

The gap all of this fills: a nudge that gave up stayed an alarm until it aged out
of the window, with no way to say the news had in fact arrived. `fleetmail` got
both halves on 2026-10-15 -- a record that the content reached its reader another
way, and a retry -- and nudges got neither.
"""
import datetime
import json
import os
import tempfile
import unittest

from fleet import nudgelog


def at(mins_ago, **kw):
    t = (datetime.datetime.now(datetime.timezone.utc).astimezone()
         - datetime.timedelta(minutes=mins_ago))
    r = {"time": t.strftime("%Y-%m-%dT%H:%M:%S%z"), "session": "alpha", "job": "111"}
    r.update(kw)
    return r


class WhatCountsAsStillOpen(unittest.TestCase):
    def open_(self, *recs, **kw):
        return nudgelog.open_trouble(list(recs), **kw)

    def test_a_give_up_is_open(self):
        r = at(60, outcome="not delivered", reason="still not typeable")
        self.assertEqual(self.open_(r), [r])

    def test_an_in_session_decline_is_not(self):
        """It was never lost: the session is told by the task running the nudge."""
        r = at(60, outcome="not delivered", notified_otherwise=True)
        self.assertEqual(self.open_(r), [])

    def test_only_the_last_waiting_counts_and_only_when_old(self):
        """The dozens of ordinary retry lines before a give-up are not trouble.
        Listing them made two flagged rows look like thirty in the clearing
        tool's dry run, which is the whole reason this rule lives in one place."""
        early = at(200, outcome="waiting", reason="mid-turn")
        last = at(190, outcome="waiting", reason="mid-turn")
        self.assertEqual(self.open_(early, last), [last])

    def test_a_waiting_that_is_still_retrying_is_not_trouble(self):
        """A retry loop still going looks exactly like one that was killed; only
        age separates them."""
        r = at(5, outcome="waiting", reason="mid-turn")
        self.assertEqual(self.open_(r), [])

    def test_a_waiting_followed_by_an_outcome_is_not_dangling(self):
        w = at(200, outcome="waiting", reason="mid-turn")
        done = at(190, outcome="delivered")
        self.assertEqual(self.open_(w, done), [])

    def test_filters_by_session_and_job(self):
        mine = at(60, outcome="not delivered", reason="x")
        other = at(60, outcome="not delivered", reason="x", session="beta")
        job2 = at(60, outcome="not delivered", reason="x", job="222")
        self.assertEqual(self.open_(mine, other, job2, session="alpha", job="111"),
                         [mine])


class AnAssertionThatTheNewsArrived(unittest.TestCase):
    """`informed` is an outcome only a human or a session writes. It suppresses,
    where a later ordinary delivery only annotates -- a later nudge about the
    same job is a DIFFERENT message, and treating it as proof would make the
    check fail toward fine."""

    def test_it_clears_a_give_up(self):
        bad = at(60, outcome="not delivered", reason="still not typeable")
        ok = at(30, outcome="informed", notified_otherwise=True, reason="told me")
        self.assertEqual(nudgelog.open_trouble([bad, ok]), [])

    def test_it_clears_a_dangling_waiting(self):
        w = at(200, outcome="waiting", reason="mid-turn")
        ok = at(30, outcome="informed", notified_otherwise=True, reason="told me")
        self.assertEqual(nudgelog.open_trouble([w, ok]), [])

    def test_an_assertion_before_the_trouble_clears_nothing(self):
        """A claim recorded before a nudge failed says nothing about that
        failure, and reading it as cover would silence every later hole for that
        session and job forever."""
        ok = at(200, outcome="informed", notified_otherwise=True, reason="told me")
        bad = at(60, outcome="not delivered", reason="still not typeable")
        self.assertEqual(nudgelog.open_trouble([ok, bad]), [bad])

    def test_it_is_scoped_to_one_session_and_job(self):
        bad = at(60, outcome="not delivered", reason="x", job="222")
        ok = at(30, outcome="informed", notified_otherwise=True, job="111")
        self.assertEqual(nudgelog.open_trouble([bad, ok]), [bad])


class ReadingTheLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "nudges.log")

    def test_an_absent_log_is_none_not_empty(self):
        """None, so a caller can say "could not read" rather than draw a quiet
        fleet. Empty would mean "nothing ever went wrong"."""
        recs, bad = nudgelog.read(self.path)
        self.assertIsNone(recs)

    def test_bad_lines_are_counted_not_silently_dropped(self):
        with open(self.path, "w") as f:
            f.write(json.dumps(at(10, outcome="delivered")) + "\n")
            f.write("{not json\n")
            f.write(json.dumps({"session": "x", "outcome": "delivered"}) + "\n")  # no time
        recs, bad = nudgelog.read(self.path)
        self.assertEqual(len(recs), 1)
        self.assertEqual(bad, 2)
