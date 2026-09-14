"""One pass over a transcript: when it lived, when it was active, and what happened in it.

Read by fleetgantt. Everything here is what the transcript itself records; nothing is
inferred about which session it belongs to (see fleet.identity for that).
"""
import datetime
import json
import os
import re

BIN = 15 * 60                 # activity bins, seconds
COMPACT_MERGE = 10 * 60       # compaction records this close together are one compaction
CLEAR_WITHIN = 3              # /clear counts if it is in the first N user records
_SELF_RE = re.compile(r"This session is (\S+) \[[0-9a-f]{6}\]")

def _epoch(ts):
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None

def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content
                        if isinstance(c, dict) and c.get("type") == "text")
    return ""

def scan(path):
    """dict for one transcript, or None if it has no timestamped record.

    names     [(epoch or None, name)] from agent-name records and ListAgents
              self-reports, in file order
    first, last, bins (sorted bin indices with any timestamped record)
    clear     started by /clear (a /clear command among the first user records)
    compact   [epoch], merged within COMPACT_MERGE
    renames   [(epoch, old, new)] where the agent-name changes; an agent-name record
              carries no timestamp, so the last timestamp before it is used
    sent      SendMessage tool_uses; received: cross-session messages delivered
    versions  [first, last] claude version seen; version_seen {version: first epoch}
    cwd       the first recorded working directory
    """
    r = {"uuid": os.path.basename(path)[:-6],
         "project": os.path.basename(os.path.dirname(path)),
         "names": [], "agent_names": [], "first": None, "last": None, "bins": set(),
         "clear": False, "compact": [], "renames": [], "sent": 0, "received": 0,
         "versions": [], "version_seen": {}, "cwd": None}
    last_ts, users, compacts, seen_msgs = None, 0, [], set()
    try:
        fh = open(path, errors="replace")
    except OSError:
        return None
    with fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict):
                continue
            typ = d.get("type")
            if typ == "agent-name" and d.get("agentName"):
                name = d["agentName"]
                prev = r["agent_names"][-1] if r["agent_names"] else None
                if prev and prev != name and last_ts is not None:
                    r["renames"].append((last_ts, prev, name))
                r["agent_names"].append(name)
                r["names"].append((last_ts, name))
                continue
            t = _epoch(d.get("timestamp")) if d.get("timestamp") else None
            msg = d.get("message") if isinstance(d.get("message"), dict) else {}
            content = msg.get("content")
            text = _text(content) if typ in ("user", "assistant") else ""
            # ListAgents' header is in a tool_result, which _text skips: search the line
            if "This session is " in line:
                for m in _SELF_RE.finditer(line):
                    r["names"].append((t, m.group(1)))
            if t is None:
                continue
            last_ts = t
            r["first"] = t if r["first"] is None else min(r["first"], t)
            r["last"] = t if r["last"] is None else max(r["last"], t)
            r["bins"].add(int(t // BIN))
            if d.get("cwd") and not r["cwd"]:
                r["cwd"] = d["cwd"]
            v = d.get("version")
            if v:
                if not r["versions"]:
                    r["versions"] = [v, v]
                r["versions"][1] = v
                r["version_seen"].setdefault(v, t)
            if d.get("isCompactSummary") or (typ == "system" and d.get("subtype") == "compact_boundary"):
                compacts.append(t)
            if typ == "user":
                if isinstance(content, list) and any(isinstance(c, dict) and c.get("type") == "tool_result"
                                                     for c in content):
                    continue
                users += 1
                if users <= CLEAR_WITHIN and "<command-name>/clear" in text:
                    r["clear"] = True
                if "<cross-session-message" in text:
                    # the same delivery can be recorded twice (queue + message)
                    key = text.split("</cross-session-message>", 1)[0][-400:]
                    if key not in seen_msgs:
                        seen_msgs.add(key)
                        r["received"] += 1
            elif typ == "assistant" and isinstance(content, list):
                r["sent"] += sum(1 for c in content if isinstance(c, dict)
                                 and c.get("type") == "tool_use" and c.get("name") == "SendMessage")
    if r["first"] is None:
        return None
    for t in sorted(compacts):
        if not r["compact"] or t - r["compact"][-1] > COMPACT_MERGE:
            r["compact"].append(t)
    r["bins"] = sorted(r["bins"])
    return r
