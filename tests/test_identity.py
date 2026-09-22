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
        """Reported by carla-talk 2026-09-22 from a chart it was putting on a slide.

        Auto-generated display names (`<project>-<short id>`) are NOT unique across
        transcripts. The real htpolynet-repo ran as
        ['htpolynet-30', 'htpolynet-8c', 'htpolynet-repo'], so the map correctly
        learns htpolynet-8c -> htpolynet-repo. A one-off Cameron started by hand in
        the same directory recorded only ['htpolynet-8c'] -- and inherited that
        lineage by bare name, drawn inside the role's lane and labelled
        "renamed: 'htpolynet-8c' became 'htpolynet-repo'". It was never renamed and
        was never that role. A confident label over an inference, and the record
        that carried it said `inferred: true` with an empty rename list in the same
        breath.

        A rename is one transcript's history. Applying it to another is a guess.
        """
        roles, renames = {"htpolynet-repo"}, {"htpolynet-8c": "htpolynet-repo"}
        owners = {"-git-htpolynet": "htpolynet-repo"}

        # the transcript that really did pass through the name: corroborated
        who, how, _ = ident.attribute("htpolynet-8c", "-git-htpolynet", roles, renames, owners,
                                      own_seq=["htpolynet-30", "htpolynet-8c", "htpolynet-repo"])
        self.assertEqual(who, "htpolynet-repo")
        self.assertIn("renamed", how)

        # a different transcript that merely ended up with the same auto name
        who, how, _ = ident.attribute("htpolynet-8c", "-git-htpolynet", roles, renames, owners,
                                      own_seq=["htpolynet-8c"], place_named=False)
        self.assertNotIn("renamed", how)          # fails even if own_seq is ignored
        self.assertEqual(who, "htpolynet-8c")     # so fleetgantt draws it unattached

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
