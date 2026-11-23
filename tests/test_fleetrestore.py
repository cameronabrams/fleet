import contextlib, io, json, os, shutil, subprocess, tempfile, unittest
from unittest import mock
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

    def run_tool(self, *args, claude_home=None):
        """Runs the real tool, so HOME decides which binary it pins.

        `claude_home` defaults to an empty directory: no version store, so bare
        `claude`, which is the fallback the launch assertions here are written
        against. **This used to inherit the real HOME**, so on a machine with a
        version store every one of those assertions failed, while on CI -- which
        has no claude installed -- they passed. The suite was green in both
        places it was run and red in the one that mattered:
        `scripts/release.sh`, which runs it in the working tree.
        """
        env = dict(os.environ, TMUX_TMPDIR=self.tmux)
        env.pop("TMUX", None)
        env["HOME"] = claude_home or os.path.join(self.tmux, "nohome")
        os.makedirs(env["HOME"], exist_ok=True)
        return subprocess.run([TOOL, *args], capture_output=True, text=True, env=env)

    def manifest(self):
        return os.path.join(self.cfg.state, "manifest.json")

    def test_the_coordinator_line_tells_the_three_states_apart(self):
        """`m.get("coordinator", "?")` reads two states where there are three, and
        the fixture above hid the whole question for six weeks.

        That fixture hand-wrote `"coordinator": "coord"` into the manifest -- so
        this tool's tests passed against a key its PRODUCER had stopped writing on
        2026-10-01, and the live tool printed `coordinator: ?` on every run while
        the suite stayed green. A consumer tested only against a fixture is tested
        against the author's memory of the producer.

        A manifest with no key at all is an OLD manifest and says to re-snapshot. A
        manifest carrying null is a snapshot that looked and found nobody, which
        needs a brief edited instead -- and `.get` alone prints it as "None"."""
        def line(mutate):
            man = json.load(open(self.manifest()))
            mutate(man)
            json.dump(man, open(self.manifest(), "w"))
            r = self.run_tool()
            self.assertEqual(r.returncode, 0, r.stderr)
            return next(x for x in r.stdout.splitlines() if "coordinator:" in x)

        named = line(lambda m: m.update(coordinator="lead"))
        self.assertIn("lead", named)

        absent = line(lambda m: m.pop("coordinator", None))
        self.assertIn("?", absent)
        self.assertIn("fleetsnap", absent, "an old manifest must say how to fix it")

        null = line(lambda m: m.update(coordinator=None))
        self.assertNotIn("None", null, "null is a finding, not a name")
        self.assertNotIn("?", null, "a snapshot that looked is not a snapshot missing")
        self.assertIn("brief", null)

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

    def run_tool(self, *args, claude_home=None):
        """Runs the real tool, so HOME decides which binary it pins.

        `claude_home` defaults to an empty directory: no version store, so bare
        `claude`, which is the fallback the launch assertions here are written
        against. **This used to inherit the real HOME**, so on a machine with a
        version store every one of those assertions failed, while on CI -- which
        has no claude installed -- they passed. The suite was green in both
        places it was run and red in the one that mattered:
        `scripts/release.sh`, which runs it in the working tree.
        """
        env = dict(os.environ, TMUX_TMPDIR=self.tmux)
        env.pop("TMUX", None)
        env["HOME"] = claude_home or os.path.join(self.tmux, "nohome")
        os.makedirs(env["HOME"], exist_ok=True)
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
        """The guard keys on the flag, not the word. A session labeled `all` is
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


class ARestoreIsTheLargestAdoption(Plan):
    """Every session comes up on whatever `claude` resolves to now, which need not
    be what the manifest recorded. The same hole as an unpark (2026-10-16) with a
    bigger blast radius: fifteen sessions at once, and the one file meant to show
    adoptions omitting all of them.

    Logged WITHOUT touching the launch loop or reading any pid, because this is
    the recovery path. The cost is that the line is written before the launches
    and so records INTENT -- which is why it says so in the line, and why the
    outcome is a second line rather than a rewrite of the first.
    """
    def log_lines(self):
        p = os.path.join(self.cfg.state, "autoroll.log")
        if not os.path.exists(p):
            return []
        with open(p) as f:
            return [l.strip() for l in f if l.strip()]

    def test_a_plan_writes_nothing(self):
        """The default. A log line for a restore that did not happen is worse than
        no line: it is the file's own lie, in the file kept to catch them."""
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.log_lines(), [])

    def test_the_intent_line_says_it_is_intent(self):
        """A reader finding this after a restore that died partway must not take
        it for an accomplished fact."""
        src = open(TOOL).read()
        i = src.index("restore INTENT")
        self.assertIn("none verified yet", src[i:i + 120])
        self.assertLess(src.index("restore INTENT"), src.index("by_win = {}"),
                        "the intent line must be written before anything launches")

    def test_the_outcome_is_a_second_line_not_a_rewrite(self):
        """Before is the right place for the first line -- a line written after a
        run that never finishes does not exist, and the unfinished restore is the
        one worth a record. So the outcome adds, it does not replace."""
        src = open(TOOL).read()
        self.assertIn("restore DONE", src)
        self.assertLess(src.index("restore INTENT"), src.index("restore DONE"))
        self.assertEqual(src.count("record_adoption"), 2)

    def test_the_outcome_does_not_claim_a_version_was_adopted(self):
        """`verify` compares each pane's @agent label and directory against the
        manifest. That is not the question "which binary came up", and a line
        claiming the stronger fact would be this week's recurring mistake in a
        new place."""
        src = open(TOOL).read()
        # The caveat sits in the sentence built just ABOVE the call, so the window
        # looks both ways. Searching only forward passed nothing and failed for a
        # reason that had nothing to do with the claim being tested.
        i = src.index("restore DONE")
        self.assertIn("not a version check", src[i - 700:i + 300])

    def test_an_unreadable_tmux_is_not_counted_as_one_failure(self):
        """`verify` returns a single row labeled `(all)` when it could not list
        panes at all. Treating that as one failed session would log "14 of 15
        matched" for a check that matched nothing -- the reassuring direction, in
        the tool whose whole job is saying whether the fleet came back."""
        src = open(TOOL).read()
        i = src.index("restore DONE")
        head = src[max(0, i - 900):i]
        self.assertIn('label == "(all)"', head)
        self.assertIn("COULD NOT CHECK", src[i - 900:i + 200])


