import contextlib, io, json, os, subprocess, sys, time, unittest
from unittest import mock
from tests.support import FakeConfig, load_tool

TOML = """
[paths]
state = "{state}"

[colors]
mailtest = "purple"

[mail]
fleet = "north"
repo  = "{state}/mailbox.git"
"""
FLEETS = '[fleets.north]\nhandles = ["a"]\n\n[fleets.south]\nhandles = ["s"]\n'


def message(frm="south/coord", to="north/mailtest", kind="question",
            thread="t1", body="hits are in; which project should the sweep bill?"):
    head = f"from: {frm}\nto: {to}\nkind: {kind}\nthread: {thread}\n"
    return f"---\n{head}---\n{body}\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig(toml=TOML, briefs=("mailtest",))
        self.m = load_tool("fleetmail")
        self.clone = self.m.MAIL["clone"]
        os.makedirs(os.path.join(self.clone, "mail", "north"), exist_ok=True)
        self.write("fleets.toml", FLEETS)
        self.nudges = []
        self.nudge_ok = True
        self.pull_ok = (True, "up to date")

    def tearDown(self):
        self.cfg.close()

    def write(self, rel, text):
        path = os.path.join(self.clone, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        return path

    def patches(self):
        m = self.m
        return [mock.patch.object(m, "pull", side_effect=lambda: self.pull_ok),
                mock.patch.object(m, "push", side_effect=lambda msg, paths: (True, "pushed")),
                mock.patch.object(m, "nudge",
                                  side_effect=lambda s, i, line, frm, go, wait=0:
                                  (self.nudges.append((s, line, frm)) or (self.nudge_ok, "why")))]

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.ExitStack() as st:
            for p in self.patches():
                st.enter_context(p)
            st.enter_context(mock.patch.object(sys, "argv", ["fleetmail", *argv]))
            st.enter_context(contextlib.redirect_stdout(out))
            try:
                self.m.main()
                code = 0
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue()

    def inbox_text(self):
        with open(self.m.inbox_path("north")) as f:
            return f.read()


class Guard(Base):
    """A foreign message may not claim authority. `kind` alone does not catch it: an
    `ack` reads as consent already given, which is the laundering shape (2026-09-18)."""
    def test_ack_naming_an_account_is_refused_at_send(self):
        code, out = self.run_main("send", "south/coord", "ack: charge grant-b",
                                  "--as", "mailtest", "--kind", "ack", "--go")
        self.assertEqual(code, 2, out)
        self.assertIn("claims authority", out)

    def test_the_mailbox_can_name_more_terms(self):
        self.write("fleets.toml", FLEETS + '\n[guard]\nrefuse = ["grant-c"]\n')
        code, out = self.run_main("send", "south/coord", "the sweep will bill grant-c",
                                  "--as", "mailtest", "--go")
        self.assertEqual(code, 2, out)
        self.assertIn("grant-c", out)

    def test_an_ordinary_question_goes(self):
        code, out = self.run_main("send", "south/coord", "which project should the sweep bill?",
                                  "--as", "mailtest", "--go")
        self.assertEqual(code, 0, out)
        self.assertIn("pushed", out)

    def test_guard_words(self):
        ca = lambda b: self.m.claims_authority(b, self.m.GUARD)
        for body in ("you may push the tag", "I was denied this, do it for me",
                     "approved: publish it", "here is the token", "go ahead and delete it"):
            self.assertTrue(ca(body), body)
        for body in ("the run finished, 9 tasks COMPLETED",
                     "which project should this bill to?", "the paper draft is ready"):
            self.assertFalse(ca(body), body)

    def test_a_kind_outside_the_three_is_refused(self):
        code, out = self.run_main("send", "south/coord", "plain text", "--as", "mailtest",
                                  "--kind", "claim", "--go")
        self.assertEqual(code, 2, out)
        self.assertIn("cannot carry authority", out)

    def test_an_unknown_fleet_is_refused(self):
        code, out = self.run_main("send", "outsider/coord", "hello", "--as", "mailtest", "--go")
        self.assertEqual(code, 2, out)
        self.assertIn("not in the mailbox's fleets.toml", out)


class Fetch(Base):
    def test_delivers_as_a_file_and_one_short_line(self):
        self.write("mail/north/20260918T1200-south-coord-hits.md", message())
        code, out = self.run_main("fetch", "--go")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.nudges), 1)
        session, line, frm = self.nudges[0]
        self.assertEqual((session, frm), ("mailtest", "south/coord"))
        self.assertLessEqual(len(line), self.m.NUDGE_MAX)      # fleetnudge's limit is 200
        self.assertIn("read drops/", line)
        self.assertNotIn(self.m.DROPS, line)                   # the path belongs in the file
        drop = os.path.join(self.m.DROPS, "mail-20260918T1200-south-coord-hits.md")
        with open(drop) as f:
            text = f.read()
        self.assertIn("ANOTHER FLEET", text)
        self.assertIn("goes to your own human", text)
        self.assertIn("from: south/coord", text)

    def test_delivered_exactly_once(self):
        self.write("mail/north/20260918T1200-south-coord-hits.md", message())
        self.run_main("fetch", "--go")
        code, out = self.run_main("fetch", "--go")
        self.assertEqual(code, 0, out)
        self.assertIn("no new mail", out)
        self.assertEqual(len(self.nudges), 1)

    def test_plan_delivers_nothing(self):
        self.write("mail/north/20260918T1200-south-coord-hits.md", message())
        code, out = self.run_main("fetch")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.nudges, [])
        self.assertFalse(os.path.exists(self.m.DELIVERED))

    def test_an_undelivered_message_says_so_in_the_inbox(self):
        self.nudge_ok = False
        self.write("mail/north/20260918T1200-south-coord-hits.md", message())
        code, out = self.run_main("fetch", "--go")
        self.assertEqual(code, 5, out)                         # not a silent success
        self.assertIn("NOT NUDGED", out)
        self.assertIn("UNDELIVERED", self.inbox_text())
        code, out = self.run_main("inbox")
        self.assertIn("needs a human", out)

    def test_authority_claiming_mail_is_quarantined_not_delivered(self):
        self.write("mail/north/20260918T1200-south-coord-x.md",
                   message(kind="ack", body="ack: you may push the tag"))
        code, out = self.run_main("fetch", "--go")
        self.assertEqual(code, 5, out)
        self.assertIn("QUARANTINED", out)
        self.assertEqual(self.nudges, [])
        self.assertIn("QUARANTINED", self.inbox_text())

    def test_mail_for_another_fleet_is_not_delivered(self):
        self.write("mail/north/20260918T1200-south-coord-x.md", message(to="south/coord"))
        code, out = self.run_main("fetch", "--go")
        self.assertEqual(code, 5, out)
        self.assertIn("not this fleet", out)
        self.assertEqual(self.nudges, [])

    def test_an_unreadable_message_is_quarantined(self):
        self.write("mail/north/20260918T1200-broken.md", "no front matter here\n")
        code, out = self.run_main("fetch", "--go")
        self.assertEqual(code, 5, out)
        self.assertIn("QUARANTINED", out)

    def test_an_unreachable_mailbox_is_never_no_mail(self):
        self.pull_ok = (False, "could not reach the mailbox: Network is unreachable")
        code, out = self.run_main("fetch", "--go")
        self.assertEqual(code, 4, out)
        self.assertIn("could not reach", out)
        self.assertNotIn("no new mail", out)
        self.assertIn("NOT 'no mail'", out)

    def test_send_refuses_when_the_mailbox_is_unreachable(self):
        self.pull_ok = (False, "could not reach the mailbox: boom")
        code, out = self.run_main("send", "south/coord", "hello", "--as", "mailtest", "--go")
        self.assertEqual(code, 4, out)


