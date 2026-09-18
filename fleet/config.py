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
                         "note": rec.get("note", ""), "group": rec.get("group", ""),
                         "cwd": os.path.expanduser(rec.get("cwd", "")) if rec.get("cwd") else ""}
    return out

def stopped_uuids(cfg):
    """Resume uuid -> (name, state) for every parked or retired session."""
    return {v["uuid"]: (k, v["state"]) for k, v in stopped(cfg).items()}

def display_zone(cfg):
    """(zone name, where it came from) for showing times to the human.

    [human] timezone_file names a file holding the human's CURRENT zone, re-read on
    every run, for a human who travels; [human] timezone is a fixed zone. The file
    wins when it is readable and names a real zone. Otherwise UTC -- and the caller
    must label it, because an unlabelled time in the wrong zone reads as right."""
    from zoneinfo import ZoneInfo
    human = cfg.get("human", {})
    tried = []
    f = human.get("timezone_file")
    if f:
        path = os.path.expanduser(f)
        try:
            z = open(path).read().strip()
            ZoneInfo(z)
            return z, f"from {f}"
        except Exception as e:
            tried.append(f"{f}: {type(e).__name__}")
    z = human.get("timezone")
    if z:
        try:
            ZoneInfo(z)
            return z, "[human] timezone" + (f" ({'; '.join(tried)})" if tried else "")
        except Exception as e:
            tried.append(f"timezone {z!r}: {type(e).__name__}")
    return "UTC", "no usable [human] timezone" + (f" ({'; '.join(tried)})" if tried else "")

def events(tz):
    """Declared fleet events from <config>/events.toml: [(epoch, label, detail, has_time)].

    [[event]] date = "YYYY-MM-DD", time = "HH:MM" (optional), label, detail
    (optional). Times are in `tz`, the display zone. A date without a time is kept
    as a date: has_time False, epoch at that day's start."""
    import datetime
    from zoneinfo import ZoneInfo
    path = os.path.join(config_dir(), "events.toml")
    if not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        data = tomllib.load(f)
    out = []
    for i, e in enumerate(data.get("event", [])):
        try:
            day = datetime.date.fromisoformat(str(e["date"]))
            label = str(e["label"])
        except (KeyError, ValueError) as err:
            raise ConfigError(f"events.toml event {i + 1}: needs date = \"YYYY-MM-DD\" and label ({err})")
        t = str(e.get("time", "")).strip()
        hh, mm = (0, 0)
        if t:
            try:
                hh, mm = (int(x) for x in t.split(":"))
            except ValueError:
                raise ConfigError(f"events.toml event {i + 1}: time must be HH:MM, got {t!r}")
        when = datetime.datetime(day.year, day.month, day.day, hh, mm, tzinfo=ZoneInfo(tz))
        out.append((when.timestamp(), label, str(e.get("detail", "")), bool(t)))
    return sorted(out)

CONTEXT_DEFAULTS = {
    "compact_above": 250_000,
    "clear_above": 500_000,
    "idle_minutes": 10,
    "compact_focus": "keep job ids, file paths, open decisions and commitments",
}

def context(cfg):
    """[context]: when fleetcontext recommends trimming a session, and what every
    /compact it types asks the summary to keep. Defaults apply per key."""
    raw = cfg.get("context", {})
    unknown = sorted(set(raw) - set(CONTEXT_DEFAULTS))
    if unknown:
        raise ConfigError(f"[context] unknown key(s): {', '.join(unknown)} "
                          f"(known: {', '.join(CONTEXT_DEFAULTS)})")
    out = dict(CONTEXT_DEFAULTS, **raw)
    for k in ("compact_above", "clear_above", "idle_minutes"):
        if not isinstance(out[k], int) or isinstance(out[k], bool) or out[k] < 0:
            raise ConfigError(f"[context] {k} must be a non-negative integer, got {out[k]!r}")
    if out["clear_above"] < out["compact_above"]:
        raise ConfigError("[context] clear_above must not be below compact_above")
    focus = out["compact_focus"]
    if not isinstance(focus, str) or "\n" in focus:
        raise ConfigError("[context] compact_focus must be one line of text")
    return out

def notify(cfg):
    """[notify]: where a tool sends a phone push when it could not reach a session.

    ntfy_topic_file names a file holding the topic -- either the topic alone, or a
    shell script with a TOPIC="..." line, so an existing notification hook can stay
    the one place the topic is written. mute_file, when it exists, silences the push
    (the tool still says it did not deliver). Returns {} when unconfigured."""
    raw = cfg.get("notify", {})
    known = {"ntfy_server", "ntfy_topic_file", "mute_file"}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ConfigError(f"[notify] unknown key(s): {', '.join(unknown)} (known: {', '.join(sorted(known))})")
    if not raw:
        return {}
    out = {"ntfy_server": str(raw.get("ntfy_server", "https://ntfy.sh")).rstrip("/"),
           "ntfy_topic_file": os.path.expanduser(raw.get("ntfy_topic_file", "")),
           "mute_file": os.path.expanduser(raw.get("mute_file", ""))}
    if not out["ntfy_topic_file"]:
        raise ConfigError("[notify] needs ntfy_topic_file")
    return out

def ntfy_topic(path):
    """The topic in `path` (see notify()), or None if it cannot be read."""
    try:
        with open(path, errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    m = re.search(r'^\s*TOPIC\s*=\s*["\']?([A-Za-z0-9_-]+)', text, re.M)
    if m:
        return m.group(1)
    first = next((l.strip() for l in text.splitlines() if l.strip()), "")
    return first if re.fullmatch(r"[A-Za-z0-9_-]+", first) else None

def mail(cfg):
    """[mail]: this fleet's name in a shared mailbox, and where that mailbox lives.

    `fleet` is the namespace addresses use (`abrams/coord`), because two fleets both
    have a `coord`. `repo` is any git URL or path; `clone` is the working copy, under
    the state dir by default -- observed state, not a declaration. Returns {} when
    unconfigured, so a fleet with no correspondents needs no section."""
    raw = cfg.get("mail", {})
    known = {"fleet", "repo", "clone"}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ConfigError(f"[mail] unknown key(s): {', '.join(unknown)} (known: {', '.join(sorted(known))})")
    if not raw:
        return {}
    for k in ("fleet", "repo"):
        if not raw.get(k):
            raise ConfigError(f"[mail] needs {k}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", str(raw["fleet"])):
        raise ConfigError(f"[mail] fleet must be a short lowercase name, got {raw['fleet']!r}")
    return {"fleet": str(raw["fleet"]), "repo": os.path.expanduser(str(raw["repo"])),
            "clone": os.path.expanduser(str(raw.get("clone")
                                            or os.path.join(state_dir(cfg), "mailbox")))}

def launch_env(cfg):
    """`KEY=val ...` prefix for launching a claude session, from [spawn].env.

    Every tool that launches or prints a launch command uses this, so a session
    comes back from a restore or an upgrade roll with the same environment it was
    spawned with. Until 2026-09-13 only fleetspawn set it: sessions rebuilt by
    fleetrestore ran without the notification flag and were silently silent."""
    import shlex
    env = cfg.get("spawn", {}).get("env", {})
    return " ".join(f"{k}={shlex.quote(str(v))}" for k, v in env.items())
