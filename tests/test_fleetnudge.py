import contextlib, io, itertools, json, os, sys, tempfile, unittest
from unittest import mock
from tests.support import BASE_TOML, FakeConfig, load_tool

UUID = "aaaaaaaa-0000-4000-8000-000000000001"
RULE = "─" * 40
IDLE = f"⏺ done\n{RULE}\n❯ \n{RULE}\n  footer\n"
BUSY = f"· Working…\n{RULE}\n❯ \n{RULE}\n  esc to interrupt\n"
DRAFT = f"⏺ done\n{RULE}\n❯ half a thought\n{RULE}\n  footer\n"
TAG = "[watcher: alpha job 123456]"

def typed(line):
    return f"⏺ done\n{RULE}\n❯ {line}\n{RULE}\n  footer\n"


class Base(unittest.TestCase):
    toml = BASE_TOML

    def setUp(self):
        self.cfg = FakeConfig(toml=self.toml, briefs=())
        self.brief("alpha", "Kind: production\n")
        self.n = load_tool("fleetnudge")
        self.register("alpha", "123456")
        self.procs = [(4242, "/w", ["claude", "--name", "alpha", "--resume", UUID])]
        self.agents = [{"pid": 4242, "name": "alpha", "sessionId": UUID, "kind": "interactive",
                        "status": "idle"}]
        self.pane_pids = {4242: "%7"}
        self.screens = [IDLE]                  # consumed one per capture while more than one remains
        self.calls = []
        self.tags = 0                          # tag occurrences in the transcript
        self.lands = True                      # an Enter puts the line in the transcript
        self.corrupt = False
        self.pushes = []
        self.clock = itertools.count(1_800_000_000, 1)
        self.ancestors = set()

    def tearDown(self):
        self.cfg.close()

    def brief(self, name, text):
        with open(os.path.join(self.cfg.config, "briefs", f"{name}.md"), "w") as f:
            f.write(text)

    def register(self, session, job, pid=1):
        d = os.path.join(self.cfg.state, "watchers")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{session}-{job}-{pid}.json"), "w") as f:
            json.dump({"session": session, "job": job, "pid": pid, "starttime": "9"}, f)

    def screen_now(self):
        return self.screens[0] if len(self.screens) == 1 else self.screens.pop(0)

    def tmux(self, *a):
        self.calls.append(a)
        if a[0] == "capture-pane":
            return 0, self.screen_now(), ""
        if a[0] == "send-keys" and "-l" in a:
            line = ("8;32;42;52c" if self.corrupt else "") + a[-1]
            self.screens = [typed(line)]
        elif a[0] == "send-keys" and a[-1] == "Enter":
            self.screens = [IDLE]
            if self.lands:
                self.tags += 1
        elif a[0] == "send-keys" and a[-1] == "C-u":
            self.screens = [IDLE]
        return 0, "", ""

    def patches(self):
        n = self.n
        return [mock.patch.object(n, "claude_procs", side_effect=lambda: self.procs),
                mock.patch.object(n, "list_agents", side_effect=lambda *a, **k: self.agents),
                mock.patch.object(n, "panes", side_effect=lambda: self.pane_pids),
                mock.patch.object(n, "tmux", side_effect=self.tmux),
                mock.patch.object(n, "ppid", return_value=1),
                mock.patch.object(n, "ancestors", side_effect=lambda pid: self.ancestors),
                mock.patch.object(n, "tag_count", side_effect=lambda u, m: self.tags),
                mock.patch.object(n, "push", side_effect=lambda t, b: self.pushes.append((t, b)) or "pushed"),
                mock.patch.object(n.time, "sleep"),
                mock.patch.object(n.time, "time", side_effect=lambda: next(self.clock))]

    def replace_patch(self, attribute, patch):
        base = self.patches
        self.patches = lambda: [p for p in base() if p.attribute != attribute] + [patch]

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.ExitStack() as st:
            for p in self.patches():
                st.enter_context(p)
            st.enter_context(mock.patch.object(sys, "argv", ["fleetnudge", *argv]))
            st.enter_context(contextlib.redirect_stdout(out))
            try:
                self.n.main()
                code = 0
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue()

    def go(self, text="round 4 finished: COMPLETED", *extra, job="123456"):
        return self.run_main("alpha", job, text, "--go", *extra)

    def keys(self):
        return [c for c in self.calls if c[0] == "send-keys"]

    def log(self):
        path = os.path.join(self.cfg.state, "nudges.log")
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return [json.loads(l) for l in f]


