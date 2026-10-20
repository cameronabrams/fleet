"""Creating a configuration, so that a fresh machine has something to run against.

`install` exits 2 without a `fleet.toml`, so this is the step that blocks every
other step -- which is why it was built before the conveniences, against the
instinct to do the easiest one first.

The constraint that shapes it: **the repository ships the schema and the
questions, never the answers.** A name, a cluster, an ssh host and an account code
belong to a person and a site, and this package may not contain them. So defaults
travel from an existing configuration or come from the prompts, and the tests
below are mostly about which parts of an existing one may travel.
"""
import os
import tempfile
import tomllib
import unittest

from tests.support import APP, FakeConfig, load_tool

SOURCE = '''# why this fleet works the way it does
[human]
name = "Someone"
timezone = "America/New_York"

# how long a session may grow
[context]
compact_above = 250000

# every member needs a declared color
[colors]
alpha = "red"
beta = "blue"

# who answers for what on the cluster
[owners]
alpha = "proj-a"

[cluster.site]
ssh_host = "login.example"
user = "someone"

[[cluster.site.accounts]]
name = "acct-1"

# parked on purpose
[parked.alpha]
uuid = "u-1"
since = "2026-10-01"

[retired.gamma]
uuid = "u-2"
since = "2026-09-01"

[authority]
said_by = "the human"
read_this_as = "a grant that has lapsed"

[updates]
status = "/var/lib/somehost-updates/status.json"

# this fleet's own name
[fleet]
name = "sourcefleet"

# where cross-fleet mail goes
[mail]
fleet = "sourcefleet"
repo = "git@example:mail.git"
'''


class WhatTravelsToANewFleet(unittest.TestCase):
    def setUp(self):
        self.t = load_tool("fleetinit")

    def strip(self):
        return self.t.strip_per_fleet(SOURCE)

    def test_preferences_and_clusters_travel(self):
        """The whole point: a new fleet of the same person's keeps their name,
        their thresholds and the cluster they work on -- including the comments,
        which say why each value is what it is."""
        text, _emptied, _dropped = self.strip()
        d = tomllib.loads(text)
        self.assertEqual(d["human"]["name"], "Someone")
        self.assertEqual(d["context"]["compact_above"], 250000)
        self.assertEqual(d["cluster"]["site"]["ssh_host"], "login.example")
        self.assertEqual(len(d["cluster"]["site"]["accounts"]), 1)
        self.assertIn("why this fleet works the way it does", text)
        self.assertEqual(d["mail"]["repo"], "git@example:mail.git",
                         "the mailbox itself is shared; only the name is per-fleet")

    def test_history_is_dropped_entirely(self):
        """A copy carrying these describes a fleet that does not exist on the new
        machine -- parked entries naming transcripts that are not on that disk."""
        text, _e, dropped = self.strip()
        d = tomllib.loads(text)
        for gone in ("parked", "retired", "authority", "updates"):
            self.assertNotIn(gone, d, gone)
        self.assertEqual(sorted(dropped),
                         ["authority", "fleet", "mail.fleet", "parked.alpha",
                          "retired.gamma", "updates"])

    def test_a_per_fleet_key_goes_without_its_section(self):
        """`[mail]` is a preference -- which mailbox, how often to poll -- but
        `fleet` inside it is this fleet's name in that mailbox. Dropping the
        section would lose the mailbox; dropping the line keeps the useful part
        and discards the identity."""
        text, _e, dropped = self.strip()
        d = tomllib.loads(text)
        self.assertEqual(d["mail"]["repo"], "git@example:mail.git")
        self.assertNotIn("fleet", d["mail"])
        self.assertIn("mail.fleet", dropped)

    def test_the_source_fleets_own_name_does_not_travel(self):
        """A copy that kept it would label its panes as the fleet it was copied
        from -- the exact confusion the name exists to prevent, and it would
        address peers under the old fleet's name too."""
        text, _e, _d = self.strip()
        self.assertNotIn("fleet", tomllib.loads(text),
                         "the new fleet inherited the old one's identity")
        self.assertNotIn("sourcefleet", text)

    def test_the_roster_is_emptied_not_deleted(self):
        """Found by running the whole path, not by a unit test: deleting the
        header left a config that `fleetspawn --color` then refused to add to --
        correctly, since it will not guess where a missing section goes. Every
        fleet HAS a roster; it is per-fleet in its contents, not its existence."""
        text, emptied, _d = self.strip()
        d = tomllib.loads(text)
        self.assertEqual(d["colors"], {})
        self.assertEqual(d["owners"], {})
        self.assertEqual(sorted(emptied), ["colors", "owners"])
        self.assertIn("[colors]", text, "the header a later --color needs is gone")

    def test_an_emptied_section_keeps_the_comment_that_explains_it(self):
        """A fresh fleet needs that paragraph more than an established one does."""
        text, _e, _d = self.strip()
        self.assertIn("every member needs a declared color", text)

    def test_a_dropped_section_takes_its_comment_with_it(self):
        """Prose explaining a section that is no longer there is worse than
        keeping both or dropping both."""
        text, _e, _d = self.strip()
        self.assertNotIn("parked on purpose", text)

    def test_the_result_parses(self):
        text, _e, _d = self.strip()
        tomllib.loads(text)          # raises if not