class TheRestoreLaunchesTheSoakedTarget(Plan):
    """Same policy as a spawn, with the fallback mattering more: a restore that
    refuses to launch because a pinned release is absent is far worse than one
    that adopts a fresh binary. This is the recovery path."""
    def test_a_pruned_target_falls_back_to_bare_claude(self):
        # `load_tool`, because these files have no .py extension and
        # `spec_from_file_location` returns None for them.
        mod = load_tool("fleetrestore")
        with mock.patch.object(mod.versions, "target",
                               lambda *a, **k: ("2.1.301", "/gone/2.1.301")):
            cmd, _launched, why = mod.claude_cmd()
        self.assertEqual(cmd, "claude")
        self.assertIn("gone from the version store", why)

    def test_nothing_soaked_falls_back_and_names_the_reason(self):
        mod = load_tool("fleetrestore")
        with mock.patch.object(mod.versions, "target", lambda *a, **k: (None, None)):
            cmd, _launched, why = mod.claude_cmd()
        self.assertEqual(cmd, "claude")
        self.assertIn("nothing has been on disk long enough", why)
        self.assertNotIn("soaked", why,
                         "a release that has merely sat on disk was not "
                         "exercised; the word invites tuning the wait as if "
                         "it bought evidence")

    def test_the_line_it_prints_names_the_release_past_the_window(self):
        """The reason printed at the top of every restore. It used to call the
        target "the newest soaked release", which claims the release was
        exercised while it waited -- nothing exercises it, and the word invited
        tuning the wait as if the duration bought evidence. The gate keeps its
        name (`--soak`, `versions.soaked`); the claim is what went."""
        mod = load_tool("fleetrestore")
        with mock.patch.object(mod.versions, "target",
                               lambda *a, **k: ("2.1.301", TOOL)):
            _cmd, _launched, why = mod.claude_cmd()
        self.assertIn("2.1.301", why)
        self.assertIn("on-disk window", why)
        self.assertNotIn("soaked", why)

    def test_the_binary_is_resolved_once_before_anything_is_built(self):
        """So a run cannot start some sessions on one release and the rest on
        another because the installer moved underneath it."""
        src = open(TOOL).read()
        self.assertLess(src.index("CLAUDE_CMD, launched, claude_why = claude_cmd()"),
                        src.index("by_win = {}"))
        self.assertEqual(src.count("claude_cmd()"), 2)   # the def and the one call

    def test_it_never_runs_claude_to_decide_how_to_run_claude(self):
        src = open(TOOL).read()
        self.assertNotIn("versions.installed()", src)


class TheAdoptionLineNamesWhatWasLaunched(Plan):
    """`to=` used to be `installed()` while the launch used `target()`.

    Those are different releases every day by design, so the fleet's only durable
    adoption record logged a version that never ran: on 2026-10-19 both restore
    lines said `to=2.1.303` while all 16 sessions came up on 2.1.302. Plausible,
    installed, and false -- and nothing downstream can detect it, which is what
    makes a wrong number in this file worse than a missing one.

    This is the consequence flagged when pinning was designed -- "`to=` becomes a
    CHOICE rather than a readout" -- implemented correctly in `fleetspawn`, which
    reads the running process, and got wrong here.
    """
    def tool(self):
        return load_tool("fleetrestore")

    def test_the_pinned_version_is_what_is_logged(self):
        mod = self.tool()
        with mock.patch.object(mod.versions, "target",
                               lambda *a, **k: ("2.1.302", "/v/2.1.302")), \
             mock.patch.object(mod.os.path, "exists", lambda p: True), \
             mock.patch.object(mod.versions, "installed",
                               lambda *a, **k: "2.1.303"):
            cmd, launched, why = mod.claude_cmd()
        self.assertEqual(launched, "2.1.302",
                         "logged the newest release, not the one launched")
        self.assertIn("2.1.302", cmd)

    def test_falling_back_logs_what_bare_claude_gives(self):
        """A different answer from the pinned branch, and the reason the version
        is returned rather than worked out again at the call site: when nothing
        is pinned the sessions really do come up on `installed`."""
        mod = self.tool()
        with mock.patch.object(mod.versions, "target", lambda *a, **k: (None, None)), \
             mock.patch.object(mod.versions, "installed", lambda *a, **k: "2.1.303"):
            _cmd, launched, why = mod.claude_cmd()
        self.assertEqual(launched, "2.1.303")
        self.assertIn("2.1.303", why, "the fallback must name what it fell back to")

    def test_both_lines_use_it_and_neither_re_derives_it(self):
        src = open(TOOL).read()
        body = src[src.index("def main("):]
        self.assertEqual(body.count("versions.installed("), 0,
                         "a line re-derived the version instead of using the "
                         "one actually launched")
        self.assertGreaterEqual(body.count("launched"), 4)  # unpack, both lines, note

    def test_the_outcome_line_says_which_release_it_launched_on(self):
        src = open(TOOL).read()
        i = src.index("restore DONE")
        self.assertIn("launched on %s", src[i:i + 120])


