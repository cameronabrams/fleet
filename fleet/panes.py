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

BUSY_MARKER = "esc to interrupt"           # footer while a turn runs (2.1.285;
                                           # still present 2026-10-26 on 2.1.302)
TRUST_MARKERS = ("trust this folder", "Is this a project you created")
BACKGROUND_MARKER = "Background work is running"
PROMPT = "❯"                              # the input line, followed by a no-break space when empty (2.1.272)
# The status bar, BELOW the input line's closing rule: `⏵⏵ auto mode on ...`. Its
# middle slot reads `(shift+tab to cycle)` when the session holds nothing and
# `· N shell · ↓ to manage` while a shell the session started is still running.
# `· esc to interrupt` is appended to the SAME bar mid-turn. The two are
# independent -- one pane read mid-turn with a shell in its bar and then idle with
# the same shell a minute later (2026-10-26), so a session can hold both -- which
# is why the marker has to win (see `reconcile`).
#
# Matched only inside the bar, and only with the bar's own `·` separator, so that
# the phrase occurring in transcript text above cannot grant typeability. The
# background-TASK indicator (`⧉ <name>`, `⧉ 2`) is a DIFFERENT thing and does not
# make `claude agents` report busy: three panes carried one while reporting idle.
SHELL_IN_BAR = re.compile(r"·\s*(\d+)\s+shells?\b")
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
# recognized -- the whole fleet at once, with fleetsnap then snapshotting nothing
# over a good manifest. Measured rather than assumed: with the fallback removed
# before the panes were re-stamped, 0 of 14 sessions were recognized; with it, 14
# of 14. So: read both, re-stamp every pane, drop the fallback, unset the old
# option. This is the fourth step, and `@repo` is no longer read anywhere.
# The two pane options that say who a pane is: its agent's name, and which fleet
# that agent belongs to. Read together, in this order, because every caller needs
# both to answer "is this one of ours" -- and a caller that read only the first is
# what let a second fleet's sessions count as this one's.
#
# `@fleet` HELD A DIFFERENT MEANING BEFORE and was retired: it named a GROUP
# within one fleet, agreed with the window name only by accident -- seven of
# fourteen panes disagreed -- and described the screen rather than the fleet. It
# now names the fleet itself. Nothing carried the old value when the meaning
# changed (checked: zero panes on 2026-10-20), so no pane means two things at
# once; a reader of the old commits should know the word was reused.
LABELS = "#{@agent}\t#{@fleet}"
LABEL_FIELDS = 2          # how many columns LABELS occupies, for callers that split

def agent_label(agent):
    """A pane's agent name, from `@agent`."""
    return (agent or "").strip()

def fleet_label(fleet):
    """A pane's fleet, from `@fleet`, or "" when it carries none."""
    return (fleet or "").strip()


def belongs(fleet, ours):
    """Whether a pane labeled `fleet` is a member of the fleet named `ours`.

    Three cases:

    * labeled with OUR name -- ours.
    * labeled with ANOTHER name -- **not ours.** Positive evidence that somebody
      else's tools own that pane, and the whole point.
    * **unlabeled -- not ours either**, once we have a name of our own. A pane
      that no tool has stamped is a pane no tool is known to own, and the fleet
      that can name itself is the one that can say so.

    That last case was the opposite until 2026-10-20, and the order mattered more
    than the answer. When `@fleet` landed, ZERO panes carried it, so excluding the
    unlabeled would have emptied every tool at once -- `fleetsnap` seeing no
    fleet, `fleetupgrade` nothing to roll, `fleetretire` no such session. So the
    permissive answer shipped first, every pane was stamped, and the flip came
    after: 15 of 15 labeled and 0 unlabeled, checked against the CONFIGURED name
    rather than against each other, because agreeing panes still vanish if
    `[fleet].name` disagrees with all of them. A correct end state reached in the
    wrong order is an outage.

    With no name of our own, everything is ours: a fleet that has never been
    named cannot say which panes are not its own, and guessing in the excluding
    direction would hide real members. This is the one branch that still fails
    toward inclusion, and it is reachable only before `fleetinit` has run.
    """
    if not ours:
        return True
    return fleet_label(fleet) == ours


def ours_agent_pane(agent, fleet, ours):
    """Whether a pane is an agent pane AND one of ours: both labels, one answer.

    Tools that ACT on a pane -- restarting it, retiring it, typing into it,
    demanding a brief for it -- must ask both questions, and asking only the first
    is what let a second fleet's sessions count as this one's. `belongs` alone was
    wired into `fleetboard` and nowhere else for most of a day, which reads like
    the gap is closed while every tool that does something still cannot tell whose
    pane it is.
    """
    return is_agent_pane(agent) and belongs(fleet, ours)


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
            if p in ("38", "48", "58"):        # extended color: skip its arguments
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