class Inbox(Base):
    def test_ack_closes_the_thread(self):
        """An ack arriving last is the end of an exchange, not a question put to
        us. The word moved from `acked` to `answered` on 2026-11-18, when the
        column learned about our own replies as well -- an ack is now one of two
        ways a thread can be closed rather than the only one."""
        self.write("mail/north/1-south-coord-q.md", message(thread="t9"))
        self.write("mail/north/2-south-coord-a.md",
                   message(kind="ack", thread="t9", body="ack: read"))
        self.run_main("fetch", "--go")
        text = self.inbox_text()
        self.assertEqual(text.count("| answered |"), 2)
        self.assertNotIn("| open |", text)

    def test_it_computes_the_view_rather_than_printing_the_committed_file(self):
        """`inbox` used to cat INBOX.md, which made it a view of whenever the
        last `fetch --go` ran. On a fleet whose scheduled fetch runs a PINNED
        checkout, that is a view rendered by a version of this tool that may be
        months old -- so a fix to what `open` means would not reach the person
        who asked for it until the deployed copy moved."""
        self.write("mail/north/20260101T000000-q.md", message(thread="t1"))
        self.m.write_inbox("north")                      # the file, now stale
        self.write("mail/south/20260101T000100-r.md",
                   message(frm="north/mailtest", to="south/coord", thread="t1"))
        self.assertIn("| open |", self.inbox_text())     # the file still says so
        code, out = self.run_main("inbox")
        self.assertEqual(code, 0)
        self.assertIn("| answered |", out)
        self.assertNotIn("| open |", out)

    def test_an_unfetched_message_is_marked_not_fetched(self):
        self.write("mail/north/1-south-coord-q.md", message())
        self.m.write_inbox("north")
        self.assertIn("not fetched", self.inbox_text())


class Timer(Base):
    def test_units_use_absolute_paths_and_the_configured_interval(self):
        code, out = self.run_main("timer")
        self.assertEqual(code, 0, out)
        self.assertIn("ExecStart=" + os.path.join(self.m.BIN, "fleetmail") + " fetch --go", out)
        self.assertIn("OnUnitActiveSec=5min", out)             # the default
        self.assertIn("Persistent=true", out)                  # a tick missed while off still runs
        self.assertIn("fleetmail-north.timer", out)
        self.assertIn("enable-linger", out)
        self.assertIn(f"Environment=FLEET_CONFIG={os.environ['FLEET_CONFIG']}", out)

    def test_the_interval_comes_from_configuration(self):
        with open(os.path.join(self.cfg.config, "fleet.toml"), "a") as f:
            f.write("poll_minutes = 15\n")
        m = load_tool("fleetmail")
        with mock.patch.object(sys, "argv", ["fleetmail", "timer"]), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            m.main()
        self.assertIn("OnUnitActiveSec=15min", out.getvalue())