class APaneIsAskedWhereItIsUntilItCanAnswer(unittest.TestCase):
    """`pane_current_path` is the pane SHELL's working directory, so it is not
    true yet at the moment the pane is created.

    tmux forks the shell and answers the question whenever it is asked. Between
    the fork and the shell's exec, the answer is the directory the tmux server
    was started from -- whatever directory somebody happened to run this tool in.
    The restore read it once, immediately, and refuses to launch on a mismatch,
    so losing that race leaves a correctly placed pane empty and prints that it
    is in the wrong directory.

    Invisible on a fast machine and on tmux 3.4. GitHub moved its runners to
    Ubuntu 26.04 on 2026-11-13 and three tests went red at once: a probe on both
    images showed the pane reading as the repository checkout at 0 s and as its
    real directory at 0.25 s. The machine most likely to lose this race is a
    loaded one rebuilding a fleet after a power cycle, which is the only machine
    this tool is for.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.r = load_tool("fleetrestore")

    def tearDown(self):
        self.cfg.close()

    def reader(self, answers):
        """Stands in for `run`, handing back one answer per call, last repeating."""
        self.asked = 0

        def fake(cmd, go, capture=False):
            self.asked += 1
            return answers[min(self.asked - 1, len(answers) - 1)]
        return fake

    def settled(self, answers, want="/home/u/work", wait=1.0):
        with mock.patch.object(self.r, "run", self.reader(answers)):
            return self.r.pane_cwd_settled("%1", want, True, wait=wait)

    def test_a_pane_that_has_not_started_yet_is_asked_again(self):
        """The failing case. One read gets the server's directory and refuses."""
        self.assertEqual(self.settled(["/somewhere/else", "/home/u/work"]),
                         "/home/u/work")
        self.assertEqual(self.asked, 2)

    def test_a_pane_already_there_is_asked_once(self):
        """No delay added to the common case, which runs once per session."""
        self.assertEqual(self.settled(["/home/u/work"]), "/home/u/work")
        self.assertEqual(self.asked, 1)

    def test_a_pane_that_is_really_elsewhere_still_fails(self):
        """What polling must NOT do. A pane somewhere else stays somewhere else,
        so the guard still refuses -- later, and with the same answer."""
        self.assertEqual(self.settled(["/wrong/place"], wait=0.2), "/wrong/place")
        self.assertGreater(self.asked, 1, "it gave up without asking twice")

    def test_the_refusal_names_where_the_pane_really_is(self):
        """The LAST reading, not the first. The first is the directory the tool
        was run in, which tells a reader nothing about the pane."""
        self.assertEqual(self.settled(["/tool/was/run/here", "/wrong/place"],
                                      wait=0.2), "/wrong/place")

    def test_an_unreadable_pane_is_not_an_empty_match(self):
        """`run` returns None when tmux says nothing. Empty must never equal a
        wanted path, or a pane nothing can read would launch."""
        self.assertEqual(self.settled([None], wait=0.2), "")


JSON_LAYOUT = ('{"V":2,"L":{"t":"v","w":234,"h":57,"x":0,"y":0,"c":['
               '{"t":"h","w":234,"h":35,"x":0,"y":0,"c":['
               '{"t":"p","w":105,"h":35,"x":0,"y":0,"a":true,"i":1,"I":"%0"},'
               '{"t":"p","w":128,"h":35,"x":106,"y":0,"i":2,"I":"%22"}]},'
               '{"t":"p","w":234,"h":21,"x":0,"y":36,"i":3,"I":"%1"}]}}')
CLASSIC_LAYOUT = "bb62,80x24,0,0{40x24,0,0,1,39x24,41,0,2}"


