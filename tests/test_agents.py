import json, subprocess, unittest
from unittest import mock
from fleet import agents

# the shape `claude agents --json` printed on 2.1.272 (trimmed, anonymized)
SAMPLE = [
    {"id": "d730bdc1", "cwd": "/home/u/p", "kind": "background", "startedAt": 1,
     "sessionId": "d730bdc1-2484-4631-8cf6-a40c6aabf4e2", "name": "repo (2)", "state": "blocked"},
    {"pid": 241921, "cwd": "/home/u/s", "kind": "interactive", "startedAt": 2,
     "sessionId": "10afb94e-a138-484c-bb0d-cb0ac4f2b8a9", "name": "coord", "status": "busy"},
    {"pid": 543137, "cwd": "/home/u/r", "kind": "background", "startedAt": 3,
     "sessionId": "b20bc72b-67e8-43d6-a31d-3e636bc68d96", "name": "study", "state": "working", "status": "busy"},
]

class ListAgents(unittest.TestCase):
    def run_with(self, **kw):
        result = subprocess.CompletedProcess(["claude"], kw.get("rc", 0), kw.get("out", ""), "")
        with mock.patch.object(agents.subprocess, "run", return_value=result):
            return agents.list_agents()

    def test_parses(self):
        self.assertEqual(len(self.run_with(out=json.dumps(SAMPLE))), 3)

    def test_failure_is_none_never_empty(self):
        self.assertIsNone(self.run_with(rc=1, out="[]"))
        self.assertIsNone(self.run_with(out="error: unknown command 'agents'"))
        self.assertIsNone(self.run_with(out='{"not": "a list"}'))
        with mock.patch.object(agents.subprocess, "run", side_effect=OSError("no claude")):
            self.assertIsNone(agents.list_agents())

    def test_lookups(self):
        self.assertEqual([a["sessionId"][:8] for a in agents.background_named(SAMPLE, "study")], ["b20bc72b"])
        self.assertEqual(agents.background_named(SAMPLE, "coord"), [])          # interactive, not background
        self.assertEqual(agents.background_named(None, "study"), [])
        self.assertEqual(agents.by_session_prefix(SAMPLE, "b20bc72b")["name"], "study")
        self.assertIsNone(agents.by_session_prefix(SAMPLE, "ffff"))