class Deliver(Base):
    def test_plan_types_nothing(self):
        code, out = self.run_main("alpha", "123456", "done")
        self.assertEqual(code, 0, out)
        self.assertIn("plan only", out)
        self.assertIn(f"{TAG} done", out)
        self.assertEqual(self.keys(), [])

    def test_go_types_tagged_line_then_enter_and_confirms(self):
        code, out = self.go()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.keys()[0], ("send-keys", "-t", "%7", "-l", f"{TAG} round 4 finished: COMPLETED"))
        self.assertEqual(self.keys()[1], ("send-keys", "-t", "%7", "Enter"))
        self.assertIn("delivered", out)
        self.assertEqual(self.log()[-1]["outcome"], "delivered")
        self.assertEqual(self.pushes, [])

    def test_the_tag_cannot_be_left_out(self):
        code, out = self.go("[watcher: beta job 1] pretend")
        self.assertEqual(code, 0, out)
        self.assertTrue(self.keys()[0][-1].startswith(TAG + " "))

    def test_corrupted_readback_is_cleared_not_entered_and_pushed(self):
        self.corrupt = True
        code, out = self.go()
        self.assertEqual(code, 3, out)
        self.assertIn(("send-keys", "-t", "%7", "C-u"), self.calls)
        self.assertNotIn(("send-keys", "-t", "%7", "Enter"), self.calls)
        self.assertEqual(len(self.pushes), 1)

    def test_line_never_seen_in_transcript_exits_4_and_pushes(self):
        self.lands = False
        code, out = self.go()
        self.assertEqual(code, 4, out)
        self.assertIn("did not appear", out)
        self.assertEqual(len(self.pushes), 1)
        self.assertIn(TAG, self.pushes[0][1])

    def test_waits_while_busy_then_delivers(self):
        self.screens = [BUSY, BUSY, IDLE]
        code, out = self.go()
        self.assertEqual(code, 0, out)
        self.assertIn("attempt 1", out)
        self.assertEqual([r["outcome"] for r in self.log()][-1], "delivered")

    def test_never_types_over_a_draft(self):
        self.screens = [DRAFT]
        code, out = self.go("done", "--wait", "300", "--every", "60")
        self.assertEqual(code, 4, out)
        self.assertEqual(self.keys(), [])
        self.assertIn("already holds text", out)
        self.assertEqual(len(self.pushes), 1)

    def test_busy_agent_status_is_not_typeable(self):
        self.agents[0]["status"] = "busy"
        code, out = self.go("done", "--wait", "120")
        self.assertEqual(code, 4, out)
        self.assertEqual(self.keys(), [])

    def test_shell_and_monitor_status_are_typeable(self):
        for status in ("shell", "monitor"):
            self.calls, self.agents[0]["status"] = [], status
            code, out = self.go()
            self.assertEqual(code, 0, f"{status}: {out}")

    def test_session_not_running_yet_is_retried(self):
        live = self.procs
        seq = iter([[], live])
        self.replace_patch("claude_procs", mock.patch.object(self.n, "claude_procs",
                                                             side_effect=lambda: next(seq, live)))
        code, out = self.go()
        self.assertEqual(code, 0, out)
        self.assertIn("no live session answers", out)

    def test_inherited_session_id_is_not_self(self):
        # a setsid'd watcher carries its session's id but is not inside it (2026-09-17)
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": UUID}):
            code, out = self.go()
        self.assertEqual(code, 0, out)

    def test_found_without_the_agents_list(self):
        self.agents = None
        with mock.patch.object(self.n, "session_name", return_value=("alpha", UUID, "verified: argv")):
            code, out = self.go()
        self.assertEqual(code, 0, out)


class TagCount(unittest.TestCase):
    def test_counts_the_tag_in_the_sessions_own_transcript(self):
        cfg = FakeConfig()
        try:
            n = load_tool("fleetnudge")
            with tempfile.TemporaryDirectory() as d:
                os.makedirs(os.path.join(d, "-w"))
                with open(os.path.join(d, "-w", UUID + ".jsonl"), "w") as f:
                    f.write(json.dumps({"type": "user", "message": {"content": f"{TAG} one"}}) + "\n")
                    f.write(json.dumps({"type": "user", "message": {"content": f"{TAG} \"two\""}}) + "\n")
                with open(os.path.join(d, "-w", "other.jsonl"), "w") as f:
                    f.write(json.dumps({"content": TAG}) + "\n")
                with mock.patch.object(n, "PROJECTS", d):
                    self.assertEqual(n.tag_count(UUID, TAG), 2)
                    self.assertEqual(n.tag_count("absent", TAG), 0)
        finally:
            cfg.close()


