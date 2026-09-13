"""The ONE place fleet tools learn about the fleet they are running against.

Three layers, deliberately kept apart::

  application    this package and bin/            -- versioned, shareable
  configuration  $FLEET_CONFIG or ~/.config/fleet  -- what a human DECLARES
  state          [paths].state, ~/.local/state/fleet by default
                                                   -- what the tools OBSERVE

Configuration and state are the pair most easily conflated, and conflating them
is the mistake the fleet's re-arm ledgers made: their inventory was state
masquerading as configuration, so it rotted. Nothing observed at runtime belongs
in fleet.toml, and nothing a human declares belongs in the state directory.

Reads TOML with the stdlib `tomllib` on purpose. These tools are the recovery
path after a disk loss or power cycle, and a recovery tool that needs a package
installed before it can read its own configuration fails at exactly the moment
it is needed.
"""
import os
import re
import tomllib

class ConfigError(RuntimeError):
    pass

def config_dir():
    return os.path.expanduser(os.environ.get("FLEET_CONFIG", "~/.config/fleet"))

def load(required=True):
    path = os.path.join(config_dir(), "fleet.toml")
    if not os.path.exists(path):
        if required:
            raise ConfigError(
                f"no fleet configuration at {path}\n"
                f"  copy examples/fleet.example.toml there and edit it,\n"
                f"  or point FLEET_CONFIG at the directory holding fleet.toml")
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)

def state_dir(cfg=None):
    cfg = cfg if cfg is not None else load(required=False)
    return os.path.expanduser(cfg.get("paths", {}).get("state", "~/.local/state/fleet"))

def cluster(cfg, name=None):
    """A cluster section. With one cluster configured, `name` may be omitted."""
    cl = cfg.get("cluster", {})
    if not cl:
        raise ConfigError("fleet.toml has no [cluster.<name>] section")
    if name is None:
        if len(cl) != 1:
            raise ConfigError(f"several clusters configured ({', '.join(cl)}); name one")
        name = next(iter(cl))
    if name not in cl:
        raise ConfigError(f"no [cluster.{name}] in fleet.toml")
    c = dict(cl[name]); c.setdefault("name", name)
    return c

def owners(cfg):
    """WorkDir fragment -> session, in the ORDER written. First match wins, so put
    more specific fragments first. An unmatched path is UNATTRIBUTED, never guessed."""
    return list(cfg.get("owners", {}).items())


# What `/color` accepts. A value outside this set would be declared, never applied.
COLORS = ("red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan")

def colors(cfg):
    """Session name -> declared colour, from [colors]. Required for every member.

    Declared here rather than kept in a state-dir note because a `/clear` drops a
    session's agent-color record while keeping its name, so the transcript cannot
    be the source of truth for what the colour SHOULD be. Duplicates are allowed:
    the human chooses the colours, and two sessions may share one."""
    out = dict(cfg.get("colors", {}))
    bad = {k: v for k, v in out.items() if v not in COLORS}
    if bad:
        raise ConfigError("[colors] values not accepted by /color: "
                          + ", ".join(f"{k}={v!r}" for k, v in bad.items())
                          + f" (allowed: {', '.join(COLORS)})")
    return out

def brief_path(name):
    """Where a session's brief must be. Required for every member."""
    return os.path.join(config_dir(), "briefs", f"{name}.md")

def membership_problems(cfg, name, live_color=None, color_known=True):
    """What a fleet member is missing: [(kind, text, fix)]. Empty means complete.

    `live_color` is the session's current agent-color record (None if a /clear
    dropped it). Pass color_known=False when the caller cannot read it, so a
    missing record is not reported as a mismatch nobody can verify."""
    out = []
    if not os.path.isfile(brief_path(name)):
        out.append(("brief", f"no brief at {brief_path(name)}",
                    "write it from examples/brief.example.md"))
    want = colors(cfg).get(name)
    if not want:
        out.append(("color", "no [colors] entry in fleet.toml",
                    f'add  {name} = "<color>"  under [colors]'))
    elif color_known and live_color != want:
        out.append(("color", f"live colour {live_color or 'NONE'}, declared {want}",
                    f"type  /color {want}  in its pane (a session cannot set its own)"))
    return out

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

def stopped(cfg):
    """Session name -> {"state": "parked"|"retired", "uuid", "since", "note"},
    from [parked.<name>] and [retired.<name>].

    Parking and retiring are human decisions, so they are declared here. The
    resume uuid is what the declaration is ABOUT: restores refuse to relaunch that
    transcript. A later session that reuses the name has a different uuid and is
    unaffected -- names are reused, transcripts are not."""
    out = {}
    for state in ("parked", "retired"):
        for name, rec in cfg.get(state, {}).items():
            if not isinstance(rec, dict):
                raise ConfigError(f"[{state}.{name}] must be a table with uuid and since")
            uuid, since = rec.get("uuid", ""), rec.get("since", "")
            if not _UUID.fullmatch(str(uuid)):
                raise ConfigError(f"[{state}.{name}] uuid must be a full session uuid, got {uuid!r}")
            if not since:
                raise ConfigError(f"[{state}.{name}] needs since = \"YYYY-MM-DD\"")
            if name in out:
                raise ConfigError(f"{name!r} is both parked and retired")
            out[name] = {"state": state, "uuid": uuid, "since": str(since),
                         "note": rec.get("note", "")}
    return out

def stopped_uuids(cfg):
    """Resume uuid -> (name, state) for every parked or retired session."""
    return {v["uuid"]: (k, v["state"]) for k, v in stopped(cfg).items()}

def launch_env(cfg):
    """`KEY=val ...` prefix for launching a claude session, from [spawn].env.

    Every tool that launches or prints a launch command uses this, so a session
    comes back from a restore or an upgrade roll with the same environment it was
    spawned with. Until 2026-09-13 only fleetspawn set it: sessions rebuilt by
    fleetrestore ran without the notification flag and were silently silent."""
    import shlex
    env = cfg.get("spawn", {}).get("env", {})
    return " ".join(f"{k}={shlex.quote(str(v))}" for k, v in env.items())
