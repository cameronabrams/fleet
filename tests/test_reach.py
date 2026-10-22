"""How long the cluster has been unreachable, and what its reservation table said.

`fleetwatch` computed `cluster_ok` on every run and recorded nothing, so its
failure line carried no duration: a two-minute blip, a two-day maintenance window
and a cluster that was never reachable at all all printed the same sentence.
The cluster was down for maintenance on the morning of 2026-10-22 and nothing in the
fleet could say when it had started.
"""
import json
import os
import tempfile
import unittest

from fleet import reach


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="fleet-reach-")
        self.state = self._tmp.name
        self.p = reach.reach_path(self.state)
        self.res = reach.reservations_path(self.state)

    def tearDown(self):
        self._tmp.cleanup()


class LastGood(Base):
    def test_a_good_read_moves_both_stamps(self):
        e = reach.record(self.p, "picotte", True, now=1000.0)
        self.assertEqual(e["last_good"], 1000.0)
        self.assertEqual(e["last_checked"], 1000.0)

    def test_a_failed_read_moves_only_last_checked(self):
        """The distinction the whole feature rests on: "down since 08:35" and
        "nobody has looked since 08:35" are different facts, and a recorder that
        wrote on success only could not tell them apart."""
        reach.record(self.p, "picotte", True, now=1000.0)
        e = reach.record(self.p, "picotte", False, now=5000.0)
        self.assertEqual(e["last_good"], 1000.0)
        self.assertEqual(e["last_checked"], 5000.0)

    def test_the_duration_is_measured_from_the_last_good_read(self):
        reach.record(self.p, "picotte", True, now=1000.0)
        e = reach.record(self.p, "picotte", False, now=5800.0)
        self.assertEqual(reach.down_for(e, now=5800.0), 4800.0)

    def test_clusters_are_kept_apart(self):
        reach.record(self.p, "one", True, now=1000.0)
        reach.record(self.p, "two", False, now=2000.0)
        d = reach.read(self.p)
        self.assertEqual(d["one"]["last_good"], 1000.0)
        self.assertIsNone(d["two"]["last_good"])

    def test_the_stamp_survives_a_reread(self):
        reach.record(self.p, "picotte", True, now=1000.0)
        self.assertEqual(reach.read(self.p)["picotte"]["last_good"], 1000.0)


class AbsenceIsNotZero(Base):
    """A fleet whose state directory was just created has not observed a cluster
    that is unreachable for no time at all."""

    def test_never_recorded_is_none_not_a_duration(self):
        e = reach.record(self.p, "picotte", False, now=1000.0)
        self.assertIsNone(reach.down_for(e, now=9999.0))

    def test_no_entry_at_all_is_none(self):
        self.assertIsNone(reach.down_for(None))
        self.assertIsNone(reach.down_for({}))

    def test_a_corrupt_file_reads_as_empty_rather_than_raising(self):
        """A convenience on top of the cluster query. A tool that could not report
        the cluster because it could not report how long the cluster had been
        down would have made the outage worse."""
        with open(self.p, "w") as f:
            f.write("{not json")
        self.assertEqual(reach.read(self.p), {})
        e = reach.record(self.p, "picotte", True, now=1000.0)
        self.assertEqual(e["last_good"], 1000.0)

    def test_a_file_holding_a_list_reads_as_empty(self):
        with open(self.p, "w") as f:
            json.dump([1, 2, 3], f)
        self.assertEqual(reach.read(self.p), {})

    def test_an_unwritable_path_does_not_raise(self):
        p = os.path.join(self.state, "nodir", "x", "reach.json")
        os.makedirs(os.path.dirname(os.path.dirname(p)))
        with open(os.path.dirname(p), "w") as f:      # a FILE where a dir must go
            f.write("x")
        e = reach.record(p, "picotte", True, now=1000.0)
        self.assertEqual(e["last_good"], 1000.0, "the entry is still returned")


class TheReservationLogIsARecorderNotAParser(Base):
    """An EXPERIMENT. SLURM holds planned maintenance as a reservation readable
    while the cluster is still up, which is exactly when a warning would help --
    but whether this site creates them is unknown. `scontrol show reservation`
    said "No reservations in the system" when the cluster returned, and a completed
    MAINT reservation is removed, so that is what an empty table looks like
    whether or not the site uses them. One look after the fact cannot tell the
    two cases apart, so nothing here interprets the text.
    """

    def test_the_first_table_is_recorded(self):
        self.assertTrue(reach.record_reservations(
            self.res, "picotte", "No reservations in the system", now=1000.0))
        self.assertIn("No reservations", open(self.res).read())

    def test_an_unchanged_table_is_not_recorded_again(self):
        """A log repeating the same line every quarter hour would bury the one
        entry that matters under thousands that do not."""
        reach.record_reservations(self.res, "picotte", "No reservations", now=1000.0)
        size = os.path.getsize(self.res)
        self.assertFalse(reach.record_reservations(
            self.res, "picotte", "No reservations", now=2000.0))
        self.assertEqual(os.path.getsize(self.res), size)

    def test_a_changed_table_is_recorded(self):
        reach.record_reservations(self.res, "picotte", "No reservations", now=1000.0)
        self.assertTrue(reach.record_reservations(
            self.res, "picotte",
            "ReservationName=maint StartTime=2026-11-01T06:00:00 Flags=MAINT",
            now=2000.0))
        body = open(self.res).read()
        self.assertIn("No reservations", body)
        self.assertIn("Flags=MAINT", body, "the earlier entry is kept, not replaced")

    def test_going_back_to_empty_is_a_change_too(self):
        """The window closing is as much a transition as its appearing, and a
        recorder that only noticed new text would log a maintenance reservation
        that never seemed to end."""
        reach.record_reservations(self.res, "picotte", "Flags=MAINT", now=1000.0)
        self.assertTrue(reach.record_reservations(
            self.res, "picotte", "No reservations", now=2000.0))

    def test_clusters_do_not_mask_each_other(self):
        reach.record_reservations(self.res, "one", "A", now=1000.0)
        self.assertTrue(reach.record_reservations(self.res, "two", "A", now=1001.0),
                        "a different cluster saying the same thing is still news")
        self.assertFalse(reach.record_reservations(self.res, "one", "A", now=1002.0))

    def test_empty_output_is_not_recorded(self):
        """A failed ssh produces no text, and "" is not an observation that the
        reservation table was empty -- the distinction this whole module exists
        to keep."""
        self.assertFalse(reach.record_reservations(self.res, "picotte", "", now=1000.0))
        self.assertFalse(reach.record_reservations(self.res, "picotte", None, now=1000.0))
        self.assertFalse(os.path.exists(self.res))

    def test_nothing_is_parsed(self):
        """Deliberately: the open question is whether MAINT entries ever appear,
        and a parser written against a guess would answer it with its own
        assumptions. The text comes back exactly as it went in."""
        odd = "ReservationName=x|y Flags=MAINT\n  Nodes=node[01-99] Weird=|=|"
        reach.record_reservations(self.res, "picotte", odd, now=1000.0)
        self.assertEqual(reach.last_reservation_text(self.res, "picotte"), odd)

    def test_no_log_yet_reads_as_none(self):
        self.assertIsNone(reach.last_reservation_text(self.res, "picotte"))
