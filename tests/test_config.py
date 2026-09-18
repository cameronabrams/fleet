import os, tempfile, tomllib, unittest
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


class Context(unittest.TestCase):
    def ctx(self, body):
        return fc.context(tomllib.loads(body))

    def test_defaults(self):
        c = self.ctx("")
        self.assertEqual((c["compact_above"], c["clear_above"], c["idle_minutes"]), (250000, 500000, 10))
        self.assertIn("job ids", c["compact_focus"])

    def test_override_one_key(self):
        c = self.ctx("[context]\ncompact_above = 100000\n")
        self.assertEqual((c["compact_above"], c["clear_above"]), (100000, 500000))

    def test_invalid(self):
        for body in ("[context]\ncompact_abve = 1\n",
                     "[context]\ncompact_above = \"250k\"\n",
                     "[context]\ncompact_above = true\n",
                     "[context]\nclear_above = 1000\n",
                     "[context]\ncompact_focus = \"a\\nb\"\n"):
            with self.subTest(body=body), self.assertRaises(fc.ConfigError):
                self.ctx(body)

class Notify(unittest.TestCase):
    def test_unconfigured_and_defaults(self):
        self.assertEqual(fc.notify({}), {})
        n = fc.notify(tomllib.loads('[notify]\nntfy_topic_file = "~/t"\n'))
        self.assertEqual(n["ntfy_server"], "https://ntfy.sh")
        self.assertEqual(n["ntfy_topic_file"], os.path.expanduser("~/t"))
        self.assertEqual(n["mute_file"], "")

    def test_invalid(self):
        for body in ('[notify]\nntfy_server = "https://x"\n', '[notify]\ntopic = "t"\n'):
            with self.subTest(body=body), self.assertRaises(fc.ConfigError):
                fc.notify(tomllib.loads(body))

    def test_topic_from_hook_script_or_plain_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t")
            for text, want in (('#!/bin/sh\nTOPIC="abc-1"\ncurl ...\n', "abc-1"),
                               ("TOPIC=plain_2\n", "plain_2"),
                               ("\n  my-topic\n", "my-topic"),
                               ("#!/bin/sh\necho hi\n", None),
                               ("two words\n", None)):
                with open(p, "w") as f:
                    f.write(text)
                self.assertEqual(fc.ntfy_topic(p), want, text)
            self.assertIsNone(fc.ntfy_topic(os.path.join(d, "absent")))

class Mail(unittest.TestCase):
    def mail(self, body):
        return fc.mail(tomllib.loads(body))

    def test_defaults(self):
        m = self.mail('[mail]\nfleet = "north"\nrepo = "/m.git"\n')
        self.assertEqual((m["fleet"], m["poll_minutes"]), ("north", 5))
        self.assertTrue(m["clone"].endswith("/mailbox"))

    def test_invalid(self):
        for body in ('[mail]\nfleet = "north"\n',                      # no repo
                     '[mail]\nrepo = "/m.git"\n',                      # no fleet
                     '[mail]\nfleet = "North Fleet"\nrepo = "/m.git"\n',
                     '[mail]\nfleet = "north"\nrepo = "/m.git"\npoll_minutes = 0\n',
                     '[mail]\nfleet = "north"\nrepo = "/m.git"\nwho = "x"\n'):
            with self.subTest(body=body), self.assertRaises(fc.ConfigError):
                self.mail(body)
        self.assertEqual(fc.mail({}), {})

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


class Zone(unittest.TestCase):
    def test_file_wins_then_fixed_then_utc(self):
        cfg = FakeConfig()
        try:
            f = os.path.join(cfg.root, "tz")
            open(f, "w").write("Europe/Lisbon\n")
            self.assertEqual(fc.display_zone({"human": {"timezone_file": f, "timezone": "Asia/Tokyo"}})[0],
                             "Europe/Lisbon")
            open(f, "w").write("Not/AZone\n")
            z, why = fc.display_zone({"human": {"timezone_file": f, "timezone": "Asia/Tokyo"}})
            self.assertEqual(z, "Asia/Tokyo"); self.assertIn("ZoneInfoNotFoundError", why)
            self.assertEqual(fc.display_zone({"human": {"timezone_file": f + ".missing"}})[0], "UTC")
            self.assertEqual(fc.display_zone({})[0], "UTC")
        finally:
            cfg.close()

class Events(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig()

    def tearDown(self):
        self.cfg.close()

    def write(self, text):
        open(os.path.join(self.cfg.config, "events.toml"), "w").write(text)

    def test_times_in_zone_and_date_only(self):
        self.write('[[event]]\ndate = "2026-09-09"\ntime = "10:01"\nlabel = "b"\n'
                   '[[event]]\ndate = "2026-09-07"\nlabel = "a"\ndetail = "d"\n')
        ev = fc.events("America/New_York")
        self.assertEqual([(e[1], e[3]) for e in ev], [("a", False), ("b", True)])   # sorted by time
        import datetime
        utc = datetime.datetime(2026, 9, 9, 14, 1, tzinfo=datetime.timezone.utc).timestamp()
        self.assertEqual(ev[1][0], utc)                  # 10:01 EDT is 14:01 UTC
        self.assertEqual(fc.events("UTC")[1][0] - ev[1][0], -4 * 3600)

    def test_missing_file_is_no_events(self):
        self.assertEqual(fc.events("UTC"), [])

    def test_bad_entries(self):
        for bad in ('[[event]]\nlabel = "no date"\n', '[[event]]\ndate = "2026-09-09"\n',
                    '[[event]]\ndate = "2026-09-09"\ntime = "10am"\nlabel = "x"\n'):
            self.write(bad)
            with self.assertRaises(fc.ConfigError, msg=bad):
                fc.events("UTC")

if __name__ == "__main__":
    unittest.main()
