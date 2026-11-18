"""Cross-fleet mail status, and the one reading of it that must be impossible.

A delivery record describes only mail that was FETCHED. So the quietest record
-- no quarantines, nothing undelivered -- is what a working mailbox and a dead
fetcher both produce, and a status that read the record alone would go silent at
the moment the machinery stopped. That is family A in
`docs/checks-that-reassure.md`: the check cannot distinguish itself from its
target. The timer is asked for exactly that reason, and `test_stale_beats_a_
cheerful_exit_code` is the shape of the failure it exists to stop.

Nothing here touches the real systemd units or the real state directory: every
probe is injected, and `FakeConfig` owns the state.
"""
import json
import os
import time
import unittest
from unittest import mock

from fleet import mailstat
from tests.support import FakeConfig

HOUR = 3600.0


def show(timer=None, service=None, missing=()):
    """Stand in for `systemctl --user show`, one dict per unit.

    `missing` names units the probe cannot answer for at all, which is what a
    machine with no user manager does -- distinct from a unit that is simply not
    installed, and the two must not collapse into one state.
    """
    def probe(name, props, timeout=10):
        if any(name.endswith(m) for m in missing):
            return None
        return dict(timer if name.endswith(".timer") else service or {})
    return probe


def timer(active=True, loaded=True, last=None):
    return {"LoadState": "loaded" if loaded else "not-found",
            "ActiveState": "active" if active else "inactive",
            "LastTriggerUSec": "@%d" % last if last else ""}


def service(code=0, ran=None):
    return {"ExecMainStatus": str(code),
            "ExecMainExitTimestamp": "@%d" % ran if ran else ""}


class TheDeliveryRecordIsReadWithoutGuessing(unittest.TestCase):
    """Three outcomes, and `{}` is only ever one of them."""

    def setUp(self):
        self.cfg = FakeConfig()
        self.addCleanup(self.cfg.close)
        self.path = mailstat.delivered_path(self.cfg.state)

    def write(self, text):
        with open(self.path, "w") as f:
            f.write(text)

    def test_a_missing_file_is_empty_and_not_an_error(self):
        """It is written on the first delivery. A fleet that has received nothing
        has no file, and that is the ordinary state of a new correspondent."""
        recs, err = mailstat.read_delivered(self.cfg.state)
        self.assertEqual(recs, {})
        self.assertIsNone(err)

    def test_an_unparseable_file_is_not_an_empty_one(self):
        self.write("{not json")
        recs, err = mailstat.read_delivered(self.cfg.state)
        self.assertIsNone(recs, "a damaged record must not read as no mail")
        self.assertIn("not readable JSON", err)

    def test_a_file_that_is_not_an_object_is_unreadable(self):
        self.write('["a list"]')
        recs, err = mailstat.read_delivered(self.cfg.state)
        self.assertIsNone(recs)
        self.assertIn("does not hold an object", err)

    def test_a_good_file_comes_back_as_it_was(self):
        self.write(json.dumps({"mail/x/1.md": {"outcome": "delivered"}}))
        recs, err = mailstat.read_delivered(self.cfg.state)
        self.assertEqual(recs, {"mail/x/1.md": {"outcome": "delivered"}})
        self.assertIsNone(err)

    def test_the_path_is_the_one_fleetmail_writes(self):
        """One derivation of where the record lives. Two would be a reader
        watching a file nobody writes, which is the failure the board already
        had once when its cache was renamed underneath it."""
        tool = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "bin", "fleetmail")
        with open(tool) as f:
            src = f.read()
        self.assertIn("DELIVERED = mailstat.delivered_path(STATE)", src)


