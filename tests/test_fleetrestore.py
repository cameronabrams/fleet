import json, os, shutil, subprocess, tempfile, unittest
from tests.support import APP, BASE_TOML, FakeConfig, load_tool

TOOL = os.path.join(APP, "bin", "fleetrestore")

def session(label, window, pane, uuid="u"):
    # No `fleet` key: fleetsnap stopped writing one on 2026-10-01, so a fixture
    # carrying it would be a shape nothing produces.
    return {"label": label, "cwd": "/tmp",
            "tmux": {"session": "0", "window": window, "window_name": "w",
                     "pane_index": pane, "pane_id": "%1", "size": "80x24"},
            "resume_uuid": uuid, "resume_uuid_source": "verified: test",
            "durable_files": []}

class Plan(unittest.TestCase):
    """The plan is the default and must change nothing. Run against a private
    tmux socket directory with no server, so no real pane is read or touched."""
    def setUp(self):
        self.cfg = FakeConfig(toml=BASE_TOML + '\n[spawn]\nenv = {{ NOTIFY = "1" }}\n')
        self.tmux = tempfile.mkdtemp(prefix="ftmux", dir="/tmp")
        man = {"captured": "now", "installed_claude": "x",
               "coordinator": "coord",
               "sessions": [session("beta", 2, 1, uuid="u-beta"),
                            session("alpha", 2, 0, uuid="u-alpha"),
                            session("gamma", 3, 0, uuid="UNVER-x")]}
        man["sessions"][2]["resume_uuid_source"] = "UNVERIFIED: guess"
        json.dump(man, open(os.path.join(self.cfg.state, "manifest.json"), "w"))

    def tearDown(self):
        shutil.rmtree(self.tmux); self.cfg.close()

    def run_tool(self, *args):
        env = dict(os.environ, TMUX_TMPDIR=self.tmux); env.pop("TMUX", None)
        return subprocess.run([TOOL, *args], capture_output=True, text=True, env=env)

    def manifest(self):
        return os.path.join(self.cfg.state, "manifest.json")

    def test_an_unnamed_session_is_not_relaunched(self):
        man = json.load(open(self.manifest()))
        man["sessions"].append(dict(session(None, 4, 0, uuid="u-unnamed"),
                                    cwd="/tmp/unnamed-cwd"))
        man["sessions"][-1]["tmux"]["pane_id"] = "%21"
        json.dump(man, open(self.manifest(), "w"))
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("could not name these panes", r.stdout)
        self.assertIn("%21", r.stdout)
        self.assertNotIn("u-unnamed", r.stdout)          # no relaunch line for it
        self.assertIn("--resume", r.stdout)              # the named ones still planned

    def test_no_arguments_plans_the_whole_fleet(self):
        """There is one manifest, so running it bare plans everything. It used to
        LIST the per-fleet manifests and plan nothing, which meant the bare command
        -- the one a recovering human types first -- did nothing at all."""
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PLAN (nothing executed", r.stdout)
        for name in ("alpha", "beta", "gamma"):
            self.assertIn(f"claude --name {name}", r.stdout)

    def test_a_named_subset_restores_only_those(self):
        r = self.run_tool("alpha")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("claude --name alpha", r.stdout)
        self.assertNotIn("claude --name beta", r.stdout)

    def test_plan_changes_nothing_and_resumes_in_pane_order(self):
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("PLAN (nothing executed", out)
        self.assertNotIn("  $ ", out)                       # executed commands are prefixed $
        self.assertIn("unverified resume targets", out)
        a = out.index("claude --name alpha --resume u-alpha")
        b = out.index("claude --name beta --resume u-beta")
        self.assertLess(a, b)                               # pane 0 before pane 1
        self.assertIn("NOTIFY=1 claude --name alpha", out)  # [spawn].env carried into a restore

    def test_a_name_the_manifest_does_not_hold_is_refused(self):
        """Not "restore the rest and say nothing": a typo would then read as a
        successful partial restore, which is the shape fleetwatch was fixed for."""
        r = self.run_tool("nope")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not in the manifest: nope", r.stderr)
        self.assertIn("alpha", r.stderr)                 # and what it does hold


class StoppedSessions(Plan):
    """A parked or retired transcript is not relaunched from an old manifest; a new
    session that reuses the name is."""
    def setUp(self):
        super().setUp()
        with open(os.path.join(self.cfg.config, "fleet.toml"), "a") as f:
            f.write('\n[retired.alpha]\nuuid = "aaaaaaaa-0000-4000-8000-000000000001"\n'
                    'since = "2026-09-13"\n')
        p = os.path.join(self.cfg.state, "manifest.json")
        m = json.load(open(p))
        m["sessions"][1]["resume_uuid"] = "aaaaaaaa-0000-4000-8000-000000000001"  # alpha, retired
        m["sessions"][0]["label"] = "alpha2"
        json.dump(m, open(p, "w"))

    def test_retired_transcript_not_relaunched(self):
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("not relaunched (fleet.toml): alpha is retired", r.stdout)
        self.assertNotIn("--resume aaaaaaaa-0000-4000-8000-000000000001", r.stdout)
        self.assertIn("claude --name alpha2 --resume u-beta", r.stdout)

    # inherited from Plan, whose manifest this class changes; not collected here
    test_plan_changes_nothing_and_resumes_in_pane_order = None
    test_no_arguments_plans_the_whole_fleet = None
    test_a_named_subset_restores_only_those = None

class StoppedByNameOnly(Plan):
    def setUp(self):
        super().setUp()
        with open(os.path.join(self.cfg.config, "fleet.toml"), "a") as f:
            f.write('\n[retired.alpha]\nuuid = "cccccccc-0000-4000-8000-000000000003"\n'
                    'since = "2026-09-01"\n')

    def test_same_name_different_transcript_is_restored(self):
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("claude --name alpha --resume u-alpha", r.stdout)
        self.assertNotIn("not relaunched", r.stdout)

class RecoveryBrief(unittest.TestCase):
    """--brief used to write RECOVERY.md into each session's cwd. For a repo
    session that is the repo root: untracked, not gitignored, and `git add -A` is
    how most commits are made. Raised independently by four sessions within
    minutes of the 2026-09-30 restore; one copy landed in a public repository and
    one in the tree that feeds a manuscript.

    It now goes to the state directory, beside the ledgers and the watcher
    registrations, which is where a record about a session already lives.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.r = load_tool("fleetrestore")

    def tearDown(self):
        self.cfg.close()

    def test_the_brief_goes_to_the_state_directory_not_a_work_tree(self):
        self.assertTrue(self.r.RECOVERY_DIR.startswith(self.cfg.state),
                        f"{self.r.RECOVERY_DIR} is not under the state dir")
        self.assertTrue(self.r.RECOVERY_DIR.endswith("recovery"))

    def test_nothing_is_written_into_a_session_cwd(self):
        """The guard that matters: no path the tool builds for a brief may sit
        under a session's working directory."""
        src = open(os.path.join(APP, "bin", "fleetrestore")).read()
        self.assertNotIn('os.path.join(s["cwd"], "RECOVERY.md")', src)
        self.assertIn("RECOVERY_DIR", src)


class RetiredAllFlag(unittest.TestCase):
    """`--all` was the documented power-cycle path until fde0cda retired it, and
    the coordinator still typed it on 2026-10-05 while preparing a reboot. The
    flag was removed because it stood in for "everything is being rebuilt" and
    was not the same thing; the bare command derives that instead.

    argparse answers an unrecognized flag with `unrecognized arguments: --all`
    and a usage line. That is correct and useless: it names what is wrong and not
    what to type, to a reader whose machine has just come back. The replacement
    is one character shorter, so there is no cost to saying it.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.tmux = tempfile.mkdtemp(prefix="ftmux", dir="/tmp")

    def tearDown(self):
        shutil.rmtree(self.tmux); self.cfg.close()

    def run_tool(self, *args):
        env = dict(os.environ, TMUX_TMPDIR=self.tmux); env.pop("TMUX", None)
        return subprocess.run([TOOL, *args], capture_output=True, text=True, env=env)

    def test_all_names_its_replacement(self):
        r = self.run_tool("--all")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("--all", out)
        self.assertIn("fleetrestore --go", out,
                      "the error must name the command to type instead")

    def test_it_refuses_before_touching_anything(self):
        """There is no manifest in this config, so a run that got as far as the
        manifest check would say so. Reaching that line with --go would be worse:
        the point is to stop at the argument, not to half-build a fleet and then
        complain."""
        r = self.run_tool("--all", "--go")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("no manifest at", r.stdout + r.stderr)

    def test_a_session_actually_named_all_is_still_restorable(self):
        """The guard keys on the flag, not the word. A session labelled `all` is
        a legitimate positional and must not be hijacked by it."""
        with open(os.path.join(APP, "bin", "fleetrestore")) as f:
            src = f.read()
        # assertNotIn would print the whole 20 kB file on failure, which buries
        # the one line that matters. Report the line number instead.
        #
        # The exclusion is per-OCCURRENCE, not per-line. Excluding any line that
        # also contains the legitimate `"--all" in sys.argv` looked equivalent and
        # was not: the natural broken form puts both tests on one line
        # (`if "all" in sys.argv or "--all" in sys.argv[1:]`), so that version
        # passed against code it was written to reject. Caught only by re-breaking
        # the guard after rewriting the assertion -- the rewrite is an edit to the
        # check itself, so the earlier proof did not carry over.
        hits = []
        for i, l in enumerate(src.splitlines(), 1):
            if '"all" in sys.argv' in l.replace('"--all" in sys.argv', ""):
                hits.append(i)
        self.assertEqual(hits, [], f"bare \'all\' matched on line(s) {hits}")


if __name__ == "__main__":
    unittest.main()
