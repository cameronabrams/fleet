---
name: fleet-snapshot
description: Capture or verify the fleet recovery snapshot (fleetsnap/fleetrestore) so the agent fleet can be rebuilt after a power cycle, crash, or tmux loss. Use when the user asks to snapshot/back up the fleet, asks whether the fleet could be recovered, adds or renames a session, or before anything that risks tmux. Also use after a fleet upgrade roll, since versions in the manifest go stale. Also use when a restore came back wrong — sessions in the wrong pane or directory, missing sessions, panes with no claude running. Triggers on "fleetsnap", "snapshot the fleet", "back up the fleet", "can we recover the fleet", "rebuild the fleet", "fleetrestore", "what happens if the machine reboots", "the restore went wrong", "panes with no claude".
---

# Snapshotting the fleet

`fleetsnap` records enough to rebuild the fleet; `fleetrestore` rebuilds from it.
**The judgement this skill carries is about time**: a snapshot is a claim about a
moment, and it starts decaying the instant it is written, with nothing to
announce that it has.

`fleetsnap` has held up. `fleetrestore` had not been exercised until 2026-09-09,
and it was wrong (§8) — so a correct manifest is a necessary condition for
recovery, never a sufficient one. **Verify the fleet after a restore, not just
the snapshot before it.**

## 1. It only works while the fleet is HEALTHY

The pane -> transcript mapping exists **only in live process arguments**. Once
tmux dies it is unrecoverable — there is no file to reconstruct it from.

**So snapshot BEFORE risk, never after.** A snapshot taken after the thing you
feared has happened captures nothing worth having. If tmux is already gone, this
skill cannot help; go to the newest `manifest.md` and rebuild by hand.

## 2. A snapshot rots silently — this is the whole problem

Found 2026-09-08: the live manifest was **13 days old**, listed a session
name retired since, and recorded claude 2.1.246 against 2.1.263 installed.
`fleetrestore` would have rebuilt that fleet, confidently and wrongly.

Same failure family as the re-arm ledgers (see `fleet-upgrade`): **writing the
entry is easy, noticing it expired is not.** Capturing writes a file; the fleet
drifting away from it writes nothing.

**Re-snapshot after any of these, because each one invalidates the manifest:**

| event | what goes stale |
| :--- | :--- |
| a fleet upgrade roll | `version` on every session; `installed_claude` |
| `/rename` or a new `--name` | `label`, and `@repo` if it was hand-set |
| adding or retiring a session | the whole session list |
| a session changing cwd | `cwd`, and the transcript path derived from it |
| tmux layout / pane changes | `window_layouts`, `tmux.pane_id` |
| a `/clear` in any session | `resume_uuid` — `/clear` rolls the transcript file |

The last one is the sneakiest: `/clear` silently changes the durable handle, so
a manifest can go wrong without anything visible happening.