class ALayoutIsOnlyExactIfThePaneCountIs(unittest.TestCase):
    """`tmux select-layout` given a layout string describing a different number
    of panes than the window holds EXITS 0, prints nothing, and leaves the
    default split. Measured 2026-11-23: a 4-pane layout on a 2-pane window.

    So `fleetsnap` recorded "exact geometry" and `fleetrestore` applied it and
    reported a clean restore, for a window that came back at 50/50 -- every time,
    for any window holding a pane that is not an agent. The silence is the defect;
    counting the panes in the string is what ends it."""

    def setUp(self):
        self.cfg = FakeConfig(toml=BASE_TOML)
        self.r = load_tool("fleetrestore")

    def tearDown(self):
        self.cfg.close()

    def test_a_json_layout_is_counted(self):
        """tmux 3.8 serializes a layout as JSON; a pane is a node of type `p`."""
        self.assertEqual(self.r.layout_panes(JSON_LAYOUT), 3)

    def test_a_classic_layout_is_counted(self):
        """Older tmux -- including the one CI runs -- writes the flat string. A
        pane is the only node carrying a fourth number; a container is not."""
        self.assertEqual(self.r.layout_panes(CLASSIC_LAYOUT), 2)

    def test_a_single_pane_classic_layout_is_one_not_none(self):
        self.assertEqual(self.r.layout_panes("b26f,80x24,0,0,0"), 1)

    def test_an_unreadable_layout_is_unknown_and_never_zero(self):
        """Zero would read as "this window should be empty" and make every window
        a mismatch -- the loud failure in the direction that destroys geometry
        nobody asked it to touch."""
        for bad in ("", None, "not-a-layout", "{", '{"V":2}', "{}"):
            with self.subTest(layout=bad):
                self.assertIsNone(self.r.layout_panes(bad))

    def calls(self):
        got = []
        return got, lambda cmd, go, capture=False: got.append(cmd)

    def apply(self, lay, planned, partial=False, go=False):
        got, run = self.calls()
        buf = io.StringIO()
        with mock.patch.object(self.r, "run", run), \
                contextlib.redirect_stdout(buf):
            self.r.apply_layout("0:1", lay, planned, "deps", partial, go)
        return got, buf.getvalue()

    def test_a_matching_count_applies_the_recorded_layout(self):
        got, out = self.apply({"layout": CLASSIC_LAYOUT}, 2)
        self.assertEqual(got, [["tmux", "select-layout", "-t", "0:1",
                                CLASSIC_LAYOUT]])
        self.assertEqual(out, "")

    def test_a_mismatch_is_said_out_loud_and_tiled(self):
        got, out = self.apply({"layout": JSON_LAYOUT}, 2)
        self.assertEqual(got, [["tmux", "select-layout", "-t", "0:1", "tiled"]])
        self.assertIn("describes 3 panes", out)
        self.assertIn("holds 2", out)
        self.assertIn("furniture", out, "the report must say what fixes it")

    def test_a_partial_restore_is_tiled_without_a_word(self):
        """It already tiles for a reason that has nothing to do with this, and a
        line per window per partial restore is how a warning becomes noise."""
        got, out = self.apply({"layout": JSON_LAYOUT}, 2, partial=True)
        self.assertEqual(got, [["tmux", "select-layout", "-t", "0:1", "tiled"]])
        self.assertEqual(out, "")

    def test_a_layout_that_cannot_be_counted_is_applied_and_flagged(self):
        """Not refused: the layout may well be right, and refusing would throw
        away geometry over a parser this file cannot prove is complete. Said out
        loud, so a window that comes back wrong has a reason on the screen."""
        got, out = self.apply({"layout": "not-a-layout"}, 2)
        self.assertEqual(got, [["tmux", "select-layout", "-t", "0:1",
                                "not-a-layout"]])
        self.assertIn("could not read", out)

    def test_no_recorded_layout_is_tiled(self):
        got, out = self.apply({}, 2)
        self.assertEqual(got, [["tmux", "select-layout", "-t", "0:1", "tiled"]])

    def test_a_go_run_counts_the_panes_tmux_HAS_not_the_ones_planned(self):
        """A split that failed leaves one pane fewer than the plan, and that is
        exactly the case where a layout is dropped in silence. The plan is the
        fallback for a dry run, which has no window to ask."""
        got, run = self.calls()
        buf = io.StringIO()
        with mock.patch.object(self.r, "run", run), \
                mock.patch.object(self.r, "tmux_run",
                                  return_value=subprocess.CompletedProcess(
                                      [], 0, "2\n", "")), \
                contextlib.redirect_stdout(buf):
            self.r.apply_layout("0:1", {"layout": JSON_LAYOUT}, 3, "deps",
                                False, True)
        self.assertIn("holds 2", buf.getvalue())
        self.assertEqual(got, [["tmux", "select-layout", "-t", "0:1", "tiled"]])


