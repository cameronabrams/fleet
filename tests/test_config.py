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

    def test_color_mismatch_and_lost(self):
        self.assertEqual(self.kinds("alpha", "blue"), ["color"])
        self.assertEqual(self.kinds("alpha", None), ["color"])

    def test_unknown_live_color_is_not_a_mismatch(self):
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


class AppendingADeclaration(unittest.TestCase):
    """A tool may append a declaration a human supplied; it may never regenerate.

    The rule began as "never write a file a human authors", justified by there
    being no comment-preserving TOML writer in the standard library. That
    justification rules out REGENERATING a file and does not rule out appending a
    line -- a peer argued it and was right (2026-10-20).

    The hazard it was really protecting against is not comments. `fc.load()`
    parses at call time and every tool calls it, so a duplicate key takes the
    whole fleet's tooling down at once rather than the feature that wrote it.
    Which is why every guard below is a refusal, and why the write is verified in
    a temp file before it replaces anything.
    """
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "fleet.toml")
        self.write('# how colors work here\n[colors]\nalpha = "red"\n\n[owners]\n')

    def write(self, text):
        with open(self.path, "w") as f:
            f.write(text)

    def test_a_new_key_is_appended_and_nothing_else_changes(self):
        before = open(self.path).read()
        ok, why = fc.declare(self.path, "colors", "beta", "blue")
        self.assertTrue(ok, why)
        after = open(self.path).read()
        self.assertEqual(fc.colors(self.load())["beta"], "blue")
        self.assertEqual(before.count("#"), after.count("#"))
        self.assertEqual([l for l in after.splitlines()
                          if l not in before.splitlines()], ['beta = "blue"'])

    def load(self):
        with open(self.path, "rb") as f:
            import tomllib
            return tomllib.load(f)

    def test_the_same_value_again_succeeds_and_changes_nothing(self):
        before = open(self.path).read()
        ok, why = fc.declare(self.path, "colors", "alpha", "red")
        self.assertTrue(ok, why)
        self.assertEqual(open(self.path).read(), before)

    def test_a_different_value_is_refused(self):
        """Changing a declaration is not appending one, and the human made that
        one."""
        ok, why = fc.declare(self.path, "colors", "alpha", "blue")
        self.assertFalse(ok)
        self.assertIn("already", why)
        self.assertEqual(fc.colors(self.load())["alpha"], "red")

    def test_a_header_in_a_comment_is_not_the_table(self):
        """The ambiguity that bit a hand-written regex on 2026-10-19: it matched
        by shape, and the shape appears in prose too."""
        self.write('# put the color under [colors]\n[colors]\nalpha = "red"\n')
        ok, why = fc.declare(self.path, "colors", "beta", "blue")
        self.assertTrue(ok, why)
        self.assertEqual(fc.colors(self.load())["beta"], "blue")

    def test_a_missing_table_is_refused_rather_than_guessed(self):
        self.write('[human]\nname = "A"\n')
        ok, why = fc.declare(self.path, "colors", "beta", "blue")
        self.assertFalse(ok)
        self.assertIn("refusing to guess", why)

    def test_a_file_that_does_not_parse_is_not_touched(self):
        """A tool must not be what discovers somebody else's broken file by
        adding to it."""
        self.write('[colors]\nalpha = "red"\nalpha = "blue"\n')
        before = open(self.path).read()
        ok, why = fc.declare(self.path, "colors", "beta", "blue")
        self.assertFalse(ok)
        self.assertIn("does not parse", why)
        self.assertEqual(open(self.path).read(), before)


class AWriteVerifiedBeforeItLands(unittest.TestCase):
    """Where the check sits is part of the check.

    "Write it, then re-parse to confirm" detects the damage correctly and
    prevents none of it: the broken file already exists while the check runs,
    every tool parses it at startup, and anything invoked in between dies.
    """
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "fleet.toml")
        with open(self.path, "w") as f:
            f.write('[human]\nname = "A"\n')

    def test_content_that_would_not_parse_never_lands(self):
        before = open(self.path).read()
        ok, why = fc.write_verified(self.path, '[human]\nname = "A"\nname = "B"\n')
        self.assertFalse(ok)
        self.assertIn("would not parse", why)
        self.assertEqual(open(self.path).read(), before,
                         "a broken file was left on disk, if only briefly")

    def test_a_failing_check_stops_it_too(self):
        ok, why = fc.write_verified(self.path, '[human]\nname = "B"\n',
                                    lambda d: "not what was asked for")
        self.assertFalse(ok)
        self.assertEqual(fc.load()["human"]["name"] if False else
                         open(self.path).read(), '[human]\nname = "A"\n')

    def test_no_temp_file_is_left_behind_either_way(self):
        fc.write_verified(self.path, '[human]\nname = "B"\n')
        fc.write_verified(self.path, 'nope = =\n')
        self.assertEqual([f for f in os.listdir(self.tmp.name)
                          if f.startswith(".fleet-write-")], [])

    def test_a_good_write_lands(self):
        ok, why = fc.write_verified(self.path, '[human]\nname = "B"\n')
        self.assertTrue(ok, why)
        self.assertIn('name = "B"', open(self.path).read())
