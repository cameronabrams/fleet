"""Reading a Claude Code pane, and typing one line into it safely.

Shared by fleetcontext and fleetnudge, so "is this pane idle" and "did the typed
line arrive intact" have one answer. Nothing here calls tmux itself: the caller
passes its own `tmux` function, which is what the tools' tests replace.

Capture panes with `capture-pane -p -e` (CAPTURE). Claude Code draws a prompt
suggestion in an empty input line as DIM text (SGR 2), and a plain capture drops
that attribute, so a suggestion read exactly like a draft the human had typed
(OBSERVED 2026-09-17 in four panes; the 2026-09-16 "draft" in one pane was one).
Typed text is drawn without the dim attribute (checked 2026-09-17 by typing into
a pane: `❯\xa0\x1b[39mzq`). So dim text in the input line is not a draft.
"""
import re
import time

BUSY_MARKER = "esc to interrupt"           # footer while a turn runs (2.1.285)
TRUST_MARKERS = ("trust this folder", "Is this a project you created")
BACKGROUND_MARKER = "Background work is running"
PROMPT = "❯"                              # the input line, followed by a no-break space when empty (2.1.272)
RULE = re.compile(r"^\s*─{3,}")           # the rules drawn above and below the input line
TYPE_WAIT = 10.0                           # seconds for typed text to reach the input line
CAPTURE = ("capture-pane", "-p", "-e")     # -e keeps the attributes that mark a suggestion
_ESC = re.compile(r"\x1b\[([0-9;:]*)([A-Za-z])|\x1b[^\[]")

# The pane option that says a pane is an agent's: `@agent`, the session's name.
# Put this in a tool's `list-panes -F` and pass the field to `agent_label`.
#
# It was `@repo` until 2026-10-01, and the rename could not be done in one step:
# the label lives in tmux runtime state, not in this repository, so the moment the
# code stopped reading `@repo` every pane still carrying it would stop being
# recognised -- the whole fleet at once, with fleetsnap then snapshotting nothing
# over a good manifest. Measured rather than assumed: with the fallback removed
# before the panes were re-stamped, 0 of 14 sessions were recognised; with it, 14
# of 14. So: read both, re-stamp every pane, drop the fallback, unset the old
# option. This is the fourth step, and `@repo` is no longer read anywhere.
LABELS = "#{@agent}"

def agent_label(agent):
    """A pane's agent name, from `@agent`."""
    return (agent or "").strip()

def is_agent_pane(agent):
    """Whether a pane belongs to an agent: does it carry a name.

    Succeeds `in_fleet`, which also took `@fleet`. That grouping is retired --
    there is one fleet, and `@fleet` agreed with the window name only by accident:
    seven of fourteen panes disagreed, six of them because one group had outgrown
    any single window. A group that cannot fit the thing it is named after was
    not describing the fleet, it was describing the screen.

    `tmux list-panes -a` still crosses tmux SESSIONS, so this check still earns its
    keep -- it is what keeps the owner's own windows out of the fleet's tools. On
    2026-09-26 one of the owner's own windows landed in fleetupgrade's count and
    got a restart plan with `CCP_AGENT=1` prepended -- the flag that makes a
    session an addressable agent. The plan asserted an environment it had never
    observed."""
    return bool(agent_label(agent))

def strip_escapes(text):
    """`text` without terminal escape sequences."""
    return _ESC.sub("", text)

def undimmed(line):
    """The characters of `line` not drawn dim, escapes removed. SGR 2 sets dim;
    0 (or empty), 22 and a bare reset clear it."""
    out, dim, pos = [], False, 0
    for m in _ESC.finditer(line):
        if not dim:
            out.append(line[pos:m.start()])
        pos = m.end()
        if m.group(2) != "m":
            continue
        params = (m.group(1) or "0").replace(":", ";").split(";")
        i = 0
        while i < len(params):
            p = params[i] or "0"
            if p in ("38", "48", "58"):        # extended colour: skip its arguments
                i += 3 if params[i + 1:i + 2] == ["5"] else 5
                continue
            if p in ("0", "22"):
                dim = False
            elif p == "2":
                dim = True
            i += 1
    if not dim:
        out.append(line[pos:])
    return "".join(out)

def input_line(text):
    """What the input line holds, whitespace-collapsed ("" when empty), or None if
    no input line is drawn. The input line is a PROMPT line followed, after any
    wrapped continuation, by a rule; earlier prompt lines on screen are history,
    so the last such line wins. Dim text (a prompt suggestion) is not counted."""
    raw = text.splitlines()
    lines = [strip_escapes(l) for l in raw]
    found = None
    for i, line in enumerate(lines):
        if not re.match(r"^\s*" + PROMPT, line):
            continue
        j = i + 1
        while j < len(lines) and not RULE.match(lines[j]):
            j += 1
        if j < len(lines):
            held = [undimmed(l) for l in raw[i:j]]
            held[0] = held[0].split(PROMPT, 1)[1] if PROMPT in held[0] else ""
            found = " ".join(held)
    return None if found is None else " ".join(found.split())