class WhatNeedsAHuman(unittest.TestCase):
    """Mail that arrived and reached nobody -- and the records that look like it
    and are not."""

    def stuck(self, **recs):
        return mailstat.needs_human(recs)

    def test_a_quarantined_message_needs_a_human(self):
        got = self.stuck(**{"m1": {"outcome": "quarantined", "reason": "unlisted fleet"}})
        self.assertEqual([r["what"] for r in got], ["quarantined"])
        self.assertEqual(got[0]["why"], "unlisted fleet")

    def test_a_message_whose_nudge_failed_needs_a_human(self):
        got = self.stuck(**{"m1": {"outcome": "delivered", "nudged": False,
                                   "detail": "pane busy", "session": "beta"}})
        self.assertEqual([r["what"] for r in got], ["not delivered"])
        self.assertEqual(got[0]["session"], "beta")

    def test_an_acked_message_is_resolved_however_the_nudge_went(self):
        """The session can only have acked by having read it, which is better
        evidence than the nudge this tool sent."""
        self.assertEqual(self.stuck(**{"m1": {"outcome": "delivered",
                                              "nudged": False, "acked": True}}), [])

    def test_a_delivered_and_nudged_message_is_not_stuck(self):
        self.assertEqual(self.stuck(**{"m1": {"outcome": "delivered",
                                              "nudged": True}}), [])

    def test_an_old_record_with_no_nudged_field_is_not_an_alarm(self):
        """`nudged is False`, not `not nudged`. A record written before the field
        existed says nothing either way, and reading absence as failure would
        turn every message in the archive into an alarm nothing can clear."""
        self.assertEqual(self.stuck(**{"m1": {"outcome": "delivered"}}), [])

    def test_a_record_that_is_not_an_object_does_not_crash_the_reader(self):
        self.assertEqual(self.stuck(**{"m1": "a string"}), [])

    def test_both_kinds_are_reported_together(self):
        got = self.stuck(**{"a": {"outcome": "quarantined"},
                            "b": {"outcome": "delivered", "nudged": False}})
        self.assertEqual(sorted(r["what"] for r in got),
                         ["not delivered", "quarantined"])

    def test_the_tool_and_the_board_share_one_definition(self):
        """`fleetmail inbox` is what the board's line sends a reader to. The two
        disagreeing about what is stuck would be worse than either being wrong."""
        tool = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "bin", "fleetmail")
        with open(tool) as f:
            src = f.read()
        self.assertIn("mailstat.needs_human(seen)", src)


class TheLastArrival(unittest.TestCase):
    def test_the_newest_record_wins(self):
        recs = {"a": {"at": "2026-11-01T10:00:00+0000", "sender": "south/x"},
                "b": {"at": "2026-11-17T10:00:00+0000", "sender": "north/y"}}
        at, who = mailstat.last_arrival(recs)
        self.assertEqual(who, "north/y")
        self.assertEqual(at, mailstat._at(recs["b"]))

    def test_a_record_with_no_readable_time_is_skipped_not_fatal(self):
        at, who = mailstat.last_arrival({"a": {"at": "the other day"},
                                         "b": {"at": "2026-11-17T10:00:00+0000",
                                               "sender": "north/y"}})
        self.assertEqual(who, "north/y")

    def test_an_old_record_has_no_sender_and_is_not_given_one(self):
        """Every record written before 2026-11-18 lacks the field. The name could
        be cut back out of the filename the same tool built -- which is two
        derivations of one fact, and the reason this returns None instead."""
        at, who = mailstat.last_arrival({"a": {"at": "2026-11-17T10:00:00+0000"}})
        self.assertIsNotNone(at)
        self.assertIsNone(who)

    def test_nothing_at_all_is_none_rather_than_zero(self):
        self.assertEqual(mailstat.last_arrival({}), (None, None))