**And until 2026-09-12 it fooled `fleetsnap` itself.** `--resume <uuid>` in argv
records where a process *started*; a `/clear` moves the session to a new file and
leaves argv alone. So a cleared session read `verified: --resume in process argv`
for a handle that would resume its pre-clear context. Caught on the coordinator;
the fixed check then caught a production session cleared 37 s after the previous
snapshot. `fleetsnap` now looks for a successor transcript
in the same project dir that self-reports the same name and whose **first record
postdates the process start** — a resumed file's first record predates launch, a
cleared one's cannot. The source then reads `verified: /clear since launch -- argv
<old> superseded ...`; the plain argv case reads `no /clear since launch`.

## 3. Running it

    fleetsnap

Writes `~/.local/state/fleet/manifest.json` (machine-readable) and
`manifest.md` (human-readable, for when nothing is running — including the
tooling that would have read the JSON). It changes nothing else and is safe to
run any time the fleet is up.

Since 2026-09-09 it also **rotates both files before overwriting them**
(`manifest.json.bak-<stamp>`, newest 10 kept). Before that a single bad snapshot
was unrecoverable, which is how the window names were lost — see §8. So a
re-snap is now cheap to get wrong, but still not free: **look at the fleet before
you take one**, because the guard only covers the failure it knows about.

## 4. Verify the snapshot; do not assume it

`fleetsnap` reports how many sessions it captured. That is a count, not a
validation. **Check all four before treating a snapshot as good:**

    python3 -c "
    import json, os
    d=json.load(open(os.path.expanduser('~/.local/state/fleet/manifest.json')))
    print('captured:', d['captured'], '| claude:', d['installed_claude'])
    bad=[s['label'] for s in d['sessions'] if not s['resume_uuid_source'].startswith('verified')]
    print('sessions:', len(d['sessions']), '| UNVERIFIED:', bad or 'none')
    for s in d['sessions']: print(' ', s['label'], s['version'], s['cwd'])
    "

1. **`UNVERIFIED` must be empty — with ONE legitimate exception.** A uuid reads
   `verified:` only when it came from `--resume` in live process argv or a
   descendant running from the scratchpad path. An unverified uuid can resume one
   session into another's history — a failure this fleet has already produced once.

   **A freshly launched session can be unverified on its first snapshot**, and
   this is not a fault: it was started with `claude --name X` and has no
   `--resume` in its argv to read. It usually still verifies — through a child
   process running from its scratchpad, or its own `agent-name` record — but with
   neither it reports `corroborated: newest in cwd ...`. It self-corrects at the
   first restart, since that adds `--resume`.

   Until then, **bind the pid to the transcript yourself.** The authoritative
   binding is `--resume` in the live process argv:

       tr '\0' ' ' < /proc/<claude-pid>/cmdline     # shows --resume <uuid>

   **`/proc/<pid>/fd` is NOT reliable and an earlier version of this file wrongly
   called it the strongest check.** claude does not hold its transcript open
   continuously — it opens to write and closes. Observed 2026-09-09: the check
   returned 1 hit for one session and **0 for the coordinator**, both healthy. A zero
   there means nothing. Use it only as positive corroboration, never as a
   negative.

   `agent-name` in the transcript is also absent on sessions that were launched
   with `--name` and never `/rename`d — both candidates read `<none>` on
   2026-09-09, so that check can be silent too.

   Corroborate with two more: the transcript self-reports `agent-name`, and it
   contains traffic you know you sent it. Observed 2026-09-08 on a repo session: its
   project dir held **two** transcripts (a live one and an abandoned 2026-08-13
   session), so "newest in cwd" was doing real work and could have gone the other
   way had the old session been touched. Do not accept a corroborated uuid on the
   assumption the directory has only one transcript — look.
2. **Session count and names match `ListAgents`.** `ListAgents` is the authority
   on names. `@repo` is hand-set and goes stale on rename; `fleetsnap` flags the
   disagreement but does not resolve it.
3. **`installed_claude` matches `claude --version`.**
4. **Every `version` matches** — a straggler here means a roll left someone behind.
5. **No `window_name` is `claude`.** That is not a window name, it is
   `automatic-rename` reporting the running command, and it means the real name
   was already gone when the snapshot was taken. Fix it in tmux, then re-snap:
   `tmux rename-window -t 0:N <name> && tmux set -w -t 0:N automatic-rename off`.

   `fleetsnap` now guards this itself: where a **fleet** window is auto-naming
   and the previous manifest holds a deliberate name, it carries the old name
   forward and says so. Read `window_name_notes` — an empty list is the pass.
   Treat the guard as a backstop, not a substitute for looking: it can only
   carry forward a name some earlier snapshot actually captured.

## 5. What it deliberately does NOT capture

**Compute.** `fleetrestore` restores sessions, layout, cwds and resume handles;
it does not restart jobs. Local runs died with the power cycle and whether to
rerun them is a judgement call, not a recovery step. Jobs on a remote cluster are
unaffected by anything that happens to this workstation.

**Session context beyond the transcript.** Restore resumes by uuid, so context
comes back only as far as `--resume` carries it — and if the human chose a summary
resume, the compaction is already baked into that transcript.

## 6. A snapshot must never cache a live permission claim

Until 2026-09-08 `fleetsnap` hardcoded a 2026-08-26 grant — *"the session whose
transcript is <uuid> carries my authority"* — into every manifest it wrote.
The human **lapsed that on 2026-08-27** ("leave it lapsed"). So each new snapshot
re-stamped a dead grant with a fresh capture date, making it read as current.

Now recorded as `status: LAPSED` with the lapse quote and date. **If a snapshot
ever needs to record standing again, record the lapse state alongside it, never
the grant alone** — a cached claim about permission that outlives its grant is
worse than no record, because the freshness of the file lends it false weight.

    fleetrestore            # prints the plan, changes nothing (default)
    fleetrestore --brief    # also write per-session RECOVERY.md notes
    fleetrestore --go       # actually rebuild

### A pane whose window does not match its fleet

Allowed, and correct under full restore — but know what partial restore does.
Example: a repo session sits in the coordinator's window while labelled with
another project's `@fleet`, because that project's window was already crowded.

Established by **reading `fleetrestore`, not by running it** — a real restore
cannot be exercised without killing the fleet:

- **`fleetrestore --all`** groups by the recorded window and applies each
  window's exact saved layout, so it reproduces the current arrangement exactly,
  that session included. **This is the power-cycle path, and it is unaffected.**
- **`fleetrestore <fleet>`** iterates the windows that fleet's sessions occupy
  and renames *each* to the fleet name. When a fleet spans two
  windows, a partial restore yields **two windows both named after it**, one
  holding only the stray session, laid out `tiled` rather than to the saved layout.

Every session still comes up with the right cwd, `--resume` and labels, so this
is cosmetic. **Prefer `--all` after a power cycle** — which is the documented
normal path anyway. Reach for a partial restore only to rebuild one fleet while
the rest is alive, and expect the window split.

## 7. Restoring

**Run it with no flags first and read the plan.** Check the labels and cwds are
the fleet you expect before `--go`; if the manifest is stale you will rebuild a
fleet that no longer exists, and the restored sessions will look right.

## 8. OBSERVED 2026-09-09: the restore was wrong while the manifest was right

First real `fleetrestore --go` after a power cycle. The manifest was perfect —
10 sessions, every uuid `verified`, every cwd correct. The rebuilt fleet was
shifted by one pane, and it looked fine.

**Two index bugs, both invisible until a real restore:**

1. `target = f"{key}.{i}"` with `i` from `enumerate`, but this machine sets
   `pane-base-index 1`. Session *n* was sent to the pane belonging to session
   *n-1*; the first session of each window was sent to a pane index that does not
   exist and **never launched at all**. Three of ten were simply missing —
   the coordinator among them.
2. The window index was assumed to equal the manifest's. It does not when the
   tmux session already exists, which is exactly the "there was no tmux but
   fleetrestore thought there was" case. Then `rename-window`, `select-layout`
   and every `send-keys` for that window address the wrong window.

Both patched 2026-09-09 (`pane_base_index()` read from tmux; real window index
captured via `new-window -P -F '#{window_index}'`).

### Why it looked fine

The panes had the **right cwds** — those come from `split-window -c` in manifest
order, which was never shifted. Only the occupants moved. So every window had the
expected set of directories, each pane had a running claude, and the damage was
one row of a table that nobody reads as a table.

And the failure was benign in the way that matters most and misleading in the way
that matters next: each session kept its **own** `--name` with its **own**
`--resume` uuid, so no session was resumed into another's history, and each wrote
back to its original transcript by uuid despite the wrong cwd. What was wrong was
the **working directory** — a website session running in another project's
build directory, loading that directory's CLAUDE.md and operating its tools there. A session doing confident
work in the wrong repo, with intact context and correct history.

### The check that catches it

`tmux list-panes` alone will not: it shows a plausible fleet. Compare **argv
against cwd against the manifest**, per pane — the pane's shell is the pane pid,
so claude is its child:

    for s in $(tmux list-panes -a -F '#{pane_pid}'); do
      for c in $(pgrep -P $s); do
        a=$(tr '\0' ' ' < /proc/$c/cmdline)
        case "$a" in claude*) echo "$(readlink /proc/$c/cwd)  <-  $a";; esac
      done
    done

Then read it against the manifest's `label`/`cwd`/`resume_uuid` triples. A shift
is obvious in that view and invisible in every other one.

### Repairing it without a second restore

Do **not** re-run `fleetrestore` on a half-built fleet — the `@repo` liveness
check in `fleetrestore` reads the shifted tags and skips the wrong sessions.
The panes are already right, so repair in place: `kill` the misplaced claude pids
**by number** (record them first; never a `pkill` pattern), wait for the panes to
fall back to a shell, then re-set `@repo`/`@fleet` and `send-keys` the correct
`claude --name X --resume UUID` into the pane whose cwd matches. Preflight every
pane's cwd against the manifest and abort on the first mismatch rather than
launching into a guess.

### The self-erasing half: window names

Reported by the human after the repair — the restore did not bring back the window
names. All three fleet windows came up as `claude`.

`fleetrestore` renamed windows only on the **partial** path
(`if m.get("fleet") and not a.all`), and to the *fleet* name, not the recorded
`window_name`. So `--all` — the documented power-cycle path, the one you will
actually use — named nothing. `automatic-rename` is on by default, so tmux then
named every window after the running command.

**This one erases its own evidence, which the pane shift did not.** The chain:

1. restore drops the names; `automatic-rename` writes `claude` into all of them
2. the next `fleetsnap` faithfully records `window_name: "claude"` — it reports
   what tmux says, and tmux is not lying
3. `fleetsnap` **overwrites `manifest.json` in place with no backup**, so the
   previous capture holding the real names is gone
4. every future restore now rebuilds windows named `claude`, correctly, forever

Step 2 is the trap: nothing is malfunctioning at the moment the truth is lost.
Contrast the pane shift, which was ugly but left every fact recoverable — the
manifest was still right, so the repair was mechanical. Here the *record itself*
degrades, and one snapshot too many makes the loss permanent.

It happened exactly that way on 2026-09-09: the post-repair `fleetsnap` at 09:56
overwrote the 09:14 manifest, which was the last copy holding the real names.
They were recovered only because they were quoted in the session transcript that
had dumped the earlier manifest. **That is luck, not a recovery path.**

Patched 2026-09-09: `--all` now renames each window to `panes[0]["tmux"]
["window_name"]`, `automatic-rename` is set off on **both** paths, and a manifest
name of `claude` prints a warning rather than being applied as a name.

**So: check window names before you re-snap, not after.** A snapshot is only
worth taking over a fleet you have already looked at.

### What now stops the erasure

Both fixes are in `fleetsnap` (2026-09-09),
and they attack different links in that chain:

- **Step 3, the unrecoverable overwrite.** `rotate()` copies `manifest.json` and
  `manifest.md` to `.bak-<stamp>` before each write, keeping 10. Every other file
  in `~/.local/state/fleet/` already had `.bak` history; the one the recovery path
  depends on had none.
- **Step 2, the faithful record of a lie.** `window_meta()` reads
  `#{?automatic-rename,1,0}` alongside the name. When a fleet window is
  auto-naming, `keep_real_window_names()` carries the previous manifest's name
  forward and records the reason in `window_name_notes`.

