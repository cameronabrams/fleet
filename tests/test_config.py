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


U1 = "aaaaaaaa-0000-4000-8000-000000000001"
U2 = "bbbbbbbb-0000-4000-8000-000000000002"

class Stopped(unittest.TestCase):
    def test_parked_and_retired(self):
        cfg = {"parked": {"a": {"uuid": U1, "since": "2026-09-13"}},
               "retired": {"b": {"uuid": U2, "since": "2026-09-01", "note": "done"}}}
        self.assertEqual(fc.stopped(cfg)["a"]["state"], "parked")
        self.assertEqual(fc.stopped(cfg)["b"]["note"], "done")
        self.assertEqual(fc.stopped_uuids(cfg), {U1: ("a", "parked"), U2: ("b", "retired")})
        self.assertEqual(fc.stopped({}), {})

    def test_invalid_entries(self):
        for bad in ({"parked": {"a": {"uuid": "aaaaaaaa", "since": "x"}}},       # short uuid
                    {"parked": {"a": {"uuid": U1}}},                              # no since
                    {"parked": {"a": "yes"}},                                     # not a table
                    {"parked": {"a": {"uuid": U1, "since": "x"}},
                     "retired": {"a": {"uuid": U2, "since": "x"}}}):              # both
            with self.assertRaises(fc.ConfigError, msg=bad):
                fc.stopped(bad)

if __name__ == "__main__":
    unittest.main()