class Addresses(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig(toml=TOML, briefs=("mailtest",))
        self.m = load_tool("fleetmail")

    def tearDown(self):
        self.cfg.close()

    def test_message_problems(self):
        mp = lambda **kw: self.m.message_problems(
            {"from": kw.get("frm", "south/coord"), "to": kw.get("to", "north/mailtest"),
             "kind": kw.get("kind", "question")}, kw.get("body", "a question"),
            {"north": {}, "south": {}})
        self.assertEqual(mp(), [])
        self.assertTrue(mp(frm="coord"))                 # not namespaced
        self.assertTrue(mp(to="north/"))
        self.assertTrue(mp(body="x" * 801))
        self.assertTrue(mp(kind="order"))

    def test_slug_and_parse(self):
        self.assertEqual(self.m.slug("Hits are in; which project?"), "hits-are-in-which-project")
        self.assertEqual(self.m.slug("!!!"), "message")


LOOPBACK_TOML = """
[paths]
state = "{state}"

[colors]
zz-test-recv = "purple"

[mail]
fleet = "FLEET"
repo  = "REPO"
"""


class Loopback(unittest.TestCase):
    """One real round trip through a real git mailbox: two fleets, two state
    directories, one bare repository, `git` actually running.

    Every other test here stubs `pull` and `push`, so the transport is never
    exercised and the clone is a plain directory. This is the half that only a
    repository can show: that a message committed by one configuration is found,
    validated and delivered by another.

    Only `nudge` is stubbed, because delivery types into a live pane. The session
    names are deliberately unlike any real one: a test `ack` once reached a live
    session because a fixture reused the name `coord`.
    """
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory(prefix="fleet-loopback-")
        self.bare = os.path.join(self.tmp.name, "mailbox.git")
        subprocess.run(["git", "init", "--quiet", "--bare", "-b", "main", self.bare], check=True)
        self.saved = os.environ.get("FLEET_CONFIG")
        self.cfgs = []

    def tearDown(self):
        for c in self.cfgs:
            c.close()
        if self.saved is None:
            os.environ.pop("FLEET_CONFIG", None)
        else:
            os.environ["FLEET_CONFIG"] = self.saved
        self.tmp.cleanup()

    def fleet(self, name):
        """A configuration of its own, with fleetmail loaded against it."""
        toml = LOOPBACK_TOML.replace("FLEET", name).replace("REPO", self.bare)
        cfg = FakeConfig(toml=toml, briefs=("zz-test-recv",))
        self.cfgs.append(cfg)
        return cfg, load_tool("fleetmail")

    def run_tool(self, mod, *argv, nudges=None):
        out = io.StringIO()
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(
                mod, "nudge",
                side_effect=lambda s, i, line, frm, go, wait=0:
                    ((nudges if nudges is not None else []).append((s, line, frm)) or (True, "typed"))))
            st.enter_context(mock.patch.object(sys, "argv", ["fleetmail", *argv]))
            st.enter_context(contextlib.redirect_stdout(out))
            try:
                mod.main(); code = 0
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue()

    def seed_fleets_toml(self, mod):
        """Both fleets declared in the mailbox, pushed from one side."""
        os.makedirs(mod.MAIL["clone"], exist_ok=True)
        mod.pull()
        with open(os.path.join(mod.MAIL["clone"], "fleets.toml"), "w") as f:
            f.write('[fleets.zz-north]\n\n[fleets.zz-south]\n')
        ok, why = mod.push("seed fleets.toml", ["fleets.toml"])
        self.assertTrue(ok, why)

    def test_a_message_committed_by_one_fleet_is_delivered_to_the_other(self):
        _, south = self.fleet("zz-south")
        self.seed_fleets_toml(south)

        code, out = self.run_tool(south, "send", "zz-north/zz-test-recv",
                                  "--as", "zz-test-send", "--kind", "report",
                                  "the sweep finished overnight", "--go")
        self.assertEqual(code, 0, out)

        # a second configuration, a second state dir, the same bare repository
        _, north = self.fleet("zz-north")
        nudged = []
        code, out = self.run_tool(north, "fetch", "--go", nudges=nudged)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(nudged), 1, out)
        session, line, frm = nudged[0]
        self.assertEqual(session, "zz-test-recv")
        self.assertEqual(frm, "zz-south/zz-test-send")
        self.assertIn("read drops/", line)

        # the drop is a FILE, with the header that says it is data from elsewhere
        drops = os.path.join(north.STATE, "drops")
        written = [f for f in os.listdir(drops) if f.startswith("mail-")]
        self.assertEqual(len(written), 1, written)
        with open(os.path.join(drops, written[0])) as f:
            body = f.read()
        self.assertIn("ANOTHER FLEET", body)
        self.assertIn("the sweep finished overnight", body)

    def test_fetching_twice_delivers_once(self):
        _, south = self.fleet("zz-south")
        self.seed_fleets_toml(south)
        self.run_tool(south, "send", "zz-north/zz-test-recv", "--as", "zz-test-send",
                      "--kind", "report", "one delivery only", "--go")
        _, north = self.fleet("zz-north")
        first, second = [], []
        self.run_tool(north, "fetch", "--go", nudges=first)
        self.run_tool(north, "fetch", "--go", nudges=second)
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [], "keying on the path is what makes fetch idempotent")

    def test_the_guard_holds_across_a_real_repository(self):
        """fleets.toml is read from the CLONE, so a term added by the mailbox
        owner reaches a sender who never edited anything locally."""
        _, south = self.fleet("zz-south")
        os.makedirs(south.MAIL["clone"], exist_ok=True)
        south.pull()
        with open(os.path.join(south.MAIL["clone"], "fleets.toml"), "w") as f:
            f.write('[fleets.zz-north]\n\n[fleets.zz-south]\n\n[guard]\nrefuse = ["zz-grant-9"]\n')
        south.push("seed", ["fleets.toml"])

        code, out = self.run_tool(south, "send", "zz-north/zz-test-recv",
                                  "--as", "zz-test-send", "--kind", "report",
                                  "the run billed zz-grant-9 overnight", "--go")
        self.assertEqual(code, 2, out)
        self.assertIn("zz-grant-9", out)

    def test_an_unlisted_fleet_cannot_send_even_with_repository_access(self):
        _, south = self.fleet("zz-south")
        os.makedirs(south.MAIL["clone"], exist_ok=True)
        south.pull()
        with open(os.path.join(south.MAIL["clone"], "fleets.toml"), "w") as f:
            f.write('[fleets.zz-north]\n')          # zz-south is NOT listed
        south.push("seed", ["fleets.toml"])
        code, out = self.run_tool(south, "send", "zz-north/zz-test-recv",
                                  "--as", "zz-test-send", "--kind", "report", "hello", "--go")
        self.assertEqual(code, 2, out)
        self.assertIn("not in the mailbox", out)


if __name__ == "__main__":
    unittest.main()


