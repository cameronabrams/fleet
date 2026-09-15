---
name: fleet-upgrade
description: Roll agent sessions onto a newer claude binary without losing their context or silently killing their monitors. Use when the user says sessions are nagging about an update, asks to upgrade/restart the fleet, or asks which sessions are on an old version. Also use before any deliberate fleet-wide restart. Triggers on "update the binary", "restart the fleet", "upgrade the agents", "everyone wants to update", "which sessions are stale".
---

# Rolling a fleet upgrade

A restart is **cheap for context and expensive for runtime**. `--resume <uuid>`
keeps the whole transcript. It does not keep Monitors, background jobs, or
cross-session subscriptions — and the resumed transcript still shows the session
creating them, with no seam, so **the session cannot tell from inside that they
are gone**. That asymmetry is the whole reason this skill exists.

Never restart a session on a hunch that it "probably needs it". Measure.

## 1. Measure first

    fleetupgrade

Reports every session: pane, running version, whether it is stale, whether it has
a re-arm ledger, and its resume UUID. It restarts nothing.

**If nothing is stale, say so and stop.** The most common right answer is "do not
restart anything" — sessions ask for updates far more often than they need them,
and the ask is not evidence.

**Names come from transcripts; `ListAgents` is the authority.** Reconcile before
acting. A tmux pane title is not a session name — it outlives whoever set it, so
a relaunched pane can advertise its predecessor's name indefinitely. The tool
prefers each session's own `agent-name` record and warns when the title differs,
but if it reports a name `ListAgents` does not, believe `ListAgents`.

**`/rename <name>` renames a running session in place** — no restart, no context
loss, and it writes a durable `agent-name` record that survives later `-c` and
`--resume`. If the only thing wrong with a session is its name, use `/rename`;
do not restart it. A session cannot rename itself on request.

Check the UUID confidence lines it prints. Two sessions sharing a working
directory cannot be told apart by scratchpad, only by their `agent-name` record;
the tool handles this but flags it. **Never restart against an UNVERIFIED uuid** —
resuming one session into another's history is the exact failure this fleet has
already produced once.

## 2. Ask before you kill

For each stale session, in the order `fleetupgrade` prints (coord last):

**a. Read the status word correctly — this is easy to get backwards.**
`ListAgents` states are not all "come back later":

| state | meaning | action |
| :--- | :--- | :--- |
| `idle` | at its prompt, nothing held | restart it |
| `busy` | mid-turn | wait, come back |
| `waiting` | blocked on the human | ask the human before touching it |
| `shell`, `monitor` | **holds runtime**, at its prompt | **restart it — this is the case the skill exists for** |

`shell` and `monitor` are the *opposite* of a reason to skip. They name what the
session is holding, and the pane footer spells it out (`1 shell`, `1 monitor`).
On 2026-08-27 this skill's first real run skipped exactly those two sessions on a
misreading of the word, leaving the only two with live runtime un-upgraded.

**b. Does it hold runtime state?** If its ledger says MISSING, message it (keep
under 800 chars, per `~/.local/state/fleet/comms.md`):

> Upgrade to <version> pending for you. Before I restart you: do you hold any
> Monitor, background job, setsid'd process, or cross-session subscription? If
> yes, write how to re-arm each one to
> `~/.local/state/fleet/rearm/<your-name>.md` as imperatives ("re-arm X"), not
> as description ("X is running"), and tell me when it is there. If you hold
> none, say so and I will restart you now.

Wait for the answer. A session that reports none needs no ledger. **Do not
restart a session that has said it holds monitors until its ledger exists** —
re-run `fleetupgrade` to confirm the file, do not take its word.

**c. Check for detached work you would orphan.** Children of the session die
with it; `setsid`'d work does not. Confirm which:

    pgrep -P <claude-pid>          # children: these die
    ps -o pid,ppid,etime,args -p <pid-of-any-long-run>   # reparented to init or a user systemd: survives

## 3. Restart, one at a time

    tmux send-keys -t <pane> '/exit' Enter
    # ALWAYS verify it is gone before relaunching. Never chain these.
    [ -d /proc/<pid> ] && echo STILL ALIVE || echo exited
    tmux send-keys -t <pane> 'claude --name <name> --resume <uuid>' Enter

If the pid is STILL ALIVE, **stop and look at the pane** — do not resend `/exit`
and do not send the relaunch, which would be typed into a live session as a
prompt:

    tmux capture-pane -p -t <pane> | tail -12