class FurnitureTakesItsOwnPlaceInThePaneOrder(unittest.TestCase):
    """Layout strings map to panes by POSITION. "Sessions first, furniture
    appended" would restore the right NUMBER of panes in the wrong places and
    hand each pane the geometry of a different one -- and the window this was
    raised for is agent, board, agent, shell."""

    def setUp(self):
        self.cfg = FakeConfig(toml=BASE_TOML)
        self.r = load_tool("fleetrestore")

    def tearDown(self):
        self.cfg.close()

    def panes(self, *idx):
        return [{"label": "s%d" % i, "cwd": "/w/%d" % i,
                 "tmux": {"pane_index": i}} for i in idx]

    def test_they_interleave_by_the_index_each_was_recorded_at(self):
        slots = self.r.window_slots(
            self.panes(0, 2),
            [{"pane_index": 1, "cwd": "/f", "start_command": "board"},
             {"pane_index": 3, "cwd": "/f", "start_command": ""}])
        self.assertEqual([s["kind"] for s in slots],
                         ["session", "furniture", "session", "furniture"])
        self.assertEqual([s["pane_index"] for s in slots], [0, 1, 2, 3])

    def test_a_session_slot_carries_no_command(self):
        """A session is launched by typing into its pane after the cwd check, not
        by handing tmux a command line -- that is how `--resume` and `--name` get
        verified. Furniture is the only slot that is created running something."""
        slots = self.r.window_slots(self.panes(0), [])
        self.assertEqual(slots[0]["cmd"], "")
        self.assertEqual(slots[0]["session"]["label"], "s0")

    def test_furniture_with_no_recorded_cwd_lands_where_the_window_does(self):
        slots = self.r.window_slots(self.panes(0), [{"pane_index": 1}])
        self.assertEqual(slots[1]["cwd"], "/w/0")

    def test_a_record_that_is_not_a_record_is_skipped_not_crashed_on(self):
        """An older or hand-edited manifest. This runs when nothing else is up."""
        slots = self.r.window_slots(self.panes(0), ["nonsense", None, 7])
        self.assertEqual(len(slots), 1)

    def test_the_recorded_command_is_unquoted_before_it_is_handed_back(self):
        """`#{pane_start_command}` is tmux's RENDERING of the argv it was given,
        and it quotes any word holding a space. A pane made with
        `split-window 'sleep 300'` reads back as `"sleep 300"`, quotes included;
        handing that back runs `sh -c '"sleep 300"'`, which is not found, and the
        pane closes within milliseconds leaving nothing to notice."""
        slots = self.r.window_slots(
            self.panes(0), [{"pane_index": 1, "start_command": '"sleep 300"'}])
        self.assertEqual(slots[1]["argv"], ["sleep 300"])

    def test_an_argv_rendering_survives_too(self):
        """The other shape tmux renders: several words, none needing quotes."""
        slots = self.r.window_slots(
            self.panes(0), [{"pane_index": 1,
                             "start_command": "/u/bin/fleetboard --watch"}])
        self.assertEqual(slots[1]["argv"], ["/u/bin/fleetboard", "--watch"])

    def test_a_command_that_cannot_be_split_is_none_not_the_raw_string(self):
        """None is what makes the caller create a plain shell and say so. The raw
        string would be handed to tmux and kill the pane on arrival -- the exact
        silent failure this parsing exists to avoid."""
        slots = self.r.window_slots(
            self.panes(0), [{"pane_index": 1, "start_command": 'sleep "300'}])
        self.assertIsNone(slots[1]["argv"])
        self.assertEqual(slots[1]["cmd"], 'sleep "300',
                         "the unparsable string is kept, to be printed")

    def test_no_command_is_an_empty_argv_not_a_failure(self):
        slots = self.r.window_slots(self.panes(0), [{"pane_index": 1}])
        self.assertEqual(slots[1]["argv"], [])

    def test_no_furniture_is_the_ordinary_window_unchanged(self):
        slots = self.r.window_slots(self.panes(0, 1), [])
        self.assertEqual([s["kind"] for s in slots], ["session", "session"])


