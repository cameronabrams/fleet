import json, os, shutil, subprocess, tempfile, unittest
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
        self.assertIn("nothing has soaked", why)

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

    @unittest.skipUnless(shutil.which("tmux"), "tmux is not installed")
    def test_a_two_session_manifest_offers_neither_name(self):
        """The early returns fire before the refusal, so they cannot lean on it."""
        self.serve("one")
        self.write(["alpha", "beta"], "one", tsessions={"beta": "two"})
        self.park_everything()
        out = self.run_tool("--socket", "attachtest").stdout
        self.assertIn("nothing to restore", out)
        self.assertNotIn("attach", out)
