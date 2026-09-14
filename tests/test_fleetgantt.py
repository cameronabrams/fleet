import json, os, tempfile, unittest
from unittest import mock
from tests.support import BASE_TOML, FakeConfig, load_tool
from fleet import history

UUID = "cccccccc-0000-4000-8000-00000000000{}"

class Gantt(unittest.TestCase):
    toml = BASE_TOML + ('\n[human]\ntimezone = "America/New_York"\n'
                        '\n[retired.old-role]\nuuid = "dddddddd-0000-4000-8000-000000000009"\n'
                        'since = "2026-09-05"\ngroup = "alpha"\ncwd = "/home/u/old"\nnote = "done"\n')

    def setUp(self):
        self.cfg = FakeConfig(toml=self.toml)
        self.tmp = tempfile.TemporaryDirectory()
        json.dump({"sessions": [
            {"label": "alpha", "fleet": "alpha", "cwd": "/home/u/a"},
            {"label": "beta", "fleet": "beta", "cwd": "/home/u/b"},
            {"label": "runs-1", "fleet": "beta", "cwd": "/home/u/shared"},
            {"label": "runs-2", "fleet": "beta", "cwd": "/home/u/shared"}]},
            open(os.path.join(self.cfg.state, "manifest.json"), "w"))
        self.g = load_tool("fleetgantt")
        self.p = mock.patch.object(self.g, "PROJECTS", self.tmp.name)
        self.p.start()
        self.n = 0

    def tearDown(self):
        self.p.stop(); self.tmp.cleanup(); self.cfg.close()

    def transcript(self, proj, name=None, day=10, hours=(10, 11), version="2.1.1", extra=()):
        self.n += 1
        d = os.path.join(self.tmp.name, proj); os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, UUID.format(self.n) + ".jsonl"), "w") as f:
            if name:
                f.write(json.dumps({"type": "agent-name", "agentName": name}) + "\n")
            for h in hours:
                f.write(json.dumps({"type": "user", "timestamp": f"2026-09-{day:02d}T{h:02d}:00:00Z",
                                    "version": version, "message": {"content": "work"}}) + "\n")
            for r in extra:
                f.write(json.dumps(r) + "\n")
        return UUID.format(self.n)[:8]

    def build(self, *argv):
        a = self.g.argparse.Namespace(since=None, until=None, all=False, no_derived=False)
        for k, v in zip(argv[::2], argv[1::2]):
            setattr(a, k, v)
        return self.g.build(a)

    def lane(self, data, role):
        return next(l for l in data["lanes"] if l["role"] == role)

    def test_lanes_groups_and_order(self):
        self.transcript("-home-u-a", "alpha"); self.transcript("-home-u-b", "beta")
        self.transcript("-home-u-old", "old-role", day=4)
        d = self.build()
        self.assertEqual([(l["group"], l["role"], l["state"]) for l in d["lanes"]],
                         [("alpha", "alpha", "live"), ("alpha", "old-role", "retired"),
                          ("beta", "beta", "live"), ("beta", "runs-1", "live"), ("beta", "runs-2", "live")])
        self.assertEqual(self.lane(d, "alpha")["color"], "red")
        self.assertEqual(self.lane(d, "old-role")["color"], "gray")

    def test_unnamed_transcript_placed_by_directory_and_marked(self):
        u = self.transcript("-home-u-b")
        s = self.lane(self.build(), "beta")["segs"][0]
        self.assertEqual(s["uuid"], u)
        self.assertTrue(s["inferred"])

    def test_renamed_transcript_is_its_last_name(self):
        self.transcript("-home-u-a", "alpha", extra=[{"type": "agent-name", "agentName": "beta"}])
        d = self.build()
        self.assertEqual(len(self.lane(d, "beta")["segs"]), 1)
        self.assertEqual(self.lane(d, "alpha")["segs"], [])
        self.assertFalse(self.lane(d, "beta")["segs"][0]["inferred"])

    def test_named_non_role_in_a_role_directory_is_unattached_not_placed(self):
        self.transcript("-home-u-b", "remote title")
        d = self.build()
        self.assertEqual(self.lane(d, "beta")["segs"], [])
        self.assertEqual([s["name"] for s in self.lane(d, "unattached")["segs"]], ["remote title"])

    def test_shared_directory_does_not_place_unnamed_transcripts(self):
        self.transcript("-home-u-shared")
        d = self.build()
        self.assertEqual(self.lane(d, "runs-1")["segs"] + self.lane(d, "runs-2")["segs"], [])
        self.assertIn("shared by runs-1, runs-2", self.lane(d, "unattached")["segs"][0]["note"])

    def test_outside_every_role_is_counted_not_drawn_unless_all(self):
        self.transcript("-home-u-a", "alpha"); self.transcript("-home-u-elsewhere", "someone")
        d = self.build()
        self.assertEqual(d["other"]["count"], 1)
        self.assertFalse(any(l["role"] == "unattached" for l in d["lanes"]))
        self.assertEqual(len(self.lane(self.build("all", True), "unattached")["segs"]), 1)

    def test_overlapping_transcripts_stack(self):
        self.transcript("-home-u-a", "alpha", hours=(10, 14)); self.transcript("-home-u-a", "alpha", hours=(12, 13))
        self.transcript("-home-u-a", "alpha", hours=(15, 16))
        self.assertEqual(self.lane(self.build(), "alpha")["rows"], 2)

    def test_window_clips(self):
        self.transcript("-home-u-a", "alpha", day=1); self.transcript("-home-u-a", "alpha", day=10)
        d = self.build("since", "2026-09-05", "until", "2026-09-12")
        self.assertEqual(len(self.lane(d, "alpha")["segs"]), 1)
        self.assertEqual(d["days"][0][1], "Sep 5")
        self.assertEqual(d["t1"] - d["t0"], 8 * 86400)          # through the end of Sep 12, EDT

    def test_derived_events(self):
        self.transcript("-home-u-old", "old-role", day=3)                      # window reaches Sep 5
        self.transcript("-home-u-a", "alpha", version="2.1.9"); self.transcript("-home-u-b", "beta", version="2.1.9")
        self.transcript("-home-u-a", "alpha", day=11, version="2.1.10")        # one role only
        open(os.path.join(self.cfg.config, "events.toml"), "w").write(
            '[[event]]\ndate = "2026-09-10"\ntime = "09:00"\nlabel = "declared one"\n')
        d = self.build()
        self.assertEqual([v["v"] for v in d["versions"]], ["2.1.9"])
        self.assertEqual({(e["label"], e["kind"]) for e in d["events"]},
                         {("declared one", "declared"), ("old-role retired", "derived")})
        d = self.build("no_derived", True)
        self.assertEqual((d["versions"], [e["kind"] for e in d["events"]]), ([], ["declared"]))

    def test_render_cannot_break_out_of_the_data_script(self):
        self.transcript("-home-u-b", "</script><script>alert(1)</script>")
        page = self.g.render(self.build())
        self.assertEqual(page.count("</script>"), 2)
        self.assertIn('"zone":"America/New_York"', page)


class DayLabels(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig()
        self.g = load_tool("fleetgantt")

    def tearDown(self):
        self.cfg.close()

    def shown(self, since, until):
        tz = "America/New_York"
        t0 = self.g.parse_when(since, tz); t1 = self.g.parse_when(until, tz, end=True)
        return [label for _, label, _, show in self.g.day_ticks(t0, t1, tz) if show]

    def test_month_label_next_to_a_monday_is_dropped(self):
        # 2026-08-31 is a Monday; Sep 1 would print on top of it
        self.assertEqual(self.shown("2026-08-26", "2026-09-10"), ["Aug 26", "Aug 31", "Sep 7"])

    def test_month_label_clear_of_mondays_is_kept(self):
        # 2026-10-01 is a Thursday; the nearest Mondays are Sep 28 and Oct 5
        self.assertEqual(self.shown("2026-09-24", "2026-10-06"), ["Sep 24", "Sep 28", "Oct 1", "Oct 5"])

    def test_month_label_next_to_the_first_label_is_dropped(self):
        self.assertEqual(self.shown("2026-09-30", "2026-10-06"), ["Sep 30", "Oct 5"])

if __name__ == "__main__":
    unittest.main()