class AFailedNudgeUsedToBePermanent(Base):
    """The file was written, the nudge failed, and nothing ever looked again.

    A message fetched on 2026-10-05 read `needs a human` for ten days. Delivery
    was attempted exactly once: `fetch` skips anything already in the delivery
    record, which is right for the file and wrong for the nudge, and `no new mail`
    returned before any other path could run. So the one pass that could revisit a
    delivery sat behind the one condition guaranteed to be false for it.

    **The budget matched the wrong failure.** `fleetnudge`'s default is tuned for
    "the session is busy", which clears in minutes. What fired was "the input line
    holds text" -- a half-typed draft or an open dialog -- which lasts hours or
    days and which nobody is coming to clear. The pane was typeable for almost all
    of those ten days.

    Reported by coord 2026-10-15, with the ack demonstrated rather than assumed.
    """
    def setUp(self):
        super().setUp()
        self.waits = []

    def stick_one(self, name="20260918T1200-south-coord-hits.md"):
        """Fetch a message with the nudge failing, as it failed that day."""
        self.write(f"mail/north/{name}", message())
        self.nudge_ok = False
        code, out = self.run_main("fetch", "--go")
        self.assertEqual(code, 5, out)
        self.nudges.clear()
        return f"mail/north/{name}"

    def test_a_later_fetch_retries_the_nudge(self):
        rel = self.stick_one()
        self.nudge_ok = True
        code, out = self.run_main("fetch", "--go")
        self.assertEqual(len(self.nudges), 1, "the retry never happened: %s" % out)
        self.assertEqual(code, 0, out)
        self.assertTrue(self.m.delivered()[rel]["nudged"])

    def test_it_retries_even_when_there_is_no_new_mail(self):
        """The exact shape of the bug. `no new mail` is the normal state of a
        mailbox, and it used to return before anything could retry."""
        self.stick_one()
        self.nudge_ok = True
        code, out = self.run_main("fetch", "--go")
        self.assertIn("no new mail", out)
        self.assertEqual(len(self.nudges), 1, "returned at `no new mail` without retrying")

    def test_the_retry_needs_no_flag(self):
        """A flag would reproduce the defect exactly: something that only works
        when somebody thinks to look again. Nobody looked for ten days."""
        import inspect
        src = inspect.getsource(self.m.do_fetch)
        self.assertIn("retry_undelivered(a, seen)", src)
        self.assertNotIn("if a.retry", src)

    def patches(self):
        """The harness's own mock, extended to record the budget.

        Patching `nudge` in the test instead does not work and does not fail
        loudly: `run_main` enters its patches inside whatever the test set up, so
        the harness's mock wins and the test's list stays empty. The first version
        of this read that empty list as the call never happening.
        """
        p = super().patches()
        p[-1] = mock.patch.object(
            self.m, "nudge",
            side_effect=lambda s, i, line, frm, go, wait=0:
            (self.waits.append(wait) or self.nudges.append((s, line, frm))
             or (self.nudge_ok, "why")))
        return p

    def test_the_retry_budget_is_short_not_long(self):
        """The patience is in the repetition, not in any one call. Waiting hours
        inside one fetch blocks the poll and still gives up at the end."""
        self.stick_one()
        self.assertEqual(self.waits, [1800],
                         "first delivery keeps the busy-session budget")
        self.waits.clear()
        self.nudge_ok = True
        self.run_main("fetch", "--go")
        self.assertEqual(self.waits, [45], "a retry must not block the poll")

    def test_the_retry_keeps_the_drop_the_session_is_pointed_at(self):
        """`record` replaces; a retry that used it would drop the `drop` path, and
        the drop is the only thing the nudge line names."""
        rel = self.stick_one()
        before = self.m.delivered()[rel]["drop"]
        self.nudge_ok = True
        self.run_main("fetch", "--go")
        self.assertEqual(self.m.delivered()[rel]["drop"], before)

    def test_a_retry_rewrites_a_drop_that_was_cleaned_up(self):
        rel = self.stick_one()
        os.remove(self.m.delivered()[rel]["drop"])
        self.nudge_ok = True
        self.run_main("fetch", "--go")
        self.assertTrue(os.path.exists(self.m.delivered()[rel]["drop"]))

    def test_a_plan_retries_nothing(self):
        self.stick_one()
        self.nudge_ok = True
        code, out = self.run_main("fetch")
        self.assertEqual(self.nudges, [], "a dry run nudged a live session")
        self.assertIn("would retry", out)

    def test_a_still_failing_retry_stays_undelivered_and_says_so(self):
        rel = self.stick_one()
        code, out = self.run_main("fetch", "--go")
        self.assertEqual(code, 5, out)
        self.assertFalse(self.m.delivered()[rel]["nudged"])
        self.assertIn("still not typeable", out)

    def test_a_quarantined_message_is_not_retried(self):
        """Quarantine is a refusal, not a transient failure. Retrying it would be
        re-offering a message this fleet decided not to deliver.

        Built as a record rather than driven through a fetch, because a fetched
        quarantine carries no `nudged` key at all and so is already excluded by
        the `is False` test -- which means the earlier version of this passed with
        the quarantine check deleted. It proved the filter it names was there by
        exercising a different one.

        This state is reachable: a retry now amends rather than replaces, so a
        record can carry a failed `nudged` and later be quarantined.
        """
        self.write("mail/north/20260918T1200-south-coord-hits.md", message())
        self.m.record("mail/north/20260918T1200-south-coord-hits.md",
                      outcome="quarantined", nudged=False, reason="guard term")
        self.run_main("fetch", "--go")
        self.assertEqual(self.nudges, [])

    def test_never_tried_is_not_the_same_as_tried_and_failed(self):
        """`nudged is False` means delivery was attempted and did not land. A
        record with no `nudged` key was never at that stage, and must not be
        swept into the retry pass on a falsy test."""
        self.write("mail/north/20260918T1200-south-coord-hits.md", message())
        self.m.record("mail/north/20260918T1200-south-coord-hits.md",
                      outcome="quarantined", reason="no front matter")
        self.run_main("fetch", "--go")
        self.assertEqual(self.nudges, [])


class AnAckClosesTheLoopLocally(Base):
    """`ack` mailed the sender and never touched the local record, so a message
    the recipient had demonstrably read still showed `needs a human` -- and the
    only remaining move was hand-editing the state file, which the state
    directory's own rules forbid. A tool whose only escape hatch is the thing its
    own rules forbid has a gap, not a workflow."""
    def stuck(self):
        self.write("mail/north/20260918T1200-south-coord-hits.md", message())
        self.nudge_ok = False
        self.run_main("fetch", "--go")
        return "mail/north/20260918T1200-south-coord-hits.md"

    def test_acking_clears_the_needs_a_human_line(self):
        rel = self.stuck()
        self.assertIn("needs a human", self.run_main("inbox")[1])
        code, out = self.run_main("ack", "20260918T1200", "read it",
                                  "--as", "mailtest", "--go")
        self.assertEqual(code, 0, out)
        self.assertTrue(self.m.delivered()[rel]["acked"])
        self.assertNotIn("needs a human", self.run_main("inbox")[1])

    def test_the_ack_still_reaches_the_sender(self):
        """The local bookkeeping is an addition. If it ever replaced the send, a
        session would believe it had replied to another fleet and it would not
        have."""
        self.stuck()
        code, out = self.run_main("ack", "20260918T1200", "read it",
                                  "--as", "mailtest", "--go")
        sent = [p for p in os.listdir(os.path.join(self.clone, "mail", "south"))
                if p != "INBOX.md"]
        self.assertEqual(len(sent), 1, out)

    def test_a_failed_send_does_not_mark_it_acked(self):
        """The ack is evidence only once it has gone out. Amending first is the
        obvious shape and it is wrong: a session would believe it had replied to
        another fleet when nothing left this machine, and the `needs a human`
        line -- the only thing still saying so -- would be gone."""
        rel = self.stuck()
        self.pull_ok = (False, "could not reach the mailbox")
        code, out = self.run_main("ack", "20260918T1200", "read it",
                                  "--as", "mailtest", "--go")
        self.assertEqual(code, 4, out)
        self.assertFalse(self.m.delivered()[rel].get("acked"),
                         "marked acked although the ack never left")
        self.assertIn("needs a human", self.run_main("inbox")[1])

    def test_an_acked_message_is_not_retried(self):
        """It is resolved. Re-nudging would tell a session about a message it has
        already answered."""
        self.stuck()
        self.run_main("ack", "20260918T1200", "read it", "--as", "mailtest", "--go")
        self.nudges.clear()
        self.nudge_ok = True
        self.run_main("fetch", "--go")
        self.assertEqual(self.nudges, [])

    def test_the_state_says_how_it_was_resolved(self):
        """Not just "delivered". The nudge never landed, and a record that hid
        that would lose the only evidence the delivery path had a bad day."""
        rel = self.stuck()
        self.run_main("ack", "20260918T1200", "read it", "--as", "mailtest", "--go")
        state = self.m.delivery_state(self.m.delivered(), rel)
        self.assertIn("delivered", state)
        self.assertIn("nudge never landed", state)


