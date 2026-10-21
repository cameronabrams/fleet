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


class PointingAtAnotherMachine(unittest.TestCase):
    """`--from <host>`, so the fleet.toml that already exists somewhere does not
    first have to be fetched by hand.

    Keeping a copy to point at is itself a step to remember, and the machine that
    HAS one is the obvious thing to name. `ssh <host> cat ~/.config/fleet/fleet.toml`
    -- `cat` and not `scp` because only the text is wanted, there is no temporary
    file to clean up, and the failure arrives on stderr where it can be quoted.

    A fake `ssh` on PATH, which also proves the argv: a test that mocked
    `subprocess.run` would assert against the call this code makes today rather
    than against ssh's actual interface.
    """

    def setUp(self):
        self.init = load_tool("fleetinit")
        self._tmp = tempfile.TemporaryDirectory(prefix="fleet-remote-")
        self.bin = os.path.join(self._tmp.name, "bin")
        os.makedirs(self.bin)
        self._path = os.environ["PATH"]
        os.environ["PATH"] = self.bin + os.pathsep + self._path

    def tearDown(self):
        os.environ["PATH"] = self._path
        self._tmp.cleanup()

    def fake_ssh(self, stdout="", stderr="", code=0):
        """An `ssh` that records its argv and answers however the test says.

        The payloads go to FILES that the script cats, rather than being quoted
        into it. A TOML fixture is multi-line and full of quotes, and embedding
        it produced a shell script that died with "unexpected EOF while looking
        for matching `'`" -- which the tool then reported as the remote read
        having failed. A fake that fails in its own right looks exactly like the
        thing under test failing."""
        self.log = os.path.join(self._tmp.name, "argv")
        out = os.path.join(self._tmp.name, "out")
        err = os.path.join(self._tmp.name, "err")
        with open(out, "w") as f:
            f.write(stdout)
        with open(err, "w") as f:
            f.write(stderr)
        p = os.path.join(self.bin, "ssh")
        with open(p, "w") as f:
            f.write("#!/bin/sh\n"
                    'printf "%s\\n" "$@" > ' + self.log + "\n"
                    "cat " + out + "\n"
                    "cat " + err + " >&2\n"
                    "exit %d\n" % code)
        os.chmod(p, 0o755)

    def argv(self):
        with open(self.log) as f:
            return [l for l in f.read().splitlines()]

    # -- which specs are hosts ------------------------------------------------

    def test_a_bare_name_is_a_host(self):
        self.assertTrue(self.init.looks_remote("otherbox"))

    def test_the_scp_spelling_is_a_host(self):
        self.assertTrue(self.init.looks_remote("otherbox:/etc/fleet.toml"))
        self.assertTrue(self.init.looks_remote("me@otherbox:cfg/fleet.toml"))

    def test_anything_with_a_slash_is_a_path(self):
        """Reported as a missing FILE rather than as an unreachable host: the two
        send a reader to entirely different places to look."""
        self.assertFalse(self.init.looks_remote("/etc/fleet.toml"))
        self.assertFalse(self.init.looks_remote("./cfg/fleet.toml"))

    def test_a_toml_name_is_a_path_even_with_no_slash(self):
        """`ssh fleet.toml` would report a DNS failure for what is obviously a
        mistyped filename."""
        self.assertFalse(self.init.looks_remote("fleet.toml"))

    # -- an existing local file always wins -----------------------------------

    def test_a_local_file_is_never_treated_as_a_hostname(self):
        p = os.path.join(self._tmp.name, "otherbox")       # a FILE named like a host
        with open(p, "w") as f:
            f.write(SOURCE)
        self.fake_ssh(stdout="should not be reached")
        text, label = self.init.read_source(p)
        self.assertEqual(label, p)
        self.assertIn("sourcefleet", text)
        self.assertFalse(os.path.exists(self.log), "ssh must not have been run")

    # -- the remote read ------------------------------------------------------

    def test_the_default_remote_path_is_the_usual_one(self):
        self.fake_ssh(stdout=SOURCE)
        text, label = self.init.fetch_remote("otherbox")
        self.assertIn("otherbox", self.argv())
        self.assertIn("cat -- ~/.config/fleet/fleet.toml", self.argv())
        self.assertEqual(label, "otherbox:~/.config/fleet/fleet.toml")
        self.assertIn("sourcefleet", text)

    def test_an_explicit_remote_path_is_used(self):
        self.fake_ssh(stdout=SOURCE)
        _, label = self.init.fetch_remote("me@otherbox:/srv/fleet.toml")
        self.assertIn("me@otherbox", self.argv())
        self.assertIn("cat -- /srv/fleet.toml", self.argv())
        self.assertEqual(label, "me@otherbox:/srv/fleet.toml")

    def test_a_connect_timeout_is_passed(self):
        """An unreachable host must fail in seconds, not hang a command that
        looks like it is working."""
        self.fake_ssh(stdout=SOURCE)
        self.init.fetch_remote("otherbox")
        self.assertIn("ConnectTimeout=" + self.init.SSH_TIMEOUT, self.argv())

    # -- failure is reported, never guessed around ----------------------------

    def test_a_failed_ssh_quotes_what_ssh_said(self):
        self.fake_ssh(stderr="ssh: Could not resolve hostname nope", code=255)
        with self.assertRaises(SystemExit) as e:
            self.init.fetch_remote("nope")
        self.assertIn("Could not resolve hostname", str(e.exception))

    def test_an_empty_remote_file_is_refused(self):
        """Proceeding would write a fleet.toml holding nothing but the answers to
        the prompts -- a configuration that looks derived and is not."""
        self.fake_ssh(stdout="", code=0)
        with self.assertRaises(SystemExit) as e:
            self.init.fetch_remote("otherbox")
        self.assertIn("empty", str(e.exception))

    def test_a_missing_local_path_says_so_rather_than_sshing(self):
        self.fake_ssh(stdout=SOURCE)
        with self.assertRaises(SystemExit) as e:
            self.init.read_source("/no/such/fleet.toml")
        self.assertIn("no such file", str(e.exception))
        self.assertFalse(os.path.exists(self.log))