### The background-work prompt

A session holding runtime does not exit on `/exit`. It raises:

    Background work is running
    The following will stop when you exit:
      <shell|monitor> · <description>
      1. Exit and stop tasks
      2. Move to background and exit
      3. Stay

Option 1 is preselected; `Enter` takes it. `Down` then `Enter` takes option 2.

**Choosing between 1 and 2 is a judgement call, and they are not interchangeable:**

- **Option 2 (background) when the work should outlive the session and nothing
  will re-create it** — a wait-loop whose only remaining job is to write a result
  to a log, a job already finished that just needs to record it. It reparents to
  systemd and survives. Then tell the session **not** to re-arm it.
- **Option 1 (stop) when the session's ledger says it will re-arm that item.**
  Backgrounding it there leaves the old watcher running *and* a freshly armed one
  — two monitors on the same job, which is worse than none because they disagree.

Decide per item by reading the ledger first, not per session.

**Before choosing option 2, check that the thing can actually finish.** A waiter
written as

    until ! pgrep -f "python -m pytest tests/unit" >/dev/null; do sleep 30; done

matches its own `bash -c` cmdline, so the condition never goes false and the loop
is immortal. Backgrounding that reparents a spinner to systemd forever. On this
skill's first run it ran 53 minutes past the job it watched and had to be killed
by pid. **Read the waiter's command before backgrounding it**; if it waits on a
*pattern* rather than a pid, take option 1 instead — a clean stop, because the
log already holds the result.

Correct form to wait on: `until ! kill -0 <pid> 2>/dev/null; do sleep 30; done`.

After option 1, confirm the work actually stopped; after option 2, confirm it
survived and note its new parent:

    ps -eo pid,ppid,etime,args --no-headers | grep '[w]atcher-name'

Use a bracketed pattern. A plain `pgrep -f name` inside `$(...)` matches the
subshell running the check and reports a stopped process as running — that
happened on this skill's first run.

Then confirm it came back: new pid under the pane, and `ListAgents` shows the
name. **Do not batch this.** One session at a time, verified up before the next,
so monitoring gaps do not overlap.

### A persistent Monitor is not persistent (2.1.272)

REPORTED by a sweep session and VERIFIED by a production session, 2026-09-15: a Monitor
armed with `persistent: true` now says "expires in 30m unless the source ends first". A
watcher built on one goes DEAD after 30 minutes on a longer job, and `fleetwatch` will
say so — that is the registry working. For a job that outlives 30 minutes, either re-arm
at expiry (and re-register the new pid), or run the watcher outside the session (a
`setsid` loop or a transient `systemd-run --user` unit logging to a file) and register
that pid. Re-check this on each new binary; it may change again.

### Run `fleetwatch` first — DERIVE the inventory, do not read it

    fleetwatch

**Do this before consulting any ledger.** Since 2026-09-12 it is
registry-authoritative: a job counts as watched **iff a registered pid is alive**
(`fleetregister <session> <job> <pid>` at arm time), never because a cmdline
mentions the job id. Inference is advisory only. An unregistered watcher reads as
UNWATCHED — deliberately the safe direction, since that raises an alarm rather
than silencing one. It derives, from live SLURM state and
the local process tree, which cluster work has a watcher and which does not, and
which watchers point at work that is already gone. It needs no session's
cooperation and cannot go stale, because it is computed at the moment you ask.

Between 2026-09-04 and 2026-09-11 a ledger was wrong **five times in eight days**
— in three distinct ways — and every one was caught by an external check rather
than by the ledger working. The reason is structural: **a ledger is a second copy
of state kept by hand, so it inherits the very defect it exists to fix.** A
session cannot tell from inside that its ledger is stale for the same reason it
cannot tell its monitors are gone.

**The case only derivation catches:** work that was never watched at all. No
ledger design finds it, because you cannot record the monitor you forgot to
create. Found twice — 2026-09-10, and 2026-09-11 on `fleetwatch`'s first run.

**So split the two kinds of content and trust them differently:**

| content | where it belongs | why |
| :--- | :--- | :--- |
| the INVENTORY — what is armed right now | **derive it** (`fleetwatch`) | recomputable, and it rots if written down |
| the RECIPE — the actual poll loop to re-arm | the ledger | not recoverable from a dead process |
| the RATIONALE — why this campaign matters | the ledger | not recoverable from anything |

Use the ledger for the bottom two rows. Treat its inventory claims as a *claim to
be tested against `fleetwatch`*, never as the answer.