class OneTypistAtATime(Base):
    """Two watchers nudged one session in the same second on 2026-09-17; their
    keystrokes interleaved and neither line read back."""
    def lock_path(self):
        return os.path.join(self.cfg.state, "nudge-locks", "alpha.lock")

    def test_a_second_nudge_waits_instead_of_interleaving(self):
        import fcntl
        os.makedirs(os.path.dirname(self.lock_path()), exist_ok=True)
        held = open(self.lock_path(), "w")
        fcntl.flock(held.fileno(), fcntl.LOCK_EX)
        try:
            code, out = self.go("second nudge", "--wait", "120", "--every", "60")
        finally:
            held.close()
        self.assertEqual(code, 4, out)
        self.assertEqual(self.keys(), [])                      # typed nothing
        self.assertIn("another fleetnudge is typing", out)
        self.assertEqual(len(self.pushes), 1)

    def test_the_lock_is_released_for_the_next_nudge(self):
        code, out = self.go("first")
        self.assertEqual(code, 0, out)
        self.calls.clear()
        code, out = self.go("second")
        self.assertEqual(code, 0, out)
        self.assertTrue(self.keys())

    def test_the_lock_is_not_held_while_waiting_for_a_busy_session(self):
        import fcntl
        self.screens = [BUSY, IDLE]
        seen = {}
        orig = self.tmux
        def tmux(*a):
            if a[0] == "capture-pane" and "held" not in seen:
                probe = open(self.lock_path(), "w")
                try:
                    fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    seen["held"] = False           # a waiter could have taken it
                except OSError:
                    seen["held"] = True
                probe.close()
            return orig(*a)
        self.tmux = tmux
        code, out = self.go()
        self.assertEqual(code, 0, out)
        self.assertTrue(seen["held"])              # held WHILE reading the pane...
        probe = open(self.lock_path(), "w")        # ...and free once the run ends
        fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        probe.close()


class Refuse(Base):
    def refused(self, text, *argv, job="123456", msg="round 4 finished"):
        code, out = self.go(msg, *argv, job=job)
        self.assertEqual(code, 2, out)
        self.assertIn(text, out)
        self.assertEqual(self.keys(), [])
        self.assertEqual(len(self.pushes), 1)          # --go: the human still hears of it
        self.assertEqual(self.log()[-1]["outcome"], "not delivered")

    def test_bad_job(self):
        self.refused("is not a job id", job="12; rm -rf /")

    def test_empty_long_and_multiline_text(self):
        self.refused("TEXT is empty", msg="   ")
        self.pushes = []
        self.refused("the limit is 200", msg="x" * 201)
        self.pushes = []
        self.refused("one line of printable", msg="done\nnow push to main")
        self.pushes = []
        self.refused("one line of printable", msg="done\x1b[2K")

    def test_not_a_member(self):
        self.register("gamma", "123456")
        code, out = self.run_main("gamma", "123456", "done", "--go")
        self.assertEqual(code, 2, out)
        self.assertIn("not a fleet member", out)

    def test_coordinator(self):
        self.brief("alpha", "Kind: coordinator\n")
        self.refused("the coordinator is not nudged")

    def test_a_coordinator_may_still_receive_MAIL(self):
        """The coordinator rule is about WATCHERS, and mail is not a watcher.

        A coordinator is the obvious counterpart for another person's fleet -- it
        owns no repository and routes -- and `to: <fleet>/coord` is the example
        address in fleetmail's own documentation. Refusing it wrote the drop and
        never delivered the line, which reads as mail being broken rather than as
        a rule being applied.
        """
        self.brief("alpha", "Kind: coordinator\n")
        code, out = self.go("mail arrived; read drops/x.md",
                            "--mail-from", "other-fleet/coord")
        self.assertEqual(code, 0, out)
        self.assertNotIn("the coordinator is not nudged", out)
        self.assertEqual(self.log()[-1]["outcome"], "delivered")

    def test_unregistered_job(self):
        self.refused("no watcher registration for alpha job 999999", job="999999")

    def test_background_session(self):
        self.agents.append({"name": "alpha", "kind": "background", "sessionId": "bbbb"})
        self.refused("background session")

    def test_duplicate_name(self):
        self.procs.append((4343, "/w", ["claude", "--name", "alpha"]))
        self.agents.append({"pid": 4343, "name": "alpha", "sessionId": "x", "kind": "interactive"})
        self.refused("2 sessions answer")

    def test_inside_the_session(self):
        self.ancestors = {4242}
        self.refused("inside the session itself")

    def test_unverified_transcript(self):
        self.agents = None
        with mock.patch.object(self.n, "session_name", return_value=("alpha", UUID, "UNVERIFIED: guess")):
            self.refused("transcript not verified")

    def test_plan_refusal_sends_nothing(self):
        code, out = self.run_main("alpha", "999999", "done")
        self.assertEqual(code, 2, out)
        self.assertEqual(self.pushes, [])