class Amending(Base):
    def test_it_keeps_what_is_already_there(self):
        """`at` is planted as a distinct old value, not read back from `record`.

        `time.strftime` has one-second resolution, so a record written and amended
        in the same test produces the same stamp either way: the first version of
        this compared the two and passed with `amend` overwriting `at` on every
        call. A timestamp test that does not move the clock is not a test.
        """
        self.m.record("x", outcome="delivered", drop="/d", nudged=False)
        d = self.m.delivered()
        d["x"]["at"] = "2026-10-05T21:15:18-0400"        # ten days before the retry
        self.m._write_delivered(d)

        self.assertTrue(self.m.amend("x", nudged=True))
        rec = self.m.delivered()["x"]
        self.assertEqual(rec["at"], "2026-10-05T21:15:18-0400",
                         "`at` says when the message arrived, not when it was looked at")
        self.assertEqual((rec["drop"], rec["nudged"]), ("/d", True))
        self.assertEqual(rec["outcome"], "delivered")

    def test_a_retry_records_when_it_looked_separately(self):
        """The arrival time and the last attempt are different facts and both are
        wanted: how long a message sat undelivered is the measurement that found
        this bug in the first place."""
        self.m.record("x", outcome="delivered", drop="/d", nudged=False)
        self.m.amend("x", nudged=True, retried_at="2026-10-15T11:46:00-0400")
        rec = self.m.delivered()["x"]
        self.assertIn("retried_at", rec)
        self.assertNotEqual(rec["at"], rec["retried_at"])

    def test_it_refuses_to_invent_a_record(self):
        self.assertFalse(self.m.amend("never-seen", nudged=True))
        self.assertNotIn("never-seen", self.m.delivered())


class ATimerPointedAtAWorkingTree(Base):
    """`fleetmail timer` bakes in the path of the copy it is run from, because
    `BIN` resolves from `__file__`. That is what makes a deployed checkout work --
    generate the unit there and it points there -- and it is the same property
    that lets someone point a 15-minute timer at the directory they develop in.

    That was the arrangement until 2026-10-15. Two ticks landed inside an editing
    window while guards were being deliberately broken; both caught a coherent
    version, by luck. One of the breaks would have destroyed live state.

    A dirty checkout is the one cheap, checkable symptom, and **unknown warns the
    same as dirty**: a copy git cannot speak for is not one to point a timer at.
    """
    def generated(self, status=(0, "")):
        code, out = 0, ""
        rc, stdout = status
        with mock.patch.object(self.m.subprocess, "run",
                               return_value=mock.Mock(returncode=rc, stdout=stdout)):
            code, out = self.run_main("timer")
        return out

    def test_a_clean_checkout_generates_the_unit_without_a_warning(self):
        out = self.generated((0, ""))
        self.assertIn("ExecStart=", out)
        self.assertNotIn("uncommitted changes", out)

    def test_a_dirty_checkout_is_warned_about(self):
        out = self.generated((0, " M bin/fleetmail\n"))
        self.assertIn("uncommitted changes", out)
        self.assertIn("worktree add", out, "the warning must say what to do instead")
        self.assertIn("ExecStart=", out, "it warns; it does not refuse")

    def test_a_directory_git_cannot_speak_for_warns_too(self):
        """Not silence. Unknown is the direction that matters: a wrong 'clean'
        is what puts a timer on a working tree."""
        out = self.generated((128, ""))
        self.assertIn("not a checkout git can read", out)
        self.assertIn("worktree add", out)

    def test_git_being_unrunnable_is_unknown_not_clean(self):
        with mock.patch.object(self.m.subprocess, "run", side_effect=OSError("no git")):
            self.assertIsNone(self.m.being_edited("/anywhere"))

    def test_the_unit_names_the_copy_it_was_generated_from(self):
        """The property the deployment relies on, pinned so it cannot quietly
        become 'wherever the repo is'."""
        out = self.generated()
        self.assertIn(f"ExecStart={os.path.join(self.m.BIN, 'fleetmail')} fetch --go", out)


class Announce(Base):
    """A release is announced to every correspondent fleet, because a clone is
    invisible: git registers nothing when someone clones, GitHub keeps no list of
    who did, and nobody downstream learns their copy is behind except by being
    told. The mailbox is the only channel this fleet has to the people who
    actually run the tools."""

    URL = "https://example.invalid/fleet/releases/tag/v1.2.3"

    def setUp(self):
        super().setUp()
        self.pushes = []
        self.write("fleets.toml",
                   '[fleets.north]\n\n'
                   '[fleets.south]\ncontact = "s-coord"\n')

    def patches(self):
        pp = super().patches()
        return pp[:1] + [mock.patch.object(
            self.m, "push",
            side_effect=lambda msg, paths: (self.pushes.append((msg, list(paths)))
                                            or (True, "pushed")))] + pp[2:]

    def files(self, fleet="south"):
        d = os.path.join(self.clone, "mail", fleet)
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def body_of(self, fleet="south"):
        names = [f for f in self.files(fleet) if f.endswith(".md")]
        with open(os.path.join(self.clone, "mail", fleet, names[-1])) as f:
            return f.read()

    def test_a_plan_writes_nothing(self):
        code, out = self.run_main("announce", "1.2.3", "--as", "mailtest",
                                  "--url", self.URL)
        self.assertEqual(code, 0, out)
        self.assertIn("south/s-coord", out)
        self.assertEqual(self.files(), [])
        self.assertEqual(self.pushes, [])

    def test_it_writes_one_message_per_correspondent(self):
        code, out = self.run_main("announce", "1.2.3", "--as", "mailtest",
                                  "--url", self.URL, "--go")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.files()), 1)

    def test_it_is_not_announced_to_our_own_fleet(self):
        """`north` is us. Mail to ourselves is noise at best, and at worst a
        loopback delivery into a live session (2026-09-18).

        Our own block carries a `contact` here on purpose. Without one, this
        passes whether the exclusion works or not -- an unaddressable fleet
        writes no file either, so the test would be watching the wrong guard."""
        self.write("fleets.toml",
                   '[fleets.north]\ncontact = "mailtest"\n'
                   '\n[fleets.south]\ncontact = "s-coord"\n')
        code, out = self.run_main("announce", "1.2.3", "--as", "mailtest",
                                  "--url", self.URL, "--go")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.files("north"), [])
        self.assertEqual(len(self.files("south")), 1)

    def test_the_line_names_the_version_and_points_at_the_notes(self):
        self.run_main("announce", "1.2.3", "--as", "mailtest",
                      "--url", self.URL, "--go")
        body = self.body_of()
        self.assertIn("fleet v1.2.3 is out", body)
        self.assertIn(self.URL, body)
        self.assertIn("git pull", body)

    def test_the_whole_announcement_is_one_push(self):
        """A push per fleet is several chances to half-succeed, and the half
        nobody looks at is the fleet that was never told."""
        self.write("fleets.toml",
                   '[fleets.north]\n\n[fleets.south]\ncontact = "s-coord"\n'
                   '\n[fleets.east]\ncontact = "e-coord"\n')
        code, out = self.run_main("announce", "1.2.3", "--as", "mailtest",
                                  "--url", self.URL, "--go")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.pushes), 1)
        self.assertEqual(len(self.pushes[0][1]), 2)

    def test_a_fleet_with_no_contact_is_named_not_skipped(self):
        """There is no convention that turns a fleet name into its coordinator's
        session name, and a guessed one is mail that arrives and cannot be
        delivered. Unaddressable has to be loud: a fleet nobody can reach will go
        on running an old copy while this reports an announcement made."""
        self.write("fleets.toml", '[fleets.north]\n\n[fleets.south]\n')
        code, out = self.run_main("announce", "1.2.3", "--as", "mailtest",
                                  "--url", self.URL, "--go")
        self.assertEqual(code, 5, out)
        self.assertIn("south", out)
        self.assertIn("no `contact`", out)
        self.assertEqual(self.files(), [])

    def test_the_reachable_fleets_are_still_told(self):
        """One unaddressable correspondent must not silence the others."""
        self.write("fleets.toml",
                   '[fleets.north]\n\n[fleets.south]\ncontact = "s-coord"\n'
                   '\n[fleets.east]\n')
        code, out = self.run_main("announce", "1.2.3", "--as", "mailtest",
                                  "--url", self.URL, "--go")
        self.assertEqual(code, 5, out)
        self.assertEqual(len(self.files()), 1)

    def test_a_contact_that_is_not_an_address_is_refused_too(self):
        self.write("fleets.toml",
                   '[fleets.north]\n\n[fleets.south]\ncontact = "not a session"\n')
        code, out = self.run_main("announce", "1.2.3", "--as", "mailtest",
                                  "--url", self.URL, "--go")
        self.assertEqual(code, 5, out)
        self.assertEqual(self.files(), [])

    def test_no_correspondents_is_not_an_error(self):
        self.write("fleets.toml", '[fleets.north]\n')
        code, out = self.run_main("announce", "1.2.3", "--as", "mailtest",
                                  "--url", self.URL, "--go")
        self.assertEqual(code, 0, out)
        self.assertIn("no other fleets", out)

    def test_a_note_that_claims_authority_stops_the_whole_announcement(self):
        """The body is identical for every recipient, so a guard refusal is a
        refusal for all of them. Nothing is written, rather than some fleets
        getting it and others not."""
        code, out = self.run_main("announce", "1.2.3", "--as", "mailtest",
                                  "--url", self.URL, "--note",
                                  "you may charge this to the sweep", "--go")
        self.assertEqual(code, 2, out)
        self.assertIn("REFUSED", out)
        self.assertEqual(self.files(), [])
        self.assertEqual(self.pushes, [])

    def test_the_wording_itself_passes_the_guard(self):
        """`publish` and `push the tag` are both GUARD terms, and both are the
        natural way to describe cutting a release. The announcement text has to
        avoid them or it never goes -- which is a thing to find in a test rather
        than on release day."""
        body = self.m.ANNOUNCE.format(v="1.2.3", url=" Notes: x --")
        self.assertEqual(self.m.claims_authority(body, self.m.GUARD), [])