class AnAttachLandsInTheCoordinator(unittest.TestCase):
    """The view a restore leaves behind had no owner, so it was the human's.

    A rebuild ends pointed at whatever it made last, and attaching therefore opens
    on an arbitrary session. Walking from there to the coordinator is one command,
    every time, which is the shape of thing that quietly becomes a standing chore.
    The manifest already records who the coordinator is -- from the session's own
    brief, not from what it is called -- so the tool can end where the human was
    going to go anyway.

    Two selections, not one: `select-window` decides which window an attach opens,
    `select-pane` decides which pane inside it is active."""

    def setUp(self):
        self.cfg = FakeConfig(toml=BASE_TOML)
        self.r = load_tool("fleetrestore")

    def tearDown(self):
        self.cfg.close()

    def listing(self, rows, rc=0, stderr=""):
        """Patch the tmux query with `rows` of (agent, fleet, session, win, pane)."""
        out = "\n".join("\t".join(r) for r in rows)
        return mock.patch.object(
            self.r, "tmux_run",
            return_value=subprocess.CompletedProcess([], rc, out, stderr))

    def recorder(self, active="%2", clients="0"):
        """(calls, run) -- a stand-in for `run` that records and answers queries.

        Two different queries go through `run`, so one canned answer would make
        the tests agree with each other rather than with tmux."""
        calls = []
        def run(cmd, go, capture=False):
            calls.append(cmd)
            if not capture:
                return None
            return clients if "session_attached" in cmd[-1] else active
        return calls, run

    def test_the_three_states_of_the_manifest_key_are_told_apart(self):
        """The same three the report line distinguishes: an old manifest with no
        key, a snapshot that looked and found nobody, and a name. Only the third
        selects anything, because the guess this replaced -- the literal string
        `coord` -- is what fleetsnap removed for checking what a session is called
        instead of what it is."""
        who, why = self.r.coordinator_target({})
        self.assertIsNone(who)
        self.assertIn("fleetsnap", why)

        who, why = self.r.coordinator_target({"coordinator": None})
        self.assertIsNone(who)
        self.assertIn("brief", why)
        self.assertNotIn("fleetsnap", why, "a snapshot that looked is not an old one")

        self.assertEqual(self.r.coordinator_target({"coordinator": "lead"}),
                         ("lead", None))

    def test_the_pane_is_found_by_both_labels_and_the_tmux_session(self):
        rows = [("alpha", "testfleet", "mainfleet", "@1", "%1"),
                ("lead", "testfleet", "mainfleet", "@2", "%7"),
                ("gamma", "testfleet", "mainfleet", "@3", "%9")]
        with self.listing(rows):
            self.assertEqual(self.r.coordinator_pane("mainfleet", "lead"),
                             (("@2", "%7"), None))

    def test_another_fleets_coordinator_is_not_ours(self):
        """`@agent` alone is not identity. Two fleets on one machine each have a
        session that routes, and the tools went strict on `@fleet` for exactly
        that: selecting someone else's pane moves a window nobody asked about and
        leaves our own attach where it was."""
        rows = [("lead", "somebody-elses-fleet", "mainfleet", "@2", "%7")]
        with self.listing(rows):
            got, why = self.r.coordinator_pane("mainfleet", "lead")
        self.assertIsNone(got)
        self.assertIn("no pane", why)

    def test_a_pane_in_another_tmux_session_is_not_where_an_attach_lands(self):
        """`list-panes -a` crosses tmux sessions. A pane of ours somewhere else is
        not reachable by `attach -t <sess>`, so selecting it would move a window
        nobody asked about and still land the human in the wrong place."""
        rows = [("lead", "testfleet", "another-server-session", "@2", "%7")]
        with self.listing(rows):
            got, why = self.r.coordinator_pane("mainfleet", "lead")
        self.assertIsNone(got)
        self.assertIn("mainfleet", why)

    def test_two_panes_with_that_label_is_refused_not_guessed(self):
        """The same answer the window-name collision gets: both candidates look
        equally right from here, and picking one would put the human in front of
        the wrong session while reporting success."""
        rows = [("lead", "testfleet", "mainfleet", "@2", "%7"),
                ("lead", "testfleet", "mainfleet", "@5", "%8")]
        with self.listing(rows):
            got, why = self.r.coordinator_pane("mainfleet", "lead")
        self.assertIsNone(got)
        self.assertIn("coin toss", why)

    def test_a_tmux_that_cannot_be_asked_is_not_an_empty_answer(self):
        with self.listing([], rc=1, stderr="no server running"):
            got, why = self.r.coordinator_pane("mainfleet", "lead")
        self.assertIsNone(got)
        self.assertIn("no server running", why)

    def test_a_plan_says_what_it_will_do_and_touches_no_pane(self):
        calls, run = self.recorder()
        with mock.patch.object(self.r, "run", run), \
                mock.patch.object(self.r, "tmux_run") as asked:
            line = self.r.select_coordinator({"coordinator": "lead"}, "mainfleet",
                                             False)
        self.assertIn("lead", line)
        self.assertEqual(calls, [], "a plan selected a pane")
        asked.assert_not_called()

    def test_going_selects_the_window_and_then_the_pane(self):
        rows = [("lead", "testfleet", "mainfleet", "@2", "%7")]
        calls, run = self.recorder(active="%7")
        with self.listing(rows), mock.patch.object(self.r, "run", run):
            line = self.r.select_coordinator({"coordinator": "lead"}, "mainfleet",
                                             True)
        self.assertIn(["tmux", "select-window", "-t", "@2"], calls,
                      "the pane was selected but not the window it is in: an "
                      "attach opens the session's CURRENT window")
        self.assertIn(["tmux", "select-pane", "-t", "%7"], calls)
        self.assertIn("%7", line)
        self.assertNotIn("!!", line)

    def test_a_selection_that_did_not_take_is_not_reported_as_one(self):
        """`run` never looks at an exit status, so the two commands above can do
        nothing at all and say nothing about it. The line they produce makes one
        claim -- that an attach lands in the coordinator -- and it has to be a
        readout rather than a hope."""
        rows = [("lead", "testfleet", "mainfleet", "@2", "%7")]
        calls, run = self.recorder(active="%1")      # tmux stayed where it was
        with self.listing(rows), mock.patch.object(self.r, "run", run):
            line = self.r.select_coordinator({"coordinator": "lead"}, "mainfleet",
                                             True)
        self.assertIn("!!", line)
        self.assertIn("%1", line)

    def test_an_unreadable_active_pane_is_not_a_match(self):
        rows = [("lead", "testfleet", "mainfleet", "@2", "%7")]
        calls, run = self.recorder(active="")
        with self.listing(rows), mock.patch.object(self.r, "run", run):
            line = self.r.select_coordinator({"coordinator": "lead"}, "mainfleet",
                                             True)
        self.assertIn("!!", line)
        self.assertIn("unreadable", line)

    def test_a_client_that_is_attached_is_not_thrown_across_the_fleet(self):
        """`select-window` moves every attached client's view there and then.

        The restore most likely to run with somebody attached is the PARTIAL one:
        a session died, the human is working in another window, and a tool he did
        not start moves him mid-sentence. A session that is already attached has
        no attach coming, which is the whole thing this placement is for."""
        rows = [("lead", "testfleet", "mainfleet", "@2", "%7")]
        calls, run = self.recorder(active="%7", clients="1")
        with self.listing(rows), mock.patch.object(self.r, "run", run):
            line = self.r.select_coordinator({"coordinator": "lead"}, "mainfleet",
                                             True)
        self.assertNotIn(["tmux", "select-window", "-t", "@2"], calls)
        self.assertNotIn(["tmux", "select-pane", "-t", "%7"], calls)
        self.assertIn("left where it is", line)
        self.assertIn("attached", line)

    def test_an_unreadable_client_count_also_leaves_it_alone(self):
        """The question is "is anyone looking at this", and guessing no is the
        answer that yanks somebody."""
        rows = [("lead", "testfleet", "mainfleet", "@2", "%7")]
        calls, run = self.recorder(active="%7", clients="")
        with self.listing(rows), mock.patch.object(self.r, "run", run):
            line = self.r.select_coordinator({"coordinator": "lead"}, "mainfleet",
                                             True)
        self.assertNotIn(["tmux", "select-pane", "-t", "%7"], calls)
        self.assertIn("would not say", line)

    def test_no_coordinator_leaves_the_view_alone_and_says_why(self):
        calls, run = self.recorder()
        with mock.patch.object(self.r, "run", run):
            line = self.r.select_coordinator({"coordinator": None}, "mainfleet",
                                             True)
        self.assertEqual(calls, [])
        self.assertIn("left where it is", line)
        self.assertIn("brief", line)