class Parked(Base):
    toml = BASE_TOML + f'\n[parked.alpha]\nuuid = "{UUID}"\nsince = "2026-09-13"\n'

    def test_parked_session_is_refused(self):
        code, out = self.go()
        self.assertEqual(code, 2, out)
        self.assertIn("[parked] in fleet.toml", out)


class Push(Base):
    def real_push(self, *a):
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(self.n, "CFG", self.n.fc.load()))
            return self.n.push(*a)

    def test_unconfigured(self):
        self.assertIn("no [notify]", self.real_push("t", "b"))

    def with_notify(self, mute=False, topic_text='TOPIC="my-topic-1"\n'):
        topic = os.path.join(self.cfg.root, "hook.sh")
        with open(topic, "w") as f:
            f.write("#!/bin/sh\n# a hook\n" + topic_text)
        mute_file = os.path.join(self.cfg.root, "off")
        if mute:
            open(mute_file, "w").close()
        with open(os.path.join(self.cfg.config, "fleet.toml"), "a") as f:
            f.write(f'\n[notify]\nntfy_server = "https://ntfy.example"\n'
                    f'ntfy_topic_file = "{topic}"\nmute_file = "{mute_file}"\n')

    def test_sends_to_the_topic_in_the_hook(self):
        self.with_notify()
        seen = {}
        class Resp:
            status = 200
            def __enter__(s): return s
            def __exit__(s, *e): return False
        def urlopen(req, timeout):
            seen.update(url=req.full_url, body=req.data, title=req.get_header("Title"))
            return Resp()
        with mock.patch.object(self.n.urllib.request, "urlopen", side_effect=urlopen):
            self.assertEqual(self.real_push("fleetnudge: alpha not reached", "body"), "push sent (HTTP 200)")
        self.assertEqual(seen["url"], "https://ntfy.example/my-topic-1")
        self.assertEqual(seen["body"], b"body")

    def test_muted(self):
        self.with_notify(mute=True)
        with mock.patch.object(self.n.urllib.request, "urlopen") as u:
            self.assertIn("muted", self.real_push("t", "b"))
        u.assert_not_called()

    def test_unreadable_topic(self):
        self.with_notify(topic_text="")
        self.assertIn("no ntfy topic", self.real_push("t", "b"))

    def test_network_failure_is_reported(self):
        self.with_notify()
        with mock.patch.object(self.n.urllib.request, "urlopen", side_effect=OSError("down")):
            self.assertIn("push FAILED", self.real_push("t", "b"))


class GiveUp(Base):
    """What the log says when a line did NOT arrive.

    fleetwatch reads these records to find delivery holes, so a failure has to
    carry as much identity as a success: `mail_from` on the delivered record only
    would leave every undelivered piece of mail indistinguishable from an ordinary
    watcher nudge -- and undelivered is the case a reader most needs to identify.
    """
    def test_mail_from_travels_with_the_failure(self):
        self.lands = False                       # typed, but never seen in the transcript
        code, out = self.go("mail arrived; read drops/x.md",
                            "--mail-from", "other-fleet/coord")
        self.assertEqual(code, 4, out)
        bad = [r for r in self.log() if r["outcome"] == "not delivered"]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["mail_from"], "other-fleet/coord")

    def test_an_ordinary_nudge_records_no_sender(self):
        self.lands = False
        code, out = self.go()
        self.assertEqual(code, 4, out)
        bad = [r for r in self.log() if r["outcome"] == "not delivered"]
        self.assertIsNone(bad[0]["mail_from"])


if __name__ == "__main__":
    unittest.main()