The guard is deliberately **scoped to windows holding a captured session**.
Scratch windows are auto-named by design, and warning about them every run is
how a warning gets trained into background noise — which is the §2 failure, not
something to reproduce in the fix for it.

Verified 2026-09-09 by reproducing the real thing: `automatic-rename on` for
window `0:3`, tmux renamed it to `claude` within seconds, and `fleetsnap` then
recorded the real name anyway and said `tmux reports 'claude' (automatic-rename is
ON) — kept '<name>' from the previous manifest`. Restored the window afterward.

### Two things that follow a repair

- **Relaunching picks up the installed binary.** 2026-09-09 the fleet went
  2.1.263 -> 2.1.266 as a side effect. Say so; it is a fleet upgrade nobody asked
  for, and the versions in the old manifest are now wrong.
- **A session blocked on the trust prompt has no pane title yet** — the pane shows
  the shell's `user@host:path` or tmux's bare hostname. Until 2026-09-13 `fleetsnap`
  took that title as a corrected label and the manifest still looked complete. It
  now swaps a label for the title only when the process was launched `--name
  <title>` or a transcript self-reports it. `fleetspawn --check` exits 3 on a
  session still at the prompt. Clear the prompt — **the human's to answer, not the
  agent's** — then re-snap.

## Reporting

Say when the snapshot was taken, how many sessions, and that all uuids verified —
or name the ones that did not. If the previous manifest was stale, say how stale
and what had changed, because that is the measure of whether snapshotting is
happening often enough.

**After a restore, report the fleet, not the manifest.** A clean `fleetsnap` says
the record is good; it says nothing about whether the rebuild matched it. Give
the per-pane label/cwd/uuid agreement, name anything that did not launch, and say
what version the relaunch left the fleet on.
