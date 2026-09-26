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

BUSY_MARKER = "esc to interrupt"           # footer while a turn runs (2.1.270)
TRUST_MARKERS = ("trust this folder", "Is this a project you created")
BACKGROUND_MARKER = "Background work is running"
PROMPT = "❯"                              # the input line, followed by a no-break space when empty (2.1.272)
RULE = re.compile(r"^\s*─{3,}")           # the rules drawn above and below the input line
TYPE_WAIT = 10.0                           # seconds for typed text to reach the input line
CAPTURE = ("capture-pane", "-p", "-e")     # -e keeps the attributes that mark a suggestion
_ESC = re.compile(r"\x1b\[([0-9;:]*)([A-Za-z])|\x1b[^\[]")

def in_fleet(repo_label, fleet_label):
    """Whether a pane belongs to this fleet, from the labels `fleetspawn` stamps.

    `tmux list-panes -a` crosses tmux SESSIONS, so it returns every pane on the
    server -- the human's own windows included. On 2026-09-26 that put a personal
    session into `fleetupgrade`'s count ("3 of 12 sessions stale") and produced a
    restart plan for it with `CCP_AGENT=1` prepended from `[spawn].env`: the flag
    that makes a session an addressable agent. Following that plan would not have
    restored what was running, it would have changed what it was. The plan
    asserted an environment it never observed.

    `fleetspawn` sets BOTH `@repo` and `@fleet` on every pane it creates, and
    `fleetsnap` already reads `@fleet` as membership. Either is enough here:
    requiring both would drop a pane someone relabelled by hand.

    Callers must REPORT what they exclude. A fleet pane that lost its labels
    would otherwise vanish from a roll with no warning, which trades a stranger's
    pane being included for one of ours being silently skipped -- the worse
    direction of the two."""
    return bool((repo_label or "").strip() or (fleet_label or "").strip())

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
