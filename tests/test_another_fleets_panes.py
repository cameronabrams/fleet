"""Another fleet's panes, in the tools that ACT on one.

`belongs` landed on 2026-10-20 and was wired into `fleetboard` -- which draws a
screen -- and nowhere else. Every tool that restarts a session, retires one, types
into one or decides one is missing still gated on `@agent` alone, so a correct
membership rule was reachable from the one place where being wrong costs nothing.

These are the other places. Each test drives the tool's own pane-mapping function
with a fake tmux, rather than the mocked pane maps the tools' own suites use: the
mapping is the thing that changed, and a suite that mocks it cannot see it.

`testfleet` is ours (tests/support.py BASE_TOML); `teaching` is somebody else's.
"""
import os
import unittest
from unittest import mock

from tests.support import FakeConfig, load_tool


class Base(unittest.TestCase):
    tool = None

    def setUp(self):
        self.cfg = FakeConfig()
        self.t = load_tool(self.tool)

    def tearDown(self):
        self.cfg.close()

    def assertOurs(self, got, expected):
        self.assertEqual(got, expected)


class FleetcontextMapsOnlyOurs(Base):
    """fleetcontext COMPACTS a session and resets its color. A pane it maps by
    mistake is another owner's session compacted without anyone asking."""
    tool = "fleetcontext"

    def rows(self, *rows):
        out = "\n".join("\t".join(r) for r in rows)
        return mock.patch.object(self.t, "tmux", return_value=(0, out, ""))

    def test_our_pane_is_mapped(self):
        with self.rows(("%1", "100", "alpha", "0", "testfleet")):
            found, outside = self.t.panes()
        self.assertEqual(found, {100: "%1"})
        self.assertEqual(outside, [])

    def test_another_fleets_pane_is_not_mapped(self):
        with self.rows(("%2", "200", "beta", "0", "teaching")):
            found, outside = self.t.panes()
        self.assertEqual(found, {})
        self.assertEqual([o["pane"] for o in outside], ["%2"])
        self.assertEqual(outside[0]["why"], "@fleet=teaching")

    def test_an_unlabeled_pane_is_not_mapped_and_says_which_label_is_missing(self):
        """The two reasons are told apart, because the fixes differ: a pane with no
        `@agent` is not a session, and a pane with no `@fleet` may well be ours and
        stamped by a tool too old to say so."""
        with self.rows(("%3", "300", "gamma", "0", ""), ("%4", "400", "", "0", "testfleet")):
            found, outside = self.t.panes()
        self.assertEqual(found, {})
        self.assertEqual([(o["pane"], o["why"]) for o in outside],
                         [("%3", "@fleet=(unlabeled)"), ("%4", "no @agent")])


class FleetnudgeTypesOnlyIntoOurs(Base):
    """fleetnudge TYPES A LINE into a pane. The wrong pane is somebody else's
    session receiving an instruction addressed to a session of ours."""
    tool = "fleetnudge"

    def rows(self, *rows):
        out = "\n".join("\t".join(r) for r in rows)
        return mock.patch.object(self.t, "tmux", return_value=(0, out, ""))

    def test_only_our_panes_are_typeable(self):
        with self.rows(("%1", "100", "alpha", "testfleet"),
                       ("%2", "200", "beta", "teaching"),
                       ("%3", "300", "gamma", "")):
            self.assertEqual(self.t.panes(), {100: "%1"})


class FleetwatchCountsOnlyOurWatchers(Base):
    """A stranger's poll loop advertised as a live watcher of our cluster work is
    the reassuring direction: the work looks attended and is not."""
    tool = "fleetwatch"

    def test_children_of_another_fleets_pane_are_not_our_watchers(self):
        rows = "100\talpha\ttestfleet\n200\tbeta\tteaching\n300\tgamma\t\n"
        seen = []

        def sh(*a):
            if a[0] == "tmux":
                return rows
            if a[0] == "pgrep":
                seen.append(a[-1])
            return ""

        with mock.patch.object(self.t, "sh", side_effect=sh):
            self.t.watchers()
        self.assertEqual(seen, ["100"], "only our fleet's panes are descended into")


class FleetwaitingAsksOnlyAboutOurs(Base):
    """A stranger's session reported as blocked on this fleet's owner is a question
    he cannot answer about a pane he should not be reading."""
    tool = "fleetwaiting"

    def test_another_fleets_session_is_not_looked_at(self):
        """Asserted on which panes it descends into, not on the returned dict: a
        session only appears in that dict once a real transcript on disk
        self-reports its name, and a fixture elaborate enough to produce one would
        be testing the transcript search instead of the membership check."""
        rows = ("alpha\ttestfleet\t100\t/w/a\n"
                "beta\tteaching\t200\t/w/b\n"
                "gamma\t\t300\t/w/c\n")
        seen = []

        def sh(*a):
            if a[0] == "tmux":
                return rows
            if a[0] == "pgrep":
                seen.append(a[-1])
            return ""

        with mock.patch.object(self.t, "sh", side_effect=sh):
            self.t.live_sessions()
        self.assertEqual(seen, ["100"], "only our fleet's panes are descended into")


class FleetretireActsOnlyOnOurs(Base):
    """Retiring another fleet's session is not a display error anybody scrolls
    past. `pane_of` matches on pid, which finds a stranger's pane as readily."""
    tool = "fleetretire"

    def pane_of(self, fleet):
        row = "\t".join(["%9", "4242", "@0", "1", "alpha", fleet])
        with mock.patch.object(self.t, "tmux", return_value=(0, row, "")), \
             mock.patch.object(self.t, "ppid", return_value=4242):
            return self.t.pane_of(4242)

    def test_our_pane_is_found(self):
        self.assertEqual(self.pane_of("testfleet")["pane"], "%9")

    def test_another_fleets_pane_is_not(self):
        self.assertIsNone(self.pane_of("teaching"))

    def test_an_unlabeled_pane_is_not(self):
        self.assertIsNone(self.pane_of(""))


class FleetrestoreStampsTheFleet(Base):
    """The outage this flip would otherwise have caused, and it would have arrived
    at a power cycle rather than at the flip.

    Membership went strict while `fleetrestore` stamped `@agent` alone, so a
    restore would have rebuilt every session correctly and left all of them
    invisible: fleetsnap seeing no fleet, fleetupgrade nothing to roll. The flip
    was checked against the panes that EXIST; this is the path that creates them.
    """
    tool = "fleetrestore"

    def test_the_plan_sets_both_labels(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                "bin", "fleetrestore")).read()
        self.assertIn('"@fleet", OURS', src,
                      "fleetrestore must stamp @fleet on every pane it restores")