class TheFetchIsAskedOfSystemd(unittest.TestCase):
    """Because `fleetmail fetch` writes no trace when there is no new mail."""

    def fetch(self, probe, poll=15, now=1000 * HOUR):
        return mailstat.fetch("testfleet", poll, show=probe, now=now)

    def test_a_running_timer_that_just_fired_is_ok(self):
        state, info = self.fetch(show(timer(last=1000 * HOUR - 300), service()))
        self.assertEqual(state, "ok")
        self.assertAlmostEqual(info["age_s"], 300)

    def test_no_unit_on_this_machine_is_not_a_healthy_timer(self):
        state, info = self.fetch(show(timer(loaded=False)))
        self.assertEqual(state, "none")
        self.assertEqual(info["timer"], "fleetmail-testfleet.timer")

    def test_an_installed_but_stopped_timer_says_so(self):
        """Distinct from never installed: one is a fleet that does not fetch on a
        schedule, the other is a schedule somebody turned off."""
        state, _ = self.fetch(show(timer(active=False)))
        self.assertEqual(state, "off")

    def test_systemctl_that_cannot_be_asked_is_unknown(self):
        state, info = self.fetch(show(missing=(".timer",)))
        self.assertEqual(state, "unknown")
        self.assertIn("systemctl", info["why"])

    def test_a_timer_that_has_never_fired_is_not_a_timer_that_just_fired(self):
        state, _ = self.fetch(show(timer(last=None), service()))
        self.assertEqual(state, "never")

    def test_a_trigger_older_than_three_polls_is_stale(self):
        state, info = self.fetch(show(timer(last=1000 * HOUR - 46 * 60), service()))
        self.assertEqual(state, "stale")
        self.assertEqual(info["window_s"], 45 * 60)

    def test_a_trigger_inside_the_window_is_not(self):
        state, _ = self.fetch(show(timer(last=1000 * HOUR - 44 * 60), service()))
        self.assertEqual(state, "ok")

    def test_a_short_poll_still_gets_half_an_hour(self):
        """At `poll_minutes = 1` a three-minute window would be red most of the
        time, and a line that is usually red is one nobody reads on the day it
        is true."""
        state, _ = self.fetch(show(timer(last=1000 * HOUR - 20 * 60), service()),
                              poll=1)
        self.assertEqual(state, "ok")
        state, info = self.fetch(show(timer(last=1000 * HOUR - 40 * 60), service()),
                                 poll=1)
        self.assertEqual(state, "stale")
        self.assertEqual(info["window_s"], 30 * 60)

    def test_a_nonzero_exit_is_a_failed_fetch(self):
        state, info = self.fetch(show(timer(last=1000 * HOUR - 300),
                                      service(code=4, ran=1000 * HOUR - 290)))
        self.assertEqual(state, "failed")
        self.assertEqual(info["code"], 4)
        self.assertIn("could not be reached", info["meaning"])

    def test_an_exit_code_with_no_known_meaning_still_reports(self):
        state, info = self.fetch(show(timer(last=1000 * HOUR - 300), service(code=9)))
        self.assertEqual(state, "failed")
        self.assertEqual(info["meaning"], "exit 9")

    def test_stale_beats_a_cheerful_exit_code(self):
        """The reading this module exists to make impossible. A timer that
        stopped triggering leaves its last exit code behind unchanged, so a
        fetcher dead for a day would otherwise report `ok` from the status of
        whatever it did last week."""
        state, _ = self.fetch(show(timer(last=1000 * HOUR - 26 * HOUR), service(code=0)))
        self.assertEqual(state, "stale")

    def test_a_service_that_cannot_be_asked_is_unknown_not_ok(self):
        """Half an answer is how a source failure reaches a screen as a pass."""
        state, info = self.fetch(show(timer(last=1000 * HOUR - 300),
                                      missing=(".service",)))
        self.assertEqual(state, "unknown")
        self.assertIn("did not", info["why"])

    def test_a_service_with_no_exit_status_is_unknown(self):
        state, _ = self.fetch(show(timer(last=1000 * HOUR - 300),
                                   {"ExecMainStatus": ""}))
        self.assertEqual(state, "unknown")

    def test_the_unit_names_come_from_the_fleet_name(self):
        seen = []
        def probe(name, props, timeout=10):
            seen.append(name)
            return timer(last=1000 * HOUR - 60) if name.endswith(".timer") else service()
        mailstat.fetch("south", 15, show=probe, now=1000 * HOUR)
        self.assertEqual(seen, ["fleetmail-south.timer", "fleetmail-south.service"])

    def test_a_timestamp_in_a_format_this_cannot_read_is_not_a_time(self):
        """`--timestamp=unix` is a systemd 247 option. An older one answers with a
        localized string, and reading that as "never" is right: it is not a
        trigger time this can date, and inventing one is the other direction."""
        self.assertIsNone(mailstat._epoch("Wed 2026-11-18 09:39:17 EST"))
        self.assertIsNone(mailstat._epoch(""))
        self.assertEqual(mailstat._epoch("@1795012757"), 1795012757)


