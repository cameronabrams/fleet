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

    def test_nothing_known(self):
        self.assertEqual(ident.attribute(None, "-x", ROLES, {}, {})[0], None)

if __name__ == "__main__":
    unittest.main()