def _input_block(lines):
    """(first, after) line indices of the input line and its closing rule, or None.

    The input line is a PROMPT line followed, after any wrapped continuation, by a
    rule; earlier prompt lines on screen are history, so the last such line wins.
    `input_line` reads what is inside the block and `status_bar` reads what is
    below it, and they share this so the two cannot disagree about where the
    block ended."""
    found = None
    for i, line in enumerate(lines):
        if not re.match(r"^\s*" + PROMPT, line):
            continue
        j = i + 1
        while j < len(lines) and not RULE.match(lines[j]):
            j += 1
        if j < len(lines):
            found = (i, j)
    return found

def input_line(text):
    """What the input line holds, whitespace-collapsed ("" when empty), or None if
    no input line is drawn. Dim text (a prompt suggestion) is not counted."""
    raw = text.splitlines()
    block = _input_block([strip_escapes(l) for l in raw])
    if block is None:
        return None
    i, j = block
    held = [undimmed(l) for l in raw[i:j]]
    held[0] = held[0].split(PROMPT, 1)[1] if PROMPT in held[0] else ""
    return " ".join(" ".join(held).split())

def status_bar(text):
    """The status bar below the input line, or None when no input line is drawn."""
    lines = [strip_escapes(l) for l in text.splitlines()]
    block = _input_block(lines)
    return None if block is None else "\n".join(lines[block[1] + 1:])

def shells_running(text):
    """How many background shells the status bar says the session is holding, or
    None when there is no bar to read. **Zero and None both mean "do not treat a
    busy status as explained"** -- the count only ever grants typeability, so an
    unreadable bar refuses, which is the direction this module fails in."""
    bar = status_bar(text)
    if bar is None:
        return None
    m = SHELL_IN_BAR.search(bar)
    return int(m.group(1)) if m else 0

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

def reconcile(screen, status, shells=None):
    """(state, disagreement or None) from the pane, `claude agents`' status, and
    the status bar's background-shell count (`shells_running`).

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
    busy: a moved busy marker looks like that, and acting on it types into a
    session mid-turn. Both directions resolve to busy -- never typing is the safe
    error -- but a caller that hides the disagreement turns a moved marker into
    silence, which is how this repository's worst bugs have all read.

    A MOVED MARKER IS NOT THE ONLY CAUSE, and until 2026-10-26 this said it was.
    `claude agents` reports a session that is sitting at its prompt with a
    background shell still running as `busy`, identically to one that is mid-turn:
    measured across every labeled pane on 2026-10-26 (2.1.302 and 2.1.308), the
    three sessions reporting busy with an idle screen were exactly the three whose
    status bar carried a live shell, and the two reporting busy with a busy screen
    were exactly the two with none -- and the marker was present in both of those.
    Nothing in the agent JSON separates the two; `pid`, `kind` and `status` are
    identical, and the child processes are not a discriminator either (a mid-turn
    Bash tool call and a detached background shell are both a `bash` child).

    So this disagreement is PERSISTENT for a session that runs long background
    work, not the transient skew the branch was written for. A watcher whose whole
    job is a long shell reports busy for that shell's entire life, and a caller
    that resolves the disagreement to busy never reaches it at all.
    `fleetnudge` already held the rule that covers the case -- a session at its
    prompt holding runtime is typeable -- but keyed it on the statuses `shell` and
    `monitor`, which this version does not emit for it. So `shells` resolves the
    disagreement where the status cannot: an idle screen whose busy status is
    accounted for by a shell in the bar is TYPEABLE, and the explanation is
    returned so the delivery records why it went ahead.

    Three things keep that from becoming the thing this module exists to prevent.
    The marker wins: `screen` is only "idle" when `BUSY_MARKER` appears nowhere on
    the pane, so a session that is mid-turn AND holding a shell -- a state one pane
    passed through on 2026-10-26 -- resolves to busy before the count is
    consulted. The count only
    ever grants, never withholds. And `shells` defaults to None, so a caller that
    has not been taught to read the bar gets the old, refusing answer rather than
    a permissive one."""
    # Belt and braces: only "idle" and "busy" are reconciled below, so any other
    # screen state would fall through to the same answer. Removing this line
    # changes nothing TODAY -- proved by breaking it -- and it is kept so that a
    # branch added later cannot start overriding a state the status cannot see.
    if screen in SCREEN_ONLY or status is None:
        return screen, None
    reported_busy = status in BUSY_STATUSES
    if screen == "idle" and reported_busy:
        if shells:
            return "idle", (f"the session reports {status!r} because it is at its prompt "
                            f"holding {shells} background shell{'s' if shells != 1 else ''}; "
                            f"the pane itself is idle")
        return "busy", (f"the pane reads idle but the session reports {status!r} -- "
                        f"the status bar shows no background shell to account for it, "
                        f"so the busy marker may have moved")
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