class SettingTheAnswers(unittest.TestCase):
    def setUp(self):
        self.t = load_tool("fleetinit")

    def test_an_existing_value_is_replaced_in_place(self):
        out = self.t.set_value(SOURCE, "human", "name", "Other")
        self.assertEqual(tomllib.loads(out)["human"]["name"], "Other")
        self.assertEqual(len(out.splitlines()), len(SOURCE.splitlines()))

    def test_a_trailing_comment_on_that_line_survives(self):
        src = '[human]\nname = "A"  # who to address\n'
        out = self.t.set_value(src, "human", "name", "B")
        self.assertIn("# who to address", out)
        self.assertEqual(tomllib.loads(out)["human"]["name"], "B")

    def test_a_missing_key_is_appended_under_its_header(self):
        out = self.t.set_value(SOURCE, "human", "aliases", "x")
        self.assertEqual(tomllib.loads(out)["human"]["aliases"], "x")

    def test_a_missing_table_is_added(self):
        out = self.t.set_value("[human]\nname = \"A\"\n", "mail", "fleet", "f")
        self.assertEqual(tomllib.loads(out)["mail"]["fleet"], "f")

    def test_it_never_touches_another_table_with_the_same_key(self):
        src = '[colors]\nalpha = "red"\n\n[owners]\nalpha = "proj"\n'
        out = self.t.set_value(src, "owners", "alpha", "other")
        d = tomllib.loads(out)
        self.assertEqual(d["colors"]["alpha"], "red")
        self.assertEqual(d["owners"]["alpha"], "other")


class OneNameReachesBothItsReaders(unittest.TestCase):
    """`fleet.config.fleet_name` prefers `[fleet].name`, but `fleetmail` reads
    `[mail].fleet` directly for its address namespace. An answer has to land in
    both, or the fleet is called one thing by its panes and another by its mail.

    A derived configuration carried the SOURCE fleet's `[mail].fleet` until this
    was noticed: a new fleet addressing peers under the old one's name.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.t = load_tool("fleetinit")
        self.addCleanup(self.cfg.close)

    def built(self, **kw):
        from types import SimpleNamespace
        a = SimpleNamespace(name=None, timezone=None, name_of_fleet=None, keep=False)
        for k, v in kw.items():
            setattr(a, k, v)
        text, _notes = self.t.build(a, SOURCE, "source")
        return tomllib.loads(text)

    def test_the_fleet_name_lands_in_both_places(self):
        d = self.built(name_of_fleet="newfleet", name="N", timezone="Z")
        self.assertEqual(d["fleet"]["name"], "newfleet")
        self.assertEqual(d["mail"]["fleet"], "newfleet",
                         "mail would address peers under another fleet's name")

    def test_it_does_not_invent_a_mail_section(self):
        """A fleet with no correspondents needs none, and creating one would
        declare a mailbox nobody configured."""
        src = SOURCE.replace('[fleet]\nname = "sourcefleet"', '')
        from types import SimpleNamespace
        a = SimpleNamespace(name="N", timezone="Z", name_of_fleet="newfleet",
                            keep=False)
        text, _ = self.t.build(a, src.replace("[mail]", "[nomail]"), "s")
        d = tomllib.loads(text)
        self.assertEqual(d["fleet"]["name"], "newfleet")
        self.assertNotIn("mail", d)


class ItWillNotOverwriteAConfiguration(unittest.TestCase):
    """One that is already there is somebody's work."""
    def test_the_refusal_is_in_the_tool(self):
        src = open(os.path.join(APP, "bin", "fleetinit")).read()
        self.assertIn("already exists", src)
        self.assertIn("somebody's work", src)
        i = src.index("already exists")
        self.assertIn("sys.exit(2)", src[i:i + 400])
