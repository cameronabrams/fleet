import os, unittest
from tests.support import FakeConfig
from fleet import config as fc

class Load(unittest.TestCase):
    def test_missing_config_raises_when_required(self):
        cfg = FakeConfig()
        try:
            os.remove(os.path.join(cfg.config, "fleet.toml"))
            with self.assertRaises(fc.ConfigError):
                fc.load()
            self.assertEqual(fc.load(required=False), {})
        finally:
            cfg.close()

    def test_state_dir_from_config_and_default(self):
        cfg = FakeConfig()
        try:
            self.assertEqual(fc.state_dir(), cfg.state)
            self.assertEqual(fc.state_dir({}), os.path.expanduser("~/.local/state/fleet"))
        finally:
            cfg.close()


class Sections(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig()
        self.c = fc.load()

    def tearDown(self):
        self.cfg.close()

    def test_single_cluster_needs_no_name(self):
        cl = fc.cluster(self.c)
        self.assertEqual(cl["name"], "testcluster")
        self.assertEqual(cl["user"], "tester")

    def test_cluster_errors(self):
        with self.assertRaises(fc.ConfigError):
            fc.cluster({})
        with self.assertRaises(fc.ConfigError):
            fc.cluster(self.c, "other")
        two = {"cluster": {"a": {}, "b": {}}}
        with self.assertRaises(fc.ConfigError):
            fc.cluster(two)
        self.assertEqual(fc.cluster(two, "b")["name"], "b")

    def test_owners_keep_written_order(self):
        # first match wins, so order is the semantics
        self.assertEqual(fc.owners(self.c),
                         [("/proj-a-sweep", "alpha-runs"), ("/proj-a", "alpha")])

    def test_colors_valid_and_invalid(self):
        self.assertEqual(fc.colors(self.c), {"alpha": "red", "beta": "blue"})
        with self.assertRaises(fc.ConfigError):
            fc.colors({"colors": {"x": "magenta"}})

    def test_launch_env_quotes_values(self):
        self.assertEqual(fc.launch_env({}), "")
        self.assertEqual(fc.launch_env({"spawn": {"env": {"A": 1, "B": "two words"}}}),
                         "A=1 B='two words'")


class Membership(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig(briefs=("alpha",))
        self.c = fc.load()

    def tearDown(self):
        self.cfg.close()

    def kinds(self, *a, **kw):
        return [k for k, _, _ in fc.membership_problems(self.c, *a, **kw)]

    def test_complete(self):
        self.assertEqual(self.kinds("alpha", "red"), [])

    def test_colour_mismatch_and_lost(self):
        self.assertEqual(self.kinds("alpha", "blue"), ["color"])
        self.assertEqual(self.kinds("alpha", None), ["color"])

    def test_unknown_live_colour_is_not_a_mismatch(self):
        self.assertEqual(self.kinds("alpha", None, color_known=False), [])

    def test_no_brief(self):
        self.assertEqual(self.kinds("beta", "blue"), ["brief"])

    def test_undeclared(self):
        self.assertEqual(self.kinds("gamma", "red"), ["brief", "color"])

if __name__ == "__main__":
    unittest.main()