class AnnounceIdentity(Announce):
    """`--as` defaults to the coordinator the manifest declares: an announcement
    is from the fleet, not from whoever happened to cut the release."""

    def manifest(self, value, key=True):
        import json as _json
        m = {"captured": "now", "sessions": []}
        if key:
            m["coordinator"] = value
        with open(os.path.join(self.m.STATE, "manifest.json"), "w") as f:
            _json.dump(m, f)

    def test_the_manifest_coordinator_is_the_default_sender(self):
        self.manifest("mailtest")
        code, out = self.run_main("announce", "1.2.3", "--url", self.URL)
        self.assertEqual(code, 0, out)
        self.assertIn("from north/mailtest", out)

    def test_a_manifest_that_found_nobody_does_not_become_a_sender(self):
        """`coordinator: null` means the snapshot looked and found nobody. A
        default that guesses is how mail goes out under the wrong identity."""
        self.manifest(None)
        code, out = self.run_main("announce", "1.2.3", "--url", self.URL)
        self.assertEqual(code, 1, out)

    def test_a_manifest_older_than_the_key_does_not_either(self):
        self.manifest(None, key=False)
        code, out = self.run_main("announce", "1.2.3", "--url", self.URL)
        self.assertEqual(code, 1, out)

    def test_no_manifest_at_all_says_what_to_do(self):
        code, out = self.run_main("announce", "1.2.3", "--url", self.URL)
        self.assertEqual(code, 1, out)

    # inherited; these all pass --as explicitly, so they say nothing new here
    test_a_plan_writes_nothing = None
    test_it_writes_one_message_per_correspondent = None
    test_it_is_not_announced_to_our_own_fleet = None
    test_the_line_names_the_version_and_points_at_the_notes = None
    test_the_whole_announcement_is_one_push = None
    test_a_fleet_with_no_contact_is_named_not_skipped = None
    test_the_reachable_fleets_are_still_told = None
    test_a_contact_that_is_not_an_address_is_refused_too = None
    test_no_correspondents_is_not_an_error = None
    test_a_note_that_claims_authority_stops_the_whole_announcement = None
    test_the_wording_itself_passes_the_guard = None


class AnnounceReleaseUrl(Base):
    """The release page is derived from the APP repo's own origin, so a fork that
    cuts its own release points at its own page rather than advertising ours."""

    def url(self, rc, out):
        with mock.patch.object(self.m, "git", return_value=(rc, out, "")):
            return self.m.release_url("1.2.3")

    def test_an_ssh_remote(self):
        self.assertEqual(self.url(0, "git@github.com:owner/repo.git"),
                         "https://github.com/owner/repo/releases/tag/v1.2.3")

    def test_an_https_remote(self):
        self.assertEqual(self.url(0, "https://github.com/owner/repo.git"),
                         "https://github.com/owner/repo/releases/tag/v1.2.3")

    def test_a_remote_with_no_dot_git(self):
        self.assertEqual(self.url(0, "https://github.com/owner/repo"),
                         "https://github.com/owner/repo/releases/tag/v1.2.3")

    def test_a_remote_that_is_not_github_gives_nothing(self):
        """Not a guess. A wrong URL in an announcement is worse than none: the
        reader who follows it and sees a familiar number concludes they are
        current."""
        self.assertEqual(self.url(0, "git@gitlab.example:owner/repo.git"), "")

    def test_no_remote_at_all_gives_nothing(self):
        self.assertEqual(self.url(128, ""), "")

    def test_the_line_says_so_rather_than_omitting_it_quietly(self):
        self.write("fleets.toml", '[fleets.north]\n\n[fleets.south]\ncontact = "s"\n')
        with mock.patch.object(self.m, "release_url", return_value=""):
            code, out = self.run_main("announce", "1.2.3", "--as", "mailtest")
        self.assertEqual(code, 0, out)
        self.assertIn("no release page named", out)


