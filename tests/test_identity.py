import unittest
from fleet import identity as ident

ROLES = {"coord", "notebook", "study"}

class RenameMap(unittest.TestCase):
    def test_lineage_and_directory_and_newest_wins(self):
        seqs = [("-site", ["x-7e", "notebook"]),        # newest: x-7e became notebook
                ("-home", ["x-7e", "coord"]),           # older claim for the same old name
                ("-runs", ["runs-41"])]                 # never renamed: directory owner
        m = ident.rename_map(seqs, ROLES, {"-runs": "study"})
        self.assertEqual(m, {"x-7e": "notebook", "runs-41": "study"})

    def test_current_names_are_never_remapped(self):
        self.assertEqual(ident.rename_map([("-a", ["coord", "notebook"])], ROLES, {}), {})

    def test_names_in_line(self):
        self.assertEqual(ident.names_in_line('{"type":"agent-name","agentName":"a"}'), ["a"])
        self.assertEqual(ident.names_in_line("This session is b [abc123] ok"), ["b"])
        self.assertEqual(ident.names_in_line('{"agentName":"not a record"}'), [])

class Attribute(unittest.TestCase):
    def test_own_current_name_beats_the_table(self):
        who, how, inferred = ident.attribute("coord", "-home", ROLES, {"coord": "notebook"}, {})
        self.assertEqual((who, inferred), ("coord", False))

    def test_retired_name_follows_the_table(self):
        self.assertEqual(ident.attribute("x-7e", "-home", ROLES, {"x-7e": "notebook"}, {})[:1], ("notebook",))

    def test_unnamed_goes_to_directory_owner_as_inference(self):
        who, how, inferred = ident.attribute(None, "-runs", ROLES, {}, {"-runs": "study"})
        self.assertEqual((who, inferred), ("study", True))
        self.assertIn("directory", how)

    def test_named_non_role_placed_only_when_asked(self):
        self.assertEqual(ident.attribute("remote title", "-runs", ROLES, {}, {"-runs": "study"})[0], "study")
        self.assertEqual(ident.attribute("remote title", "-runs", ROLES, {}, {"-runs": "study"},
                                         place_named=False)[0], "remote title")

    def test_a_rename_needs_THIS_transcripts_own_record(self):
        """Reported by talk-session 2026-09-22 from a chart it was putting on a slide.

        Auto-generated display names (`<project>-<short id>`) are NOT unique across
        transcripts. The real sim-repo ran as
        ['sim-30', 'sim-8c', 'sim-repo'], so the map correctly
        learns sim-8c -> sim-repo. A one-off the fleet's owner started by hand in
        the same directory recorded only ['sim-8c'] -- and inherited that
        lineage by bare name, drawn inside the role's lane and labeled
        "renamed: 'sim-8c' became 'sim-repo'". It was never renamed and
        was never that role. A confident label over an inference, and the record
        that carried it said `inferred: true` with an empty rename list in the same
        breath.

        A rename is one transcript's history. Applying it to another is a guess.
        """
        roles, renames = {"sim-repo"}, {"sim-8c": "sim-repo"}
        owners = {"-git-sim": "sim-repo"}

        # the transcript that really did pass through the name: corroborated
        who, how, _ = ident.attribute("sim-8c", "-git-sim", roles, renames, owners,
                                      own_seq=["sim-30", "sim-8c", "sim-repo"])
        self.assertEqual(who, "sim-repo")
        self.assertIn("renamed", how)

        # a different transcript that merely ended up with the same auto name
        who, how, _ = ident.attribute("sim-8c", "-git-sim", roles, renames, owners,
                                      own_seq=["sim-8c"], place_named=False)
        self.assertNotIn("renamed", how)          # fails even if own_seq is ignored
        self.assertEqual(who, "sim-8c")     # so fleetgantt draws it unattached

    def test_no_own_seq_keeps_the_cross_transcript_lineage(self):
        """fleetlog needs it: the message graph wants old messages under the role
        that sent them, and has no lane to mislabel."""
        who, how, _ = ident.attribute("x-7e", "-home", ROLES, {"x-7e": "notebook"}, {})
        self.assertEqual(who, "notebook")
        self.assertIn("renamed", how)

    def test_nothing_known(self):
        self.assertEqual(ident.attribute(None, "-x", ROLES, {}, {})[0], None)

if __name__ == "__main__":
    unittest.main()


class TheChartStillRefusesToPlace(unittest.TestCase):
    """Reporting a candidate must not become placing one.

    The whole point of `place_named=False` is that a lane states an identity, and
    an uncorroborated rename is a guess. Adding the candidate is for the label,
    not the lane.
    """
    def test_an_uncorroborated_rename_is_still_not_placed(self):
        who, how, inferred = ident.attribute(
            "oldname", "oldname-mirror", {"newname"},
            {"oldname": "newname"}, {"oldname-mirror": "newname"},
            place_named=False, own_seq=["oldname"])
        self.assertEqual(who, "oldname")
        self.assertNotEqual(who, "newname")

    def test_a_corroborated_rename_is_placed_even_for_a_chart(self):
        who, how, inferred = ident.attribute(
            "oldname", "oldname-mirror", {"newname"},
            {"oldname": "newname"}, {"oldname-mirror": "newname"},
            place_named=False, own_seq=["oldname", "newname"])
        self.assertEqual(who, "newname")
        self.assertIn("renamed", how)