class EverythingUpToTheTmuxServer(unittest.TestCase):
    """One command, because four were too many to remember.

    The configuration was only ever the first of the things a clean machine
    needs; the conventions file `fleet.toml` points at, and the symlinks, lived
    in a docs page. A setup whose steps live in prose is a setup performed from
    memory and got wrong.

    What is deliberately NOT done: starting a tmux server. Which server a human
    is attached to is theirs to choose, and a tool that picks one has made a
    decision it cannot see the consequences of.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="fleet-setup-")
        self.home = os.path.join(self._tmp.name, "home")
        self.cfg = os.path.join(self.home, ".config", "fleet")
        os.makedirs(self.home)

    def tearDown(self):
        self._tmp.cleanup()

    def init(self, *args):
        import subprocess
        env = dict(os.environ, HOME=self.home)
        env.pop("FLEET_CONFIG", None)
        return subprocess.run([os.path.join(APP, "bin", "fleetinit"),
                               "--name", "A", "--timezone", "UTC",
                               "--fleet", "doe", *args],
                              capture_output=True, text=True, env=env, timeout=60)

    def test_one_command_leaves_a_machine_ready(self):
        r = self.init("--go")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.cfg, "fleet.toml")))
        self.assertTrue(os.path.isdir(os.path.join(self.cfg, "briefs")))
        self.assertTrue(os.path.isfile(os.path.join(self.cfg, "conventions.md")))
        self.assertTrue(os.path.islink(os.path.join(self.home, "bin", "fleetspawn")))
        self.assertTrue(os.path.islink(
            os.path.join(self.home, ".claude", "skills", "fleet-bootstrap")))

    def test_the_conventions_file_is_the_one_fleet_toml_points_at(self):
        """A declared path that nothing put a file at is a dangling reference in
        the first thing a new session reads."""
        self.init("--go")
        with open(os.path.join(self.cfg, "fleet.toml"), "rb") as f:
            declared = tomllib.load(f)["paths"]["conventions"]
        self.assertEqual(os.path.expanduser(declared.replace("~", self.home, 1)),
                         os.path.join(self.cfg, "conventions.md"))

    def test_an_existing_conventions_file_is_not_replaced(self):
        """It holds a fleet's accumulated lessons once it has any. A second run
        must not put the shipped example over them."""
        os.makedirs(self.cfg)
        keep = os.path.join(self.cfg, "conventions.md")
        with open(keep, "w") as f:
            f.write("# what THIS fleet learned\n")
        self.init("--go")
        self.assertEqual(open(keep).read(), "# what THIS fleet learned\n")

    def test_no_link_writes_the_configuration_and_stops(self):
        r = self.init("--no-link", "--go")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.cfg, "fleet.toml")))
        self.assertFalse(os.path.exists(os.path.join(self.home, "bin")))

    def test_without_go_nothing_is_created(self):
        r = self.init()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(self.cfg))
        self.assertFalse(os.path.exists(os.path.join(self.home, "bin")))
        self.assertIn("plan only", r.stdout)

    def test_the_plan_names_the_symlinks_it_will_make(self):
        """Read-only by default means the preview has to be complete, or the
        thing it does not mention is the thing nobody expected."""
        r = self.init()
        self.assertIn("symlinks", r.stdout)
        self.assertIn("conventions.md", r.stdout)

    def test_it_does_not_start_a_tmux_server(self):
        r = self.init("--go")
        self.assertIn("tmux new-session", r.stdout,
                      "the remaining step must be named, not performed")

    def test_a_failed_install_fails_the_setup(self):
        """`install` exits non-zero when a link could not be made. Reporting
        success over that would recreate the silent-success bug one layer up."""
        with open(os.path.join(self.home, ".claude"), "w") as f:
            f.write("not a directory\n")
        r = self.init("--go")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("INCOMPLETE", r.stdout + r.stderr)

    def test_the_install_uses_the_configuration_just_written(self):
        """`FLEET_CONFIG` is pinned to the directory created, not left to the
        environment: an install linking against a DIFFERENT configuration than
        the one just made is a mismatch nobody re-checks."""
        other = os.path.join(self._tmp.name, "elsewhere")
        os.makedirs(other)
        import subprocess
        env = dict(os.environ, HOME=self.home, FLEET_CONFIG=self.cfg)
        r = subprocess.run([os.path.join(APP, "bin", "fleetinit"),
                            "--name", "A", "--timezone", "UTC",
                            "--fleet", "doe", "--go"],
                           capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.islink(os.path.join(self.home, "bin", "fleetboard")))