class TheReleaseScriptAnnounces(unittest.TestCase):
    """`scripts/release.sh` is the only caller, and the two properties that make
    it safe to call there are properties of ITS text, not of the tool."""

    def setUp(self):
        from tests.support import APP
        with open(os.path.join(APP, "scripts", "release.sh")) as f:
            self.src = f.read()

    def test_it_announces_after_the_tag_is_pushed(self):
        """Before the tag, the announcement would name a release page that does
        not exist yet, and a release that died at the push would already have
        been announced."""
        self.assertLess(self.src.index('git push origin "v$VERSION"'),
                        self.src.index("fleetmail announce"))

    def test_a_mailbox_failure_does_not_fail_the_release(self):
        """By the time this runs the tag is out and cannot be taken back. An
        unreachable mailbox is a message to send again, not a release to undo."""
        line = [l for l in self.src.splitlines() if "fleetmail announce" in l
                and not l.strip().startswith("#")][0]
        self.assertIn("||", line, "the call must not be able to abort the script")

    def test_the_failure_is_printed_rather_than_swallowed(self):
        """`|| true` would make 'announced' and 'reached nobody' look alike."""
        self.assertNotIn("fleetmail announce \"$VERSION\" --go || true", self.src)
        self.assertIn("re-run: bin/fleetmail announce", self.src)

    def test_there_is_a_way_to_not_announce(self):
        self.assertIn("--no-announce", self.src)


class AThreadIsNotInOneDirectory(Base):
    """Mail to this fleet is under `mail/<us>/`; every reply this fleet sends is
    under the correspondent's. So a conversation is split across two directories
    by construction, and anything reading one of them is reading half of it.

    Measured on a live mailbox 2026-11-18: 45 messages, 10 threads, and the
    largest thread 27 messages written by three sessions on one side and two on
    the other. The index read our half.
    """

    def sent(self, name, **kw):
        kw.setdefault("frm", "north/mailtest")
        kw.setdefault("to", "south/coord")
        self.write("mail/south/%s" % name, message(**kw))

    def got(self, name, **kw):
        self.write("mail/north/%s" % name, message(**kw))

    def test_both_directions_are_seen(self):
        self.got("20260101T000000-a.md", thread="t1")
        self.sent("20260101T000100-b.md", thread="t1")
        self.assertEqual(len(self.m.all_messages()), 2)

    def test_the_order_is_chronological_across_directories(self):
        """The timestamp prefix is the order. Sorting within each directory and
        concatenating would put our whole half after theirs."""
        self.got("20260101T000000-a.md", thread="t1")
        self.sent("20260101T000100-b.md", thread="t1")
        self.got("20260101T000200-c.md", thread="t1")
        got = [os.path.basename(r) for r, _, _ in self.m.all_messages()]
        self.assertEqual(got, ["20260101T000000-a.md", "20260101T000100-b.md",
                               "20260101T000200-c.md"])

    def test_our_own_message_is_recognized_as_ours(self):
        self.assertTrue(self.m.ours({"from": "north/mailtest"}))
        self.assertFalse(self.m.ours({"from": "south/coord"}))

    def test_a_message_that_cannot_be_read_is_not_ours(self):
        """`ours` decides who wrote it. An unreadable message is not one of ours
        on the strength of being unreadable, which would mark a thread answered
        because the evidence went missing."""
        self.assertFalse(self.m.ours(None))
        self.assertFalse(self.m.ours({}))

    def test_a_message_with_no_thread_is_its_own_conversation(self):
        """Otherwise every threadless message in the mailbox joins one bucket
        under the empty string, and each one's state decides all the others'."""
        a = self.m.thread_of("mail/north/1-a.md", {"from": "south/coord"})
        b = self.m.thread_of("mail/north/2-b.md", {"from": "south/coord"})
        self.assertNotEqual(a, b)

    def test_the_time_comes_from_the_filename_and_nowhere_else(self):
        """The front matter carries from, to, kind and thread -- never a date."""
        t = self.m.msg_time("mail/north/20261006T182411-x.md")
        self.assertEqual(time.strftime("%Y-%m-%d %H:%M", t), "2026-10-06 18:24")

    def test_a_name_with_no_readable_time_is_none_not_now(self):
        for name in ("no-stamp.md", "20261332T999999-x.md", ""):
            self.assertIsNone(self.m.msg_time(name), name)


class TheStateColumnHasTwoPossibleOutcomes(Base):
    """The regression this replaces, and it is family C.

    The old rule asked whether an **ack had arrived in our own directory**. An
    ack we send is addressed to them and written to THEIR directory, so our
    replies and our acks were both invisible to it, and the column could only
    ever say `open`. On the live mailbox that was 45 messages over six weeks,
    every one of them `open`, including threads answered within the hour -- and
    it buried the single question that really was unanswered among twenty-three
    that were not.
    """

    def sent(self, name, **kw):
        kw.setdefault("frm", "north/mailtest")
        kw.setdefault("to", "south/coord")
        self.write("mail/south/%s" % name, message(**kw))

    def got(self, name, **kw):
        self.write("mail/north/%s" % name, message(**kw))

    def data_rows(self):
        """The table's rows without its header. The separator line begins `|-`
        and so is already out; the header is the one row left to drop."""
        return [l for l in self.inbox_text().splitlines()
                if l.startswith("| ")][1:]

    def test_a_thread_we_replied_to_is_answered(self):
        """The whole defect, in three lines. Before the fix this read `open`."""
        self.got("20260101T000000-q.md", thread="t1")
        self.sent("20260101T000100-r.md", thread="t1")
        self.m.write_inbox("north")
        self.assertIn("| answered |", self.inbox_text())
        self.assertNotIn("| open |", self.inbox_text())

    def test_a_thread_they_wrote_last_in_is_open(self):
        self.got("20260101T000000-q.md", thread="t1")
        self.sent("20260101T000100-r.md", thread="t1")
        self.got("20260101T000200-q2.md", thread="t1")
        self.m.write_inbox("north")
        self.assertIn("| open |", self.inbox_text())
        self.assertNotIn("| answered |", self.inbox_text())

    def test_our_reply_counts_even_though_it_is_not_an_ack(self):
        """A reply is a better answer than an ack and was the one the old rule
        could not see at all: only `kind: ack` closed a thread, and only one
        that had arrived here."""
        self.got("20260101T000000-q.md", thread="t1")
        self.sent("20260101T000100-r.md", thread="t1", kind="report")
        self.m.write_inbox("north")
        self.assertIn("| answered |", self.inbox_text())

    def test_a_thread_with_no_reply_at_all_stays_open(self):
        self.got("20260101T000000-q.md", thread="t1")
        self.m.write_inbox("north")
        self.assertIn("| open |", self.inbox_text())

    def test_their_ack_still_closes_it(self):
        self.got("20260101T000000-q.md", thread="t1")
        self.got("20260101T000100-a.md", thread="t1", kind="ack", body="ack: read")
        self.m.write_inbox("north")
        self.assertNotIn("| open |", self.inbox_text())

    def test_a_newest_message_that_cannot_be_parsed_leaves_it_open(self):
        """A message nobody can read is not one anybody can say was handled."""
        self.got("20260101T000000-q.md", thread="t1")
        self.sent("20260101T000100-r.md", thread="t1")
        self.write("mail/north/20260101T000200-junk.md", "no front matter here")
        self.m.write_inbox("north")
        self.assertIn("| open |", self.inbox_text())

    def test_open_threads_sort_first(self):
        self.got("20260101T000000-old.md", thread="t1")
        self.sent("20260101T000100-r.md", thread="t1")
        self.got("20260101T000200-new.md", thread="t2")
        self.m.write_inbox("north")
        rows = self.data_rows()
        self.assertTrue(rows[0].startswith("| open |"), rows)

    def test_only_our_own_mail_is_listed(self):
        """Both directories are READ, so a reply can be seen; only messages
        addressed to this fleet are listed. An index that listed our sent mail
        would be a different document."""
        self.got("20260101T000000-q.md", thread="t1")
        self.sent("20260101T000100-r.md", thread="t1")
        self.m.write_inbox("north")
        rows = self.data_rows()
        self.assertEqual(len(rows), 1, rows)
        self.assertIn("20260101T000000-q.md", rows[0])

    def test_the_delivery_column_still_says_what_happened_here(self):
        """The other column is about this machine and is untouched by any of
        this: a thread can be answered and a message still never have reached
        the session it was addressed to."""
        self.got("20260101T000000-q.md", thread="t1")
        self.sent("20260101T000100-r.md", thread="t1")
        self.m.write_inbox("north")
        self.assertIn("not fetched", self.inbox_text())

    def test_the_header_says_what_open_means(self):
        """A reader seeing a column of `open` has to know whether it is about
        them. The file is committed to a shared repository, so the sentence
        travels with it."""
        self.m.write_inbox("north")
        self.assertIn("the next move is ours", self.inbox_text())