class ItSaysHowToGetBackIn(unittest.TestCase):
    """The tool ended by saying what to do next and never how to get there.

    After a reboot the fleet comes back inside a tmux session whose name only the
    manifest knows, and the human was left to remember it at the one moment when
    nothing is up to remind him. The name is a fact this tool has already read and
    used; printing it costs a line."""

    def setUp(self):
        self.cfg = FakeConfig(toml=BASE_TOML)
        self.tmux = tempfile.mkdtemp(prefix="ftmux", dir="/tmp")
        # NOT "0": a test whose fixture carries the literal this line used to be
        # cannot tell a name that was read from one that was hardcoded.
        self.write(["alpha", "beta"], "mainfleet")

    def tearDown(self):
        shutil.rmtree(self.tmux); self.cfg.close()

    def write(self, labels, tsess, tsessions=None):
        sess = []
        for i, lab in enumerate(labels):
            s = session(lab, 1, i, uuid="u-" + lab)
            s["tmux"]["session"] = (tsessions or {}).get(lab, tsess)
            s["tmux"]["pane_id"] = f"%{i + 1}"
            sess.append(s)
        man = {"captured": "now", "installed_claude": "x", "coordinator": "alpha",
               "sessions": sess}
        json.dump(man, open(os.path.join(self.cfg.state, "manifest.json"), "w"))

    def run_tool(self, *args):
        env = dict(os.environ, TMUX_TMPDIR=self.tmux)
        env.pop("TMUX", None)
        env["HOME"] = os.path.join(self.tmux, "nohome")
        os.makedirs(env["HOME"], exist_ok=True)
        return subprocess.run([TOOL, *args], capture_output=True, text=True, env=env)

    def test_a_plan_says_how_to_attach_once_it_has_run(self):
        """Printed on a PLAN too, in the future tense. The name is in the manifest
        either way, and the question gets asked before the reboot as often as
        after -- which is the only time there is still a session to ask in."""
        out = self.run_tool().stdout
        self.assertIn("tmux attach -t mainfleet", out)
        self.assertIn("After `--go`", out)

    def test_the_name_comes_from_the_manifest_not_a_default(self):
        self.write(["alpha"], "renamed-to-something-else")
        self.assertIn("tmux attach -t renamed-to-something-else",
                      self.run_tool().stdout)

    def test_it_is_the_last_thing_printed(self):
        """The fleetsnap reminder is for afterwards; the attach command is for the
        next thirty seconds. Printed first, it scrolls past."""
        lines = [l for l in self.run_tool().stdout.splitlines() if l.strip()]
        self.assertIn("tmux attach", lines[-1])

    def test_a_run_against_another_server_prints_that_servers_command(self):
        """`--socket` moves every other tmux call in this tool to another server.
        A bare `tmux attach` would name the DEFAULT one: a command that runs,
        attaches to something, and is wrong -- which is worse than none."""
        out = self.run_tool("--socket", "scratchsock").stdout
        self.assertIn("tmux -L scratchsock attach -t mainfleet", out)


class ItRefusesAManifestSpanningTwoServers(ItSaysHowToGetBackIn):
    """Windows are grouped by index alone, so panes recorded in two tmux sessions
    collide at window 0. The old code read the session name off the FIRST pane and
    applied it to every one, which is that collision with no warning: half the
    fleet silently restored into the wrong session."""

    def test_it_refuses_rather_than_picking_one(self):
        self.write(["alpha", "beta"], "one", tsessions={"beta": "two"})
        r = self.run_tool()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("more than one tmux session", r.stderr)

    def test_the_refusal_names_both(self):
        self.write(["alpha", "beta"], "one", tsessions={"beta": "two"})
        err = self.run_tool().stderr
        self.assertIn("one", err); self.assertIn("two", err)

    def test_it_refuses_before_building_anything(self):
        self.write(["alpha", "beta"], "one", tsessions={"beta": "two"})
        r = self.run_tool("--go")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("new-session", r.stdout)

    def test_one_session_is_the_ordinary_case_and_is_not_refused(self):
        self.assertEqual(self.run_tool().returncode, 0)


class EveryPaneUnnamedIsNotACrash(ItSaysHowToGetBackIn):
    """A manifest whose panes the snapshot could not name is filtered down to
    nothing, and the filter had no emptiness check: the next line that wanted the
    first session raised IndexError. Two filters above it check; this one did not,
    and it crashes in the tool that runs when nothing else is up."""

    def test_it_says_there_is_nothing_to_restore(self):
        man = json.load(open(os.path.join(self.cfg.state, "manifest.json")))
        for s in man["sessions"]:
            s["label"] = ""
        json.dump(man, open(os.path.join(self.cfg.state, "manifest.json"), "w"))
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("nothing to restore", r.stdout)
        self.assertNotIn("Traceback", r.stderr)