class TheProbeIsReachableByATest(unittest.TestCase):
    """A guard on the guards.

    `show` was a default argument until 2026-11-18, which binds at import: a test
    patching `mailstat._systemctl` would have left it pointing at the original and
    run `systemctl` against the real machine, passing or failing on whatever that
    machine's own fleetmail timer happened to be doing. Every test above would
    still have been green, and none of them would have been testing anything.
    """

    def test_patching_the_module_attribute_reaches_the_reader(self):
        calls = []
        def probe(name, props, timeout=10):
            calls.append(name)
            return {"LoadState": "not-found", "ActiveState": "inactive"}
        with mock.patch.object(mailstat, "_systemctl", probe):
            state, _ = mailstat.fetch("testfleet", 15)
        self.assertEqual(state, "none")
        self.assertTrue(calls, "the injected probe was never called")


class TheCombinedReading(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig()
        self.addCleanup(self.cfg.close)
        self.mail = {"fleet": "testfleet", "poll_minutes": 15}

    def write(self, recs):
        with open(mailstat.delivered_path(self.cfg.state), "w") as f:
            json.dump(recs, f)

    def read(self, probe, now=1000 * HOUR):
        return mailstat.read(self.mail, self.cfg.state, show=probe, now=now)

    def healthy(self):
        return show(timer(last=1000 * HOUR - 300), service())

    def test_nothing_stuck_and_a_live_timer_is_ok(self):
        self.write({"m": {"outcome": "delivered", "nudged": True,
                          "at": "2026-11-17T10:00:00+0000"}})
        state, data = self.read(self.healthy())
        self.assertEqual(state, "ok")
        self.assertEqual(data["stuck"], [])
        self.assertEqual(data["received"], 1)

    def test_stuck_mail_outranks_a_healthy_timer(self):
        self.write({"m": {"outcome": "delivered", "nudged": False, "session": "beta"}})
        state, data = self.read(self.healthy())
        self.assertEqual(state, "stuck")
        self.assertEqual(data["stuck"][0]["session"], "beta")

    def test_a_clean_record_does_not_rescue_a_dead_timer(self):
        """The whole point. The record is clean *because* nothing has been
        fetched, and that is the one case where clean means nothing."""
        self.write({"m": {"outcome": "delivered", "nudged": True}})
        state, _ = self.read(show(timer(last=1000 * HOUR - 30 * HOUR), service()))
        self.assertEqual(state, "stale")

    def test_an_unreadable_record_is_unknown_whatever_the_timer_says(self):
        with open(mailstat.delivered_path(self.cfg.state), "w") as f:
            f.write("{not json")
        state, data = self.read(self.healthy())
        self.assertEqual(state, "unknown")
        self.assertNotIn("stuck", data, "a line must not pair UNKNOWN with a count")
        self.assertIn("not readable JSON", data["why"])

    def test_the_fetch_state_is_carried_even_when_mail_is_stuck(self):
        """Both halves travel, always: a reader looking at an undelivered message
        still needs to know whether anything is bringing more in."""
        self.write({"m": {"outcome": "quarantined"}})
        state, data = self.read(show(timer(last=1000 * HOUR - 30 * HOUR), service()))
        self.assertEqual(state, "stuck")
        self.assertEqual(data["fetch"], "stale")


if __name__ == "__main__":
    unittest.main()