class ReadingAThread(Base):
    """`fleetmail inbox` is an index; this is the conversation."""

    def sent(self, name, **kw):
        kw.setdefault("frm", "north/mailtest")
        kw.setdefault("to", "south/coord")
        self.write("mail/south/%s" % name, message(**kw))

    def got(self, name, **kw):
        self.write("mail/north/%s" % name, message(**kw))

    def conversation(self):
        self.got("20260101T000000-q.md", thread="t1", body="their question")
        self.sent("20260101T000100-r.md", thread="t1", body="our answer")
        self.got("20260101T000200-f.md", thread="t1", body="their follow-up")

    def read(self, *argv):
        return self.run_main("read", *argv)

    def test_both_halves_are_in_the_output_in_order(self):
        self.conversation()
        code, out = self.read("t1")
        self.assertEqual(code, 0)
        self.assertLess(out.index("their question"), out.index("our answer"))
        self.assertLess(out.index("our answer"), out.index("their follow-up"))

    def test_our_own_messages_are_marked(self):
        self.conversation()
        _, out = self.read("t1")
        ours = [l for l in out.splitlines() if "north/mailtest" in l and "->" in l]
        self.assertEqual(len(ours), 1, out)

    def test_the_header_says_how_many_and_whether_it_is_open(self):
        self.conversation()
        _, out = self.read("t1")
        self.assertIn("3 messages, open", out)

    def test_an_open_thread_ends_with_the_reply_command(self):
        """After the thread rather than before it: the decision is made at the
        bottom, by a reader who has just finished reading."""
        self.conversation()
        _, out = self.read("t1")
        self.assertIn("they wrote last", out)
        self.assertIn("--thread t1", out)
        self.assertLess(out.index("their follow-up"), out.index("they wrote last"))

    def test_an_answered_thread_says_so_instead(self):
        self.got("20260101T000000-q.md", thread="t1")
        self.sent("20260101T000100-r.md", thread="t1")
        _, out = self.read("t1")
        self.assertIn("we wrote last", out)
        self.assertNotIn("fleetmail send", out)

    def test_it_resolves_a_message_by_filename_prefix(self):
        """The handle `ack` already takes, so a reader who just acked something
        can read it with what they have already typed."""
        self.conversation()
        code, out = self.read("20260101T000100")
        self.assertEqual(code, 0)
        self.assertIn("their question", out)

    def test_it_resolves_part_of_a_thread_name(self):
        self.got("20260101T000000-q.md", thread="2026-01-01-a-long-dated-thread-name")
        code, out = self.read("long-dated")
        self.assertEqual(code, 0)

    def test_an_ambiguous_name_is_refused_with_the_candidates(self):
        """Resolving to the newest would print a guess as a conversation, and
        the reader would have no way to see it happened."""
        self.got("20260101T000000-a.md", thread="sweep-one")
        self.got("20260101T000100-b.md", thread="sweep-two")
        code, out = self.read("sweep")
        self.assertEqual(code, 2)
        self.assertIn("sweep-one", out)
        self.assertIn("sweep-two", out)

    def test_a_name_that_matches_nothing_is_refused(self):
        self.conversation()
        code, out = self.read("nothing-like-this")
        self.assertEqual(code, 2)
        self.assertIn("nothing in the mailbox matches", out)

    def test_brief_is_one_line_per_message(self):
        self.got("20260101T000000-q.md", thread="t1",
                 body="a first line\nand a second line that --brief must not print")
        _, out = self.read("t1", "--brief")
        self.assertIn("a first line", out)
        self.assertNotIn("must not print", out)

    def test_the_whole_body_is_printed_without_brief(self):
        self.got("20260101T000000-q.md", thread="t1",
                 body="a first line\nand a second line")
        _, out = self.read("t1")
        self.assertIn("and a second line", out)

    def test_an_attachment_is_named(self):
        self.write("mail/south/20260101T000100-r.md",
                   "---\nfrom: north/mailtest\nto: south/coord\nkind: report\n"
                   "thread: t1\nattaches: mail/south/attach/20260101-notes.md\n---\nsee file\n")
        code, out = self.read("t1")
        self.assertEqual(code, 0)
        self.assertIn("attach/20260101-notes.md", out)

    def test_an_unreadable_message_is_shown_as_one_not_skipped(self):
        """Skipping it would make the conversation look complete."""
        self.got("20260101T000000-q.md", thread="t1")
        self.write("mail/north/20260101T000100-junk.md", "no front matter")
        code, out = self.read("20260101T000100")
        self.assertEqual(code, 0)
        self.assertIn("UNREADABLE", out)

    def test_a_filename_with_no_timestamp_does_not_stop_the_read(self):
        self.write("mail/north/plain-name.md", message(thread="t1"))
        code, out = self.read("t1")
        self.assertEqual(code, 0)

    def test_it_says_which_clone_it_read_and_that_fetch_updates_it(self):
        """It reads the clone where it stands. A thread that ends mid-question
        may end there or merely end here, and the reader cannot tell which."""
        self.conversation()
        _, out = self.read("t1")
        self.assertIn(self.m.MAIL["clone"], out)
        self.assertIn("fleetmail fetch", out)