def screen_state(text):
    """idle, busy, trust, dialog, input (text already typed) or no-prompt."""
    plain = strip_escapes(text)
    if any(m in plain for m in TRUST_MARKERS):
        return "trust"
    if BACKGROUND_MARKER in plain:
        return "dialog"
    if BUSY_MARKER in plain:
        return "busy"
    held = input_line(text)
    if held is None:
        return "no-prompt"
    return "input" if held else "idle"

# `claude agents` reports these while a session cannot take a typed line.
# fleetnudge counted "waiting" and fleetcontext did not, so the two tools
# disagreed about what busy means; this is the superset, which is the safe one.
BUSY_STATUSES = ("busy", "waiting")

# States only the SCREEN can report: `claude agents` has no idea a folder-trust
# prompt, a background-work dialog or a half-typed draft is on the pane.
SCREEN_ONLY = ("trust", "dialog", "input", "no-prompt", "no-pane")

def reconcile(screen, status):
    """(state, disagreement or None) from the pane and `claude agents`' status.

    The screen is a parse of a TUI that moves. `BUSY_MARKER` and `PROMPT` each
    carry the version they were last checked against, and they carry DIFFERENT
    versions because they were re-checked separately after moving. A dim prompt
    suggestion once read as a human's draft in four panes (2026-09-17), which made
    fleetnudge decline to type into sessions that were in fact idle.

    The structured status cannot replace the screen -- it cannot see a trust
    prompt, a dialog or a draft -- but where both can answer, it is the one that
    does not depend on how a frame was drawn. So the structured source decides
    busy-vs-idle, the screen decides what only it can see, and a disagreement is
    RETURNED rather than resolved quietly.

    The dangerous direction is a screen that reads idle while the session reports
    busy: that is what a moved busy marker looks like, and acting on it types into
    a session mid-turn. Both directions resolve to busy -- never typing is the
    safe error -- but a caller that hides the disagreement turns a moved marker
    into silence, which is how this repository's worst bugs have all read."""
    # Belt and braces: only "idle" and "busy" are reconciled below, so any other
    # screen state would fall through to the same answer. Removing this line
    # changes nothing TODAY -- proved by breaking it -- and it is kept so that a
    # branch added later cannot start overriding a state the status cannot see.
    if screen in SCREEN_ONLY or status is None:
        return screen, None
    reported_busy = status in BUSY_STATUSES
    if screen == "idle" and reported_busy:
        return "busy", (f"the pane reads idle but the session reports {status!r} -- "
                        f"the busy marker may have moved")
    if screen == "busy" and not reported_busy:
        return "busy", (f"the pane reads busy but the session reports {status!r} -- "
                        f"one of the two is stale")
    return screen, None

def state_problem(state, name, pane):
    """Why a pane in `state` must not be typed into, or None when it is idle."""
    return {
        "trust": f"pane {pane} shows the folder-trust prompt",
        "dialog": f"pane {pane} shows the background-work dialog",
        "busy": f"{name} is mid-turn; wait until it is idle",
        "input": (f"the input line in {pane} already holds text (a draft, or a dialog); "
                  f"typing would add to it"),
        "no-prompt": f"pane {pane} shows no input line (a dialog or a menu?)",
        "no-pane": "no tmux pane shows this session",
    }.get(state)

def send_text(tmux, pane, text):
    """Type `text` literally, including a trailing ';'.

    tmux reads a ';' at the END of a send-keys argument as its own command
    separator and drops it -- OBSERVED 2026-09-17: "trail;" arrived as "trail",
    and a watcher line ending ";" failed its readback in production. A ';'
    anywhere else is safe. So the trailing ones go as key codes instead."""
    head = text.rstrip(";")
    if head:
        tmux("send-keys", "-t", pane, "-l", head)
    for _ in range(len(text) - len(head)):
        tmux("send-keys", "-t", pane, "-H", "3b")

def squashed(text):
    """`text` with all whitespace removed. What the input line reads back is
    compared this way because a line wrapped mid-word gains a space at the wrap."""
    return "".join(text.split())

def clear_input(tmux, pane):
    """Empty the input line. Returns True if it is empty afterwards.

    C-u alone is not enough: on a wrapped, multi-line input it leaves earlier
    lines behind (OBSERVED 2026-09-17), and the next thing typed is appended to
    them."""
    tmux("send-keys", "-t", pane, "C-u")
    for _ in range(4):
        time.sleep(0.5)
        held = input_line(tmux(*CAPTURE, "-t", pane)[1])
        if not held:
            return True
        tmux("send-keys", "-t", pane, "-N", str(len(held) + 50), "BSpace")
    return not input_line(tmux(*CAPTURE, "-t", pane)[1])

def type_line(tmux, pane, line, wait=TYPE_WAIT):
    """Type `line` without Enter and confirm the input line holds exactly it.
    Returns None, or the reason it did not (the input line is then cleared)."""
    send_text(tmux, pane, line)
    want = squashed(line)
    t_end = time.time() + wait
    while time.time() < t_end:
        time.sleep(0.5)
        if squashed(input_line(tmux(*CAPTURE, "-t", pane)[1]) or "") == want:
            return None
    cleared = clear_input(tmux, pane)
    return (f"the input line in {pane} did not read exactly {line!r} within {wait:.0f}s "
            f"(a terminal reply can corrupt keys); "
            + ("cleared it and stopped" if cleared
               else "AND COULD NOT BE CLEARED -- look at the pane"))