### Stale ledgers rot in BOTH directions — check state against ledger, both ways

| ledger says | session actually | consequence if you trust the ledger |
| :--- | :--- | :--- |
| "re-arm X" | holds nothing | it arms a watcher on finished work — noisy, wasteful |
| **"nothing held"** | **holds a monitor** | **the watcher dies and NOBODY re-arms it — silent** |

**The second is the dangerous one and this skill documented only the first.**
Seen 2026-09-10: a study session's ledger (a day old) said "Re-arm nothing.
This session holds no runtime" and "every array is finished and pulled", while
`ListAgents` showed it holding a shell — the monitor on an array which
`sacct` reported as **64/64 RUNNING**. Restarting on that ledger would have left
a live 64-task array unwatched with nothing to indicate it.

**So compare in both directions before every restart:**

    ListAgents state   ->  shell/monitor means runtime IS held
    the ledger         ->  does it name that runtime?

A mismatch either way is a stop. **`idle` + "re-arm X"** → tell it not to re-arm
and to fix the file. **`shell`/`monitor` + "nothing held"** → make it write the
ledger BEFORE you restart it, per step 2b.

### Stale ledgers: check what the ledger WATCHES, not just that it exists

`fleetupgrade`'s LEDGER column says a file exists, not that it is true. On
2026-09-07 two ledgers dated two days earlier both said RE-ARM, while
`ListAgents` showed both sessions `idle` — because the jobs they watched had
finished and the monitors had exited on their own.

**When a ledger says re-arm but the session holds no runtime, resolve the
contradiction before restarting.** Check the watched work directly (`sacct`,
the log, the pid). Then tell the session explicitly NOT to re-arm, and to fix
the ledger — otherwise it will faithfully arm a watcher on finished work.

A re-arm ledger is **runtime state, not a task list**: when the runtime it names
ends, the entry is *wrong*, not merely complete.

**Why it rots silently** (raised by a production session, 2026-09-07): *a monitor that exits on
its own leaves no trace in the file*, so the ledger cannot age correctly by
itself. Arming writes an entry; finishing writes nothing. The asymmetry means an
entry naming a runtime **must be deleted or rewritten by whoever observes that
runtime end** — and if nobody does, the next restart reads a finished job as a
live instruction.

A ledger that mixes "re-arm X" with "the human owes a decision on Y" invites the
same conflation from the other side; keep open decisions in a separate section.

### `/exit` can move a session to the background instead of stopping it

OBSERVED 2026-09-15 on 2.1.272, on a session with Artifact comment auto-replies armed,
and with no background-work dialog shown. The pane printed:

    Moving to background…
    backgrounded · b20bc72b
      claude attach b20bc72b    open in this terminal

The pid exited — and a fork carried on under a **new pid and session id**
(`--session-id <new> --fork-session --resume <old transcript>`), still replying, still
holding its watcher. **"The pid is gone" is not "the session stopped."** Relaunching
`claude --resume <old uuid>` there would start a second live session on a forked history.

So after `/exit`, before relaunching anything:

    tmux capture-pane -p -t <pane> | grep -E 'backgrounded ·|Moving to background'
    claude agents --json        # a `kind: background` entry with the session's name?

Either one means **stop**: reattach with `claude attach <id>` in the pane and decide with
the human what to do with it — do not relaunch from the plan. `fleetupgrade` resolves a
pane running `claude attach <id>` through `claude agents --json`, flags it as a
background session, and leaves it out of the plan; it also lists background sessions
that no pane shows. `fleetretire` stops with exit 3 when this happens and leaves the
ledger unchanged.

### Escape sequences can corrupt `tmux send-keys '/exit' Enter`

Seen 2026-09-07: a session received `8;32;42;52c/exit` — a terminal
device-attributes reply concatenated onto the command — which ran as a *prompt*
instead of exiting, and the session started a turn on garbage.

**Send the text and the Enter as separate calls, and capture the screen in
between:**

    tmux send-keys -t <pane> '/exit'          # no Enter
    tmux capture-pane -p -t <pane> | grep -E '❯\s*/exit\s*$'   # the input line reads exactly "/exit"
    tmux send-keys -t <pane> Enter

Search the whole screen, not a fixed row: typing `/exit` opens the slash-command menu,
which pushes the input line up. The prompt glyph can be followed by a non-breaking
space. And wait for the echo — a busy pane took ~3 s to show typed text (2026-09-15);
1.5 s missed it.