class ARunWithNothingToRestoreStillSaysHowToGetIn(ItSaysHowToGetBackIn):
    """The runs that end early are the ones that most need the attach line.

    `sess` binds after the filters, so the three "nothing to restore" returns fired
    before it existed and printed no attach line at all -- including the case where
    every session is already up, which is precisely the person in a fresh shell
    asking how to get back into a fleet that is perfectly healthy. A terminal can
    die without taking the tmux server with it; that is the ordinary way to be
    outside a running fleet.

    It is gated on the session actually being there. "Everything is parked" reaches
    the same return and can mean there is nothing on that server at all, and a
    command that fails is a worse answer than silence."""

    def park_everything(self):
        man = json.load(open(os.path.join(self.cfg.state, "manifest.json")))
        with open(os.path.join(self.cfg.config, "fleet.toml"), "a") as f:
            for i, s in enumerate(man["sessions"]):
                s["resume_uuid"] = "aaaaaaaa-0000-4000-8000-00000000000%d" % (i + 1)
                f.write('\n[retired.%s]\nuuid = "%s"\nsince = "2026-09-13"\n'
                        % (s["label"], s["resume_uuid"]))
        json.dump(man, open(os.path.join(self.cfg.state, "manifest.json"), "w"))

    def serve(self, name):
        """A real tmux server of this test's own, holding one session of `name`."""
        env = dict(os.environ, TMUX_TMPDIR=self.tmux)
        env.pop("TMUX", None)
        subprocess.run(["tmux", "-L", "attachtest", "new-session", "-d",
                        "-s", name], env=env, check=True,
                       capture_output=True, timeout=10)
        self.addCleanup(subprocess.run, ["tmux", "-L", "attachtest", "kill-server"],
                        env=env, capture_output=True)

    def test_a_session_that_is_not_there_is_not_offered(self):
        """No server at all on this socket: there is nowhere to attach, and a
        command that fails would be a confident wrong answer."""
        self.park_everything()
        out = self.run_tool("--socket", "no-such-server-here").stdout
        self.assertIn("nothing to restore", out)
        self.assertNotIn("attach", out)

    @unittest.skipUnless(shutil.which("tmux"), "tmux is not installed")
    def test_a_fleet_that_is_already_up_is_told_how_to_be_entered(self):
        self.serve("mainfleet")
        self.park_everything()
        out = self.run_tool("--socket", "attachtest").stdout
        self.assertIn("nothing to restore", out)
        self.assertIn("tmux -L attachtest attach -t mainfleet", out)

    @unittest.skipUnless(shutil.which("tmux"), "tmux is not installed")
    def test_it_is_the_present_tense_there_because_the_fleet_is_up(self):
        """Not `After --go`: there is no --go to come, and the command works now."""
        self.serve("mainfleet")
        self.park_everything()
        out = self.run_tool("--socket", "attachtest").stdout
        self.assertIn("Attach with:", out)
        self.assertNotIn("After `--go`", out)

    @unittest.skipUnless(shutil.which("tmux"), "tmux is not installed")
    def test_every_pane_unnamed_also_says_it(self):
        """The third early return, reached by a different filter."""
        self.serve("mainfleet")
        man = json.load(open(os.path.join(self.cfg.state, "manifest.json")))
        for s in man["sessions"]:
            s["label"] = ""
        json.dump(man, open(os.path.join(self.cfg.state, "manifest.json"), "w"))
        out = self.run_tool("--socket", "attachtest").stdout
        self.assertIn("tmux -L attachtest attach -t mainfleet", out)

    def tm(self, *args):
        env = dict(os.environ, TMUX_TMPDIR=self.tmux)
        env.pop("TMUX", None)
        return subprocess.run(["tmux", "-L", "attachtest", *args], env=env,
                              capture_output=True, text=True, timeout=10)

    @unittest.skipUnless(shutil.which("tmux"), "tmux is not installed")
    def test_a_fleet_that_is_already_up_still_gets_its_active_pane_placed(self):
        """The early return is not a lesser path: it is the COMMONEST attach.

        A terminal dying without taking the tmux server with it leaves every
        session running, so every one is filtered out and this tool builds
        nothing -- and that is exactly the person about to reattach. A placement
        that happened only when panes were created would miss them all.
        """
        self.serve("mainfleet")
        self.tm("set", "-p", "-t", "mainfleet", "@agent", "alpha")
        self.tm("set", "-p", "-t", "mainfleet", "@fleet", "testfleet")
        before = self.tm("display", "-p", "-t", "mainfleet", "#{pane_id}").stdout.strip()
        # A second window, created after the coordinator's, so tmux's current
        # window is not already the right one.
        self.tm("new-window", "-t", "mainfleet:")
        self.park_everything()
        out = self.run_tool("--socket", "attachtest", "--go").stdout
        self.assertIn("alpha's pane", out)
        after = self.tm("display", "-p", "-t", "mainfleet", "#{pane_id}").stdout.strip()
        self.assertEqual(after, before,
                         "an attach would not land in the coordinator\n" + out)

    @unittest.skipUnless(shutil.which("tmux"), "tmux is not installed")
    def test_a_plan_on_that_path_says_it_without_moving_anything(self):
        self.serve("mainfleet")
        self.tm("new-window", "-t", "mainfleet:")
        was = self.tm("display", "-p", "-t", "mainfleet", "#{pane_id}").stdout.strip()
        self.park_everything()
        out = self.run_tool("--socket", "attachtest").stdout
        self.assertIn("will make alpha's pane active", out)
        self.assertEqual(
            self.tm("display", "-p", "-t", "mainfleet", "#{pane_id}").stdout.strip(),
            was, "the plan moved the view")

    @unittest.skipUnless(shutil.which("tmux"), "tmux is not installed")
    def test_a_two_session_manifest_offers_neither_name(self):
        """The early returns fire before the refusal, so they cannot lean on it."""
        self.serve("one")
        self.write(["alpha", "beta"], "one", tsessions={"beta": "two"})
        self.park_everything()
        out = self.run_tool("--socket", "attachtest").stdout
        self.assertIn("nothing to restore", out)
        self.assertNotIn("attach", out)
