"""Claude Code's own list of sessions: `claude agents --json`.

Each entry names a session as it answers now (a /rename included), its session id,
its pid when it has one, and its kind: `interactive` (in a terminal) or
`background`. The background kind matters because `/exit` can MOVE a session to
the background instead of stopping it -- OBSERVED 2026-09-15 on 2.1.272, when
Artifact comment auto-replies were armed: the pane printed "backgrounded · <id>",
the pid exited, and a fork carried on under a new pid and session id. "The pid is
gone" does not mean "the session stopped".

The command is newer than some claude versions a fleet may run, so a failure is
returned as None and callers must say they could not check -- never read it as
"no sessions".
"""
import json
import subprocess

def list_agents(timeout=30):
    """[dict] from `claude agents --json`, or None if it could not be read."""
    try:
        r = subprocess.run(["claude", "agents", "--json"], capture_output=True, text=True,
                           timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    try:
        data = json.loads(r.stdout)
    except ValueError:
        return None
    return data if isinstance(data, list) else None

def background_named(agents, name):
    """Background sessions answering to `name` (session still live, maybe pid-less)."""
    return [a for a in agents or [] if a.get("kind") == "background" and a.get("name") == name]

def by_session_prefix(agents, prefix):
    """The agent whose session id starts with `prefix` (as `claude attach <id>` gives it)."""
    hits = [a for a in agents or [] if str(a.get("sessionId", "")).startswith(prefix)]
    return hits[0] if len(hits) == 1 else None