To recover: `Escape` to interrupt the turn, `C-u` to clear the input line,
confirm the box is empty, then retype. Do not send `/exit` again on top of a
dirty line.

### The resume-mode prompt — a relaunch can stall without failing

Seen 2026-09-03 on the 2.1.259 -> 2.1.260 roll. A large session (5 h 35 m,
121.6k tokens) came back with:

    This session is 5h 35m old and 121.6k tokens.
    Resuming the full session will consume a substantial portion of
    your usage limits. We recommend resuming from a summary.

      1. Resume from summary (recommended)
      2. Resume full session as-is
      3. Don't ask me again

**`fleetupgrade` reported that session as 2.1.260 and NOT stale while it sat
here.** The binary had started and answers `--version`; the transcript had not
loaded. So *"the version updated"* is not evidence the session is back —
**confirm with `ListAgents` state or the pane footer showing the session name**,
never with the version column alone. Only one of eight hit it; small sessions
resumed straight through, so a roll can look complete while one session is parked.

**Option 1 is preselected and it is LOSSY** — it compacts, which is the context
loss `--resume` exists to avoid, and it is the opposite of what this skill is
for. Do not press Enter reflexively. But option 2 spends real usage on reload,
and token spend is the human's to weigh, so on a large session **ask the human**
rather than choosing for them. `Down` then `Enter` takes option 2;
verify the caret moved before confirming.

A session parked here holds no runtime and loses nothing by waiting, so there is
no rush to answer.

`--name` is belt-and-braces: a name already set persists through `-c` and
`--resume` via the session's `agent-name` record. Passing it again costs nothing
and protects a session that never had one.

**Never `/clear` as part of an upgrade.** `/clear` rolls the transcript to a new
file and drops the context you just preserved. `--resume` alone continues in
place.

## 4. Hand back the ledger

Once a session with a ledger is up, tell it to act on it:

> Back up on <version>. Your runtime did not survive: re-arm from
> `~/.local/state/fleet/rearm/<name>.md`, then confirm what you re-armed.

If you took option 2 for an item, say so explicitly and tell it **not** to re-arm
that one, with the pid it now runs under. A session cannot see that its watcher
survived, so silence here produces a duplicate.

Then verify it actually did before moving on. "I re-armed it" from a session that
cannot observe its own restart is a claim, not a fact — where the monitor's effect
is observable (a file being written, a job being polled), check that instead.

## 5. coord goes last, and cannot do itself

Restarting `coord` kills the session running this skill. Do the other sessions
first, then hand the human the command. Do not send `/exit` to your own pane.

**The hand-off is not optional and it is easy to skip.** `fleetupgrade` prints
the block, but that is tool output — it does not count as telling the human. **End the
final report with the two commands written out in full**, in the message itself:

    /exit
    cd <coord's directory> && <[spawn].env> claude --name coord --resume <uuid>

plus "no `/clear` afterwards". Saying "only coord is left, that one's yours"
is not a hand-off: the human then has to go find the uuid. This was missed on the
second run (2026-08-28) and the human had to ask.

## 6. Re-measure at the end — the target can move mid-roll

`fleetupgrade` reads the installed version once, at the start. A new version can
land while you are still rolling, and then the sessions you did first are stale
again. Observed 2026-09-02: 2.1.252 at the start, 2.1.258 by the third session,
so the first two had to be redone.

**Always re-run `fleetupgrade` after the last session and roll any stragglers.**
The board is the authority, not the plan you printed at the beginning.

A session restarted earlier in the same roll may also have **re-armed its
monitor** by the time you come back to it, so expect the background-work prompt
again on the second pass — that is the ledger working, not a fault.

## 7. Snapshot after the roll

A roll invalidates the recovery manifest: every session's `version` changes, and
so does `installed_claude`. `fleetrestore` would rebuild the pre-roll fleet.

    fleetsnap

Do it after the LAST session is up (including coord, so hand the human its
restart commands if you cannot). See the `fleet-snapshot` skill for what to
verify. On 2026-09-08 the manifest was found 13 days stale — three rolls had gone
by without one.

## Reporting

**Every upgrade report ends with the coord commands in full** — see step 5. If
coord was not stale, say so explicitly instead; silence reads as an omission.

Say which sessions were stale, which were restarted, which were skipped and why,
and which reported monitors. If any session was skipped for lack of a ledger,
say that plainly — it is still running an old binary and that is the correct
outcome, not a failure.
